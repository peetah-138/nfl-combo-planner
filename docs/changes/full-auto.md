# Full auto: the real master switch, OFF by default (issue #7)

**Section:** "The $300 full-auto experiment" (ROADMAP) / "The daily panel"

The one switch that is OFF by default (hard rule 6's exception to "new switches default ON"). Nothing buys on its own until
Pete turns it on in Settings › Money, after the paper gate shows passed or with an explicit "override the paper gate".

**How it works (no new order code).** Full auto is not a second buyer. `full_auto_pass` runs every minute in the watcher's
`panel_loop`, just before `panel_exec`, and only does what Pete's two taps do: `panel_approve` on a fresh draft panel, and
`panel_add(ids, "extra")` for the "New since you approved" extras. Every order is still placed by `panel_exec` through
`_buy_panel_bet` (`buy_single` / `accept_offer`): the held and opposite-side checks, the fresh price check, Pause, `can_trade()`
(never the Pi), the unread-balance hold, rule 8 (an unclear outcome is "check", never retried) and the order-block guards are all
unchanged. Exits are the existing smart sell and loss cut. A failure inside the pass is logged and never holds back bets Pete
already approved.

**Where the switch lives.** `combo_fullauto.json` in the Mac's home (git-ignored by `combo_*.json`), read by `fa_state()`. It is
not in `CFG`, `SHARED_KEYS`, `SET_KEYS` or any Pi/phone sync list, so a stray settings post or a synced copy can never turn it
on. A missing, unreadable or odd file means OFF (only a real `true` counts). Writes use `file_lock` + `save_json(strict=True)`.
Turning on goes through `fa_set` (web act `full_auto_set`, not an order act): it needs `can_trade()`, and
`panel_record()["paper"]["ready"]` (recorded as `gate: "passed"`) or `override: true` (recorded as `"overridden"`, with a snapshot
of the paper numbers and a history line). The page asks for the override as a second, separate confirmation. Turning off is
always allowed.

**Limits (all clamped, Settings › Money).** Bankroll $300; daily spend cap $30 (2 to 100); max open bets 15 (1 to 30); pause after
4 losses in a row (2 to 10); daily loss limit $20 (2 to 100). Spend today counts every real panel bet today (any origin), so it is
conservative. Open bets are panel bets bought, buying or unclear with no result, plus today's scheduled ones. Bankroll free =
bankroll + full-auto's settled P/L - its stakes still riding. Draft approval picks, in panel order, the bets that fit the cap,
open slots and free bankroll; extras are added the same way, each also checked against the overlap guard (no "add anyway";
an unreadable guard adds nothing). Ids it chose are written to the file's ledger before approving.

**Brakes.** `fa_check` trips the streak brake on N consecutive losses among full-auto bets settled after the last reset, and the
day brake when its settled P/L today is at or under minus the daily loss limit. A trip is saved with a plain-English reason. The
streak brake stays until Pete taps "Reset the pause" (old losses are not recounted); the day brake ends with the panel day.
Blockers also include Pause (watcher or app), a computer that can't trade, cap used up, open limit, no free bankroll, today's
panel cancelled or not built yet, and a failed positions read (`_held_all` raises: nothing is approved). The shared buy path
blocks again at buy time.

**Status card** (`faCard`, `watcher/spa/fullauto.js`): Settings › Money (with the switch and limits) and Results (read only). Shows
on/off/waiting, spent today of the cap, open bets, the streak brake, down today, bankroll free and what is blocking it.
`full_auto` rides on the `/app/api/settings` and results payloads (`full_auto_view`, never raises).

**Tests** (`t_fullauto.py`, Kalshi faked, every call recorded, none sent): off by default and unreadable/odd file means off, so
nothing is approved, bought or sent; refused without the gate, override needs an explicit `true` and is recorded, Pi refused;
cap respected, extras added through `panel_add` and bought once; open-bet limit; Pause (watcher flag and app callable) and
`can_trade` false block; a failed positions read blocks (stubbed and through the real `_held_all`); streak and daily-loss brakes
trip, say why, stay until reset; a stray `full_auto` setting does nothing.

ROADMAP: the "$300 full-auto experiment" switch is built, OFF; Pete flips it after the paper gate passes.
