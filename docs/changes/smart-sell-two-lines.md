# Smart sell reads as one feature: Take profit and Loss cut lines on the card (wording only)

**Section:** Live page, Selling

A pending combo card now shows one **Smart sell** block with two plain lines, both display only (no selling behaviour
changes, nothing is written):

- **Take profit:** the old chip text, reworded with the live numbers: "waiting, win chance 11% is below the 50% needed",
  or, when the offer is what is short, "waiting, offer $1.00 is below the $6.50 it sells at". Field `smart_profit`
  (from `smart_chip`) in `smart_trigger`.
- **Loss cut:** new field `loss_chip` from `stop_loss_chip(t, h)`: "off (this league hasn't earned it yet)" (`smart_params`
  loss is None), "armed at 20% win chance", "waiting for half the game" (the loss guard's `stoploss_params` prog, read
  off each live pick's fresh score), "off (Auto cash-out is off in Settings)", "off (you sell this one)", "off (Smart
  sell is off)", plus "(Pause is on, nothing sells)" when paused.

`smart_chip` text changed ("waiting (needs 50%+ win chance)" gone); the card button is now just "Smart sell" when the
two lines exist (`ssLines` in `watcher/spa/live.js`, `.sslines` in `app.css`). Tests: section K and the updated F
checks in `tests/suite/t_mom_shadow.py`.
