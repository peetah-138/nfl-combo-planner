# Money-guard batch: fee-aware "profit" (#432) and Combo Buy legs re-check gaps (#498)

**Section:** Selling (cost floor, Flexible sell price) and Build page (Combo Buy, rule 7)

Three small safety tightenings. Each makes the app do less; nothing new buys or sells, and Pause, caps, quarter Kelly and
rule 8 are untouched.

- **#432, "a profit" is after the selling fee.** The auto cash-out cost floor was already net of the fee on the first
  offer (`auto_sell_now`, `combo_sale_net`) and on a retry (`FLEX_COST_SHARE`, 95% of cost net). Two places still said
  "at or above cost" on the gross offer. `flex_decide` now judges its `profit` flag on `min(offer, net)` (net passed by
  `_accept_with_retries`; with no net passed, a manual tap, it is the offer as before), so a retry that nets under cost
  can no longer be taken as "a profit, and the chance has dropped". `cash_nudge` (alert only, never sells) stays quiet
  when the offer nets under cost. `combo_sell_fee` still switches the fee model off (then net = gross). Singles already net
  the fee (`single_sell_reason`).
- **#498 (1), sent-but-empty legs list.** `accept_offer(..., legs_sent_empty=True)` / `buy_legs_refusal(sent_empty=True)`
  refuse with "the page sent an empty legs list" (nothing sent, offer kept). The web app's Buy sets it when the page's `legs`
  key is a list with nothing in it. A page that sends no `legs` key at all (the pages leave it out when they have none) is
  unchanged: still held to offer = card.
- **#498 (2), hub build-form Buy.** The hub's `/simple` Build form now carries the card's leg tickers in a hidden `legs`
  field; `builder.buy(i, legs)` refuses a Buy with no legs ("That page is out of date ... Nothing was bought") and passes
  them to `accept_offer(expect_legs=...)`, which checks them against the stored offer and the combo now on that card
  (hard rule 7). An old page open across the upgrade just has to be reloaded.
- **Skipped on purpose (commented on the issues):** #365 (a per-game overlap skip on killer, standing orders and the
  panel changes which automatic buys happen and needs Pete's thresholds), #328 (no real combo fee data: no ledger on this
  machine to read, and guessing a fee would change sizing).
- Test: `t_money_guards.py` (synthetic engine, faked Kalshi). Existing `t_buy_legs_203`, `t_flexcostfloor`, `t_combofee`,
  `t_cashnudge` still hold.
