# Apple Highpoint iPhone Duo stock monitor

Checks Apple's live Australian product catalogue and pickup inventory for Highpoint (R504, postcode 3032). Covers both colours and all four capacities (eight variants). Unknown or incomplete inventory fails closed without email.

## Run

GitHub Actions runs `python -m unittest -v` then `python monitor.py` on a five-minute cron and manual dispatch. GitHub schedules are best effort and may be delayed. The first successful run validates live inventory and sends a clearly labelled setup test email before enabling stock alerts.

Required existing repository secret: `GMAIL_APP_PASSWORD`. SMTP login and alert recipient: `m@delga.do`. The app password must belong to that Google account. No secret is stored in source or printed.

## Duplicate suppression

`.monitor/state.json` persists validated setup and the last complete successful availability snapshot. Runs are serialized. A variant alerts on first availability and on each observed unavailable → available transition. Continuous availability is silent. Failed or incomplete checks preserve the previous snapshot. Legacy permanent claims seed the first snapshot, then no longer prevent restock alerts.

The snapshot is committed before SMTP to prevent duplicate alerts after interrupted runs. An ambiguous SMTP failure can lose that alert; inspect failed runs before changing state. A sell-out and restock entirely between checks cannot be detected.

The setup email is also reserved before SMTP; an interrupted setup deliberately requires inspection before resetting `test_claimed`. SMTP acceptance is not proof of inbox placement.
