# rank-e-312: hedge weighed before skipping a below-cost cash-out (#312)

Split out of #599 because it adds a NEW automatic hedge BUY trigger (a below-cost sale offer can now lead to an automatic hedge). Pete opted in on 2026-11-27 ("Yes, build it in"); Opus-reviewed OK.

- Switch `hedge_before_loss_skip` (default ON): in `auto_sell_now`, when the offer is below cost (and not a guarded stop-loss), a hedge is weighed first. Requires `auto_hedge`, all existing hedge guards, the fresh-price check, and a hedge that locks in at least the cost. Otherwise the old skip stays. A below-cost sale never happens on this path.
- Hedge records on this path are not tagged `stop_loss`/`fee_loss` (they are not stop-loss sales).
- Live number that could move: auto cash-out may place a hedge buy it previously skipped.

Tests: `tests/suite/t_rank_e312.py`, `t_combofee.py` (source assertion).

Pete opted in on 2026-11-27.
