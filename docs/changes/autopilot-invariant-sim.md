# Autopilot invariant simulator (tests only)

- New `tests/suite/t_autopilot_sim.py`: a seeded, offline simulator that runs full auto with every autopilot step active (registry,
  soft brake, knob log, buy-bar borrow, open-bet limit, league/bet-type shares, stake size/cap-use, loss-room fit) over 50-day
  runs (about 1,000 passes) of normal, winning, losing, bad-week, small-stake and empty-data worlds, with Pause days, a clock jump,
  an Undo, and frozen / master-off / full-auto-off runs. It also feeds unreadable, truncated, NaN, wrong-type and missing-key
  state files.
- After every pass it checks: daily stake under the $30 cap, no bet over 150% of normal or free bankroll, open exposure under $300,
  daily loss room, open bets under 15, learned values inside their bounds, Pete's limits untouched, no loosening while the soft
  brake is up, no more than 2 looser settings a week, Undo hold, nothing moves when frozen or master-off, no buys when off or paused,
  no crash and no buys on unreadable data.
- Registration is automatic through the `# CHECK: group=engine` first line; no `run_checks.sh` or CI shard edit is needed.
- Known gap: no run reached a loosening step, so "loosen only with evidence" is checked only as far as nothing loosened wrongly.
- No product code changed.
