# Polish 143: hedge card words and a shorter Settings page (issues #572, #574)

**Section:** Live (Do now hedge card), Settings

Display and wording only: nothing about buying, selling, sizing, hedging or any setting's value changes.

- **#572 hedge card.** The card used to show Offer now, Holding is worth, "Let-it-ride line" and You paid, which read as
  look-alike dollar figures. The hedge card now shows four named numbers: Hedge costs, Locks in, the cash-out offer (or
  "Likely cash-out" when it is an estimate) and You paid. It also says plainly: "Dismiss hides this for today. It comes back
  if the hedge price or the amount it locks in changes by 20% and at least 50¢" (the real rule, `HEDGE_RE_MOVE` and
  `HEDGE_RE_MIN`, unchanged). The jargon "Let-it-ride line" is gone everywhere on Live: the number is "Sell at" on the Do now
  cards and "sells once the offer reaches $X" on a combo row.
- **#574 Settings length.** Every long explanation under a setting (toggles, sliders, Selling at a loss) now shows two lines
  with a **More** button. The rest of the text is still in the page, so Search finds it, and tapping More never flips the
  setting. On a phone the default page goes from about 3,900px to about 3,400px, and with every section opened from about
  12,800px to about 11,000px (Cash out & hedging 4,050px to 2,730px). The sections already fold (#212), and the Haptics test
  card was left alone.
- **Already done on develop, no change here:** #195 (the hero pill is `data-still` when only an estimate backs it), #196 (the
  switch's highlight is drawn 24px tall inside the 44px hit area, #535), #438 (Comebacks panel slides closed), and #518 items
  1 to 3 (no "recommended" beside a red profit, exit-route log names legs by team, "based on how your past bets did, before
  fees"). Item 4 of #518 (a single's break episode never closed) is the separate #316 item 1 and is not touched.
- **Tests.** `test_hedge_dismiss_ui` (numbers named, comes-back sentence, no let-it-ride), `test_settingsfold` (More opens the
  text and never flips a switch), `t_mom_shadow` and `test_singlesell_ui` (new wording).
- Screenshots: `~/dev/wt/screens/polish-143/`.
