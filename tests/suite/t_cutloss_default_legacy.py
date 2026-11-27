# CHECK: group=engine
# Review fixes on the 12.5% default loss cut (#556): a league that already tuned itself to "never cut" BEFORE the
# `loss_off` marker existed (loss None with 30+ results, no marker) keeps no cut; a settings read error fails closed
# (no default cut); an untouched league (under 30 results) still gets 12.5%. No real orders: nothing trades here.
import os, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(smart_sell=True, loss_cut_default=True)
def table(e):
    E.save_json(E.SMART_FILE, {"nba": e}); E.SMART_CACHE["at"] = 0

table({"floor": 1.5, "lam": 1.0, "loss": None, "n": 40})
ok("pre-marker league (30+ results, loss None, no loss_off) keeps 'never cut'", E.smart_params([T])["loss"] is None)
ok("...and the helper reads it as chosen off", E._loss_cut_chosen_off("nba") is True)
ok("...and the Results table shows no default for it", {x["key"]: x for x in E.smart_summary()}["nba"]["loss_default"] is None)
before = open(E.SMART_FILE).read(); E.smart_params([T]); E._loss_cut_chosen_off("nba")
ok("reading is idempotent: the file is not rewritten", open(E.SMART_FILE).read() == before)
table({"floor": 1.5, "lam": 1.0, "loss": None, "n": 29})
ok("under 30 results, nothing tuned: still 12.5%", E.smart_params([T])["loss"] == 0.125)
table({"floor": 1.5, "lam": 1.0, "loss": None, "loss_off": False, "n": 40})
ok("an explicit loss_off False (tuner kept the default) still gets 12.5%", E.smart_params([T])["loss"] == 0.125)
table({"floor": 1.5, "lam": 1.0, "loss": None, "loss_off": True, "n": 40})
ok("explicit loss_off True stays off", E.smart_params([T])["loss"] is None)

# fail closed: a settings read error means no default cut
table({"floor": 1.5, "lam": 1.0, "loss": None, "n": 4})
real = E.smart_table
def boom(): raise OSError("cannot read settings")
E.smart_table = boom
ok("error reading settings: _loss_cut_chosen_off fails closed (True)", E._loss_cut_chosen_off("nba") is True)
E.smart_table = real; E.SMART_CACHE["at"] = 0
ok("readable again: the default returns", E.smart_params([T])["loss"] == 0.125)
