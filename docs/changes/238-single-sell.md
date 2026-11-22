# Sell a single bet by hand (issue #238)

**Section:** Live page

**Sell a single by hand (GitHub #238; Pete's tap only, no new automatic selling).** Single bets/spreads/totals never had a manual Sell (only smart sell sold them). Each open card on Live › Single bets & spreads (and the game page's "Your bets") now has **Get new price** (`sellquote`: `single_sell_quote` reads the book with `book_depth(max_age=0)`, updates Worth now and shows what selling gets after the fee) and **Sell** (`watcher/spa/sell_single.js`: a sheet with the bid, what comes back, profit, holding's chance, warnings; two taps; `soldSheet` on success). `single_sell` (act `singlesell`, in `ORDER_ACTS`) uses the quote once (20 s, `_SQ`, a sell quote can never buy), refuses on Pause, no trading access, the unknown-outcome block or a lower bid on a fresh re-read, needs Sell anyway when the gap is over 6¢, then one IOC reduce-only sale at the quoted bid (`sell_single_now`, `cw-ss-<quote>`); unclear = "check", blocked, never resent. Not logged in the sell log (that counts automatic cash-outs toward the daily cap). Totals' "On track" now follows the pace (`_single_how`: total so far over the share played), not the running total. Tests: `t_singlesell`, `test_singlesell_ui`.

ROADMAP: none
