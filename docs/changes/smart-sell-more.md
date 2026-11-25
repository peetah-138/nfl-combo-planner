# Smart sell more (Pete's opt-in, 2026-11-24)

**Section:** Selling

**Default-ON, on purpose.** Pete explicitly opted in to smart sell acting more with real money, so the two new switches
(`sell_more_cheap`, `sell_more_loss`) are **ON by default** and live in Settings > Cash out so he can turn either off.
Everything below is additive: it is only looked at where smart sell's own rule already said "hold", so with both switches
off every decision is exactly develop's (`t_sellmore.py` proves it).

**A, a lower profit floor for cheaper singles (`sell_more_cheap`).** A single bought under 60c a contract (entry price,
`MORE_UNDER`) may sell at 1.35x what was paid (`MORE_FLOOR`) instead of its league's learned floor, never above that
league floor and never under smart sell's 1.2x bound. Everything else in `exit_policy` still has to hold: the
risk-adjusted hold-value comparison, chance of winning at least 0.5, spread within `LIVE_SPREAD` (6c), no resting sell,
a known last order, whole contracts.

**B, an earlier loss cut on a clearly sliding single (`sell_more_loss`).** A league with no learned loss cut yet (smart
sell needs 30 settled bets per league) gets a stand-in cut-off of 15% (`MORE_LOSS`, the self-tuner's first value). It
keeps every loss guard: a fresh score, game at least half played, a big fall below the pregame chance, never at a
halftime or break, 3+ confirming checks over 3+ minutes (counted under its own key `cutB:`, never the real loss cut's),
never below 97% of the bid. Skipped in "Never sell at a loss" mode, where the league's self-tuning brake is holding, and
wherever the league already has its own learned cut-off (that one wins).

**Freshness, fail closed.** Neither path ever compares against a stale reference (a sportsbook line, a pre-game number
that hasn't moved). `more_fresh` requires: the market's own Kalshi fetch no older than 120s (`MORE_AGE`, stamped per
market in `SINGLES["mk_at"]`; an old fallback copy has no stamp), a two-sided bid and ask within the spread limit (no
last-price-only or one-sided book), the game in play, and a score feed under 150s old. The chance used is that book's
middle, recomputed on the spot. Any of those missing means no sale. (B's existing pre-game drop guard still compares to
a pre-game chance as an extra restriction; B's trigger itself is live-only.)

**Self-adjusting daily limit (replaces a fixed cap).** Both paths share one dollar limit on what they may sell in a day
(`more_limit`, `more_cap_blocks`). It starts at the Settings number (`sell_more_cap`, $50) and moves by a written rule,
from the record alone with no network: each smart-sell-more sale whose game is over (the history file's
`sell_log.outcome`/`held`, filled by `sale_outcomes`) is compared with what holding would have paid, net of the sale's
fee.
- Nothing moves until 20 such sales have finished games (`MORE_MIN_N`).
- Then after every 10 more, over the last 20: beat holding by more than $1 means +25%, at most weekly and never over 4x
  the start; worse than holding means halved, never under 20% of the start.
- Brake: 4 sales in a row worse than holding, or the last 30 days $25 under holding, pauses both for 7 days; after that
  it restarts at the smallest limit and must earn its way back (nothing carries over).
- Same record always gives the same limit. State is `combo_more.json`; an unreadable record uses it, else the smallest
  limit (never the start, never unlimited). Settings shows today's limit, what is used and why (`more_view`).
The existing `auto_cap`, Pause (re-read right before the order), rule 8 (an unknown order outcome means "check", never
retried), "Never sell at a loss" and the whole-contract guard all still apply.

**Recording.** Every pass writes the `more_shadow` table per held single (bounded: 60 days / 200k rows, 60s per ticker,
errors swallowed, off the trading path, never read by a decision); a sale is a `log_decision` line tagged `more` (A/B)
with its after-fee net, so net dollars after fees versus hold can be measured.

**Registry.** KNOBS entries `sell_more_start`, `sell_more_floor`, `sell_more_loss`, `sell_more_age` (invariant, with their
source constants); the keys are in `SHARED_KEYS` and the watcher's `SET_KEYS` but deliberately not phone-synced.

**Ambiguities.** "Under about 60c" is read as the entry price per contract. A works only in play with a fresh score. B is
roughly neutral by construction (selling at about 15c against about a 15% chance), so the shadow record is how it gets
judged. Pete's opt-in is recorded here, not in CLAUDE.md.

**Tests:** `t_sellmore.py` (defaults, off = develop, A/B, stale blocks, Pause, rule 8, Never mode, whole contracts, limit
grow/shrink/minimum sample/brake, shadow table unread), plus `t_knobs.py`'s allow-list.
