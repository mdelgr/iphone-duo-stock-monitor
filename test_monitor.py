import copy
import unittest
from unittest.mock import patch, Mock
import monitor

PARTS = {f'P{i}X/A': f'iPhone Duo {s} {c}' for i, (c, s) in enumerate((c, s) for c in ('Star White', 'Night Sky') for s in ('256GB', '512GB', '1TB', '2TB'))}

def payload():
    return {'head': {'status': '200'}, 'body': {'stores': [{'storeNumber': 'R504', 'storeName': 'Highpoint', 'country': 'AU', 'partsAvailability': {p: {'partNumber': p, 'pickupDisplay': 'unavailable', 'storePickEligible': True, 'messageTypes': {'regular': {'storePickupProductTitle': n}}} for p, n in PARTS.items()}}]}}

class Tests(unittest.TestCase):
    def test_full_catalogue(self):
        html = ','.join(f'"partNumber":"{p}","name":"{n}"' for p, n in PARTS.items())
        self.assertEqual(monitor.catalogue(html), PARTS)
        with self.assertRaises(ValueError): monitor.catalogue(html[60:])

    def test_unavailable_is_not_stock(self):
        self.assertEqual(monitor.parse_inventory(payload(), PARTS), {})

    def test_available_and_duplicate_prevention(self):
        data = payload()
        p = next(iter(PARTS))
        data['body']['stores'][0]['partsAvailability'][p]['pickupDisplay'] = 'available'
        stock = monitor.parse_inventory(data, PARTS)
        self.assertEqual(stock, {p: PARTS[p]})
        self.assertEqual(monitor.new_stock(stock, {'claimed': [p]}), {})

    def test_invalid_responses_fail_closed(self):
        for change in ('missing', 'store', 'status', 'title'):
            data = payload()
            store = data['body']['stores'][0]
            p = next(iter(PARTS))
            if change == 'missing': del store['partsAvailability'][p]
            if change == 'store': store['storeNumber'] = 'R999'
            if change == 'status': store['partsAvailability'][p]['pickupDisplay'] = 'unknown'
            if change == 'title': store['partsAvailability'][p]['messageTypes']['regular']['storePickupProductTitle'] = 'Other iPhone'
            with self.assertRaises((ValueError, KeyError)): monitor.parse_inventory(data, PARTS)

    @patch('monitor.mail')
    @patch('monitor.State')
    @patch('monitor.live', side_effect=ValueError('invalid inventory'))
    def test_invalid_live_never_emails(self, live, state, mail):
        with self.assertRaises(ValueError): monitor.main()
        mail.assert_not_called()
        state.assert_not_called()

    @patch('monitor.mail')
    @patch('monitor.State')
    @patch('monitor.live', return_value={'p': 'variant'})
    def test_reservation_persisted_before_mail(self, live, State, mail):
        state = {'validated': True, 'claimed': []}
        State.return_value.load.return_value = state
        events = []
        State.return_value.save.side_effect = lambda s: events.append(('saved', list(s['claimed'])))
        mail.side_effect = lambda *a: events.append(('mail', None))
        monitor.main()
        self.assertEqual(events, [('saved', ['p']), ('mail', None)])
        monitor.main()
        self.assertEqual(mail.call_count, 1)

if __name__ == '__main__': unittest.main()
