# CHECK: group=engine
# Browser refresh pacing (faster scores and prices): exact values and where each is used. The browser only calls our own
# server; a hidden tab never polls; no trading code is touched.
import os, re
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
HERE = os.path.abspath("wtest")
REPO = os.environ.get("REPO") or os.path.dirname(os.path.dirname(HERE))
rd = lambda n: open(os.path.join(REPO, "watcher", "spa", n)).read()
common, boot, moments = rd("common.js"), rd("boot.js"), rd("moments.js")
ok("pacing constants have the exact values", "const TICK_GATE_MS=1500,POLL_EVERY_MS=5000,POLL_SSE_SKIP_MS=30000,POLL_NOSSE_SKIP_MS=4000,FG_RELOAD_MIN_MS=5000;" in common)
ok("a stream tick refetches Live/Games when the last load is over TICK_GATE_MS old",
   "Date.now()-(S.lastLoad||0)>TICK_GATE_MS&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}" in moments
   and "S.lastLoad||0)>4000&&!$('#modal')" not in moments)
poll = [l for l in boot.splitlines() if l.startswith("setInterval(") and "POLL_EVERY_MS" in l]
ok("the fallback poll runs every POLL_EVERY_MS and never in a hidden tab", len(poll) == 1 and poll[0].startswith("setInterval(()=>{if(document.hidden)return;") and poll[0].endswith("},POLL_EVERY_MS);"), poll)
ok("the poll skips a recent load: 30 s with the stream up, 4 s without",
   len(poll) == 1 and "<(S.live_ok?POLL_SSE_SKIP_MS:POLL_NOSSE_SKIP_MS))return;" in poll[0])
ok("the old 12 s timer is gone", ",12000);" not in boot)
vis = [l for l in boot.splitlines() if "visibilitychange" in l]
ok("coming back to the tab reloads Live or Games when the last load is over FG_RELOAD_MIN_MS old, not when hidden",
   vis == ["document.addEventListener('visibilitychange',()=>{if(document.hidden||!['live','games'].includes(S.view))return;if(Date.now()-(S.lastLoad||0)>FG_RELOAD_MIN_MS){S.lastLoad=Date.now();load(S.view);}});"], vis)
ok("no new external hosts in the three files", not re.search(r"https?://", boot + moments + common.split("\n", 3)[2]))
