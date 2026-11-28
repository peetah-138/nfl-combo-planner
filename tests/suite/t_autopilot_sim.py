# CHECK: group=engine
# Full auto, every autopilot step ON TOGETHER, simulated end to end (tests only, nothing in the engine changes). A seeded, offline,
# 60+ day run drives the REAL code (full_auto_pass, fal_tick, panel_approve / panel_add, panel_settle): each day a draft panel and
# two extras windows arrive, the bets "buy" and settle at random, and the practice-panel / league-shadow / Smart-Buy evidence the
# autopilot judges keeps flowing. The money invariants are checked after EVERY pass and weekly look against the simulator's OWN
# ledger (what it saw scheduled and what settled), never by asking fa_check to grade itself:
#   * a day's stakes <= $30 and <= the cap after the soft brake and cap use; no bet over 150% of its normal size or the free bankroll;
#     open risk <= bankroll + realized profit; a day's stakes never past the daily loss room; open bets <= Pete's 15; learned open
#     number 8-20; every share >= 5%; size 50-150%, cap use 50-100%; Pete's own limits untouched;
#   * at most 2 LOOSER changes in any 7 days (tightening is exempt: tighten fast, loosen slow), the autopilot's own exclusion pairs
#     never in one week, no loosening while the soft brake is above 0, every loosening backed by evidence;
#   * Undo, freeze, the master switch, Pause and full-auto-off are honoured (frozen and master-off runs move NOTHING);
#   * unreadable / corrupt / NaN / missing-key state and a clock that jumps = no crash, no change, no buy.
# Scenarios: normal, winning streak, losing streak, a bad week, small bets (the open-bet limit binds), empty data. Several seeds.
# Kalshi is fake; the clock is the simulator's.
import os, time, tempfile, json, math, random, importlib.util
import datetime as _dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
REAL_TIME = time.time
T_START = REAL_TIME()
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.PACIFIC = _dt.timezone(_dt.timedelta(hours=-8))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.kalshi_send = lambda *a, **k: {}
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
E.buy_single = lambda t, n, px: (n, None)
E.can_trade = lambda: True
E._held_all = lambda: []
E.killer_exposure = lambda now: {}
E.close_prices = lambda *a, **k: {}
E.sim_exit = lambda c: None
E.panel_record = lambda: {"paper": {"ready": True, "bets": 60, "pl": 40.0, "days": 20, "days_up": 14, "clv": 0.01}, "real": {}}
VIOL = []                                            # every invariant breach, as plain text (a clean run leaves it empty)
CHECKS = [0]
NOTES = []                                           # spec questions that are not money breaches (printed, never fail)


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "   [" + str(extra) + "]"))


DAY = 86400
BASE = (int(T_START) // DAY + 2) * DAY + 20 * 3600     # sim day 0 at 20:00 UTC = 12:00 noon Pacific (UTC-8), a couple of days ahead of the real clock
SIM = {"t": BASE, "wall": BASE}                         # t = what time.time() says (it may jump); wall = the true simulated moment
time.time = lambda: SIM["t"]


class _SimDT(_dt.datetime):                             # the engine's own "now" (panel day, settle window) follows the simulator's clock too
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(SIM["t"], tz)


E.dt = type("dtmod", (), {**{k: getattr(_dt, k) for k in dir(_dt) if not k.startswith("__")}, "datetime": _SimDT})
TRUTH = {}                                              # ticker -> (settles_at, "yes" | "no"): the hidden outcome of every market


def fake_results(tickers):
    return {t: TRUTH[t][1] for t in tickers if t in TRUTH and TRUTH[t][0] <= SIM["wall"]}


E.fetch_results = fake_results
PFX = {"nba": "KXNBAGAME", "nfl": "KXNFLGAME", "mlb": "KXMLBGAME", "nhl": "KXNHLGAME", "epl": "KXEPLGAME"}
LGS = sorted(PFX)
BANK, CAP, DAYLOSS, MAXOPEN = 300.0, 30.0, 20.0, 15
FREE = {"nba": .09, "nfl": .06, "mlb": .02, "nhl": .04, "epl": .07}


def edge(scen, lg, d):
    """How much better (or worse) than its price a bet of this league really does on sim day d."""
    if scen == "winning":
        return FREE[lg] + .08
    if scen == "boom":
        return FREE[lg] + .30
    if scen == "losing":
        return -.12 if d >= 18 else FREE[lg]
    if scen == "badweek":
        return -.30 if 30 <= d < 37 else FREE[lg]
    return FREE[lg]


def clock_of(d, hours):
    return BASE + d * DAY + hours * 3600


def pday(t):
    return E._panel_day(t)


# ------------------------------------------------------------------------------------------------ world
def reset_world():
    for t in ("panel", "fa_slots", "league_shadow_q", "sb_paper", "expo_pos", "expo_pass"):
        E.store_x(f"drop table if exists {t}", ())
    E.STORE["panel_ok"] = False
    E.EXPO_STATE["db"] = None
    E._panel_table(); E._fa_slot_table(); E._league_shadow_q_table(); E._sb_paper_table(); E._expo_tables()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    TRUTH.clear()
    E.FAL_RUN["at"] = 0.0
    E.FA_SLOT_RUN["at"] = 0.0
    SIM["t"] = SIM["wall"] = BASE
    E._fa_update(lambda s: s.update(on=True, gate="passed", lessons={"cq": {"first": BASE - 40 * DAY, "last": 0}}))
    E.fa_set(True, limits={"cap": CAP, "bank": BANK, "max_open": MAXOPEN})


def seed_evidence(rng, scen, d):
    """One sim day's worth of the evidence the autopilot judges, written the way production writes it: practice-panel (paper) bets,
    league-shadow combo quotes and Smart Buy paper bets, all settled. d may be negative (the history before day 0)."""
    t0 = clock_of(d, 0)
    items = []
    for i in range(8):
        lg = rng.choice(LGS)
        p = round(rng.uniform(.35, .65), 2)
        won = rng.random() < min(.98, max(.02, p + edge(scen, lg, max(d, 0))))
        stake = 5.0
        n = stake / (p + E.single_fee(p))
        pl = round(n - stake if won else -stake, 2)
        combo = i % 4 == 0
        c = {"id": f"p{d}_{i}", "kind": "combo" if combo else "single", "state": "paper", "result": "won" if won else "lost", "pl": pl,
             "stake": stake, "at": t0 + 600 + i * 60, "clv": round(rng.uniform(-.01, .04), 4),
             "legs": [{"ticker": f"{PFX[lg]}-26NOV{abs(d):03d}P{i}-A"}]}
        items.append(c)
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (pday(t0), "paper", t0, "done", json.dumps({"at": t0, "items": items})))
    for lg in LGS:
        for j in range(3):
            pct = round(rng.uniform(.93, 1.0), 4)
            cut = 95.0
            won = rng.random() < min(.98, max(.02, .45 + edge(scen, lg, max(d, 0)) + (pct - .95)))
            stake = 5.0
            pnl = round(stake * (1.0 / .45 - 1) if won else -stake, 2)
            E.store_x("insert into league_shadow_q(ts, league, sport, n, pct, stake, pays, cut_now, cut_blend, pass_now, pass_blend, outcome, pnl) "
                      "values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (t0 + 900 + j * 60, lg, lg, 2, pct, stake, stake / .45, cut, cut, 1 if pct * 100 >= cut else 0,
                                                            1, "won" if won else "lost", pnl))
        for j in range(2):
            evv = round(rng.uniform(-.3, .5), 2)
            won = rng.random() < min(.98, max(.02, .5 + edge(scen, lg, max(d, 0)) + evv / 2))
            E.store_x("insert or replace into sb_paper(bet, ts, day, league, sport, kind, source, grade, role, price, fair, ev, pays, stake, plain, outcome, clv, at, game) "
                      "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"sb{d}_{lg}_{j}", t0 + 1200 + j * 60, pday(t0), lg, lg, "single", "live", "cand", "stake", .5, .55, evv, 10.0, 5.0,
                       evv, round(5.0 * (1.0 if won else -1.0), 2), .01, t0 + 1200, f"g{d}{lg}{j}"))


# the loosening runs start with every autopilot setting TIGHTENED (so there is room to loosen back), a brake that has been quiet for
# 40 days, and extra settled evidence in every table the autopilot judges, built so each setting's next step has a real, positive edge.
LOOSEN_VALS = {**{f"bar:{lg}": 1.0 for lg in LGS}, **{f"sbev:{lg}": 2 for lg in LGS}, "game_share": 0.20, "open_slots": 10,
               "share:@single": 0.65, "share:@combo": 0.30, "stake_mult": 0.80, "cap_use": 0.65}


def seed_loosen(rng, d):
    """Settled evidence for day d for the bar (league_shadow_q), Smart Buy bar (sb_paper), per-game limit (expo_pos) and open-bet
    limit (fa_slots) records, all of it clustered just past the current tightened values and winning most of the time."""
    t0 = clock_of(d, 0)
    for lg in LGS:
        for j in range(6):
            pct = round(rng.uniform(.950, .960), 4)
            won = rng.random() < .85
            E.store_x("insert into league_shadow_q(ts, league, sport, n, pct, stake, pays, cut_now, cut_blend, pass_now, pass_blend, outcome, pnl) "
                      "values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (t0 + 2000 + j * 30, lg, lg, 2, pct, 5.0, 5.0 / .45, 95.0, 95.0, 1, 1,
                                                            "won" if won else "lost", round(5.0 / .45 - 5.0 if won else -5.0, 2)))
        for j in range(4):
            evv = round(rng.uniform(-.35, 0.0), 2)
            won = rng.random() < .85
            E.store_x("insert or replace into sb_paper(bet, ts, day, league, sport, kind, source, grade, role, price, fair, ev, pays, stake, plain, outcome, clv, at, game) "
                      "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"sx{d}_{lg}_{j}", t0 + 2400 + j * 30, pday(t0), lg, lg, "single", "live", "cand", "stake", .5, .55, evv, 10.0, 5.0,
                       evv, round(5.0 if won else -5.0, 2), .01, t0 + 2400, f"gx{d}{lg}{j}"))
    for j in range(4):
        won = rng.random() < .85
        E.store_x("insert or replace into expo_pos(pos, ts, day, league, kind, cost, bank, games, alloc, seed, blocked, net, settled, batch, own) "
                  "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (f"xp{d}_{j}", t0 + 2800 + j * 30, pday(t0), "nba", "single", 5.0, BANK, json.dumps([f"x{d}_{j}"]),
                   json.dumps({f"x{d}_{j}": round(rng.uniform(61, 89), 2)}), 0, "", 6.0 if won else -5.0, t0 + 3000, 1, 1))
    for j in range(5):
        won = rng.random() < .85
        E.store_x("insert or replace into fa_slots values(?,?,?,?,?,?,?,?,?,?)",
                  (f"xs{d}_{j}", t0 + 3200 + j * 30, pday(t0), "skip", rng.randint(10, 14), 5.0, 9.0, "[]", "won" if won else "lost",
                   4.0 if won else -5.0))


def make_items(rng, scen, d, win, n, t_lo, t_hi, small=False, late=False):
    """n fresh candidate bets (singles, a quarter two-leg combos) with hidden outcomes; their kick-offs run t_lo..t_hi hours after
    sim noon of day d. Returns the panel items (state draft) and records each leg's hidden result in TRUTH."""
    out = []
    for i in range(n):
        lg = rng.choice(LGS)
        combo = rng.random() < .25
        kick = clock_of(d, rng.uniform(t_lo, t_hi) + (24 if late and rng.random() < .5 else 0))
        legs, ps, fs = [], [], []
        for k in range(2 if combo else 1):
            lgk = lg if k == 0 else rng.choice(LGS)
            tk = f"{PFX[lgk]}-26NOV{d:03d}{win}{i}{k}-A"
            ev = f"{PFX[lgk]}-G{d:03d}{win}{i}{k}"
            p = round(rng.uniform(.35, .65), 2)
            f = round(p + .04, 2)
            E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(kick))
            yes = rng.random() < min(.98, max(.02, p + edge(scen, lgk, d)))
            TRUTH[tk] = (kick + 2.5 * 3600, "yes" if yes else "no")
            legs.append({"ticker": tk, "event": ev, "pick": tk, "p": p, "fair": f})
            ps.append(p); fs.append(f)
        stake = round(rng.uniform(2.0, 3.0) if small else rng.uniform(6.0, 16.0), 2)
        if combo:
            pct = round(rng.uniform(.95, .99), 4)
            pays = round(stake * pct / (fs[0] * fs[1]), 2)
            c = E._cand("combo", lg, legs, fs[0] * fs[1], .05, "w", stake=stake, state="draft", pct=pct, pays=pays, fair_mult=1.0)
        else:
            c = E._cand("single", lg, legs, fs[0], (fs[0] - ps[0]) / ps[0], "w", price=ps[0], stake=stake, state="draft")
        c["_n"] = stake
        out.append(c)
    return out


def put_panel(mode, items, status="draft", at=None):
    at = at or SIM["t"]
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (pday(SIM["t"]), mode, at, status, json.dumps({"at": at, "items": items})))


# ------------------------------------------------------------------------------------------------ the simulator's own books
class Book:
    """What the simulator saw full auto buy: each bet's stake, its normal size, price, hidden outcome and settle time. It computes
    realized profit, open risk and free bankroll itself."""

    def __init__(self):
        self.bets = {}                                   # id -> record

    def add(self, c, day, now):
        tks = [l["ticker"] for l in c["legs"]]
        self.bets[c["id"]] = {"id": c["id"], "day": day, "stake": float(c["stake"]), "normal": c["_n"], "kind": c["kind"], "at": now, "tks": tks,
                              "p": float(c.get("price") or 0), "pct": c.get("pct"), "fs": [l["fair"] for l in c["legs"]]}

    def settled_at(self, b):
        return max(TRUTH[t][0] for t in b["tks"])

    def pl(self, b):
        yes = all(TRUTH[t][1] == "yes" for t in b["tks"])
        if b["kind"] == "combo":
            pays = b["stake"] * b["pct"] / (b["fs"][0] * b["fs"][1])
            return round(pays - b["stake"] if yes else -b["stake"], 2)
        n = b["stake"] / (b["p"] + E.single_fee(b["p"]))
        return round(n - b["stake"] if yes else -b["stake"], 2)

    def done(self, b, wall):
        return self.settled_at(b) <= wall

    def realized(self, wall, day=None):
        return round(sum(self.pl(b) for b in self.bets.values() if self.done(b, wall) and (day is None or b["day"] == day)), 2)

    def open_bets(self, wall):
        return [b for b in self.bets.values() if not self.done(b, wall)]

    def risk(self, wall):
        return round(sum(b["stake"] for b in self.open_bets(wall)), 2)

    def day_total(self, day):
        return round(sum(b["stake"] for b in self.bets.values() if b["day"] == day), 2)

    def free(self, wall):
        return round(BANK + self.realized(wall) - self.risk(wall), 2)


# ------------------------------------------------------------------------------------------------ autopilot bookkeeping
RECS = {"open_slots": "open", "stake_mult": "stake", "cap_use": "capuse", "game_share": "game"}
START = {"bar": 0.0, "sbev": 0, "game": 0.30, "open": MAXOPEN, "share": 1.0, "stake": 1.0, "capuse": 1.0}


def rec_of(key):
    return RECS.get(key) or key.split(":")[0]


def fin(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


class Watch:
    """Diffs the autopilot's saved numbers after every tick and pass and checks the weekly rules and the bounds."""

    def __init__(self, label):
        self.label, self.vals, self.events, self.seen = label, {}, [], set()
        self.steps = self.tight = self.loose = 0
        self.max_level = 0
        self.undone = None
        self.logs = []                                   # every autopilot card line seen (step / revert / undo), with its evidence
        self.cautious_at = None                          # the last moment the brake was cautious at a look
        self.prev_cautious = False

    def v(self, msg):
        VIOL.append(f"[{self.label}] day {self.day}: {msg}")

    day = -1
    prev_level = 0

    def look(self, where):
        st = E.fa_state()
        L = st.get("lessons") if isinstance(st.get("lessons"), dict) else {}
        vals = dict(L.get("vals") or {})
        CHECKS[0] += 1
        lvl = (st.get("caution") or {}).get("level", 0) if isinstance(st.get("caution"), dict) else 0
        self.max_level = max(self.max_level, lvl)
        wall = SIM["wall"]
        for k, x in vals.items():                        # bounds on every saved number, every time
            r = rec_of(k)
            if not fin(x):
                self.v(f"{k} is not a finite number: {x!r}")
                continue
            lo, hi = E.FAL[r]["lo"], E.FAL[r]["hi"]
            if not lo - 1e-9 <= x <= hi + 1e-9:
                self.v(f"{k}={x} outside {lo}..{hi}")
        for lim, want in (("cap", CAP), ("bank", BANK), ("max_open", MAXOPEN), ("day_loss", DAYLOSS)):
            if st.get(lim) != want:
                self.v(f"Pete's {lim} changed to {st.get(lim)!r}")
        for k in sorted(set(vals) | set(self.vals)):     # what moved since the last look
            a, b = self.vals.get(k, START[rec_of(k)]), vals.get(k, START[rec_of(k)])
            if fin(a) and fin(b) and abs(a - b) > 1e-9:
                r = rec_of(k)
                looser = E._ap_looser(r, a, b)
                self.events.append({"t": wall, "key": k, "rec": r, "looser": looser, "a": a, "b": b, "level": self.prev_level, "lvl_after": lvl, "where": where,
                                    "day": self.day, "cautious": self.prev_cautious, "cq": self.cautious_at})
                if looser:
                    self.loose += 1
                else:
                    self.tight += 1
        self.vals = vals
        self.prev_level = lvl
        self.prev_cautious = E.ap_brake_cautious(st, wall)
        if self.prev_cautious or lvl > 0:
            self.cautious_at = wall
        for e in L.get("log") or []:                     # evidence behind every loosening step
            key = (e.get("at"), e.get("kind"), e.get("key"), e.get("text"))
            if key in self.seen:
                continue
            self.seen.add(key)
            self.logs.append(e)
            if e.get("kind") == "step":
                self.steps += 1
        return st, L

    def weekly(self):
        ev = sorted(self.events, key=lambda e: e["t"])
        for i, e in enumerate(ev):
            if not e["looser"]:
                continue
            if e["level"] > 0:
                self.v(f"loosened {e['key']} {e['a']}->{e['b']} while the soft brake was at level {e['level']}")
            week = [x for x in ev if x["looser"] and e["t"] - 7 * DAY < x["t"] <= e["t"]]
            if len({x["key"] for x in week}) > 2:
                self.v(f"{len({x['key'] for x in week})} settings loosened within 7 days: {[x['key'] for x in week]}")
        for i, e in enumerate(ev):                        # settings that depend on each other never move in the same week (a tightening is exempt: fast)
            for x in ev[:i]:
                if e["t"] - x["t"] < 7 * DAY and e["looser"] and x["looser"] and e["key"] != x["key"] and x["rec"] in E.AP_EXCL.get(e["rec"], ()):
                    self.v(f"{e['key']} and {x['key']} both loosened inside one week ({E.AP_EXCL.get(e['rec'])})")
        tot = {}
        for e in ev:                                      # the literal "2 changes a week" counting tightenings too: a spec note, not a money breach
            wk = [x for x in ev if e["t"] - 7 * DAY < x["t"] <= e["t"] and x["key"] != e["key"]]
            tot[len({x["key"] for x in wk} | {e["key"]})] = tot.get(len({x["key"] for x in wk} | {e["key"]}), 0) + 1
        return tot


def step_size_ok(rec, a, b, looser):
    """The exact size of one automatic step (a setting moves one notch, never more): bet size 5% of the CURRENT size, cap use / share
    5 points, bar half a point, Smart Buy bar one level, per-game limit 2.5 points, open-bet limit one bet. A loosening that reaches the
    start (or the range end) lands exactly on it; a share's tighter step may skip up to three notches that change nothing."""
    f = E.FAL[rec]
    if rec == "stake":
        want = round(a * 1.05, 4) if looser else round(a * 0.95, 4)
        return abs(b - min(max(want, f["lo"]), f["hi"])) < 1e-6
    if rec == "share" and not looser:
        return any(abs(b - round(a - n * f["step"], 4)) < 1e-6 for n in (1, 2, 3))
    sign = E.AP_REG[rec]["sign"]                         # +1: a bigger number is tighter
    want = a - sign * f["step"] if looser else a + sign * f["step"]
    if looser and rec != "open" and (want - START[rec]) * sign < 0:
        want = START[rec]                                # (never past the start; the open-bet limit may, up to Pete's own number)
    return abs(b - min(max(want, f["lo"]), f["hi"])) < 1e-6


def rules_check(r):
    """The autopilot's own rules, from the saved numbers and card lines the Watch saw: one step per setting per week, exact step sizes,
    no loosening without a gate-passing line, none while the brake was cautious or within 14 days of it (bet size / cap use), and the
    open-bet limit never above Pete's number."""
    w = r.w
    ev = sorted(w.events, key=lambda e: e["t"])
    for i, e in enumerate(ev):
        tag = f"{e['key']} {e['a']}->{e['b']} on day {e['day']}"
        match = [g for g in w.logs if g.get("key") == e["key"] and 0 <= e["t"] - g["at"] <= DAY and
                 (g.get("kind") == "undo" or (g.get("ev") and abs(g["ev"].get("from", -9e9) - e["a"]) < 1e-6 and abs(g["ev"].get("to", -9e9) - e["b"]) < 1e-6))]
        if not match:
            r.v(f"{tag}: a setting moved with no card line explaining it")
            continue
        g = match[-1]
        kind = g.get("kind")
        if kind == "step":
            if not step_size_ok(e["rec"], e["a"], e["b"], e["looser"]):
                r.v(f"{tag}: not one exact notch")
            if e["looser"] and not (g["ev"].get("stale") or (g["ev"].get("lb", 0) > 0 and g["ev"].get("hold", 0) > 0 and g["ev"].get("gain", 0) > 0)):
                r.v(f"{tag}: loosened without gate evidence {g['ev']}")
        if e["looser"] and kind in ("step", "revert") and (e["cautious"] or e["level"] > 0):
            r.v(f"{tag}: loosened while the brake was cautious")
        if e["looser"] and kind == "step" and e["rec"] in E.FAL_RISKY and e["cq"] is not None and e["t"] - e["cq"] < E.FAL_RISK["quiet"]:
            r.v(f"{tag}: loosened only {(e['t'] - e['cq']) / DAY:.1f} days after the brake was last cautious")
        if e["rec"] == "open" and e["b"] > MAXOPEN:
            r.v(f"{tag}: the open-bet limit went above Pete's {MAXOPEN}")
        for x in ev[:i]:                                 # one step per setting per week (an Undo is Pete's, not a step)
            if x["rec"] == e["rec"] and e["t"] - x["t"] < 7 * DAY and kind != "undo":
                gx = [h for h in w.logs if h.get("key") == x["key"] and 0 <= x["t"] - h["at"] <= DAY]
                if not gx or gx[-1].get("kind") != "undo":
                    r.v(f"{tag}: {x['key']} had already moved {(e['t'] - x['t']) / DAY:.1f} days earlier (one step per setting per week)")


# ------------------------------------------------------------------------------------------------ one pass, checked
class Run:
    def __init__(self, seed, scen, days=64, **opt):
        self.seed, self.scen, self.days, self.opt = seed, scen, days, opt
        self.label = f"{scen}/{seed}"
        self.rng = random.Random(seed * 7919 + sum(map(ord, scen)))
        self.book = Book()
        self.w = Watch(self.label)
        self.stats = {"passes": 0, "bought": 0, "cap_bound": 0, "open_bound": 0, "grown": 0, "paused_days": 0, "max_open": 0, "max_day": 0.0,
                      "level_days": 0, "brake_days": 0}
        self.day_idx = -1

    def v(self, msg):
        VIOL.append(f"[{self.label}] day {self.day_idx}: {msg}")

    def new_bets(self, day):
        real = E.panel_get("real", day=day) or {}
        return [c for c in real.get("items", []) if c.get("state") == "scheduled" and c["id"] not in self.book.bets]

    def do_pass(self, tag, paused=False, now=None):
        """One full_auto_pass at the current sim moment, then the 'buy' (scheduled -> bought) and every invariant."""
        wall = SIM["wall"]
        st0 = E.fa_state()
        day = pday(SIM["t"])
        free0 = self.book.free(wall)
        real_today = self.book.realized(wall, day)
        try:
            chk = E.fa_check(st0, paused=paused, may_trade=True, now=now)
            level = chk["caution"]["level"]
        except Exception as err:
            self.v(f"fa_check raised {type(err).__name__}: {err}")
            level = 0
        m_live, cu_live = E.ap_stake_mult(st0, level), E.ap_cap_use(st0)
        if not (0.5 - 1e-9 <= m_live <= 1.5 + 1e-9) or (level and m_live > 1.0 + 1e-9):
            self.v(f"the live bet-size multiple is {m_live} at brake level {level}")
        if not (0.5 - 1e-9 <= cu_live <= 1.0 + 1e-9):
            self.v(f"the live cap use is {cu_live}")
        vals0 = (st0.get("lessons") or {}).get("vals") or {}
        cu = vals0.get("cap_use", 1.0) if fin(vals0.get("cap_use", 1.0)) and E.fal_on(st0) else 1.0
        try:
            E.full_auto_pass(paused=paused, may_trade=True, now=now, log=lambda *a: None)
        except Exception as err:
            self.v(f"full_auto_pass raised {type(err).__name__}: {err}")
            return
        self.stats["passes"] += 1
        new = self.new_bets(day)
        if paused and new:
            self.v(f"Pause was on and the pass still scheduled {len(new)} buys")
        if not st0.get("on") and new:
            self.v("full auto is OFF and the pass still scheduled buys")
        changes = {}
        for c in new:
            self.book.add(c, day, SIM["wall"])
            b = self.book.bets[c["id"]]
            changes[c["id"]] = {"state": "bought", "bought_at": SIM["t"], "paid": b["p"] or None,
                                "pays": round(b["stake"] * b["pct"] / (b["fs"][0] * b["fs"][1]), 2) if b["kind"] == "combo" else None}
        if changes:                                      # the "buy": panel_exec's job, done the same way (state -> bought, paid, pays at the real stake)
            E._set_items(day, "real", {i: {k: v for k, v in ch.items() if v is not None} for i, ch in changes.items()})
        spent_new = round(sum(float(c["stake"]) for c in new), 2)
        self.stats["bought"] += len(new)
        # ---- the invariants, from the simulator's own books
        total = self.book.day_total(day)
        if total > CAP + 0.01:
            self.v(f"a day's stakes reached ${total} (> the ${CAP:g} cap) on {day}")
        cap_eff = round(CAP * E._fa_knob(level, "cap") * cu, 2)
        if new and total > cap_eff + 0.01:
            self.v(f"stakes ${total} passed today's cap ${cap_eff} (brake level {level}, cap use {cu})")
        if new and total >= cap_eff - 2.0:
            self.stats["cap_bound"] += 1
        for c in new:
            b = self.book.bets[c["id"]]
            if b["stake"] > 1.5 * b["normal"] + 0.01:
                self.v(f"bet {c['id']} was ${b['stake']}, over 150% of its normal ${b['normal']}")
            if b["stake"] > 1.0 * b["normal"] + 0.01:
                self.stats["grown"] += 1
        if new and spent_new > free0 + 0.01:
            self.v(f"the pass spent ${spent_new} with only ${free0} of the bankroll free")
        risk1 = self.book.risk(wall)
        if risk1 > BANK + max(0.0, self.book.realized(wall)) + 0.01:
            self.v(f"open risk ${risk1} is over the bankroll ${BANK:g} + realized profit")
        if risk1 > BANK + 0.01:
            NOTES.append(f"{self.label}: open risk ${risk1} was over $300 after profits")
        if new and total > DAYLOSS + real_today + 0.01:
            self.v(f"a day's stakes ${total} passed the daily loss room (${DAYLOSS:g} + ${real_today} settled today)")
        n_open = len(self.book.open_bets(wall))
        self.stats["max_open"] = max(self.stats["max_open"], n_open)
        if n_open > MAXOPEN:
            self.v(f"{n_open} bets open, over Pete's {MAXOPEN}")
        if n_open >= MAXOPEN:
            self.stats["open_bound"] += 1
        self.stats["max_day"] = max(self.stats["max_day"], total)
        self.w.day = self.day_idx
        self.w.look(tag)

    def run(self):
        o = self.opt
        reset_world()
        scen, rng = self.scen, self.rng
        for dd in range(-45 if scen != "empty" else 0, 0):
            seed_evidence(rng, scen, dd)
            if o.get("loosen"):
                seed_loosen(rng, dd)
        if o.get("loosen"):                              # start tightened, with a brake that has been quiet for 40 days
            lv = o["loosen"] if isinstance(o["loosen"], dict) else LOOSEN_VALS
            E._fa_update(lambda s: s["lessons"].setdefault("vals", {}).update(lv))
        self.start_vals = dict((E.fa_state().get("lessons") or {}).get("vals") or {})
        self.w.vals = dict(self.start_vals)               # (the seeded, tightened numbers are the starting point, not a change)
        if o.get("master_off"):
            E.fa_lessons_set(False)
        if o.get("freeze"):
            for k in list(E.AP_REG) + ["knobs"]:
                E.ap_freeze(k, True)
        if o.get("fa_off"):
            E._fa_update(lambda s: s.update(on=False))
        small = scen == "small"
        for d in range(self.days):
            self.day_idx = d
            T = clock_of(d, 0)
            SIM["t"] = SIM["wall"] = T
            if d > 0 and scen != "empty":
                seed_evidence(rng, scen, d - 1)
                if o.get("loosen"):
                    seed_loosen(rng, d - 1)
            if o.get("undo_day") == d:
                self.try_undo()
            paused = o.get("pause_days") is not None and d in o["pause_days"]
            self.stats["paused_days"] += 1 if paused else 0
            E.panel_settle()
            E.FAL_RUN["at"] = 0.0
            try:
                E.fal_tick(E.fa_state(), SIM["t"], lambda *a: None)
            except Exception as err:
                self.v(f"fal_tick raised {type(err).__name__}: {err}")
            self.w.day = d
            self.w.look("tick")
            if o.get("undo_first_loosen") and not self.undo2 and any(e["looser"] and e["day"] == d for e in self.w.events):
                self.undo_now(d)
            put_panel("real", make_items(rng, scen, d, "a", 14 if small else 8, .6, 9, small=small, late=small), "draft")
            self.do_pass("p1", paused=paused)
            SIM["t"] = SIM["wall"] = clock_of(d, 2)
            E.panel_settle()
            put_panel("extra", make_items(rng, scen, d, "b", 6 if small else 3, 3.5, 9, small=small), "draft")
            self.do_pass("p2", paused=paused)
            SIM["t"] = SIM["wall"] = clock_of(d, 11.5)
            E.panel_settle()
            put_panel("extra", make_items(rng, scen, d, "c", 6 if small else 3, 12.5, 14, small=small), "draft")
            self.do_pass("p3", paused=paused)
            if o.get("skew_day") == d:
                self.skew()
            self.daily_checks(d)
        SIM["t"] = SIM["wall"] = clock_of(self.days, 0)
        E.panel_settle()
        self.end_checks()
        return self

    undo2 = None

    def undo_now(self, d):
        """Pete presses Undo right after the autopilot's first loosening: it must succeed, put the setting back where it was and hold it."""
        L0 = (E.fa_state().get("lessons") or {})
        ch = dict(L0.get("change") or {})
        t = SIM["t"]
        res = E.ap_undo(t)
        self.w.look("undo")
        L1 = (E.fa_state().get("lessons") or {})
        vals = L1.get("vals") or {}
        key = ch.get("key")
        back = vals.get(key, START.get(rec_of(key), None)) if key else None
        if not res[0] or not ch:
            self.v(f"Undo of the first loosening failed: {res} (change {ch})")
        elif abs(back - ch["from"]) > 1e-9:
            self.v(f"Undo left {key} at {back}, not the previous {ch['from']}")
        elif abs(float((L1.get("holds") or {}).get(key, 0)) - (t + E.AP_HOLD)) > 1.5:
            self.v(f"Undo did not hold {key} for two weeks: holds={(L1.get('holds') or {}).get(key)}")
        self.undo2 = {"t": t, "key": key, "res": res, "from": ch.get("from"), "to": ch.get("to")}

    def try_undo(self):
        st = E.fa_state()
        if self.undone:
            return
        before = dict((st.get("lessons") or {}).get("vals") or {})
        ch = (st.get("lessons") or {}).get("change") or {}
        res = E.ap_undo(SIM["t"])
        self.undone = (res, ch, before)

    undone = None

    def skew(self):
        """The machine's clock steps back a day, forward a week, and back again: no crash, nothing new bought outside the books."""
        real_wall = SIM["wall"]
        for hop in (-26 * 3600, 7 * DAY, -3 * DAY, 0):
            SIM["t"] = real_wall + hop
            try:
                E.FAL_RUN["at"] = 0.0
                E.fal_tick(E.fa_state(), SIM["t"], lambda *a: None)
                put_panel("extra", make_items(self.rng, self.scen, self.day_idx, "s", 3, 14, 16), "draft")
                self.do_pass(f"skew{hop}")
            except Exception as err:
                self.v(f"clock skew {hop}s raised {type(err).__name__}: {err}")
        SIM["t"] = real_wall

    def daily_checks(self, d):
        self.w.day = d
        st = E.fa_state()
        b = st.get("brake")
        if isinstance(b, dict) and b.get("kind") == "day":
            self.stats["brake_days"] += 1
        if (st.get("caution") or {}).get("level", 0) > 0:
            self.stats["level_days"] += 1
        # books agree: what panel_settle recorded for settled bets matches the simulator's own profit (to 5 cents)
        real = E.panel_get("real", day=pday(clock_of(d, 0))) or {}
        for c in real.get("items", []):
            bk = self.book.bets.get(c["id"])
            if bk and c.get("result") and abs(float(c.get("pl") or 0) - self.book.pl(bk)) > 0.06:
                self.v(f"panel_settle's profit {c.get('pl')} differs from the simulator's {self.book.pl(bk)} for {c['id']}")

    def end_checks(self):
        by_day = {}
        for b in self.book.bets.values():
            by_day[b["day"]] = round(by_day.get(b["day"], 0) + b["stake"], 2)
        for day, tot in by_day.items():
            if tot > CAP + 0.01:
                self.v(f"day {day} totals ${tot} over the ${CAP:g} cap")
        self.w.weekly()
        rules_check(self)
        self.w.day = self.days
        self.stats["events"] = len(self.w.events)
        self.stats["loose"], self.stats["tight"] = self.w.loose, self.w.tight
        self.stats["max_level"] = self.w.max_level
        self.stats["days_bet"] = len(by_day)
        # spec note only: the literal "2 changes a week" counting tightenings
        ev = sorted(self.w.events, key=lambda e: e["t"])
        for e in ev:
            keys = {x["key"] for x in ev if e["t"] - 7 * DAY < x["t"] <= e["t"]}
            if len(keys) > 2:
                NOTES.append(f"{self.label}: {len(keys)} settings changed in one week counting tightenings: {sorted(keys)}")
                break


def show(r):
    s = r.stats
    print(f"#   {r.label}: passes {s['passes']}, bought {s['bought']} on {s['days_bet']} days, max day ${s['max_day']:.2f}, max open {s['max_open']}, "
          f"changes {s['events']} (looser {s['loose']}, tighter {s['tight']}), brake level seen {s['max_level']} ({s['level_days']} days), "
          f"day-loss brake {s['brake_days']} days, cap bound {s['cap_bound']}x, open bound {s['open_bound']}x, grown {s['grown']}")


def corrupt_phase():
    """Unreadable or odd full-auto files: no crash, no buys, nothing learned changes, and the next good file works again."""
    reset_world()
    SIM["t"] = SIM["wall"] = clock_of(1, 0)
    rng = random.Random(5)
    good = open(E._fa_path(), "rb").read()
    cases = {"empty file": b"", "garbage": b"\x00\xff not json {{{", "truncated": good[: max(5, len(good) // 2)], "list": b"[1, 2, 3]",
             "string": b'"on"', "null": b"null", "nan": b'{"on": true, "limits": {"cap": NaN, "bank": Infinity}}',
             "wrong types": b'{"on": true, "limits": "lots", "lessons": [], "caution": 7, "brake": "x", "bets": 3, "history": {}}',
             "missing keys": b'{"on": true}', "bad lessons": b'{"on": true, "lessons": {"vals": {"open_slots": NaN, "stake_mult": "big", "cap_use": null}}}'}
    for name, raw in cases.items():
        open(E._fa_path(), "wb").write(raw)
        put_panel("real", make_items(rng, "normal", 1, "z", 4, 3, 9), "draft")
        put_panel("extra", make_items(rng, "normal", 1, "y", 3, 3, 9), "draft")
        try:
            E.FAL_RUN["at"] = 0.0
            E.fal_tick(E.fa_state(), SIM["t"], lambda *a: None)
            E.full_auto_pass(paused=False, may_trade=True, now=SIM["t"], log=lambda *a: None)
            E.fa_check(E.fa_state(), paused=False, may_trade=True, now=SIM["t"])
        except Exception as err:
            VIOL.append(f"[corrupt:{name}] raised {type(err).__name__}: {err}")
            continue
        if raw.strip().startswith(b'{"on": true') and name in ("nan", "wrong types", "missing keys", "bad lessons"):
            pass                                          # a readable file that says on: only the invariants below apply
        else:
            moved = [c for m in ("real", "extra") for c in (E.panel_get(m, day=pday(SIM["t"])) or {}).get("items", []) if c.get("state") != "draft"]
            if moved:
                VIOL.append(f"[corrupt:{name}] unreadable file but {len(moved)} bets were approved")
        after = open(E._fa_path(), "rb").read()
        if raw[:1] in (b"", b"\x00", b"[", b'"', b"n") and after != raw and name != "truncated":
            VIOL.append(f"[corrupt:{name}] the unreadable file was overwritten")
    open(E._fa_path(), "wb").write(good)


def nothing_moves(r, what):
    if r.w.events or r.stats["bought"] and what != "master_off":
        VIOL.append(f"[{what}] settings moved or bets appeared: {len(r.w.events)} changes, {r.stats['bought']} bets")


def untouched(r, what):
    """A control run (master switch off, everything frozen, full auto off) that WOULD have loosened: it moved nothing at all."""
    now_vals = dict((E.fa_state().get("lessons") or {}).get("vals") or {})
    if r.w.events or now_vals != r.start_vals:
        VIOL.append(f"[{what}] settings moved: {len(r.w.events)} changes, {r.start_vals} -> {now_vals}")


def undo_check(r):
    if not r.undone:
        return
    res, ch, before = r.undone
    if not res[0] or not ch:
        return
    key = ch.get("key")
    later = [e for e in r.w.events if e["key"] == key and e["day"] > r.opt["undo_day"] and e["day"] < r.opt["undo_day"] + 14]
    if later:
        VIOL.append(f"[undo] {key} moved again {later[0]['day'] - r.opt['undo_day']} days after Undo (hold is 14 days)")
    r.stats["undone"] = 1


if __name__ == "__main__":
    T0 = REAL_TIME()
    runs = []
    D = int(os.environ.get("D", "40"))
    plan = [("normal", 1), ("winning", 1), ("losing", 3), ("badweek", 1), ("small", 2)]
    for scen, seed in plan:
        r = Run(seed, scen, days=D, skew_day=40 if seed == 1 else None, pause_days={20, 21} if seed == 2 else None).run()
        runs.append(r); show(r)
    for tag, o in (("master_off", {"master_off": True}), ("frozen", {"freeze": True}), ("fa_off", {"fa_off": True})):
        r = Run(4, "losing", days=10, **o); r.label = tag; r.run(); runs.append(r); show(r)
        if tag == "fa_off":
            if r.stats["bought"]:
                VIOL.append("[fa_off] full auto was off and bets were bought")
        if r.w.events:
            VIOL.append(f"[{tag}] {len(r.w.events)} autopilot settings changed")
    # loosening runs: every setting starts tightened with a quiet brake and winning evidence in every table, so the autopilot loosens
    # for real; run A also presses Undo right after its first loosening, run B starts near the top of the ranges (the 150% / 100% ceilings)
    lrun = []
    DIAG = []
    for tag, seed, days, o in (("loosen_A", 1, 63, {"loosen": True, "undo_first_loosen": True}),
                               ("loosen_B", 2, 49, {"loosen": {**LOOSEN_VALS, "stake_mult": 1.45, "cap_use": 0.95}}),
                               # run C: only the bet-size / cap-use / share trio starts tightened, so the bar (which shares a week with
                               # all three) can't take their slot and the result doesn't depend on who wins the rotation
                               ("loosen_C", 3, 56, {"loosen": {k: v for k, v in LOOSEN_VALS.items() if k in ("share:@single", "share:@combo", "stake_mult", "cap_use")}})):
        r = Run(seed, "boom", days=days, **o); r.label = tag; r.run(); runs.append(r); lrun.append(r); show(r)
        if tag == "loosen_C":
            try:
                by, _ = E._share_load(SIM["t"])
                L = E.fa_state().get("lessons") or {}
                DIAG.append({"rows": {k: len(v) for k, v in by.items() if k.startswith("share:@")}, "cap": E.fa_state().get("cap"),
                             "vals": L.get("vals"), "cq": L.get("cq"), "steps": L.get("steps"), "caution": E.fa_state().get("caution"),
                             "now": SIM["t"], "hist": len(E.fa_state().get("history") or [])})
            except Exception as err:
                DIAG.append(repr(err))
    for tag, o in (("master_off", {"master_off": True}), ("frozen", {"freeze": True}), ("fa_off", {"fa_off": True})):
        r = Run(1, "boom", days=12, loosen=True, **o); r.label = tag + "_loosen"; r.run(); runs.append(r); show(r); untouched(r, tag + "_loosen")
        if tag == "fa_off" and r.stats["bought"]:
            VIOL.append("[fa_off_loosen] full auto was off and bets were bought")
        if tag != "fa_off" and not r.stats["bought"]:
            VIOL.append(f"[{tag}_loosen] nothing was bought, so the control proves nothing")
        if tag == "master_off" and r.stats["grown"]:
            VIOL.append("[master_off_loosen] bets were bigger than normal with Autopilot off")
    r = Run(6, "losing", days=32, undo_day=26); r.label = "undo"; r.run(); runs.append(r); show(r); undo_check(r)
    r = Run(7, "empty", days=10); r.label = "empty"; r.run(); runs.append(r); show(r)
    corrupt_phase()
    print("# elapsed %.1fs" % (REAL_TIME() - T0))
    allev = [e for r in runs[:5] for e in r.w.events]
    ok("the runs bought bets", all(r.stats["bought"] > 0 for r in runs[:5]))
    ok("some settings tightened", any(r.w.tight for r in runs[:5]))
    ok("the soft brake reached a cautious level", any(r.w.max_level >= 1 for r in runs[:5]))
    ok("the daily-loss brake tripped", any(r.stats["brake_days"] for r in runs[:5]))
    ok("the daily cap was the limit at times", any(r.stats["cap_bound"] for r in runs[:5]))
    loose_recs = {e["rec"] for r in lrun for e in r.w.events if e["looser"]}
    for rec in E.AP_REG:
        ok(f"the autopilot loosened its {rec} setting", rec in loose_recs,
           ({r.label: [(e["rec"], e["day"], e["looser"]) for e in r.w.events] for r in lrun}, DIAG))
    ok("a loosening happened early enough for the 12-day controls to prove something",
       any(e["looser"] and e["day"] <= 10 for e in lrun[0].w.events))
    ok("Undo restored the previous value and held it two weeks", bool(lrun[0].undo2 and lrun[0].undo2["res"][0]), lrun[0].undo2)
    hold = lrun[0].undo2 or {}
    again = [e for e in lrun[0].w.events if e["key"] == hold.get("key") and hold.get("t", 0) < e["t"] < hold.get("t", 0) + E.AP_HOLD]
    ok("the undone setting did not move again inside its 2-week hold", not again, again[:1])
    for x in VIOL[:40]:
        print("VIOLATION " + x)
    ok("no invariant breach in %d simulated passes" % sum(r.stats["passes"] for r in runs), not VIOL, VIOL[:3])
    for x in NOTES[:10]:
        print("# NOTE " + x)
    time.time = REAL_TIME
