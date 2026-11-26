# Batch F: small no-money fixes (Refs #528 #378 #380 #435 #438 #313 #307 #304 #283)

**Section:** Dev Mac log access; Build / Results polish; Settings and self-tuning wording

Display, wording and log-reading limits only. Nothing here buys, sells, prices or changes a setting.

- **Log access, column cap (#528, security-relevant, kept minimal).** `log_db_connect` also sets `SQLITE_LIMIT_COLUMN` to
  `LOG_DB_COLUMNS_MAX` (100). The byte budget was only checked after a whole row was read, so `select v,v,... x900` over
  a 60 KB value built a huge row first; now SQLite refuses a result with more than 100 columns ("too many columns", a
  plain 400 with its short reason). Real tables are narrow, so nothing normal is affected. Test: `t_logs_db.py` (exactly
  100 columns works, 101 and 900 copies are refused).
- **Log access, long lines (#380, partly).** In `log_answer`, a line over `LOG_LINE_HUGE` (20,000 characters) is replaced
  by `[line too long]` before any scrubbing runs on it (a dated line keeps the time from the line above, as an undated
  one already does). Test: `t_logs_caps.py` (a 400 KB line in a ~1 MB log is replaced, the lines above stay, the answer
  takes under a second). Not done: measuring on the real Mac, and lowering `LOG_RATE` to 10 a minute; both wait on that
  measurement (the issue says only if it costs over ~100 ms).
- **Log access, app sheet instead of `confirm()` (#378).** Turning the dev Mac's log reading off, and "New code", now ask
  in the app's own bottom sheet (`modal()`): "Stop the dev Mac reading logs?" and "Make a new code?", each with Cancel
  and a plain action button (44px). Test: `test_logaccess_ui.py` (the sheet appears, Cancel changes nothing, no native
  dialog ever fires).
- **Reprice focus and announce (#435).** After a fresh price, focus goes back to the card's button (or the result when
  there is no button) and the result is read out through one live region (`#repLive` in `index.html`) that is never
  redrawn. Test: `test_smallwins_ui.py`.
- **Comebacks slides closed (#438).** `cbTog` shrinks and fades the body over 220 ms before removing it (skipped with
  reduced motion); focus stays on the header. Test: `test_smallwins_ui.py`.
- **Self-tuning wording (#304, #283, #307).** The brake reads "less than holding was worth at the time" everywhere (registry
  card, intro, Settings). The registry card's live intro is split into What moves / The bar / The brake and says "clearly
  more than luck explains". A value already shown under Changed is not repeated under "Where it stands now". The haptics
  test card lists Settings' folded section headers as known-quiet (#281). Test: `t_batchf_text.py`.
- **Settings, Selling at a loss (#313).** The row says where "Let it tune itself" is on ("Right now it is on in NBA, off
  elsewhere", or why it is off); the settings answer carries `sl_auto` from the display-only `sl_auto_view()`. "Prefer
  hedging" no longer prints a fixed "up to 5%". The hedge rows dimmed by Auto cash-out say so. Test: `t_batchf_text.py`.

Already done on develop, not rebuilt: #439 (Add anyway shows a "Showing..." spinner, #406 in PR #412), #307 items 1-3,
#304 header counting a brake. Not done: #283's "tint rows changed since the last visit" and card-only test pushes (both
need a decision on what counts as a visit and on dropping a push), #304's shorter registry brake sentence.

ROADMAP: none
