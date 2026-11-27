# Log access batch E: one-paste setup for the dev Mac (display and tooling only)

**Section:** Settings › This Mac › "Let the dev Mac read logs"; `tools/read_prod_logs.py`

Nothing about buying, selling, sizing or any number the app tunes changed. Log access stays read-only.

- **#379:** the one-time code sheet has a **Copy setup command** button. It copies one Terminal line that saves the address and
  the code in the dev Mac's keychain (under the names `read_prod_logs.py` already reads), then prints a hint. The line is built in the page
  from what is on screen and goes only to the clipboard (never sent, logged or stored); its leading space keeps it out of shell history where that is on.
  `tools/read_prod_logs.py --problems` is a one-word grep for `refused|check|failed|held|Traceback`.
  Tests: `test_logaccess_ui.py` (button, command shape, quote escaping, 44px, light and dark), `t_logs_problems.py`.
- **Already done on develop, no change here:** #528 (result column limit, `LOG_DB_COLUMNS_MAX`), #378 (app sheet instead of `confirm()`
  in `logaccess.js`), #380 (long-line cut to "[line too long]" and the under-1-second worst-case assertion in `t_logs_caps.py`).
  PR #532. `LOG_RATE` stays at 30/min until a real-Mac measurement says otherwise.
