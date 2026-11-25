# Paper test: capped profit line for favorites bought above ~67c (issue #375)

**Section:** Selling

Smart sell's profit line for a single (`max(q*P - lam*P*sqrt(q(1-q)), floor*cost)`) is above what the bet can ever sell for
once it was bought above about 1/floor, so smart sell never takes a profit on those favorites (`sell_line_shown`'s
"over", #371). Pete's call (2026-11-24): paper first, default OFF, nothing new automatic. This PR only RECORDS.

`exit_cap_shadow(x, bid)` (called from `open_singles` for a held single whose line is out of reach, only when the new
setting `exit_cap_shadow` is on; default False): writes one row to the new table `exit_cap_shadow` with the time, the sale
price after fees, today's answer (`live_decision`, hold or the reason) and the answer a line capped at
`sell_top - EXIT_CAP_MARGIN` (3c a contract) would give (`alt_decision`, `alt_line`). Rows are throttled (a changed answer at
once, an unchanged one every 5 minutes), pruned at 60 days / 100k rows, every error swallowed. Nothing reads the table back.
`single_sell_reason` got an optional `cap=None` argument that only the recorder passes (always with `track=False`, so no
peak moves); with `cap=None` the code path is the one that was there. No sell, buy, Pause, cap or rule 8 path is touched.
Turning the paper rule into a live one is a separate decision for Pete, to be judged on this record.

Tests: `t_exitcapshadow.py` (default off; row contents; the live decision identical with the switch on or off over a grid,
through `smart_sell_singles`, with peaks and settings untouched; throttle, prune, failures swallowed, no reader).

ROADMAP: adds "Capped profit line for favorites (#375)": waits on the paper record from `exit_cap_shadow` and Pete's opt-in; then a live switch with old-versus-new logging.
