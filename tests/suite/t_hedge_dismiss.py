# CHECK: group=engine
# Dismissing a hedge card (display only): hides that combo's hedge suggestion for today, persisted in a file, and brings it
# back when what the hedge locks in or costs moves 20% and $0.50, or on a new day. Dismissing places, cancels and blocks
# nothing: hedge_for (what the Hedge button and auto-hedge use) is unchanged. Also checks the SPA wiring (Dismiss button,
# the Do-now filter, clearable Moments rows) and that the web action is not a money action.
import os, tempfile, importlib.util, re
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.HERE = tempfile.mkdtemp(); E.HEDGE_DISMISS = os.path.join(E.HERE, "hd.json"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
T = "KXNBAGAME-26NOV19LALBOS-LAL"
def board(price):
    E.MINE["hold"] = {T: {"need": [(("yes", "LEG-A"), 0.5)], "pays": 10.0}}
    E.MINE["all_games"] = {"g": [{"ticker": "LEG-A", "pick": "Chicago", "p": 0.4}, {"ticker": "LEG-B", "pick": "Cleveland", "p": price}]}
board(0.70)
hg = E.hedge_for(T)
ok("a hedge exists to dismiss", hg and hg["n"] >= 1)
ok("not dismissed at first", not E.hedge_dismissed(T, hg))
before = dict(hg)
ok("dismiss saves", E.hedge_dismiss(T) is True and os.path.exists(E.HEDGE_DISMISS))
ok("hidden afterwards (and after a 'reload': state comes from the file)", E.hedge_dismissed(T, E.hedge_for(T)))
ok("dismissing changed nothing about the hedge itself (the Hedge button's numbers)", E.hedge_for(T) == before)
ok("another combo is unaffected", not E.hedge_dismissed("OTHER-1", hg))
board(0.69)
ok("a small wobble keeps it hidden", E.hedge_dismissed(T, E.hedge_for(T)))
board(0.50)
ok("a material change (cost and lock-in move 20%+ and $0.50+) brings it back", not E.hedge_dismissed(T, E.hedge_for(T)))
board(0.70)
st = E.load_json(E.HEDGE_DISMISS, {}); st["day"] = "2000-01-01"; E.save_json(E.HEDGE_DISMISS, st)
ok("a new day brings it back", not E.hedge_dismissed(T, E.hedge_for(T)))
ok("nothing to hedge: dismiss refuses", (E.MINE["hold"].clear() or True) and E.hedge_dismiss(T) is False)
ok("garbage file never hides a card", (open(E.HEDGE_DISMISS, "w").write("{bad") or True) and not E.hedge_dismissed(T, hg))

# ---- wiring (display only)
repo = os.environ.get("REPO", ".")
live = open(os.path.join(repo, "watcher/spa/live.js")).read()
wat = open(os.path.join(repo, "watcher/combo_watcher.py")).read()
ok("Do-now skips a dismissed hedge", "!c.hedge_dismissed&&c.hedge.locked" in live)
ok("hedge card has a Dismiss button next to Hedge", 'onclick="hedgeDismiss(this.dataset.t)">Dismiss' in live and 'onclick="hedge(this.dataset.t)">Hedge</button>' in live)
ok("Moments rows can be cleared", "momClear(" in live and "cw_mom_x" in live)
ok("the web action exists and is not an order action", 'a == "hedge_dismiss"' in wat and not re.search(r'ORDER_ACTS = \([^)]*hedge_dismiss', wat))
