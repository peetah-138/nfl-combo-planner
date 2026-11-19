# Local dev environment

The real planner web app, running on your machine against a fake internet. Use it to try UI and engine changes
without touching your real data, your Kalshi account or the live watcher.

## Launch and stop

```
./dev.sh          # then open http://127.0.0.1:18800/app
Ctrl-C            # stops it and deletes the throwaway folder
```

It needs only `python3` and `requests` (the same as the watcher). If it says port 18800 is busy, another dev
instance is running; stop that one first.

## What you get

- Build (NBA and NHL): four NBA and two NHL games with prices, so combos can be built and priced.
- Live: six seeded combos (pending, won, lost, cashed) over those games, with fake ESPN scores (per sport the first game is live and the
  second is final: two live and two final across both sports; the rest not started), a fake balance of $211.03, and one fake cash-out offer.
  The tennis combos use fake Kalshi live data: Rublev-Zverev in play (sets, games, points), Sinner-Alcaraz finished,
  and Djokovic-Medvedev unknown to it (so it still reads "Probably finished").
- Results/history: stored in the throwaway home folder's own database. A week of made-up "worth now" history is
  seeded there at start, so the Live hero chart (Day/Week, scrub) has a line to draw.

Everything is faked in `tests/suite/fakenet.py` (Kalshi, ESPN, GitHub, ntfy, odds). Edit the games or scores there.
The seeded bets are in `tests/dev_webapp.py`.

## Safety guarantees

- Data lives in `~/combodev.XXXX` (made fresh each run, deleted on exit), never `~/combowatch`. The engine is a symlink to
  `nfl_combo_planner.py`, so it keeps its settings and history next to that link, inside the throwaway folder.
  `dev_webapp.py` refuses to start unless `COMBOWATCH_HOME` is such a folder (marker file made by `dev.sh`).
- No Kalshi key and no Key ID anywhere, so `can_trade()` is false. As a second layer the fake refuses every non-GET call
  to Kalshi. Start-up checks again and stops if trading or a hub is somehow possible.
- No hub: `watcher.json` has no topic or secret, so the web app never configures the hub at 127.0.0.1:8765 or posts
  settings to ntfy. The fake internet also refuses any local address other than its own port, and `hub_call` is stubbed.
- Refuses ports 8765 and 8766 (real hub and app) and a busy port. The app listens on 127.0.0.1 only.
- Notifications go nowhere (`COMBOWATCH_NTFY=http://127.0.0.1:9`), auto-update is off, and the watcher file is copied
  into the throwaway home before running, so nothing runs from, or self-updates over, the repo.
- Not covered: the full watcher main loop (hub, auto cash-out, updates). Use `tests/run_checks.sh` for that.
