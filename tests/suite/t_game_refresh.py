# CHECK: group=engine
# Game page refresh pacing: exact intervals and where each is used. Browser only calls our own server (whose own score
# cache and the 36/min, 4 s pacer are untouched); a hidden tab never polls.
import os, re
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
HERE = os.path.abspath("wtest")
REPO = os.environ.get("REPO") or os.path.dirname(os.path.dirname(HERE))
rd = lambda n: open(os.path.join(REPO, "watcher", "spa", n)).read()
common, moments, game = rd("common.js"), rd("moments.js"), rd("game.js")
ok("game constants have exact values", "FG_RELOAD_MIN_MS=5000,GAME_TICK_GATE_MS=3000,GAME_POLL_EVERY_MS=2000,GAME_POLL_SKIP_MS=3500,GAME_STALE_S=20;" in common)
ok("stream tick redraws an open game after GAME_TICK_GATE_MS", "(S.gameAt||0)>GAME_TICK_GATE_MS)drawGame();return;" in moments and ">4000)drawGame" not in moments)
poll = [l for l in common.splitlines() if l.startswith("setInterval(") and "GAME_POLL_EVERY_MS" in l]
ok("fallback game poll skips hidden tabs and recent draws", len(poll) == 1 and "!document.hidden&&S.gameOpen" in poll[0] and ">GAME_POLL_SKIP_MS)drawGame();},GAME_POLL_EVERY_MS);" in poll[0], poll)
ok("old 5500 gate is gone", "5500)drawGame" not in common)
vis = [l for l in game.splitlines() if "visibilitychange" in l]
ok("tab return redraws an open game if last draw is over FG_RELOAD_MIN_MS, not when hidden",
   vis == ["document.addEventListener('visibilitychange',()=>{if(document.hidden||!S.gameOpen||!$('#modal').classList.contains('on'))return;if(Date.now()-(S.gameAt||0)>FG_RELOAD_MIN_MS)drawGame();});"], vis)
ok("game indicator turns stale after GAME_STALE_S", "(k==='G'?GAME_STALE_S:60)" in common)
ok("no server pacing, engine or buy code touched by this change", "max_age" not in game and not re.search(r"https?://", game))
