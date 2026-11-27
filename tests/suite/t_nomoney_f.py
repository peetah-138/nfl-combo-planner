# CHECK: group=engine
"""nomoney-f-144 (#453 #112 #140): a lost buy reply leaves a durable note, the cap message uses the slider's $10 steps,
and the toast / focus / grey-text quick wins. Source text checks (display only; nothing here buys or sells)."""
import os
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
rd = lambda f: open(os.path.join("wtest", "spa", f), encoding="utf-8").read()
mo, bj, ls, ide, ix, ap = rd("moments.js"), rd("build.js"), rd("longshots.js"), rd("ideas.js"), rd("index.html"), rd("app.css")
ok("checkLive helper: a sheet when none is open, else a long toast",
   "function checkLive(" in mo and "okSheet(title||'Check Live',null,msg,true)" in mo and "toast((title||'Check Live')" in mo)
ok("Build buy: a lost reply is flagged and shown by checkLive, not a plain toast",
   "lost:true" in bj and "checkLive(m" in bj and "if(r.check)toast(m,9000" not in bj)
ok("Long shots buy: same", "lost:true" in ls and "checkLive(m" in ls and "if(res.check)toast(m,9000" not in ls)
ok("Live ideas buy: a lost or unclear reply uses checkLive", "if(r.check||r.lost)checkLive(m" in ide)
ok("the toast is a polite live region", 'id="toast" role="status" aria-live="polite"' in ix)
ok("grey text is darker in light mode and lighter in dark mode (contrast)", "--mute:#8790a3;" in ap and "--mute:#6f7890;" in ap)
ok("a keyboard focus ring exists for buttons and links", ":focus-visible{outline:2px solid var(--acc)" in rd("chrome.css"))
