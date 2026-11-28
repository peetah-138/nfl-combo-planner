# Button feedback follow-ups (UI only)

Three fixes to `watcher/spa/press.js` after the Opus review of the button-feedback change. No request body, endpoint,
amount or server code changed.

1. One Cash out / Place hedge at a time per combo, even if the sheet is closed and reopened from the Live card while the
   first is still pending. `S.fbFly[ticker]` is set when the request goes out and cleared when the answer arrives or the
   request fails. `sell()`, `hedge()`, `fbSell()` and `fbHedge()` check it and show "still going through" instead.
2. A refusal that arrives after the sheet was closed or replaced now shows as a red toast (the button is no longer on
   screen). Unclear outcomes still open the Check Kalshi sheet.
3. Only the Mac's known refusal messages show red. Any other `ok:false`, including "That didn't work: <error>" (which can
   mean the outcome is unknown), is treated as Check Kalshi.

Tests: `tests/suite/test_buttonfeedback_ui.py` covers each case for both Cash out and Place hedge.
