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
- Loosening runs (added): a boom world where every setting starts tightened, the brake has been quiet 40 days and every evidence
  table (league shadow, Smart Buy paper, per-game, open-slot, practice and real bets) holds winning results. Over 63 and 49 days the
  autopilot loosens all seven settings (bar, Smart Buy bar, per-game limit, open-bet limit, budget share, bet size, cap use); run B
  starts near the 150% / 100% ceilings, run C tightens only bet size / cap use / share so the result never depends on who wins the weekly rotation. Checked on every step: an exact notch (bet size 5% of the current size, cap use and share 5
  points, bar half a point, Smart Buy one level, per-game 2.5 points, open limit one bet), a card line with gate evidence (positive
  bootstrap low end and newest-30% gain), one step per setting per week, at most 2 loosened settings a week, the exclusion pairs, no
  loosening while the brake is cautious or within 14 days of it (bet size / cap use), open limit never above Pete's number, and the live
  size multiple and cap use inside their bounds. Undo right after the first loosening must succeed, restore the previous value and
  hold it 2 weeks; 12-day frozen / master-off / full-auto-off controls that would otherwise loosen must move nothing.
- Known gap: the tightening rules for bet size and cap use are exercised only by the losing / bad-week runs; evidence tables for the
  loosening runs are synthetic (seeded directly), not produced by the production writers.
- No product code changed.
