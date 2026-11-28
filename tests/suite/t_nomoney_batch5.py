# CHECK: group=engine
# No-money batch 5 (display only): fullauto freeze button uses data-rec, games cards are keyboard buttons, the empty chance
# row keeps its height, and _cut_guard_ts survives a bet with no legs.
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
repo = os.environ.get("REPO", ".")
rd = lambda f: open(os.path.join(repo, "watcher/spa", f)).read()
fa, gj, gc = rd("fullauto.js"), rd("games.js"), rd("games.css")
ok("freeze button: no esc(x.rec) inside a JS string", "faFreeze(this,'${esc(x.rec)}'" not in fa)
ok("freeze button: key read from data-rec", 'data-rec="${esc(x.rec)}"' in fa and "faFreeze(this,this.dataset.rec,this.dataset.on==='true')" in fa)
ok("games card: role=button and tabindex=0", 'role="button" tabindex="0"' in gj)
ok("games card: Enter and Space open the game", "event.key==='Enter'||event.key===' '" in gj)
ok("games card: empty chance row keeps its height", ".gc .gl.none{visibility:hidden}" in gc and ".gl.none{display:none}" not in gc)
ok("games card: focus ring", ".gc:focus-visible{outline:2px solid var(--acc)" in gc)
ok("_cut_guard_ts: bet with no legs gives the empty set", E._cut_guard_ts({"id": "x"}, [], 0.2, 0.5, 0.2) == set())
ok("_cut_guard_ts: legs None gives the empty set", E._cut_guard_ts({"id": "x", "legs": None}, [], 0.2, 0.5, 0.2) == set())
