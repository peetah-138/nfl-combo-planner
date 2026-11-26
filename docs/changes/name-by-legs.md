# Name combos by their picks (issue #520)

**Section:** Live page, Selling (autosell log)

Refs #520. Pete could not remember what "Combo 3" was, and the autosell log said only "Combo N", so a real miss
(a combo with a Nuggets leg that rode to settlement) could not be traced. A combo is now named by its picks wherever
Pete reads text: `Nuggets + Chiefs +2`.

- `combo_names()` / `short_leg()` (engine, next to `team_short`): up to 3 picks joined with " + ", a longer combo says
  "+N more"; pro teams use their nickname (`team_short`), a spread stays on its team, a player market or college team
  keeps its name, anything over 24 characters is cut. Two combos with the same name get their first kickoff added
  ("Nuggets (Nov 23)"), then a "(2)". Display only: the market ticker is the id and nothing keys off the name.
- `mine_page` builds the names once and uses them as the `label` of Live's cards and views (`views[].label`),
  `MINE["snap"]` and `MINE["hold"]`, so the sell/buy notifications, Live and Sold cards, hedge and cash-out sheets,
  toasts and the activity feed (`record_view`) all say the picks with no further change. The old number is kept as
  `num` ("Combo 7") on all three.
- Autosell log (`log_decision`): `combo` is now the picks, `combo_id` holds the old "Combo N", and `picks` (every
  leg, as before) is still added. The `combo` column of `sell_log` follows. Older lines keep their old name.
- `combo_link` (watcher) finds the combo an alert names by its picks (or its number), whole text only, and a name inside
  a longer matching name does not count.

Never touched: any selling or buying decision, Pause, caps, rule 8. Tests: `t_combonames.py`, `t_push_target.py`.
