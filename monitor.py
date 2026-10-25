"""Apple Highpoint monitor; standard library only; fail closed on invalid data."""
import base64
import json
import os
import re
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

CATALOG = 'https://www.apple.com/au/shop/buy-iphone/iphone-duo'
INVENTORY = 'https://www.apple.com/au/shop/retail/pickup-message'
STATE_PATH = '.monitor/state.json'


def request(url, data=None, method=None, token=None):
    headers = {'User-Agent': 'HighpointStockMonitor/1.0', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
        headers['X-GitHub-Api-Version'] = '2022-11-28'
    if data is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=30) as r:
        return r.read()


def catalogue(html):
    parts = dict(re.findall(r'"partNumber":"([A-Z0-9]+X/A)".*?"name":"(iPhone[^"\n]*Duo[^"\n]*)"', html))
    expected = {(c, s) for c in ('Star White', 'Night Sky') for s in ('256GB', '512GB', '1TB', '2TB')}
    actual = set()
    for name in parts.values():
        name = name.replace('\xa0', ' ')
        m = re.fullmatch(r'iPhone Duo (256GB|512GB|1TB|2TB) (Star White|Night Sky)', name)
        if not m:
            raise ValueError('Unexpected catalogue product')
        actual.add((m[2], m[1]))
    if len(parts) != 8 or actual != expected:
        raise ValueError('Catalogue coverage changed or incomplete; review before alerting')
    return parts


def parse_inventory(payload, parts):
    if str(payload.get('head', {}).get('status')) != '200':
        raise ValueError('Apple inventory status invalid')
    stores = [s for s in payload['body']['stores'] if s.get('storeNumber') == 'R504']
    if len(stores) != 1 or stores[0].get('storeName') != 'Highpoint' or stores[0].get('country') != 'AU':
        raise ValueError('Apple Highpoint identity missing or mismatched')
    availability = stores[0]['partsAvailability']
    available = {}
    for part, name in parts.items():
        item = availability[part]
        if item.get('partNumber') != part:
            raise ValueError('Part identity mismatch')
        title = item['messageTypes']['regular']['storePickupProductTitle']
        if ' '.join(title.split()) != ' '.join(name.split()):
            raise ValueError('Inventory product title mismatch')
        status = item['pickupDisplay']
        if status not in ('available', 'unavailable', 'ineligible'):
            raise ValueError(f'Unknown pickup status: {status}')
        if status == 'available' and item.get('storePickEligible') is True:
            available[part] = name
    return available


def live():
    parts = catalogue(request(CATALOG).decode())
    query = urllib.parse.urlencode({'location': '3032', **{f'parts.{i}': p for i, p in enumerate(parts)}})
    available = parse_inventory(json.loads(request(INVENTORY + '?' + query)), parts)
    print(f'Validated live Apple Highpoint R504 inventory: {len(parts)} variants; {len(available)} available')
    return available


def new_stock(available, state):
    # Legacy claims seed the first snapshot without repeating an existing alert.
    previous = state.get('last_available', state.get('claimed', []))
    return {p: n for p, n in available.items() if p not in previous}


class State:
    def __init__(self):
        repo = os.environ['GITHUB_REPOSITORY']
        self.url = f'https://api.github.com/repos/{repo}/contents/{STATE_PATH}'
        self.token = os.environ['GITHUB_TOKEN']
        self.sha = None

    def load(self):
        try:
            result = json.loads(request(self.url, token=self.token))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            return {'claimed': [], 'validated': False}
        self.sha = result['sha']
        state = json.loads(base64.b64decode(result['content']))
        if not isinstance(state.get('claimed'), list) or not isinstance(state.get('validated'), bool):
            raise ValueError('Invalid persistent state; refusing to reset deduplication')
        if 'last_available' in state and (not isinstance(state['last_available'], list) or not all(isinstance(p, str) for p in state['last_available'])):
            raise ValueError('Invalid availability snapshot')
        return state

    def save(self, state):
        data = {'message': 'Persist monitor state [skip ci]', 'content': base64.b64encode(json.dumps(state, indent=2).encode()).decode()}
        if self.sha:
            data['sha'] = self.sha
        result = json.loads(request(self.url, data, 'PUT', self.token))
        self.sha = result['content']['sha']


def mail(subject, body):
    user = os.environ['GMAIL_USER']
    message = EmailMessage()
    message['From'] = user
    message['To'] = os.environ['ALERT_TO']
    message['Subject'] = subject
    message.set_content(body)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(user, os.environ['GMAIL_APP_PASSWORD'])
        smtp.send_message(message)


def main():
    available = live()  # All eight live variants must validate before any email.
    storage = State()
    state = storage.load()
    if not state['validated']:
        # Reserve test before SMTP, so an interrupted run cannot repeat it.
        if state.get('test_claimed'):
            raise RuntimeError('Previous initialization incomplete; inspect SMTP/run logs before resetting test_claimed')
        state['test_claimed'] = True
        storage.save(state)
        mail('TEST: Apple Highpoint stock monitor validated',
             'Live Apple inventory validated for all eight iPhone Duo variants at Highpoint (R504). This is a setup test, not a stock alert.')
        state['validated'] = True
        state['validated_at'] = datetime.now(timezone.utc).isoformat()
        storage.save(state)
    fresh = new_stock(available, state)
    current = sorted(available)
    if state.get('last_available') != current:
        # Persist a complete successful snapshot BEFORE SMTP. Failed live checks never reach here.
        # An observed sell-out rearms that variant; continuous availability does not repeat.
        state['last_available'] = current
        storage.save(state)
    if fresh:
        mail('iPhone Duo available for pickup at Apple Highpoint',
             '\n'.join(fresh.values()) + '\n\n' + CATALOG + '\n\nAvailability may change before checkout.')
        print(f'SMTP accepted stock alert for {len(fresh)} new variants')
    else:
        print('No new stock alerts')


if __name__ == '__main__':
    main()
