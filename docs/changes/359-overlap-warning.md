# Overlap guard: games you already have enough on are held back (issue #359)

**Section:** Build page / Live page (Buy ideas) / Panel (extras); Settings › Money

Pete bought several combos on one game because each one looked recommended. Every pick list now holds back a game he
already has enough riding on: **2 or more open bets** on it (`overlap_n`), **or 8% or more of the panel's sizing base
at risk** on it (`overlap_pct`). The game is greyed, sorted last, and shows "You already have N open bets on this game
($X at risk)." with one **Add anyway** button that works only on Pete's own tap.

- **Engine** (`nfl_combo_planner.py`, block before `panel_add`): `overlap_key` maps a game-winner, spread or total
  market (or its event) and any combo leg to one GAME key. `game_exposure()` counts open bets per game from what's
  already been read (account combos, `SINGLES`, today's panel items not yet on the account; a combo counts its full cost
  once on each game it touches; a `check` panel bet counts, settled/failed/skipped never). `overlap_games(allow, base,
  exposure)` applies the thresholds (base = `_overlap_base`, the panel's sizing base; no balance read = count rule only).
  `overlap_allow` cleans the page's allow list (game keys only, at most `OVERLAP_ALLOW_MAX` = 20). `overlap_note(legs)`
  is the quote line (any open bet on a game in the quote). On the display lists any failure = no guard (`{}` / `None`),
  never a broken list. Singles count from the last list read even while a buy has cleared its stamp, so a game doesn't
  drop out of the guard right after a buy.
- **Settings › Money:** "Hold back games I already have bets on" (`overlap_guard`, on), "Held back from" (1-5 bets,
  default 2), "Or once this much is riding on it" (2-25% of panel money, default 8). All three in `SHARED_KEYS` and the
  watcher's `SET_KEYS`.
- **Where it shows:** Build board (rows greyed, pick buttons do nothing), Surprise me (`ccard` greyed, no Get price),
  Best bets (inputs on held games are not fed to `best_bets_feed`; a "Left out" card lists them), single games, long
  shots, Buy ideas (Live) and the panel's extras (greyed, not counted in "Add N"). The `/app/api/build`, `/live` and
  `/panel` routes take `?allow=`; `panel_add` for `view=extra` drops extras on a held game unless the request's `allow`
  names it (`overlap_extra_ids`), and says how many it left out. That one path buys, so it fails closed: if open bets
  can't be read it refuses ("Couldn't check your open bets on those games."). "↻ Another" and Flip send the allow list
  too and the combo they return carries `over`, so a swap onto a held game comes back greyed.
- **Quotes:** a combo quote, the slip's quote and a Buy straight price carry `overlap` / a `warn` `{"k":"overlap"}` line
  when there's already a bet on that game. Display only: the price, `clears` and the Buy button are unchanged.
- **Never touches the money paths:** rule 7 holds (nothing is removed from `CTX`; cards keep their numbers and legs
  whether greyed or not, only a per-request `over` flag is added). The allow list lives only in the page (`S.ovAllow`,
  gone on reload), is never saved, and nothing automatic reads it. Killer deals, standing orders, the panel's own
  buying and the hedge are unchanged (see the PR's audit and the `profit` issue for what they lack). The Mac's buy-idea
  alerts are unchanged.
- **Tests:** `t_overlap.py` (engine: keys, exposure, thresholds at their edges, allow list, switch, fail-open, quote
  line with `clears` unchanged, singles counted while their stamp is cleared, a non-list allow ignored),
  `test_overlap_ui.py` (page, 390x844 dark/light: greyed board row last, 44pt Add
  anyway that ticks at once and sends `allow=`, Surprise numbers stable, Left out card, quote warning line, greyed
  ideas/long shots/extras, panel_add refusing an extra on a held game without Add anyway, reload forgets, Settings).

ROADMAP: none
