# Ready to promote? scoreboard for the paper tests (issue #541)

**Section:** Results page

A read-only card on Results, under "What's working", that says for each paper test whether it has earned a "go" yet,
in dollars after fees. **Report only: it never turns anything on, and nothing that buys, sells, sizes or sets a limit
reads or imports it.** Turning a test on stays Pete's decision; this is the record he decides with.

**What is judged (settled to dollars today):** the momentum shadow (`mom_shadow` joined to `mom_after`: sell when the
price slips, "protect" and "cut", against holding to the end; bets really sold are left out and counted), the signal
shadow (`sig_sharp`: a paper $10 single bought pre-game when the sharp books' fair price beats Kalshi's ask by 2c, 4c
or 6c after fees; settled from `closes` else `bp_mkt`, whose implied `rs=9` labels are ignored; the lag replay buys at
the ask 30-90 s later), the exposure paper log (`expo_pos`: money a no-both-sides or a game / league / day cap would
have saved, bets that appeared one at a time only), and the exit-cap shadow (`exit_cap_shadow`: capped sell line vs
holding; the recorder defaults OFF, so the row says "switched off" until it is on. This never switches it on).
**Cannot be measured in dollars yet** (grey rows): the league shadow (#476, it compares settings, not bets), prop
prices (no fair price recorded), slate concentration (aggregates, no rule to replay) and the news moves.

**The judge** (`promote_judge`, generalizing `tools/exit_replay.py` `group_result`; its helpers are copied, not
imported: that file is pinned by docs/EXIT_REPLAY.md). Per signal: **one decision per position** (the first time the
rule fires; the recorders write a row every 1-5 minutes, so counting rows would inflate n), the game as the cluster
(second ticker part for a single, the whole ticker for a combo, the first game key for exposure), a game-resampled
range for the total (95%, **99% when more than 6 settings were tried**), the setting picked on the first 70% of games
by time and **scored on the last 30%**, both halves of the time, and the 30-60 s lag replay where the recorder has it
(momentum o30/o60, signal ask 30-90 s later). **Passing** needs: 20+ decisions and 5+ games in the latest stretch, the
range's low end above $0, the last-30% net above $0, both halves above $0, and the lag replay above $0 where it exists.
**Failing**: enough data but net, the latest games, a half or the lag is $0 or less. **Not enough data**: too few
decisions or games, or positive but the range straddles $0 ("too close to call"). The reason on screen is the first
check that failed, in plain words.

**Where it lives and why:** one fenced block in `watcher/combo_watcher.py` ("READY TO PROMOTE (report only)"), pure
(`q(sql, args)` rows, config, time), so the Air's updater ships it with no change to the updater, and the engine has
zero diff. Reads are read-only SQL with a `LIMIT 50000`. `GET /app/api/promote` returns a cache (15 minutes) rebuilt on
a background thread, never in the request; the first call returns a "computing" stub and the card asks again after 7 s.
The card (`promoBlock` in `results.js`, styles in `results.css`, the fetch in `common.js` `load('results')`) is one
row per signal: name, status chip, reason, then the dollars and range.

**Push:** the first time a signal is Passing, one message "<signal> passed the bar, say go" through
`Notifier.add(kind="promote")`: a normal update, so quiet hours and the 30-minute digest apply, and it avoids every
urgent word. Once per signal, remembered in `promote_pushed.json` in the home folder (written after it is queued, so a
restart does not repeat it). Sent only from the watcher's main process (`promote_loop`, every 15 minutes), not the web
app or a backup Pi. Watcher-only switches in `watcher.json`: `promote_report` and `promote_push`, both default true.
No engine setting and no phone toggle.

Existing tests that assert "the watcher never mentions the shadow tables" (`t_broad_shadow.py`, `t_signal_shadow.py`,
`t_paper_shadows.py`) now strip the fenced block first; `t_promote.py` proves the block itself only reads.

Tests: `t_promote.py` (one decision per position, the 95/99% rule, the 70/30 pick without peeking, every status and
reason, each recorder settled on a throwaway sqlite file, missing tables, the push once and after a restart, the cache
never computing in a request, and the isolation checks).

ROADMAP: the pass/fail bars here are first guesses (20 decisions, 5 latest games); revisit once real data has passed
through the card.
