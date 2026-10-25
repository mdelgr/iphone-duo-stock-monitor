# Apple Highpoint iPhone Duo stock monitor

Checks Apple's live Australian product catalogue and pickup inventory for Highpoint (R504, postcode 3032). Covers both colours and all four capacities (eight variants). Unknown or incomplete inventory fails closed without email.

## Run

GitHub Actions runs `python -m unittest -v` then `python monitor.py` on a five-minute cron and manual dispatch. GitHub schedules are best effort and may be delayed. The first successful run validates live inventory and sends a clearly labelled setup test email before enabling stock alerts.

Required existing repository secret: `GMAIL_APP_PASSWORD`. SMTP login and alert recipient: `m@delga.do`. The app password must belong to that Google account. No secret is stored in source or printed.

## Duplicate suppression

`.monitor/state.json` persists validated setup and alerted variant IDs in the repository. Runs are serialized. Each variant is alerted at most once, even if it later restocks. To prioritise avoiding duplicates, the alert reservation is committed before SMTP. A crash or ambiguous SMTP failure after reservation can therefore lose an alert rather than repeat it; inspect failed run logs before changing state. Do not delete state casually.

The setup email is also reserved before SMTP; an interrupted setup deliberately requires inspection before resetting `test_claimed`. SMTP acceptance is not proof of inbox placement.
