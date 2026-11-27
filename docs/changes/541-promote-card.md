# Ready to promote? scoreboard for the paper tests (issue #541)

**Section:** Results page

A read-only card on Results, under "What's working", that says for each paper test whether it has earned a "go" yet,
in dollars after fees. **Report only: it never turns anything on, and nothing that buys, sells, sizes or sets a limit
reads or imports it.** Turning a test on stays Pete's decision; this is the record he decides with.

**What is judged (settled to dollars today):** the momentum shadow (`mom_shadow` joined to `mom_after`: sell when the
price slips, "protect" and "cut", against holding to the end; bets really sold are left out and counted), the signal
shadow (`sig_sharp`: a paper $10 single bought pre-game when the sharp books' fair price beats Kalshi's ask by 2c, 4c
or 6c after fees; settled from `closes` else `bp_mkt`, whose implied `rs=9` labels are ignored; the lag replay buys at
the ask 30-60 s later), the exposure paper log (`expo_pos`: money a no-both-sides or a game / league / day cap would
have saved, bets that appeared one at a time only), and the exit-cap shadow (`exit_cap_shadow`: capped sell line vs
holding; the recorder defaults OFF, so the row says "switched off" until it is on. This never switches it on).
**Cannot be measured in dollars yet** (grey rows): the league shadow (#476, it compares settings, not bets), prop
prices (no fair price recorded), slate concentration (aggregates, no rule to replay) and the news moves.

**The judge** (`promote_judge`, generalizing `tools/exit_replay.py` `group_result`; its helpers are copied, not
imported: that file is pinned by docs/EXIT_REPLAY.md). Per signal: **one decision per position** (the first time the
rule fires; the recorders write a row every 1-5 minutes, so counting rows would inflate n), the game as the cluster
(second ticker part for a single, the whole ticker for a combo, the first game key for exposure), a game-resampled
range for the total (99%, **99.5% when more than one setting was tried**, because the best of several was picked), the
setting picked on the first 70% of games by time and **scored on the last 30%** (the range is built on those latest
games only), both halves of the time, and the 30-60 s lag replay where the recorder has it (momentum o30/o60, signal ask
30-60 s later). **Passing** needs: **40+ games in all and 15+ games in the latest 30%** (below that: "Not enough data",
no test is run), 20+ decisions, the range's low end above $0, the last-30% net above $0, both halves above $0, and the
lag replay above $0 (a signal with no lag replay cannot pass). **Failing**: enough data but net, the latest games, a half
or the lag is $0 or less. **Not enough data**: too few decisions or games, or positive but the range straddles $0 ("too
close to call"). The reason on screen is the first check that failed, in plain words. **The result is recomputed only
when the settled count changes** (decisions, games, settings tried, total), so refreshing again on the same data cannot
re-roll it.

**Why so strict (season-long false alarms):** the card is re-judged every 15 minutes all season and the push fires
once, ever, so the risk that matters is "a no-edge signal EVER passes". One check at 99% is wrong about 1% of the time
(2-3% with only ~20-25 games and ~6 in the latest slice), but over an 80-game season repeated looks compound it to 7-24%.
Defences: the minimum sample above; the stricter **push band (99.9%, 99.95% with several settings)**, separate from the
card's 99% "Passing" label; and the push needs the pass to hold on **3 successive looks, each on newly settled games**
(not three refreshes of the same data). Simulated with the real judge and streak rule on zero-edge seasons (80 games, 2
bets a game, a look after every game): **1.0% ever pushed with one setting (3,200 seasons) and 1.3% with three settings tried (1,200 seasons)**, against 6-8% of the same seasons in which the card's own 99% label reads Passing at some point. `t_promote.py` repeats the simulation and fails if the rate
passes 3%.

**Real games, not combos (correlated bets):** a real game often spawns several combos (and singles) that win and lose
together. Counting each combo as its own "game" let three combos from ONE game look like three new games, so one lucky
game could beat the "3 batches of newly settled games" rule (19.7% of zero-edge seasons ever pushed, 1,000 simulated).
Now every decision is clustered by the REAL game: a single by its game, a combo by the games of its legs (read from the
`bets` table's leg tickers; a combo whose legs are unknown counts as its own unit, since nothing better is known), and
two bets that share any game are merged into one cluster. Zero-edge seasons with 3 correlated combos per real game: **1.2% ever pushed (1,000 seasons)**; the old per-combo code fails the same test (14% over 250 seasons in `t_promote.py`). The minimum sample (40+ clusters, 15+ in the latest 30%), the
"newly settled" streak, the range and the 70/30 split all count clusters, not combos.

**Fail closed on missing games:** a combo with no entry in the `bets` table cannot be tied to its real games, so it still counts as its own unit, but that is the case where the simulated false-push rate rises (2.1% / 6.2% / 10.4% when 10% / 30% / 50% of combos are missing). The judge now counts those combos (`missing`, `promote_unknown`); while there are any in the evidence, the push band is refused (`push_ok` false, the streak stays at 0, and `promote_push_check` also skips any signal with `missing`). The card still shows "Looking good, not proven yet" with the reason "Some combos are missing their games; waiting", and the push can fire only once every combo's games are known. The `bets` read (`promote_legs`) now has an `ORDER BY` so the 50000-row limit always keeps the same rows.

**What the chip says (no false "go"):** the judge can read "passes" in about 5-7% of zero-edge seasons at some point, so
that is no longer shown as a green "Passing". It reads **"Looking good, not proven yet"** in calm amber, with the streak
("Streak 1 of 3: it has to keep holding on new games before you are told it is ready"). Only a signal that already cleared
the strict bar on 3 batches of new games and was pushed shows the green **"Ready: say go"**.

**Where it lives and why:** one fenced block in `watcher/combo_watcher.py` ("READY TO PROMOTE (report only)"), pure
(`q(sql, args)` rows, config, time), so the Air's updater ships it with no change to the updater, and the engine has
zero diff. Reads are read-only SQL with a `LIMIT 50000`. `GET /app/api/promote` returns a cache (15 minutes) rebuilt on
a background thread, never in the request; the first call returns a "computing" stub and the card asks again after 7 s.
The card (`promoBlock` in `results.js`, styles in `results.css`, the fetch in `common.js` `load('results')`) is one
row per signal: name, status chip, reason, then the dollars and range.

**Push:** the first time a signal clears the push band on 3 successive looks that each have more games settled than the
last (and it is Passing on each), one message "<signal> passed the bar, say go" through `Notifier.add(kind="promote")`:
a normal update, so quiet hours and the 30-minute digest apply, and it avoids every urgent word. A look on unchanged data
adds nothing; a look that is not Passing resets the count. The count (`promote_streak.json`) and the once-per-signal
record (`promote_pushed.json`) live in the home folder and survive a restart (the record is written after the message
is queued, so a restart does not repeat it). Sent only from the watcher's main process (`promote_loop`, every 15
minutes), not the web app or a backup Pi. Watcher-only switches in `watcher.json`: `promote_report` and `promote_push`,
both default true. No engine setting and no phone toggle.

Existing tests that assert "the watcher never mentions the shadow tables" (`t_broad_shadow.py`, `t_signal_shadow.py`,
`t_paper_shadows.py`) now strip the fenced block first; `t_promote.py` proves the block itself only reads.

Tests: `t_promote.py` (one decision per position, the minimum sample, the judge cache, the 99/99.5% rule, the season-long false-push simulation, the 70/30 pick without peeking, every status and
reason, each recorder settled on a throwaway sqlite file, missing tables, the push (3 looks on new data, once, after a restart), the cache
never computing in a request, and the isolation checks).

ROADMAP: the pass/fail bars here are first guesses (40 games, 15 latest games, 3 looks); revisit once real data has passed
through the card.
