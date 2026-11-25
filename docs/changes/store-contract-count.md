# Store each bet's contract count in the ledger (follow-up to #461)

**Section:** Results page (profit scoreboard), ledger

Single bets did not keep how many contracts were bought, so the Results page could not price them (the "could have
been sold higher" line only covers combos, whose payout is in `bets.pays`). The `ledger` table now keeps, per bet:
- `n_bought` (real): contracts opened (bought). A fill that closes a position is not counted; a fill that flips
  the side counts only the part that opens.
- `unit_cost` (real): all-in cost per contract, fees included (`ledger.cost / n_bought`, rounded to 0.1 cent).

**Bookkeeping only. No buy, sell, sizing or gate decision reads these fields; nothing moves money; rule 8 is untouched.**
No new Kalshi call: both come from the fills `_single_ledger` / `ledger_note` already read (`bought_n` for combos).
The buy path itself is not touched.

Schema: additive and backward compatible. `_ledger_table` adds the columns to an older file with `alter table` (checked
against `pragma table_info`, so it is safe to run twice), alongside the existing `nf` column. Old rows stay NULL = unknown.
The next account read fills a row whose fills are still inside Kalshi's window (`_ledger_same` sees the difference);
a row whose fills have aged out stays NULL, and a saved count is never overwritten by an unknown one
(`coalesce(excluded.n_bought, ledger.n_bought)`). A settlement-only row (no fills) stays unknown rather than guessed.

Reading: `ledger_price_paid(row)` returns `(contracts, cost per contract)` or `(None, None)`; it never raises on NULL,
zero, negative, text or a missing key. `_ledger_rows()` puts the cleaned `n_bought` / `unit_cost` on every row, so
`profit_board` rows carry them.

**Follow-up (small, not done here because #462 is not in develop yet):** once #462 (held losers) lands, `_held_facts`
can price a single from `ledger_price_paid(r)`: its payout is `n_bought` (a contract pays $1), its best sell price
comes from the single's own price history, and it is "no price history" when `ledger_price_paid` gives `(None, None)`.
Replace the "a single bet's contract count is not kept" wording in `_held_facts` / `_held_summary` and its doc then.

Tests: `t_storecounts.py` (counts from fills, settlement-only unknown, migration of an old-schema file, NULL handling,
`ledger_price_paid` edge cases, and that the new names appear only in ledger bookkeeping, never in a buy/sell/sizing
function); `t_ledgersales.py` still passes unchanged.
