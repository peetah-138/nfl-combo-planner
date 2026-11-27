# CHECK: group=engine
"""Batch F (#313 #304 #283 #307): the wording and the loss-selling status line. Source text checks for the screen
copy, plus sl_auto_view (display only) with the self-tuning switch and registry faked."""
import sys, os
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
rd = lambda f: open(os.path.join("wtest", "spa", f), encoding="utf-8").read()   # the web app files sit in wtest/spa
kn, st, hp = rd("knobs.js"), rd("settings.js"), rd("haptics.js")

# #304: one phrase for the brake everywhere
ok("brake words: 'worth at the time' on the registry card and Settings",
   kn.count("less than holding was worth at the time") >= 2 and "less than holding was worth at the time" in st)
ok("brake words: the old 'expected to pay when they sold' is gone from the screens",
   "expected to pay" not in kn and "expected to pay" not in st)
# #283: shorter intro in three labelled parts, plain luck wording, no repeated value
ok("registry intro: what moves / the bar / the brake", all(x in kn for x in ("<b>What moves:</b>", "<b>The bar:</b>", "<b>The brake:</b>")))
ok("registry intro: says 'clearly more than luck', not 'standard errors clear of luck'",
   "clearly more than luck explains" in kn and "standard errors clear of luck" not in kn)
ok("a value already under Changed is not repeated under 'Where it stands now'", "const mv=(L.moved||[]).filter(" in kn and "${mv.map(" in kn)
# #307 item 4: the haptics test card lists the folded Settings headers as known-quiet
ok("haptics card names the folded Settings headers as known exceptions", "folded section headers" in hp)
# #313: status line, hedging text, dim reason
ok("Selling at a loss shows where it is on", "function slWhere()" in st and "${slWhere()}" in st and "off elsewhere" in st)
ok("Prefer hedging no longer prints a fixed 5%", "up to 5% less" not in st)
ok("rows dimmed by Auto cash-out say why", st.count("Dimmed because Auto cash-out is off.") >= 3)

# sl_auto_view (display only)
real_sw, real_kv = M.knob_switch_on, M.knob_view
try:
    M.knob_switch_on = lambda: False
    ok("self-tuning off: {'live': False, 'on': []}", M.sl_auto_view() == {"live": False, "on": []})
    M.knob_switch_on = lambda: True
    M.knob_view = lambda now=None: {"leagues": [{"key": "all", "name": "All"}, {"key": "nba", "name": "NBA"}, {"key": "nfl", "name": "NFL"}],
                                    "knobs": [{"name": "sl_auto", "values": {"all": {"v": 1}, "nba": {"v": 1}, "nfl": {"v": 0}}}]}
    ok("on in NBA only ('all' never counts)", M.sl_auto_view() == {"live": True, "on": ["NBA"]})
    M.knob_view = lambda now=None: {}
    ok("an empty registry: on in no league", M.sl_auto_view() == {"live": True, "on": []})
    M.knob_view = lambda now=None: 1 / 0
    ok("an unreadable registry gives None, never raises", M.sl_auto_view() is None)
finally:
    M.knob_switch_on, M.knob_view = real_sw, real_kv
# wording-c: shorter registry brake sentence; New tag since the last visit (#283); no test-brake push
ok("registry brake sentence is one short line", "(any number it had made stricter stays). Loss guards, hedging and Smart Buy are still a test." in kn)
ok("a change since the last open of the card says New", "cw_ks_seen" in kn and ">New</span>" in kn)
