# Combo trail: a read-only tool that traces what happened to a team's combos

**Section:** Tools (next to `tools/exit_replay.py`)

`tools/combo_trail.py` answers "why did that combo ride to settlement?" without touching anything. Run from the app folder:

    python3 tools/combo_trail.py --team nuggets --date 2026-11-23

- Finds every combo or single whose legs name the team (case-insensitive; names are decoded from the leg tickers using the
  engine's own team tables) within 2 days of the date.
- Prints legs by name, cost, payout, when bought; a timeline of at most ~60 lines (combo chance, Kalshi offer real vs
  estimate, the smart-sell line when logged, every auto-sell decision with its reason and the Let-it-ride setting, the
  result); then peak offer vs cost vs sell line. Also saved to `~/combo_trail_summary.txt` (`--out` to change).
- Reads `combo_history.db` (sqlite `mode=ro`) and `combo_autosell_log.jsonl` (where skips and their reasons live; only
  sales are in the database). No network, no Kalshi keys, never starts the watcher, never writes. Only a fixed list of
  fields is printed: no tokens, keys, order ids or balances. Missing tables or files print a "skipped:" line.
- The decision log names combos only as "Combo N"; the tool prints that name next to the legs so the two can be matched.
- Test: `tests/suite/t_combo_trail.py`. No trading logic is touched.
- Importable: `build_report(db, log, team, day)` takes any open sqlite connection plus the decision-log records, so a remote read-only front end can reuse it; the local command stays as a fallback.
