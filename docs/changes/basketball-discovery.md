# Basketball discovery: offline research on NBA and men's college play-by-play (no product change)

**Section:** Fair prices and data (research tooling only; nothing here is read by the app, the watcher or any money path)

Offline research code in `tools/research/` (`discovery_common.py`, `basketball_fetch.py`, `basketball_data.py`,
`basketball_discovery.py`) plus `docs/BASKETBALL_DISCOVERY.md` (pre-registration, method, caveats) and
`docs/results/basketball-discovery-first-run.md` (aggregate numbers only). The data (hoopR/sportsdataverse files, ESPN
derived, labelled CC-BY-4.0) stays outside the repo in `~/dev/research/basketball/`, is never committed or
redistributed, and the venv is `~/dev/research/venv`. stats.nba.com and cdn.nba.com are not used.

What it does: an expanding-window (train on earlier seasons, test on the next, 2022-2026) live win-probability baseline
from game state plus the pre-game line, a richer model with permutation importance, a game-clustered residual scan with
Benjamini-Hochberg control (hypothesis counts printed per family), a totals pace/anchor study, 13 pre-registered
anecdotes and 5 totals anecdotes, and a decay tracker. A "survivor" needs BH q<0.05, at least 1 win-probability point
(1 total point), 100+ games, same sign in 4 of 5 held-out seasons, and same sign in the other league.

Result in one line: nothing here is a demonstrated edge. There are no live market prices in the data, so a residual
against our own model is a lead to price, never a mispricing. Most survivors are the baseline's own late-game calibration
and derived-possession artifacts. One pre-registered anecdote (rested team vs back-to-back team at half) is a weak
college-led lead worth a look once live prices exist.

Never touches: the engine, the watcher, Pause, caps, rule 8, sizing, any buy or sell path, `~/combowatch`, keys, the
history database or any `combo_*.json`.

Test: `tests/suite/t_discovery_synth.py` (synthetic data with a planted +3 point effect: the scan finds it, null segments
stay out, game-clustered SE is wider than the naive one, BH known example, decay slope, permutation importance, scoring).
It needs numpy and pandas, now in `tests/requirements-ci.txt`; locally it prints a SKIP if they are missing, in CI a
missing import is a FAIL.

ROADMAP: none

Review follow-up: overtime explains much of the close-game-late-over total residual (NBA +3.1 to +0.7, college +5.7 to +2.9 without overtime); T3 was dropped for too few games.
