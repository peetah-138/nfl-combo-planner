# CHECK: group=static
# Polish D (Build, Settings, Knobs; display only): the league/sport chip rows are ONE sideways row of 44px chips, not a wall
# of wrapped 32px ones, and phone Settings loses its stacked gaps and shows each folded section's one-line summary.
# Exact values are pinned here; nothing about a setting, a switch or a save is read or changed.
import os, re
bad = 0
def check(name, cond, why=""):
    global bad
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else ": " + why))
    bad += not cond
here = os.path.dirname(os.path.abspath(__file__))
spa = os.path.join(os.environ.get("REPO") or os.path.abspath(os.path.join(here, "..", "..")), "watcher", "spa")
rd = lambda f: open(os.path.join(spa, f), encoding="utf-8").read()
bj, bc, sj, sc = rd("build.js"), rd("build.css"), rd("settings.js"), rd("settings.css")

rule = re.search(r"\.chips\.chrow\{([^}]*)\}", bc)
r = rule.group(1) if rule else ""
check("chip row is one non-wrapping row", "flex-wrap:nowrap" in r and "overflow-x:auto" in r, r)
check("chip row gap is 8px and the row fades at the right edge", "gap:8px" in r and "linear-gradient(90deg,#000 calc(100% - 28px),transparent)" in r, r)
cr = re.search(r"\.chips\.chrow \.chip\{([^}]*)\}", bc)
check("chips in the row are 44px tall and do not shrink", bool(cr) and "min-height:44px" in cr.group(1) and "flex:none" in cr.group(1), cr and cr.group(1))
check("Build league row uses it", 'const chipRow=`<div class="chips chrow" style="margin-bottom:14px">' in bj)
check("Build lines filter row uses it", '<div class="chips chrow" style="margin-bottom:10px">${types.map' in bj)
check("Settings sport row uses it", '<div class="chips chrow" style="margin-bottom:16px" id="sleagues">' in sj)
check("no sport-row chip is left in a wrapping row", bj.count("chips chrow") == 2 and sj.count("chips chrow") == 1)
check("the chosen chip is scrolled into view, row only", "function chrowFit()" in bj and "r.scrollLeft=" in bj and "scrollIntoView" not in bj.split("function chrowFit()")[1].split("\n")[0])
check("Build keeps the row's scroll across redraws", "const rl=(document.querySelector('#main .chrow')||{}).scrollLeft||0;" in bj)
check("Settings fits the row after drawing", "function sAfter(m,hadF,a,b){sBadges();chrowFit();" in sj)
check("the jump chips are 44px tall", ".sidx .sj{min-height:44px;" in sc)
check("phone Settings has no stacked grid gap", "@media (max-width:1100px){.set{gap:0}" in sc)
check("a folded section keeps its one-line summary", ".scard.shut>header p{padding-bottom:12px;margin-top:-10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" in sc)
check("an unreadable Mac status is grey, not red", ".smac .dot.off{background:var(--mute);" in sc)
check("Mac status wording is calm", "status can't be read right now" in sj and "status isn't available right now" not in sj)
print("ALL OK" if not bad else "FAILED")
raise SystemExit(1 if bad else 0)
