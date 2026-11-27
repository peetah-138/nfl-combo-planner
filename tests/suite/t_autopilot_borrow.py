# CHECK: group=engine
# Autopilot bar borrow (#145): a league with too little data for its own buy-bar step may borrow the other leagues'
# evidence, tighten-only, through the same gate, log, Undo, freeze and brake hook. Kalshi is fake.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
SENT = []
E.kalshi_send = lambda *a, **k: (SENT.append((a, k)) or {})
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
BOUGHT = []
E.buy_single = lambda t, n, px: (BOUGHT.append((t, n, px)) or (n, None))
E.can_trade = lambda: True
E._held_all = lambda: []
E.panel_record = lambda: {"paper": {"ready": True, "bets": 60, "pl": 40.0, "days": 20, "days_up": 14, "clv": 0.01}, "real": {}}
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()
DAY = 86400


def reset(on=True, lessons=True):
    for t in ("league_shadow_q", "sb_paper", "expo_pos"):
        E.store_x(f"drop table if exists {t}", ())
    E.EXPO_STATE["db"] = None
    E._league_shadow_q_table(); E._sb_paper_table(); E._expo_tables()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.FAL_RUN["at"] = 0.0
    E.TRADING_PAUSED = None
    BOUGHT.clear(); SENT.clear()
    if on:
        E._fa_update(lambda s: s.update(on=True, gate="passed", **({} if lessons else {"fa_lessons": False})))


def tick(at):
    E.FAL_RUN["at"] = 0.0
    return E.fal_tick(E.fa_state(), at, lambda *a: None)


def lessons():
    return E.fa_state().get("lessons") or {}


def vals():
    return lessons().get("vals") or {}



def row(i, lg, t, band, win=False):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (i, t, lg, lg, 2, 0.951 if band else 0.99, 5.0, 5.5, 95.0, 95.0, 1, 1,
               "won" if (win or not band) else "lost", (4.0 if win else -4.0) if band else 0.5))


def seed(rich_win=False, rich_n=80, thin_n=6):
    """nba (rich): half in the +0.5 band, losing unless rich_win. nhl (thin): a few rows only."""
    for i in range(rich_n):
        row(1000 + i, "nba", NOW - 4 * DAY + i * 3600, i % 2 == 0, rich_win)
    for i in range(thin_n):
        row(5000 + i, "nhl", NOW - 3 * DAY + i * 3600, i % 2 == 0)


def setup(**k):
    reset(); seed(**k)
    E.ap_freeze("bar:nba", True)                         # so only the thin league can be the step this week


setup()
tick(NOW)
ok("a thin league borrows the group's evidence and steps its bar", vals() == {"bar:nhl": 0.5})
ok("the card says it borrowed", any("other leagues" in (e.get("text") or "") and "NHL" in e["text"] for e in lessons()["log"]))
ok("the step is flagged as borrowed in its evidence", lessons()["log"][-1]["ev"].get("borrow") is True)
ok("the thin league's own data is still too small for its own gate",
   not E.ap_gate("bar", "bar:nhl", E._fal_load("bar", NOW)[0]["bar:nhl"], E._fal_load("bar", NOW)[1], 0.0, 0.5, 0)[0])
ok("the bar stays inside 0 to 5 and nothing else moved", E.fa_state()["lessons"]["vals"]["bar:nhl"] <= 5.0
   and all(E.fa_state()[k] == E.FA[k] for k in E.FA_LIMITS))

# not at all when the group evidence is negative (the band wins)
setup(rich_win=True)
tick(NOW)
ok("no borrow when the group's evidence says the bar would cost money", vals() == {})

# no borrow when the group itself is thin / unreadable
setup(rich_n=10)
tick(NOW)
ok("no borrow when the whole group is thin", vals() == {})
setup()
E.AP_REG["bar"]["load"] = lambda rec, now: (_ for _ in ()).throw(RuntimeError("disk"))
tick(NOW)
ok("unreadable data fails closed", vals() == {})
E.AP_REG["bar"]["load"] = lambda rec, now: E._fal_load(rec, now)

# skip-only: a borrowed league never loosens a bar from the group's evidence
reset(); seed(rich_win=True)
E.ap_freeze("bar:nba", True)
E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nhl": 2.0}, "frozen": {"bar:nba": True}}))
tick(NOW)
ok("a borrowed league is never loosened by borrowed evidence (skip-only)", vals() == {"bar:nhl": 2.0})
ok("the registry range stays 0 to 5, step 0.5", E.AP_REG["bar"]["bounds"] == {"lo": 0.0, "hi": 5.0, "step": 0.5})

# brake: tightening by borrow still allowed while cautious; a losing borrowed step is not walked back to looser
setup()
E._fa_update(lambda s: s.update(brake={"kind": "streak", "why": "t"}))
tick(NOW)
ok("tightening by borrow is still allowed while cautious", vals() == {"bar:nhl": 0.5})
at = lessons()["last"]["bar"]["at"]
for i in range(6):
    row(9000 + i, "nhl", at + 3600 * (i + 1), True, win=True)
tick(NOW + 8 * DAY)
ok("brake cautious: a lost borrowed step is not loosened back", vals() == {"bar:nhl": 0.5})
E._fa_update(lambda s: s.update(brake=None))
tick(NOW + 9 * DAY)
ok("brake clear: it reverts", vals() == {})
setup()
E._fa_update(lambda s: s.update(caution={"level": 1}))
tick(NOW)
ok("soft-brake caution: borrowed tightening allowed", vals() == {"bar:nhl": 0.5})

# undo and freeze
setup()
tick(NOW)
okU, msgU = E.ap_undo(NOW + 3600)
ok("undo takes the borrowed step back and holds it", okU and vals() == {} and E.full_auto_view()["lessons"]["holds"])
reset(); seed()
E.ap_freeze("bar:nhl", True); E.ap_freeze("bar:nba", True)
tick(NOW)
ok("a frozen thin league takes no borrowed step", vals() == {})
reset(); seed()
E.ap_freeze("bar", True)
tick(NOW)
ok("freezing the record stops borrowing too", vals() == {})
reset(); seed()
E._fa_update(lambda s: s.update(fa_lessons=False))
tick(NOW)
ok("Autopilot off: no borrowing", vals() == {})
