# Early-exit value test, phase 1 (exit-replay)

**Section:** Fair prices and data

Measurement only; no buy, sell, sizing or gate behaviour changes and nothing new is automatic. `tools/exit_replay.py`
(read-only, `mode=ro`, no network) replays fixed exit rules (+3c/+5c/+10c, fair target, T-1h, T-15m, hold) on the paper
book's singles and real ledger buys using `price_path`, with the engine's fee rate on entry and exit and the bid-ask gap,
a game-level bootstrap and a 70/30 time split, and prints only aggregates (cells under 20 hidden, no tickers or dates).
It also reports measured replacements for SB_PRE_CLOSE, SB_PRE_VOL, SB_SPREAD and SB_LIVE_WIDEN, the real combo buyback
discount from `offers`, and (`--combo-fee`) the ratio of recorded combo entry fees to the standard taker formula.
`signal_shadow` (called once in the panel pass after `mkt_fair_shadow`) records `sig_sharp`, `sig_related` and `sig_state`
from data already in memory: write-only, errors swallowed, flag `sig_shadow` (ON by default for recording), 21-day / 300k
row bound. Combo RFQ sampling: nothing new (held combos are already in `offers`, candidate quotes in `quotes`; more would need extra quote calls). `sig_shadow` is a real `CFG` key so a saved false is kept. How to run it: `docs/EXIT_REPLAY.md`.
Tests: `t_exit_replay.py`, `t_signal_shadow.py`.
