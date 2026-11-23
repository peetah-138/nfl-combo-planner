# CHECK: group=engine
"""Issue #324: a live score alert said "Jets score against your points" on a Chargers spread leg.

record_view named the pick with short_name(lg['name']), the last word of the leg's name once it is over 12
characters; a spread/total leg is named by its whole bet description ('Los Angeles C wins by over 2.5 points'), so
the last word was 'points'. Now alert_pick names the team the pick is on (the score's own side, the ticker's team
code, else the words before 'wins by'), adds the line for a spread ('Chargers (-2.5)') and calls a total what it is
('Over 47.5'). Text only: ticks, plays and every buy/sell path are untouched (checked at the end)."""
import os, re, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))

E.store_open(os.path.join(tempfile.mkdtemp(), "alerts.db"))
EV = "26NOV22LACNYJ"


def leg(ticker, name, sport="nfl", side="yes", me=0, opp=0, abbr="LAC", opp_abbr="NYJ", opp_name="", ch=0.5, **kw):
    d = {"ticker": ticker, "name": name, "opp": opp_name, "chance": ch, "live": ch, "res": None, "state": "live",
         "sport": sport, "side": side, "sc": {"me": me, "opp": opp, "abbr": abbr, "opp_abbr": opp_abbr, "detail": "Q2 13:34"}}
    d.update(kw)
    return d


def events(first, second, single=False):
    """Two Live refreshes: the first sets the score, the second changes it. Returns the second's events."""
    E.STORE["last"] = {}
    out = []
    for lg in (first, second):
        if single:
            x = dict(lg, t=lg["ticker"])
            out = E.record_view({"combos": [], "singles": [x]})
        else:
            out = E.record_view({"combos": [{"t": "COMBO45", "label": "Combo 45", "group": "pending", "cost": 5, "pays": 40,
                                             "p": 0.1, "legs": [lg]}]})
    return [e for e in out if e["kind"] in ("score", "swing")]


def texts(evs):
    return [e["text"] for e in evs]


# ---- 1. Pete's screenshot: Chargers spread leg, Jets score
SPR = "KXNFLSPREAD-" + EV + "-LAC3"
desc = "Los Angeles C wins by over 2.5 points"
ev = events(leg(SPR, desc, me=3, opp=3), leg(SPR, desc, me=3, opp=10))
ok("spread leg: names the team and the line, not 'points'",
   texts(ev) == ["Jets score against your Chargers (-2.5). Down 10–3 · Q2 13:34"], texts(ev))
ok("spread leg: still a bad-news alert", ev and ev[0]["good"] is False)
ev = events(leg(SPR, desc, me=3, opp=3), leg(SPR, desc, me=10, opp=3))
ok("spread leg: a score for you", texts(ev) == ["Score for your Chargers (-2.5)! Up 10–3 · Q2 13:34"], texts(ev))

# the other side of the same spread (NO): the score is already from the Jets' side (leg_score flips it)
ev = events(leg(SPR, "Not: " + desc, side="no", me=3, opp=3, abbr="NYJ", opp_abbr="LAC"),
            leg(SPR, "Not: " + desc, side="no", me=10, opp=3, abbr="NYJ", opp_abbr="LAC"))
ok("spread NO leg: the team it needs, with the plus line", texts(ev) == ["Score for your Jets (+2.5)! Up 10–3 · Q2 13:34"], texts(ev))

# ---- 2. a plain game-winner leg
WIN = "KXNFLGAME-" + EV + "-LAC"
ev = events(leg(WIN, "Los Angeles Chargers", opp_name="New York Jets", me=0, opp=0),
            leg(WIN, "Los Angeles Chargers", opp_name="New York Jets", me=0, opp=7))
ok("win leg: nickname for both teams", texts(ev) == ["Jets score against your Chargers. Down 7–0 · Q2 13:34"], texts(ev))

# ---- 3. totals: an Over and an Under, any score counts for the Over
TOT = "KXNFLTOTAL-" + EV + "-47"
ev = events(leg(TOT, "Over 47.5 points scored", me=3, opp=3), leg(TOT, "Over 47.5 points scored", me=3, opp=10))
ok("total Over leg: says the Over, never 'scored'",
   texts(ev) == ["Score! 13 total so far, your Over 47.5 (3–10) · Q2 13:34"], texts(ev))
ok("total Over leg: a score is good news", ev and ev[0]["good"] is True)
ev = events(leg(TOT, "Not: Over 47.5 points scored", side="no", me=3, opp=3),
            leg(TOT, "Not: Over 47.5 points scored", side="no", me=3, opp=10))
ok("total Under leg: says the Under", texts(ev) == ["Score! 13 total so far, your Under 47.5 (3–10) · Q2 13:34"], texts(ev))
ok("total Under leg: a score is bad news", ev and ev[0]["good"] is False)

# ---- 4. basketball lead changes: spread names the team and line; a total has no 'lead' to report
NSP = "KXNBASPREAD-26NOV22BOSLAL-LAL5"
nd = "Los Angeles L wins by over 5.5 points"
ev = events(leg(NSP, nd, sport="nba", me=48, opp=50, abbr="LAL", opp_abbr="BOS"),
            leg(NSP, nd, sport="nba", me=52, opp=50, abbr="LAL", opp_abbr="BOS"))
ok("NBA spread lead change: 'Your Lakers (-5.5) take the lead'",
   texts(ev) == ["Your Lakers (-5.5) take the lead 52–50 vs Celtics · Q2 13:34"], texts(ev))
NTO = "KXNBATOTAL-26NOV22BOSLAL-220"
ev = events(leg(NTO, "Over 220.5 points scored", sport="nba", me=48, opp=50, abbr="LAL", opp_abbr="BOS"),
            leg(NTO, "Over 220.5 points scored", sport="nba", me=52, opp=50, abbr="LAL", opp_abbr="BOS"))
ok("NBA total: no 'take the lead' alert", texts(ev) == [], texts(ev))

# ---- 5. swings say what the chance is for
ev = events(leg(SPR, desc, me=3, opp=3, ch=0.50), leg(SPR, desc, me=3, opp=3, ch=0.65))
ok("spread swing: 'Chargers (-2.5) up to 65% to cover'", texts(ev) == ["Chargers (-2.5) up to 65% to cover"], texts(ev))
ev = events(leg(TOT, "Over 47.5 points scored", ch=0.50), leg(TOT, "Over 47.5 points scored", ch=0.30))
ok("total swing: 'Over 47.5 down to 30% to hit'", texts(ev) == ["Over 47.5 down to 30% to hit"], texts(ev))
ev = events(leg(WIN, "Los Angeles Chargers", ch=0.50), leg(WIN, "Los Angeles Chargers", ch=0.70))
ok("win swing unchanged in shape", texts(ev) == ["Chargers up to 70% to win"], texts(ev))

# ---- 6. a single spread bet (name = team, label = description) and college names kept whole
single = dict(leg(SPR, "Los Angeles C", me=3, opp=3, opp_name="New York Jets"), label=desc, kind="spread")
ev = events(single, dict(single, sc=dict(single["sc"], opp=10)), single=True)
ok("single spread: 'your Chargers (-2.5)'", texts(ev) == ["Jets score against your Chargers (-2.5). Down 10–3 · Q2 13:34"], texts(ev))
CSP = "KXNCAAFSPREAD-26NOV22MSUMICH-MSU3"
cd = "Michigan State wins by over 3.5 points"
ev = events(leg(CSP, cd, sport="ncaaf", me=7, opp=7, abbr="MSU", opp_abbr="MICH", opp_name="Michigan"),
            leg(CSP, cd, sport="ncaaf", me=7, opp=14, abbr="MSU", opp_abbr="MICH", opp_name="Michigan"))
ok("college spread: 'Michigan State (-3.5)', never 'State' or 'points'",
   texts(ev) == ["Michigan score against your Michigan State (-3.5). Down 14–7 · Q2 13:34"], texts(ev))

# ---- 7. no alert text ever ends a team on a bet-description word
bad = re.compile(r"your (points|scored|goals|runs|total)\b", re.I)
allt = []
for lg_ in (leg(SPR, desc), leg(TOT, "Over 47.5 points scored"), leg(NSP, nd, sport="nba", abbr="LAL", opp_abbr="BOS")):
    allt.append(E.alert_pick(lg_)[1])
ok("alert_pick never returns a description word", not any(bad.search("your " + x) for x in allt), allt)
ok("alert_pick never raises on junk", E.alert_pick({"ticker": None, "sc": "x"}) == ("win", "pick", ""))

# ---- 8. text only: nothing that buys, sells or decides a pick's state reads the new helper
import inspect
src = open("wahome/engine.py").read()
uses = [m.start() for m in re.finditer(r"\balert_pick\(", src)]
rv = inspect.getsource(E.record_view)
ok("alert_pick is used only in record_view's alert text", len(uses) == 1 + rv.count("alert_pick("), (len(uses), rv.count("alert_pick(")))
ok("short_name (last word of a description) is gone", "short_name(" not in src)
