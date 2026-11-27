# Polish batch B: stable Buy button width, one log-access description in CLAUDE.md (display and docs only)

**Section:** Buy ideas; docs

- **#456:** on a Buy idea, the Buy button keeps the same minimum width when "Buy · 12s" turns into "Buying…", so the buttons
  beside it no longer shift (CSS only, `smallwins.css`). Nothing about when or whether a buy happens changed.
- **#544:** `CLAUDE.md` hard rule 9 no longer repeats the log-access details. It keeps the rule (the dev Mac never gets the
  Kalshi key, `~/combowatch`, a copy of the history DB file or any `combo_*.json` file; read-only, credential-scrubbed log and
  SELECT access only; not a money path) and points at `docs/LOG_ACCESS.md` and the "Reading production logs from the dev Mac"
  bullet. The meaning of the rule is unchanged (reviewer: please check). This PR edits `CLAUDE.md` on purpose, because the issue is about that file.
- **Already done on develop, no change here:** #528 (`SQLITE_LIMIT_COLUMN` is set in `combo_watcher.py`), #378 (log-access sheet
  uses `modal()`), #435 (`pReprice` restores focus and announces via `#repLive`), #438 (comebacks panel slides closed, `cbTog`),
  #439 (Add anyway shows a spinner and "Showing…", `ovAdd`).
