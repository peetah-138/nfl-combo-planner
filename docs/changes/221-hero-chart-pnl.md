# Live hero chart plots profit and loss (issue #221)

**Section:** Live page (replaces the "Hero chart" paragraph; the "Hero card" line's "a chart of open-bet worth (`pulse`
table)" becomes "a profit/loss chart")

Hero chart (`heroChart`/`wireChart`, issue #221): plots **profit and loss**, not worth. Day (16 h, `pnl` in
`/app/api/live`) or Week (`/app/api/pulse?h=168` → `pnl`; read-only, pulse keeps 30 days) via a plain-text switcher
(remembered, `cw_rng`). The engine's `pnl_series` (display only, cached 20 s, never raises, writes nothing) builds it:
P/L(t) = (worth − cost of open bets) + (back − cost of bets that finished in the window: `ledger`, then `bets` for a
combo the ledger lacks) − the open-bet sum at the window's start, so the window starts at $0, a bet bought in it counts
from what was paid, a bet **already open at the start counts from its worth then** (the legend says so), and a bet
leaving moves the line only by what it brought back beyond its last worth. A finished bet's cash is placed at the
first pulse row (≤ 15 min after Kalshi's time) where its stake left the open list. `record_view` also writes
`pulse_more(ts, xworth, xcost)` (a separate table so older 3-value inserts keep working): singles whose game is
over but Kalshi hasn't paid (`_limbo_worth`: payout if decided, else bid, else cost), and one 0/0 row once nothing
is open (the line then runs flat to now). Rows from before `pulse_more` make the chart say "Rough before <time>"
(a finished single may dip until its payout lands). Partial cash-outs show only when the bet finishes. Drawn as a
flat zero line, green above / red below (one gradient split at zero), the glowing end dot, and what was staked as a
faint stepped band on its own scale. Press and drag to scrub: line and dot follow the finger, the readout shows
"+$3.20 · $18 staked · 2:40 PM", each point ticks a haptic; the big "worth now if sold" number and its pill never
change. Live refreshes wait while a finger is on it (`S.scrub`). Tests: `t_heropnl`, `test_heropnl`, `test_motion`.

ROADMAP: none
