#!/usr/bin/env python3
"""
nfl_combo_planner.py - plan Kalshi NFL combos for a weekend slate.
Read-only: uses Kalshi's public market data (and, optionally, sportsbook odds
from the-odds-api.com). It never places a bet.

Pythonista on iPhone: tap Run, set the sliders and switches, tap Build.
Everything is remembered. No need to edit anything in this file.
"""
import csv, datetime as dt, html, itertools, json, math, os, random, re, statistics, sys
from collections import defaultdict
from urllib.parse import quote, unquote
import requests

SEED = None  # leave as is
VERSION = "2026.11.16.10"
UPDATE_URL = "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main"   # new versions (your GitHub repo)

# Starting values. The settings screen changes these for you and remembers them.
CFG = {
    "stake": 5, "budget": 100, "accept_pct": 80,
    "full_count": 3, "upsets_min": 3, "upsets_max": 4,
    "safer_count": 2,    "safer_min": 2,    "safer_max": 4,
    "middle_count": 3,   "middle_min": 4,   "middle_max": 7,
    "moonshot_count": 2, "moonshot_min": 8, "moonshot_max": 12,
    "thursday": False, "saturday": False, "monday": False,
    "skip_news": True, "odds_key": "", "kalshi_key_id": "",
    "max_share": 50,      # no pick in more than this % of safer/middle/moonshot combos
    "hedge_close": True,  # split coin-flip games between both sides across combos
    "include_live": True, # mid-day: allow games already in progress (with safety screens)
    "live_min": 25,       # a team in a game under way needs at least this % live chance to be picked
    "cash_pct": 90,       # suggest cashing out when Kalshi's offer is at least this % of what holding is worth
    "auto_cash": True,    # during game-day alerts, ask Kalshi for cash-out offers on combos worth checking
    "cash_every": 2,      # minutes between fresh cash-out offers for every live combo
    "refresh_secs": 15,   # seconds between live refreshes of scores, chances and your combos
    "bankroll": 500,      # money set aside for betting: bigger sure amounts vs this get favoured
    "next_day": False,    # college basketball: build tomorrow's games instead of today's
    "dogs_late": True,
    "dark": True,         # dark pages
    "tp_mult": 3,         # auto-sell (take-profit) orders sell at this many times what you paid
    "tp_auto": False,     # put an auto-sell order on every combo bought from the planner    # underdog picks go in the latest games, favourites in the earliest
    "picks": {},   # game -> team ticker to lock, or "skip"
}
DEFAULTS = json.loads(json.dumps(CFG))
TIERS = ["safer", "middle", "moonshot"]
NEWS_GAP = 0.06   # Kalshi vs sportsbooks this far apart = probably breaking news

SCRIPT_PATH = os.path.abspath(__file__)   # recorded now: Pythonista clears __file__ once the script's main part ends
HERE = os.path.dirname(SCRIPT_PATH)
# Updates are saved here, never over the file you tap (Pythonista can crash on start if the
# file it has open was replaced). The file you tap runs this one whenever it's newer.
ENGINE = os.path.join(HERE, "combo_planner_engine.py")
SAVED = os.path.join(HERE, "combo_settings.json")
LATEST = os.path.join(HERE, "combos_latest.html")
HISTORY = os.path.join(HERE, "combo_history.json")
LEAGUE_FILE = os.path.join(HERE, "combo_league.json")
MAIN_SAVED = SAVED
KEYS_SAVED = os.path.join(HERE, "combo_keys.json")   # Key ID and sportsbook key, kept apart

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXNFLGAME"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAC": "Jacksonville Jaguars",
    "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs", "LV": "Las Vegas Raiders",
    "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams", "LAR": "Los Angeles Rams",
    "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings", "NE": "New England Patriots",
    "NO": "New Orleans Saints", "NYG": "New York Giants", "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SF": "San Francisco 49ers",
    "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders", "WSH": "Washington Commanders",
}
DAY_ORDER = ["Thursday", "Friday", "Saturday", "Sunday", "Monday", "Today", "Tomorrow"]
NFL_TEAMS = TEAMS
NBA_TEAMS = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "BRK": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHO": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons", "GSW": "Golden State Warriors",
    "GS": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers", "LAC": "Los Angeles Clippers",
    "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat", "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans", "NO": "New Orleans Pelicans",
    "NYK": "New York Knicks", "NY": "New York Knicks", "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns", "PHO": "Phoenix Suns", "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "SA": "San Antonio Spurs", "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz", "UTAH": "Utah Jazz", "WAS": "Washington Wizards", "WSH": "Washington Wizards",
}

LEAGUES = {
    "nfl": {"name": "NFL", "short": "NFL", "icon": "🏈", "series": "KXNFLGAME", "odds": "americanfootball_nfl", "full": True, "teams": "nfl",
            "espn": "football/nfl", "espn_q": {}, "slate": "week", "game_hours": 3.5, "periods": 4,
            "settings": "combo_settings.json", "latest": "combos_latest.html", "defaults": {}},
    "nba": {"name": "NBA", "short": "NBA", "icon": "🏀", "series": "KXNBAGAME", "odds": "basketball_nba",
            "espn": "basketball/nba", "espn_q": {}, "slate": "day", "game_hours": 2.5, "periods": 4,
            "full": True, "teams": "nba",
            "settings": "combo_settings_nba.json", "latest": "combos_latest_nba.html",
            "defaults": {"budget": 50, "full_count": 2, "upsets_min": 1, "upsets_max": 2,
                         "safer_count": 3, "safer_min": 2, "safer_max": 3,
                         "middle_count": 3, "middle_min": 3, "middle_max": 5,
                         "moonshot_count": 2, "moonshot_min": 5, "moonshot_max": 7}},
}
LEAGUE = {"code": "nfl"}
SHARED_KEYS = ("kalshi_key_id", "odds_key", "bankroll", "auto_cash", "cash_every")


def next_league():
    """The league the bar's switch button goes to (NFL <-> NBA)."""
    order = list(LEAGUES)
    return order[(order.index(LEAGUE["code"]) + 1) % len(order)]


def LG():
    return LEAGUES[LEAGUE["code"]]


def by_day():
    """True for daily slates (college basketball), False for the NFL's Thursday-Monday week."""
    return LG()["slate"] == "day"


def slate_word():
    return "day" if by_day() else "weekend"


def day_on():
    """Which day labels are switched on."""
    return {"Sunday": True, "Thursday": CFG["thursday"], "Friday": CFG["thursday"],
            "Saturday": CFG["saturday"], "Monday": CFG["monday"], "Today": True, "Tomorrow": True}


def day_tag(d):
    return "" if d in ("Today", "Tomorrow") else d[:3]
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
PACIFIC = dt.timezone(dt.timedelta(hours=-8))
TYPE_NAMES = {"full": "Full slate", "safer": "Safer", "middle": "Middle", "moonshot": "Moonshot",
              "own": "Your own combos"}


# ================================================================ files
def set_league(code):
    """Point the planner at a league: its Kalshi games, odds, scores, and its own settings."""
    global SERIES, ODDS_URL, SCORES_URL, SAVED, LATEST, TEAMS
    code = code if code in LEAGUES else "nfl"
    changed = code != LEAGUE["code"]
    LEAGUE["code"] = code
    lg = LEAGUES[code]
    SERIES = lg["series"]
    ODDS_URL = f"https://api.the-odds-api.com/v4/sports/{lg['odds']}/odds"
    SCORES_URL = f"https://site.api.espn.com/apis/site/v2/sports/{lg['espn']}/scoreboard"
    SAVED = os.path.join(HERE, lg["settings"])
    LATEST = os.path.join(HERE, lg["latest"])
    TEAMS = {"nfl": NFL_TEAMS, "nba": NBA_TEAMS}.get(lg.get("teams"), {})
    if changed:
        CFG.clear()
        CFG.update(json.loads(json.dumps(DEFAULTS)))
        CFG.update(lg["defaults"])
        SCORES["at"] = 0
        ACCT_CACHE["at"] = 0
        CTX.clear()
        MINE["live"] = False
    CFG.update({k: v for k, v in load_json(SAVED, {}).items() if k in CFG})
    if SAVED != MAIN_SAVED:                      # keys and bankroll are shared by every league
        main = load_json(MAIN_SAVED, {})
        CFG.update({k: main[k] for k in SHARED_KEYS if k in main})
    keys = load_json(KEYS_SAVED, {})             # a saved key is never lost to a blank
    for k in KEY_FIELDS:
        if not str(CFG.get(k, "")).strip() and keys.get(k):
            CFG[k] = keys[k]
    if any(str(CFG.get(k, "")).strip() and not keys.get(k) for k in KEY_FIELDS):
        save_json(KEYS_SAVED, dict(keys, **{k: CFG[k].strip() for k in KEY_FIELDS if str(CFG.get(k, "")).strip()}))


KEY_FIELDS = ("kalshi_key_id", "odds_key")


def save_cfg(cleared=()):
    """Save settings. Your Kalshi Key ID and sportsbook key are also kept in their own small
    file, and a blank never overwrites them unless you cleared them yourself in Settings."""
    keys = load_json(KEYS_SAVED, {})
    for k in KEY_FIELDS:
        v = str(CFG.get(k, "")).strip()
        if v:
            keys[k] = v
        elif k in cleared:
            keys.pop(k, None)
        elif keys.get(k):
            CFG[k] = keys[k]
    save_json(KEYS_SAVED, keys)
    save_json(SAVED, CFG)
    if SAVED != MAIN_SAVED:
        main = load_json(MAIN_SAVED, {})
        main.update({k: CFG[k] for k in SHARED_KEYS})
        save_json(MAIN_SAVED, main)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def money(x):
    return f"${x:,.0f}" if abs(x) >= 10 else f"${x:,.2f}".replace(".00", "")


# ================================================================ Kalshi
def price(m):
    """Yes ask (what a pick costs) as a probability from 0 to 1."""
    if m.get("yes_ask_dollars"):
        return float(m["yes_ask_dollars"])
    if m.get("yes_ask"):
        return m["yes_ask"] / 100
    return None


def live_bid(m):
    """Best price someone will pay for YES right now (0-1), or None."""
    if m.get("yes_bid_dollars") not in (None, ""):
        return float(m["yes_bid_dollars"])
    if m.get("yes_bid") not in (None, ""):
        return m["yes_bid"] / 100
    return None


LIVE_SPREAD = 0.06    # buy/sell gap above 6c = thin, jumpy in-game market
LIVE_DECIDED = 0.95   # favourite at 95%+ live = nearly decided
LIVE_DISAGREE = 0.08  # Kalshi live vs live sportsbook odds 8+ points apart


def screen_live(all_games, book_fair):
    """Mid-day mode. For games already under way: use Kalshi's live chance, and
    return {game: reason} for live games that are bad bets right now."""
    skip, live = {}, set()
    for e, sides in all_games.items():
        if not any(started(x) for x in sides):
            continue
        live.add(e)
        if not CFG["include_live"]:
            skip[e] = "In progress. Games under way are switched off in Settings."
            continue
        if any(x.get("bid") is None for x in sides):
            skip[e] = "In progress, but Kalshi has no live buyers right now."
            continue
        gap = max(x["p"] - x["bid"] for x in sides)
        if gap > LIVE_SPREAD:
            skip[e] = f"In progress, and the live price is jumpy ({gap * 100:.0f}¢ between buy and sell)."
            continue
        mids = [(x["p"] + x["bid"]) / 2 for x in sides]
        tot = sum(mids)
        live_fair = [m / tot for m in mids]
        if max(live_fair) >= LIVE_DECIDED:
            lead = sides[live_fair.index(max(live_fair))]["pick"]
            skip[e] = (f"In progress and nearly decided ({lead} {max(live_fair):.0%} live). "
                       "Adds almost nothing to a payout but can still flip.")
            continue
        books = book_fair.get(e)
        if books and CFG["skip_news"]:
            diff = max(abs(b - lf) for b, lf in zip(books, live_fair))
            if diff >= LIVE_DISAGREE:
                skip[e] = (f"In progress, and Kalshi's live price disagrees with live sportsbook odds by "
                           f"{diff:.0%}. One of them hasn't caught up.")
                continue
        for x, lf in zip(sides, live_fair):
            x["fair"], x["edge"], x["live"] = lf, None, True
    return skip, live


def fetch_markets():
    out, cursor = [], None
    while True:
        params = {"series_ticker": SERIES, "status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{KALSHI}/markets", params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        out += data.get("markets", [])
        cursor = data.get("cursor")
        if not cursor:
            return out


def game_date(m):
    hit = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", m.get("event_ticker", ""))
    if hit and hit.group(2) in MONTHS:
        try:
            return dt.date(2000 + int(hit.group(1)), MONTHS[hit.group(2)], int(hit.group(3)))
        except ValueError:
            pass
    exp = m.get("expected_expiration_time") or m.get("close_time", "")
    try:
        return dt.datetime.fromisoformat(exp.replace("Z", "+00:00")).astimezone(PACIFIC).date()
    except ValueError:
        return None


PICK_NAME = {}   # market ticker -> team name as Kalshi shows it
GAME_EXP = {}    # game -> when Kalshi expects it to settle


def start_dt(event):
    """When a game starts: the sportsbook's kickoff time, else an estimate from Kalshi's
    expected settle time. None if unknown."""
    kick = KICKOFF.get(event)
    try:
        if kick:
            return dt.datetime.fromisoformat(kick.replace("Z", "+00:00"))
        if GAME_EXP.get(event):
            return (dt.datetime.fromisoformat(GAME_EXP[event].replace("Z", "+00:00"))
                    - dt.timedelta(hours=LG()["game_hours"]))
    except ValueError:
        pass
    return None


def start_label(event):
    t = start_dt(event)
    if not t:
        return ""
    t = t.astimezone()
    today = dt.datetime.now().astimezone().date()
    if t.date() == today:
        return t.strftime("%-I:%M %p")
    if 0 < (t.date() - today).days < 7:
        return t.strftime("%a %-I:%M %p")
    return t.strftime("%b %-d %-I:%M %p")


def start_key(event):
    t = start_dt(event)
    return t.timestamp() if t else 9e12


def week_games(markets, loose=False):
    """This NFL week's games (Thu-Mon around the coming Sunday), or for daily leagues today's
    (or tomorrow's) games, keyed by game. Returns (games, day label per game, slate date).
    loose=True keeps near-certain prices (games nearly over) for live updates."""
    today = dt.date.today()
    if by_day():
        sunday = today + dt.timedelta(days=1 if CFG.get("next_day") else 0)
        day_of = {sunday: "Tomorrow" if CFG.get("next_day") else "Today"}
    else:
        sunday = today + dt.timedelta(days=(6 - today.weekday()) % 7)
        day_of = {sunday + dt.timedelta(days=d): n for d, n in zip(range(-3, 2), DAY_ORDER)}
    games, days = defaultdict(list), {}
    for m in markets:
        p = price(m)
        lo, hi = (0.001, 0.999) if loose else (0.02, 0.98)
        if not p or not lo <= p <= hi:
            continue
        day = day_of.get(game_date(m))
        if day:
            PICK_NAME[m["ticker"]] = m.get("yes_sub_title") or m["ticker"]
            if m.get("expected_expiration_time"):
                GAME_EXP[m["event_ticker"]] = m["expected_expiration_time"]
            days[m["event_ticker"]] = day
            games[m["event_ticker"]].append({
                "event": m["event_ticker"], "ticker": m["ticker"],
                "abbr": m["ticker"].rsplit("-", 1)[-1].upper(),
                "pick": m.get("yes_sub_title") or m["ticker"], "p": p,
                "bid": live_bid(m), "exp": m.get("expected_expiration_time") or ""})
    games = {e: s for e, s in games.items() if len(s) == 2}
    order = sorted(games, key=lambda e: (DAY_ORDER.index(days[e]), games[e][0]["exp"]))
    return {e: games[e] for e in order}, {e: days[e] for e in order}, sunday


MARKET_INFO = {}   # ticker -> {status, exp, live}: filled while looking up results


def pick_state(leg, side_of):
    """'pre' (not started), 'live' (in progress), 'over' (ended, not paid out yet)."""
    info = MARKET_INFO.get(leg["ticker"]) or {}
    if info.get("status") in ("closed", "determined"):
        return "over"
    event = (leg.get("event") or (leg["ticker"] or "").rsplit("-", 1)[0])
    side = side_of.get(leg["ticker"]) or {"event": event, "exp": info.get("exp", "")}
    return "live" if started(side) else "pre"


def live_price(m):
    """Kalshi's current chance for a pick: middle of bid/ask, else last trade."""
    def d(name):
        v = m.get(name + "_dollars")
        if v not in (None, ""):
            return float(v)
        v = m.get(name)
        return float(v) / 100 if v not in (None, "") else None
    bid, ask, last = d("yes_bid"), d("yes_ask"), d("last_price")
    if bid is not None and ask is not None and 0 < ask and ask - bid <= 0.2:
        return (bid + ask) / 2
    return last if last else None


def fetch_results(tickers):
    """{ticker: 'yes'/'no'} for picks Kalshi has settled. Quietly skips failures."""
    out, seen, tickers = {}, set(), list(tickers)

    def take(m):
        if not m:
            return
        seen.add(m.get("ticker"))
        sub, title = (m.get("yes_sub_title") or "").strip(), (m.get("title") or "").strip()
        MARKET_INFO[m.get("ticker")] = {"status": (m.get("status") or "").lower(),
                                        "exp": m.get("expected_expiration_time") or "",
                                        "live": live_price(m),
                                        "name": sub if len(sub) > 3 and not sub.replace(".", "").isdigit() else (title or sub)}
        if m.get("result") in ("yes", "no"):
            out[m["ticker"]] = m["result"]

    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        try:
            r = requests.get(f"{KALSHI}/markets", params={"tickers": ",".join(chunk)}, timeout=20)
            r.raise_for_status()
            for m in r.json().get("markets", []):
                take(m)
        except (requests.RequestException, ValueError):
            pass
    missing = [t for t in tickers if t not in seen]   # not returned at all: maybe archived
    if len(missing) > 40:
        missing = missing[:40]
    for t in missing:
        if t in out:
            continue
        for url in (f"{KALSHI}/markets/{t}", f"{KALSHI}/historical/markets/{t}"):
            try:
                r = requests.get(url, timeout=15)
                if r.ok:
                    take(r.json().get("market"))
            except (requests.RequestException, ValueError):
                pass
            if t in out:
                break
    return out


# ================================================================ sportsbooks
TEAM_KICKOFF = {}   # full team name -> kickoff time, from the sportsbook feed
KICKOFF = {}        # Kalshi game -> kickoff time


def fetch_book_odds(key):
    """{full team name: (fair win chance, source)} plus a note for the report."""
    try:
        r = requests.get(ODDS_URL, timeout=20, params={
            "apiKey": key, "regions": "us,eu", "markets": "h2h", "oddsFormat": "decimal"})
    except requests.RequestException:
        return {}, "Couldn't reach the sportsbook service, so chances use Kalshi's prices."
    if r.status_code == 401:
        return {}, "Your sportsbook key wasn't accepted. Check it on the settings screen."
    if r.status_code == 429:
        return {}, "Sportsbook service is out of free credits this month. Using Kalshi's prices."
    if not r.ok:
        return {}, f"Sportsbook service error ({r.status_code}). Using Kalshi's prices."
    fair = {}
    for ev in r.json():
        if ev.get("home_team") and ev.get("away_team"):
            BOOK_OPP[ev["home_team"]] = ev["away_team"]
            BOOK_OPP[ev["away_team"]] = ev["home_team"]
        if ev.get("commence_time"):
            for team in (ev.get("home_team"), ev.get("away_team")):
                if team:
                    TEAM_KICKOFF[team] = ev["commence_time"]
        books, pinnacle = defaultdict(list), {}
        for b in ev.get("bookmakers", []):
            for mk in b.get("markets", []):
                outs = mk.get("outcomes", [])
                if mk.get("key") != "h2h" or len(outs) != 2:
                    continue
                inv = [1 / o["price"] for o in outs]
                for o, i in zip(outs, inv):
                    p = i / sum(inv)
                    books[o["name"]].append(p)
                    if b.get("key") == "pinnacle":
                        pinnacle[o["name"]] = p
        for team, ps in books.items():
            fair[team] = (pinnacle[team], "Pinnacle") if team in pinnacle \
                else (statistics.median(ps), f"{len(ps)} books")
    left = r.headers.get("x-requests-remaining")
    note = "Chances and fair payouts use sportsbook lines (Pinnacle when available)."
    if left:
        note += f" {left} free credits left this month."
    return fair, note


BOOK_OPP = {}   # sportsbook team name -> its opponent


def norm_team(x):
    x = (x or "").lower().replace("&", " and ")
    x = re.sub(r"\bst\b\.?", "state", x)
    x = re.sub(r"[^a-z0-9 ]", "", x)
    return " ".join(x.split())


def match_book(pick, book):
    """The sportsbook's full name for a Kalshi team name ('Kansas' -> 'Kansas Jayhawks',
    not 'Kansas State Wildcats'): same start, shortest nickname."""
    p = norm_team(pick)
    best = None
    for t in book:
        n = norm_team(t)
        if n == p:
            return t
        if n.startswith(p + " "):
            cand = (len(n[len(p) + 1:].split()), t)
            best = min(best, cand) if best else cand
    return best[1] if best else None


def attach_fair(games, book):
    """Give every side a fair win chance, its edge vs Kalshi, and a news gap."""
    matched, news = 0, {}
    for e, sides in games.items():
        kal = [s["p"] / sum(x["p"] for x in sides) for s in sides]
        names = []
        for s in sides:
            full = TEAMS.get(s["abbr"])
            if full not in book:
                full = match_book(full or s["pick"], book) or match_book(s["pick"], book)
            names.append(full if full in book else None)
        if not TEAMS and all(names) and BOOK_OPP.get(names[0]) != names[1]:
            names = [None, None]                  # not the same game: use Kalshi's prices
        kick = next((TEAM_KICKOFF[n] for n in names if n in TEAM_KICKOFF), None)
        if kick:
            KICKOFF[e] = kick
        if all(names):
            raw = [book[n][0] for n in names]
            src = book[names[0]][1]
            matched += 1
        else:
            raw, src = kal, None
        for s, r, k in zip(sides, raw, kal):
            s["fair"] = r / sum(raw)
            s["src"] = src
            s["edge"] = s["fair"] - s["p"] if src else None
        news[e] = max(abs(s["fair"] - k) for s, k in zip(sides, kal)) if src else 0
    return matched, news


# ================================================================ combos
def fav(sides):
    return max(sides, key=lambda s: s["fair"])


def dog(sides):
    return min(sides, key=lambda s: s["fair"])


def weight(s, usage):
    """Likelier picks, Kalshi bargains, and picks not used much yet score higher."""
    edge = max(-0.1, min(0.1, s["edge"] or 0))
    return max(0.01, s["fair"] ** 2 * (1 + 8 * edge)) / (1 + usage[s["ticker"]])


def pickable(side):
    """Teams in games under way need a real chance left (Kalshi's live price reflects
    the score and the clock). Teams in games not started yet are always pickable."""
    return not side.get("live") or side["fair"] >= CFG["live_min"] / 100


def underdog_sets(games, free, k, want):
    """The `want` most likely sets of k upsets among the unlocked games.
    Only one exact result happens on Sunday, so full-slate combos can never
    both hit: picking the likeliest distinct outcomes maximises the chance
    that one of them does."""
    free = [e for e in free if pickable(dog(games[e]))]   # no long-shot live underdogs
    if CFG.get("dogs_late") and len(free) > 2 * k:
        # underdogs in the later games: the early ones decide first, so you can cash out before the risky ones
        free = sorted(free, key=start_key)[-max(2 * k, len(free) // 2):]
    k = min(k, len(free))
    ratio = {e: dog(games[e])["fair"] / fav(games[e])["fair"] for e in free}
    score = lambda c: math.prod(ratio[e] for e in c)
    if math.comb(len(free), k) <= 60000:
        pool = itertools.combinations(free, k)
    else:
        rng = random.Random(1)
        pool = {tuple(sorted(rng.choices(free, weights=[ratio[e] for e in free], k=k)))
                for _ in range(20000)}
        pool = [c for c in pool if len(set(c)) == k]
    import heapq
    return heapq.nlargest(want, pool, key=score)


CLOSE_GAME = 0.58   # favourite under 58% = close to a coin flip


def share_limit(n_partial):
    """Most safer/middle/moonshot combos any one pick may appear in."""
    if CFG["max_share"] >= 100 or n_partial <= 1:
        return 10 ** 6
    return max(1, math.ceil(CFG["max_share"] / 100 * n_partial))


def pick_partial(games, free, locked, size, rng, usage, limit):
    """One combo: your locked picks plus games chosen to spread risk.
    - a pick already at the limit can't be used again (the other side still can)
    - games used less so far are more likely to be chosen
    - close games go to whichever side has been used less (hedging)"""
    eligible = [e for e in free if any(usage[s["ticker"]] < limit and pickable(s) for s in games[e])]
    extra = max(0, min(size - len(locked), len(eligible)))
    if len(locked) + extra < 2:
        return None
    gw = {e: 1 / (1 + sum(usage[s["ticker"]] for s in games[e])) for e in eligible}
    chosen, pool = [], list(eligible)
    for _ in range(extra):
        e = rng.choices(pool, weights=[gw[x] for x in pool])[0]
        pool.remove(e)
        chosen.append(e)
    legs = list(locked)
    late = set()
    if CFG.get("dogs_late") and chosen:
        by_time = sorted(chosen, key=start_key)
        late = set(by_time[-max(1, len(by_time) // 3):])     # the last third may be underdogs
    for e in chosen:
        opts = [x for x in games[e] if usage[x["ticker"]] < limit and pickable(x)]
        if e not in late and CFG.get("dogs_late") and fav(games[e])["fair"] >= CLOSE_GAME:
            f = fav(games[e])
            if f in opts:
                legs.append(f)                    # early games: take the favourite
            continue                              # favourite used up: leave this game out, no early underdog
        if CFG["hedge_close"] and len(opts) == 2 and fav(games[e])["fair"] < CLOSE_GAME \
                and usage[opts[0]["ticker"]] != usage[opts[1]["ticker"]]:
            legs.append(min(opts, key=lambda x: usage[x["ticker"]]))
        else:
            legs.append(rng.choices(opts, weights=[weight(x, usage) for x in opts])[0])
    return legs


def build_combos(games, locks, rng):
    stake = CFG["stake"]
    max_bets = int(CFG["budget"] // stake)
    plan = [("full", CFG["full_count"])] + [(t, CFG[f"{t}_count"]) for t in TIERS]
    combos, seen, usage = [], set(), defaultdict(int)     # usage: safer/middle/moonshot only
    free = [e for e in games if e not in locks]
    locked_legs = [next(s for s in games[e] if s["ticker"] == t) for e, t in locks.items()]
    n_partial = max(0, min(sum(n for _, n in plan[1:]), max_bets - min(CFG["full_count"], max_bets)))
    limit = share_limit(n_partial)

    def add(kind, label, legs):
        key = frozenset(l["ticker"] for l in legs)
        if key in seen or len(combos) >= max_bets or not legs:
            return False
        seen.add(key)
        if kind != "full":
            for l in legs:
                if l["event"] not in locks:
                    usage[l["ticker"]] += 1
        fair_pay = stake / math.prod(l["fair"] for l in legs)
        combos.append({"kind": kind, "tier": label, "legs": legs, "fair": fair_pay,
                       "min": fair_pay * CFG["accept_pct"] / 100,
                       "kalshi": stake / math.prod(l["p"] for l in legs)})
        return True

    # Full slate: likeliest distinct underdog sets, sized by the settings.
    cycle = list(range(CFG["upsets_min"], CFG["upsets_max"] + 1))
    want = defaultdict(int)
    for i in range(CFG["full_count"]):
        want[cycle[i % len(cycle)]] += 1
    ranked = {k: underdog_sets(games, free, k, n + 3) for k, n in want.items()}
    for i in range(CFG["full_count"]):
        k = cycle[i % len(cycle)]
        while ranked[k]:
            upsets = set(ranked[k].pop(0))
            legs = locked_legs + [dog(games[e]) if e in upsets else fav(games[e]) for e in free]
            n = sum(l["fair"] < 0.5 for l in legs)
            if add("full", f"Full slate · {n} underdog{'s' * (n != 1)}", legs):
                break

    # Other tiers: every locked pick plus random games, leaning to bargains.
    for tier, count in plan[1:]:
        made, tries = 0, 0
        while made < count and tries < 500 and len(combos) < max_bets:
            tries += 1
            size = rng.randint(CFG[f"{tier}_min"], CFG[f"{tier}_max"])
            legs = pick_partial(games, free, locked_legs, size, rng, usage, limit)
            if legs is None:
                break                                  # limit reached: nothing new fits
            made += add(tier, tier.capitalize(), legs)
    trimmed = sum(n for _, n in plan) > max_bets
    return combos, trimmed


def simulate(combos, games, trials=20000, seed=1):
    rng = random.Random(seed)
    any_hit, each = 0, [0] * len(combos)
    for _ in range(trials):
        won = {(s[0] if rng.random() < s[0]["fair"] else s[1])["ticker"] for s in games.values()}
        hit = False
        for i, c in enumerate(combos):
            if all(l["ticker"] in won for l in c["legs"]):
                each[i] += 1
                hit = True
        any_hit += hit
    return any_hit / trials, [h / trials for h in each]


def clean_cfg(n_games):
    pairs = [("upsets_min", "upsets_max")] + [(f"{t}_min", f"{t}_max") for t in TIERS]
    for lo, hi in pairs:
        if CFG[lo] > CFG[hi]:
            CFG[lo], CFG[hi] = CFG[hi], CFG[lo]
        CFG[hi] = min(CFG[hi], n_games)
        CFG[lo] = min(CFG[lo], CFG[hi])


# ================================================================ Kalshi account (optional, read-only)
KEYFILE = os.path.join(HERE, "kalshi_private_key.pem")
LEGS_CACHE = os.path.join(HERE, "combo_legs_cache.json")


def _der(data, i):
    """Read one DER item at i: returns (tag, value bytes, next index)."""
    tag, ln = data[i], data[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(data[i:i + n], "big")
        i += n
    return tag, data[i:i + ln], i + ln


def _der_seq(data):
    out, i = [], 0
    while i < len(data):
        tag, val, i = _der(data, i)
        out.append((tag, val))
    return out


def pem_body(pem):
    """Just the base64 part of a pasted key, even if iOS turned the dashes
    into long dashes, the lines got joined, or stray spaces crept in."""
    text = pem.replace("\u2014", "-").replace("\u2013", "-").replace("\u2012", "-")
    text = re.sub(r"[-\s]*(BEGIN|END)[A-Z ]*?PRIVATE KEY[-\s]*", " ", text)
    return re.sub(r"[^A-Za-z0-9+/=]", "", text)


ED25519_OID = bytes.fromhex("2b6570")          # 1.3.101.112
RSA_OID = bytes.fromhex("2a864886f70d010101")   # 1.2.840.113549.1.1.1


def load_private_key(pem):
    """Kalshi private key (RSA or Ed25519, PEM) -> key dict. Raises ValueError."""
    import base64
    if "ENCRYPTED" in pem.upper():
        raise ValueError("That key is password-protected. Kalshi's keys aren't, so this "
                         "may be a different file.")
    if "OPENSSH" in pem.upper() or "EC PRIVATE" in pem.upper():
        raise ValueError("That's not a Kalshi key. Use the private key Kalshi gave you.")
    body = pem_body(pem)
    body += "=" * (-len(body) % 4)
    key = None
    try:
        der = base64.b64decode(body)
        _, val, _ = _der(der, 0)
        items = _der_seq(val)
        if items[1][0] == 0x30:                       # PKCS#8: check which algorithm
            oid = _der_seq(items[1][1])[0][1]
            if oid == ED25519_OID:
                _, seed, _ = _der(items[2][1], 0)     # OCTET STRING inside OCTET STRING
                if len(seed) == 32:
                    key = {"type": "ed25519", "seed": seed}
            elif oid == RSA_OID:
                _, inner, _ = _der(items[2][1], 0)
                items = _der_seq(inner)
                key = {"type": "rsa", "n": int.from_bytes(items[1][1], "big"),
                       "d": int.from_bytes(items[3][1], "big")}
        else:                                         # PKCS#1 RSA
            key = {"type": "rsa", "n": int.from_bytes(items[1][1], "big"),
                   "d": int.from_bytes(items[3][1], "big")}
    except Exception:
        key = None
    if key and key["type"] == "rsa" and key["n"] < 2 ** 1000:
        key = None
    if not key:
        if "PRIVATE KEY" not in pem.upper():
            raise ValueError("That doesn't look like a private key. Copy the whole key, "
                             "from -----BEGIN to -----END.")
        raise ValueError("The key text looks cut off or changed. Copy the whole key again, "
                         "from -----BEGIN to -----END.")
    return key


def describe_key(key):
    return "Ed25519 key" if key["type"] == "ed25519" else f"RSA key, {key['n'].bit_length()} bits"


def rsa_pss_sign(key, message):
    """RSA-PSS with SHA-256, salt length 32 (what Kalshi expects)."""
    import hashlib
    n, d = key["n"], key["d"]
    mod_bits = n.bit_length()
    em_len = (mod_bits - 1 + 7) // 8
    m_hash = hashlib.sha256(message).digest()
    salt = os.urandom(32)
    h = hashlib.sha256(b"\x00" * 8 + m_hash + salt).digest()
    db = b"\x00" * (em_len - 32 - 32 - 2) + b"\x01" + salt
    mask, c = b"", 0
    while len(mask) < len(db):
        mask += hashlib.sha256(h + c.to_bytes(4, "big")).digest()
        c += 1
    masked = bytearray(x ^ y for x, y in zip(db, mask))
    masked[0] &= 0xFF >> (8 * em_len - (mod_bits - 1))
    em = bytes(masked) + h + b"\xbc"
    sig = pow(int.from_bytes(em, "big"), d, n)
    return sig.to_bytes((mod_bits + 7) // 8, "big")


def ed25519_sign(seed, message):
    """Ed25519 signature (RFC 8032), plain Python."""
    import hashlib
    p = 2 ** 255 - 19
    q = 2 ** 252 + 27742317777372353535851937790883648493
    d = -121665 * pow(121666, p - 2, p) % p
    sqrt_m1 = pow(2, (p - 1) // 4, p)

    def add(P, Q):
        A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
        B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
        C = 2 * P[3] * Q[3] * d % p
        D = 2 * P[2] * Q[2] % p
        E, F, G, H = B - A, D - C, D + C, B + A
        return (E * F % p, G * H % p, F * G % p, E * H % p)

    def mul(k, P):
        Q = (0, 1, 1, 0)
        while k:
            if k & 1:
                Q = add(Q, P)
            P = add(P, P)
            k >>= 1
        return Q

    def compress(P):
        zi = pow(P[2], p - 2, p)
        x, y = P[0] * zi % p, P[1] * zi % p
        return (y | ((x & 1) << 255)).to_bytes(32, "little")

    gy = 4 * pow(5, p - 2, p) % p
    x2 = (gy * gy - 1) * pow(d * gy * gy + 1, p - 2, p) % p
    gx = pow(x2, (p + 3) // 8, p)
    if (gx * gx - x2) % p:
        gx = gx * sqrt_m1 % p
    if gx & 1:
        gx = p - gx
    G = (gx, gy, 1, gx * gy % p)

    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    A = compress(mul(a, G))
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % q
    R = compress(mul(r, G))
    k = int.from_bytes(hashlib.sha512(R + A + message).digest(), "little") % q
    return R + ((r + k * a) % q).to_bytes(32, "little")


def sign(key, message):
    return ed25519_sign(key["seed"], message) if key["type"] == "ed25519" else rsa_pss_sign(key, message)


def account_get(key, key_id, path, params=None):
    """Signed GET to Kalshi's account API. path like /portfolio/fills."""
    import base64, time
    full = "/trade-api/v2" + path
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(sign(key, (ts + "GET" + full).encode())).decode()
    r = requests.get(KALSHI + path, params=params or {}, timeout=20, headers={
        "KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sig})
    if r.status_code in (401, 403):
        raise PermissionError("Kalshi didn't accept your API key. Check the key ID and private key in settings.")
    r.raise_for_status()
    return r.json()


def all_positions(key, key_id):
    """Positions including ones you've closed (sold back to zero) but that haven't settled."""
    for params in ({"count_filter": "position,total_traded"}, None):
        try:
            return account_pages(key, key_id, "/portfolio/positions", "market_positions", params)
        except requests.RequestException:
            continue
    return []


def account_pages(key, key_id, path, field, params=None):
    out, cursor = [], None
    for _ in range(50):
        p = dict(params or {}, limit=200)
        if cursor:
            p["cursor"] = cursor
        data = account_get(key, key_id, path, p)
        out += data.get(field, [])
        cursor = data.get("cursor")
        if not cursor:
            break
    return out


def dollars(obj, *names):
    """Read a money field whether Kalshi sends dollars ('x_dollars') or cents ('x')."""
    for name in names:
        if obj.get(name + "_dollars") not in (None, ""):
            return float(obj[name + "_dollars"])
        v = obj.get(name)
        if v not in (None, ""):
            # Older fields are whole cents (20); newer ones are dollar strings ("0.20").
            return float(v) if isinstance(v, str) and "." in v else float(v) / 100
    return 0.0


def count_of(obj):
    for name in ("count_fp", "count"):
        if obj.get(name) not in (None, ""):
            return float(obj[name])
    return 0.0


def is_combo(ticker):
    """Kalshi combo markets all start with KXMVE (e.g. KXMVECROSSCATEGORY0-...)."""
    return bool(ticker) and ticker.upper().startswith("KXMVE")


def fetch_legs_parallel(tickers, cache):
    """Look up several combos' picks at once (only ones not already remembered)."""
    todo = [t for t in tickers if t not in cache]
    if not todo:
        return
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda t: combo_legs(t, cache), todo))


def combo_legs(ticker, cache):
    """The legs of a Kalshi combo market (public data, cached)."""
    if ticker not in cache:
        try:
            r = requests.get(f"{KALSHI}/markets/{ticker}", timeout=15)
            m = r.json().get("market", {}) if r.ok else {}
        except (requests.RequestException, ValueError):
            m = {}
        legs = m.get("mve_selected_legs")
        if legs is None:
            return None                         # couldn't tell; try again next time
        cache[ticker] = [{"ticker": l.get("market_ticker"), "event": l.get("event_ticker"),
                          "side": l.get("side", "yes")} for l in legs]
    return cache[ticker]


def combo_league(legs):
    """'nfl', 'ncaamb' or 'other' from the picks' market tickers."""
    ts = [(l["ticker"] or "").upper() for l in legs]
    if any(t.startswith("KXNCAAMB") for t in ts):
        return "ncaamb" if "ncaamb" in LEAGUES else "other"   # college was dropped: shown with NFL
    if any(t.startswith("KXNBA") for t in ts):
        return "nba"
    if any(t.startswith("KXNFL") for t in ts):
        return "nfl"
    return "other"


WINNER_SERIES = ("KXNFLGAME", "KXNCAAMBGAME", "KXNBAGAME")


def winners_only(legs):
    return all((l["ticker"] or "").startswith(WINNER_SERIES) for l in legs)


def week_of(ticker):
    d = game_date({"event_ticker": ticker})
    if not d:
        return None
    if (ticker or "").upper().startswith(("KXNCAAMB", "KXNBA")):
        return d                                  # daily leagues: the game's own day
    return d - dt.timedelta(days=1) if d.weekday() == 0 else d + dt.timedelta(days=(6 - d.weekday()) % 7)


ACCT_CACHE = {"at": 0, "value": None}


def in_week(a, week):
    """A combo belongs to every NFL week it has a game in (one can mix this week and next)."""
    if not week or not a.get("week"):
        return False
    return (a.get("first_week") or a["week"]) <= week <= a["week"]


def fetch_account(max_age=60):
    """Your NFL combo bets from Kalshi (cached for a minute). Returns (bets, balance, note)."""
    import time
    if ACCT_CACHE["value"] and time.time() - ACCT_CACHE["at"] < max_age:
        return ACCT_CACHE["value"]
    value = _fetch_account()
    if value[0] is not None:
        ACCT_CACHE.update(at=time.time(), value=value)
    return value


def _fetch_account():
    key_id = CFG.get("kalshi_key_id", "").strip()
    if not key_id or not os.path.exists(KEYFILE):
        return None, None, None
    try:
        with open(KEYFILE, encoding="utf-8") as f:
            key = load_private_key(f.read())
        fills = account_pages(key, key_id, "/portfolio/fills", "fills",
                              {"min_ts": int((dt.datetime.now() - dt.timedelta(days=200)).timestamp())})
        settles = account_pages(key, key_id, "/portfolio/settlements", "settlements")
        positions = all_positions(key, key_id)
        bal = account_get(key, key_id, "/portfolio/balance")
    except (ValueError, PermissionError) as err:
        return None, None, str(err)
    except (requests.RequestException, OSError):
        return None, None, "Couldn't reach your Kalshi account just now. Showing what's saved."

    held = defaultdict(lambda: {"cost": 0.0, "contracts": 0.0, "fees": 0.0, "sold": 0.0, "sold_n": 0.0,
                                "bought_n": 0.0, "first": None})
    for f in fills:
        t = f.get("ticker") or f.get("market_ticker")
        if not is_combo(t):
            continue                             # single bets (any sport) aren't combos
        side = f.get("side", "yes")
        n = count_of(f)
        # Combos are only ever bought on the YES side, so only "buy yes" adds to what you hold.
        # Any sell ("sell yes", or "sell no" as Kalshi reports app cash-outs) or a "buy no"
        # takes contracts away, at the YES price.
        no_px = dollars(f, "no_price")
        yes_px = dollars(f, "yes_price") or (1 - no_px if no_px else 0.0) or dollars(f, "price")
        buying_yes = f.get("action") != "sell" and side != "no"
        if buying_yes:
            held[t]["cost"] += n * yes_px
            held[t]["contracts"] += n
            held[t]["bought_n"] += n
        else:
            held[t]["sold"] += n * yes_px
            held[t]["sold_n"] += n
            held[t]["contracts"] -= n
        held[t]["fees"] += dollars(f, "fee_cost")
        when = str(f.get("created_time") or "")[:10]
        if when and (not held[t]["first"] or when < held[t]["first"]):
            held[t]["first"] = when
    pos_by = {(p.get("ticker") or p.get("market_ticker")): p for p in positions}
    for p in positions:                          # combos the fills list missed
        t = p.get("ticker") or p.get("market_ticker")
        if not is_combo(t) or t in held:
            continue
        n = abs(float(p.get("position_fp") or p.get("position") or 0))
        if n:
            held[t]["contracts"] = n
            held[t]["cost"] = dollars(p, "market_exposure") or dollars(p, "total_traded")
            held[t]["fees"] = dollars(p, "fees_paid")
    settled = {s.get("ticker"): s for s in settles}
    for t, s in settled.items():                 # settled combos no longer in fills/positions
        if is_combo(t) and t not in held:
            held[t]["contracts"] = count_of({"count": s.get("yes_count") or s.get("no_count")})
            held[t]["cost"] = dollars(s, "yes_total_cost") + dollars(s, "no_total_cost")

    cache = load_json(LEGS_CACHE, {})
    fetch_legs_parallel(list(held), cache)
    bets = []
    for t, h in held.items():
        legs = combo_legs(t, cache)
        if not legs:
            continue
        lg = combo_league(legs)
        if lg != LEAGUE["code"] and not (lg == "other" and LEAGUE["code"] == "nfl"):
            continue                             # another league's combo (shown there)
        s = settled.get(t)
        status, back = "pending", h["sold"]
        pos = pos_by.get(t)
        now_held = None
        if pos is not None:
            now_held = abs(float(pos.get("position_fp") or pos.get("position") or 0))
        if h["sold_n"] and h["contracts"] <= 0.005:
            status = "cashed"                    # sold before it finished
        elif not s and now_held is not None and now_held <= 0.005 and h["contracts"] > 0.005:
            # Kalshi says you hold none of it any more, but no payout yet: you cashed out
            status = "cashed"
            realized = dollars(pos, "realized_pnl")
            back = max(0.0, h["cost"] + realized) if (pos.get("realized_pnl_dollars") or pos.get("realized_pnl")) else 0.0
            h["contracts"] = 0.0
        elif s:
            back += dollars(s, "revenue")
            status = "won" if dollars(s, "revenue") > 0 else "lost"
        weeks = [w for w in (week_of(l["ticker"] or "") for l in legs) if w]
        if not weeks and h["first"]:              # no dates in its picks: use when you bought it
            try:
                weeks = [week_of("X-" + dt.date.fromisoformat(h["first"]).strftime("%y%b%d").upper())]
            except ValueError:
                pass
        bets.append({"ticker": t, "legs": legs, "cost": round(h["cost"] + h["fees"], 2),
                     "pays": round(max(h["contracts"], 0), 2), "status": status, "back": round(back, 2),
                     "week": max(weeks).isoformat() if weeks else None,
                     "first_week": min(weeks).isoformat() if weeks else None,
                     "full_pays": round(h["bought_n"] or h["contracts"] or h["sold_n"], 2),
                     "winners": winners_only(legs)})
    save_json(LEGS_CACHE, cache)
    balance = dollars(bal, "balance")
    return bets, balance, f"From your Kalshi account · balance {money(balance)}"


KEY_ERROR = {"msg": None}


def save_private_key(pem):
    """Keep the private key in its own file on this phone (never in settings)."""
    try:
        load_private_key(pem)
    except ValueError as err:
        first = pem.strip().splitlines()[0][:40] if pem.strip() else ""
        if "BEGIN" not in first.upper():
            first = "(no BEGIN line)"
        KEY_ERROR["msg"] = (f"{err} (Pasted {len(pem)} characters on "
                            f"{len(pem.strip().splitlines())} line(s); first line starts: “{first}”)")
        console_note(KEY_ERROR["msg"])
        return False
    KEY_ERROR["msg"] = None
    body = pem_body(pem)
    kind = "RSA PRIVATE KEY" if "RSA PRIVATE" in pem.upper() else "PRIVATE KEY"
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    with open(KEYFILE, "w", encoding="utf-8") as f:
        f.write(f"-----BEGIN {kind}-----\n" + "\n".join(lines) + f"\n-----END {kind}-----\n")
    try:
        os.chmod(KEYFILE, 0o600)
    except OSError:
        pass
    return True


def import_key_file():
    """If there's no saved key, use a Kalshi key file put in this folder (e.g. via Files)."""
    if os.path.exists(KEYFILE):
        return
    for name in sorted(os.listdir(HERE)):
        if name.lower().endswith((".key", ".pem", ".txt")) and name != os.path.basename(KEYFILE):
            try:
                with open(os.path.join(HERE, name), encoding="utf-8", errors="ignore") as fh:
                    text = fh.read(20000)
            except OSError:
                continue
            if "PRIVATE KEY" in text and save_private_key(text):
                KEY_ERROR["msg"] = None
                return name


def leg_key(legs):
    """Same picks = same combo. A 'no' on one team is a 'yes' on the other."""
    return frozenset(l["ticker"] if l.get("side", "yes") == "yes" else "NO:" + l["ticker"] for l in legs)


def safe_delegate(cls):
    """Wrap a page's link handler so a mistake shows on the page, never the code."""
    inner = cls.webview_should_start_load

    def guarded(self, webview, url, nav_type):
        try:
            return inner(self, webview, url, nav_type)
        except Exception as err:
            try:
                webview.evaluate_javascript("document.body.insertAdjacentHTML('afterbegin', %s)" % json.dumps(
                    f"<div class='empty' style='margin:12px'>Something went wrong with that button: "
                    f"{html.escape(str(err)[:150])}. Close and tap Run to try again.</div>"))
            except Exception:
                pass
            return False
    cls.webview_should_start_load = guarded
    return cls


# ================================================================ pre-game chances
PREGAME = os.path.join(HERE, "pregame_chances.json")


def started(side):
    """Has this game kicked off? Uses the real kickoff time from the sportsbook feed
    when we have it; otherwise estimates it as 3.5 hours before Kalshi expects to settle."""
    now = dt.datetime.now(dt.timezone.utc)
    kick = KICKOFF.get(side.get("event") or "")
    if kick:
        try:
            return now >= dt.datetime.fromisoformat(kick.replace("Z", "+00:00"))
        except ValueError:
            pass
    try:
        end = dt.datetime.fromisoformat(side["exp"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return False
    return now >= end - dt.timedelta(hours=LG()["game_hours"])


def remember_pregame(all_games):
    """Save each pick's chance the first time we see it before kickoff."""
    saved = load_json(PREGAME, {})
    changed = False
    for sides in all_games.values():
        for s in sides:
            if s["ticker"] not in saved and s.get("fair") and not started(s):
                saved[s["ticker"]] = round(s["fair"], 4)
                changed = True
    if changed:
        # keep the file small: drop picks from games more than ~3 weeks old
        cutoff = dt.date.today() - dt.timedelta(days=21)
        saved = {t: v for t, v in saved.items() if (game_date({"event_ticker": t}) or cutoff) >= cutoff}
        save_json(PREGAME, saved)
    return saved


# ================================================================ record
def settle(history):
    """Look up results for any placed combo that isn't decided yet."""
    need = set()
    for b in history["builds"]:
        for i in b.get("placed", []):
            for l in b["combos"][i - 1]["legs"]:
                if l["ticker"] not in b["results"]:
                    need.add(l["ticker"])
    if not need:
        return False
    got = fetch_results(need)
    for b in history["builds"]:
        for i in b.get("placed", []):
            for l in b["combos"][i - 1]["legs"]:
                if l["ticker"] in got:
                    b["results"][l["ticker"]] = got[l["ticker"]]
    return bool(got)


def combo_status(b, c):
    res = [b["results"].get(l["ticker"]) for l in c["legs"]]
    if "no" in res:
        return "lost"
    if all(r == "yes" for r in res):
        return "won"
    return "pending"


def bets_from_history(history):
    """Combos you ticked as placed, with results looked up from Kalshi."""
    bets = []
    for b in history["builds"]:
        for i in b.get("placed", []):
            c = b["combos"][i - 1]
            st = combo_status(b, c)
            quote = b.get("quotes", {}).get(str(i))
            dogs = sum(1 for l in c["legs"] if l.get("dog")) if any("dog" in l for l in c["legs"]) else None
            bets.append({"week": b["week"], "kind": c["kind"], "cost": b["stake"], "status": st,
                         "back": (float(quote) if quote else c["min"]) if st == "won" else 0,
                         "est": st == "won" and not quote, "legs": len(c["legs"]), "dogs": dogs,
                         "pct": float(quote) / c["fair"] if quote and c.get("fair") else None})
    return bets


def bets_from_account(acct, history):
    """Your real Kalshi combos, labelled with the planner's type when they match."""
    plan = {}
    for b in history["builds"]:
        for c in b["combos"]:
            plan[frozenset(l["ticker"] for l in c["legs"])] = (c, b["stake"])
    out = []
    for a in acct:
        c, stake = plan.get(leg_key(a["legs"]), (None, None))
        dogs = sum(1 for l in c["legs"] if l.get("dog")) if c and any("dog" in l for l in c["legs"]) else None
        pct = a["pays"] / (c["fair"] / stake * a["cost"]) if c and c.get("fair") and a["cost"] else None
        out.append({"week": a.get("first_week") or a["week"] or "unknown", "kind": c["kind"] if c else "own",
                    "cost": a["cost"], "status": a["status"], "back": a["back"], "est": False,
                    "legs": len(a["legs"]), "dogs": dogs, "pct": pct})
    return out


def render_record(bets, note=None):
    total = defaultdict(float)
    by_type = defaultdict(lambda: defaultdict(float))
    weeks = defaultdict(lambda: defaultdict(float))
    by_legs = defaultdict(lambda: defaultdict(float))
    by_dogs = defaultdict(lambda: defaultdict(float))

    def legs_bucket(n):
        return "2–3 picks" if n <= 3 else "4–6 picks" if n <= 6 else "7–9 picks" if n <= 9 else "10+ picks"

    for bet in bets:
        groups = [total, by_type[bet["kind"]], weeks[bet["week"]]]
        if bet.get("legs"):
            groups.append(by_legs[legs_bucket(bet["legs"])])
        if bet.get("dogs") is not None:
            groups.append(by_dogs["4+ underdogs" if bet["dogs"] >= 4 else
                                  f"{bet['dogs']} underdog{'s' if bet['dogs'] != 1 else ''}"])
        for bucket in groups:
            bucket["placed"] += 1
            bucket[bet["status"]] += 1
            if bet["status"] == "won" or (bet["status"] == "cashed" and bet["back"] > bet["cost"]):
                bucket["paid"] += 1
            bucket["spent"] += bet["cost"]
            if bet["status"] != "pending":
                bucket["decided_spent"] += bet["cost"]
            bucket["back"] += bet["back"]
            if bet["est"]:
                bucket["est"] = 1
    head = f"<div class='note'>{html.escape(note)}</div>" if note else ""
    if not total["placed"]:
        return head + ("<div class='empty'><b>No bets tracked yet.</b><br>Connect your Kalshi account "
                       "in settings and your combos show up here on their own. Or tick <b>Placed</b> "
                       "on each combo you bet and type Kalshi's offer.</div>")

    def net_cell(d):
        if d["pending"] == d["placed"]:
            return "<span class='muted'>waiting</span>"
        net = d["back"] - d["decided_spent"]
        cls = "pos" if net >= 0 else "neg"
        return f"<span class='{cls}'>{'+' if net >= 0 else '−'}{money(abs(net))}</span>"

    t = total
    decided = t["placed"] - t["pending"]
    out = [head, "<div class='stats'>",
           f"<div class='stat'><b>{int(t['paid'])}/{int(decided)}</b><span class='lbl'>combos paid off</span></div>",
           f"<div class='stat'><b>{money(t['spent'])}</b><span class='lbl'>staked</span></div>",
           f"<div class='stat'><b>{net_cell(t)}</b><span class='lbl'>profit / loss</span></div></div>"]
    if t["pending"]:
        out.append(f"<div class='note'>{int(t['pending'])} combo(s) still waiting on games.</div>")
    if t["cashed"]:
        out.append(f"<div class='note'>{int(t['cashed'])} combo(s) cashed out early, counted at what Kalshi paid.</div>")
    if t.get("est"):
        out.append("<div class='note'>Wins without Kalshi's offer typed in are counted at your minimum payout.</div>")
    out.append("<h2>By type</h2><div class='game'>")
    for k in ["full", "safer", "middle", "moonshot", "own"]:
        d = by_type.get(k)
        if d:
            out.append(f"<div class='row'><span><b>{TYPE_NAMES[k]}</b> "
                       f"<span class='muted'>{int(d['paid'])} paid off of {int(d['placed'])}</span></span>"
                       f"<span>{net_cell(d)}</span></div>")
    def table(title, data, order):
        rows = [f"<div class='row'><span><b>{k}</b> <span class='muted'>{int(data[k]['paid'])} paid off of "
                f"{int(data[k]['placed'])}</span></span><span>{net_cell(data[k])}</span></div>"
                for k in order if k in data]
        return f"</div><h2>{title}</h2><div class='game'>" + "".join(rows) if rows else ""

    out.append(table("By number of picks", by_legs, ["2–3 picks", "4–6 picks", "7–9 picks", "10+ picks"]))
    out.append(table("By underdogs (planner combos)", by_dogs,
                     ["0 underdogs", "1 underdog", "2 underdogs", "3 underdogs", "4+ underdogs"]))
    pcts = [b["pct"] for b in bets if b.get("pct")]
    if pcts:
        avg = sum(pcts) / len(pcts)
        verdict = ("about what a fair price would pay" if avg >= 0.95 else
                   "a modest house cut" if avg >= 0.85 else "a steep house cut")
        out.append(f"</div><h2>Kalshi's prices</h2><div class='game'><div class='row'><span>"
                   f"Your offers averaged <b>{avg:.0%}</b> of fair value across {len(pcts)} combo(s), "
                   f"{verdict}. Lowest {min(pcts):.0%}, highest {max(pcts):.0%}.</span></div>")
    out.append("</div><h2>By week</h2><div class='game'>")
    for w in sorted(weeks, reverse=True):
        d = weeks[w]
        label = f"{dt.date.fromisoformat(w):%b %-d}" if w != "unknown" else "Other"
        out.append(f"<div class='row'><span><b>{label}</b> "
                   f"<span class='muted'>{int(d['placed'])} placed · {int(d['won'])} won</span></span>"
                   f"<span>{net_cell(d)}</span></div>")
    out.append("</div>")
    return "".join(out)


# ================================================================ results page
CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e5e7eb;
--accent:#1f6feb;--good:#15803d;--goodbg:#dcfce7;--bad:#b45309;--badbg:#fef3c7;
--red:#b91c1c;--redbg:#fee2e2;--dogbg:#ede9fe;--dog:#6d28d9;--done:#eef6ee}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#1a1d23;--ink:#eceef2;
--muted:#9aa1ad;--line:#2a2e36;--accent:#5b9dff;--good:#4ade80;--goodbg:#14301f;
--bad:#fbbf24;--badbg:#3a2c0b;--red:#f87171;--redbg:#3b1416;--dogbg:#2a2140;--dog:#c4b5fd;--done:#15241a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.4 -apple-system,system-ui,sans-serif;-webkit-text-size-adjust:100%}
header{padding:18px 16px 8px}h1{font-size:22px;margin:0 0 4px}
.sub,.muted{color:var(--muted);font-size:14px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:8px 0}
header+.stats{padding:8px 16px}
.stat{background:var(--card);border-radius:12px;padding:10px 12px}
.stat b{display:block;font-size:20px}.stat .lbl{display:block;color:var(--muted);font-size:12px}
.note{margin:4px 0 0;font-size:13px;color:var(--muted)}.top-notes{padding:0 16px}
.tabs{display:flex;gap:6px;padding:12px 16px;background:var(--bg)}
.tabs button{flex:1;border:0;border-radius:10px;padding:10px 4px;font:600 15px -apple-system,sans-serif;
background:var(--card);color:var(--ink)}.tabs button.on{background:var(--accent);color:#fff}
section{padding:0 16px 40px}.hidden{display:none}
.card{background:var(--card);border-radius:14px;padding:14px;margin:0 0 12px;border:1px solid var(--line)}
.card.done{background:var(--done)}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.tier{font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.03em}
.pay{font-size:26px;font-weight:800}.meta{color:var(--muted);font-size:14px}
.placed{display:flex;align-items:center;gap:6px;font-size:14px;font-weight:600;
padding:8px 10px;border-radius:10px;border:1px solid var(--line);white-space:nowrap}
.placed input{width:20px;height:20px}
.min{margin-top:10px;padding:10px;border-radius:10px;background:var(--bg);font-size:14px}
.min b{font-size:16px}
.quote{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}
.quote input{width:110px;font:600 16px -apple-system,sans-serif;padding:8px;border-radius:8px;
border:1px solid var(--line);background:var(--card);color:var(--ink)}
.verdict{font-size:13px;font-weight:700;padding:4px 8px;border-radius:8px;white-space:nowrap;display:inline-block}
.verdict.ok{background:var(--goodbg);color:var(--good)}.verdict.no{background:var(--redbg);color:var(--red)}
ol{list-style:none;margin:12px 0 0;padding:0}
li{display:flex;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--line)}
.n{width:22px;color:var(--muted);font-size:13px}.who{flex:1}.who b{font-weight:650}
.who small{display:block;color:var(--muted);font-size:13px}
.pct{font-weight:600;font-size:15px;min-width:40px;text-align:right}
.tag{font-size:11px;font-weight:700;padding:2px 6px;border-radius:6px;white-space:nowrap;vertical-align:2px}
.tag.dog{background:var(--dogbg);color:var(--dog)}.tag.good{background:var(--goodbg);color:var(--good)}
.tag.bad{background:var(--badbg);color:var(--bad)}.tag.red{background:var(--redbg);color:var(--red)}
.tag.lock{background:var(--accent);color:#fff}
h2{font-size:17px;margin:18px 0 8px;display:flex;justify-content:space-between;align-items:center;gap:8px}
h2 .tag{font-size:12px}.game{background:var(--card);border-radius:12px;padding:10px 12px;margin-bottom:8px}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:4px 0}
.row .nums{color:var(--muted);font-size:13px;text-align:right}
.warn{font-size:13px;color:var(--red);margin-top:4px}
.pos{color:var(--good);font-weight:700}.neg{color:var(--red);font-weight:700}
.empty{background:var(--card);border-radius:12px;padding:16px;margin-top:8px;font-size:15px}
.foot{color:var(--muted);font-size:12px;padding:0 16px 30px}
.btn{font:600 14px -apple-system,sans-serif;padding:8px 12px;border-radius:9px;border:1px solid var(--line);
background:var(--card);color:var(--ink)}.btn.go{background:var(--accent);color:#fff;border-color:var(--accent)}
.trade{margin-top:8px;font-size:14px}.trade:empty{display:none}
.flip{margin-left:8px;font:600 12px -apple-system,sans-serif;padding:5px 8px;border-radius:8px;
border:1px solid var(--line);background:var(--bg);color:var(--accent)}
.klink{font-size:12px;font-weight:600;color:var(--accent);text-decoration:none;white-space:nowrap}
.now{border:2px solid var(--accent)}.now .quote .btn{width:100%}
.lostbox{margin:4px 0 16px}.lostbox summary{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:12px 14px;font-weight:700;list-style:none;cursor:pointer}.lostbox summary::-webkit-details-marker{display:none}
.lostbox[open] summary{margin-bottom:12px}.lostbox[open] summary .muted{display:none}.lostbox .card{opacity:.7}
.side{display:flex;flex-direction:column;gap:6px}
.expbar{flex:1;height:8px;border-radius:4px;background:var(--line);overflow:hidden;margin:0 8px}
.expbar span{display:block;height:100%;background:var(--accent)}.expbar span.hot{background:var(--red)}.batch{background:var(--card);border-radius:14px;padding:12px;
margin:0 0 12px;border:1px solid var(--line);display:flex;flex-direction:column;gap:8px}
.amt{width:64px!important}
"""

JS = """
var state = /*STATE*/null;
if(!state){ try{ state = JSON.parse(localStorage.getItem(KEY)||'null'); }catch(e){} }
state = state || {placed:[], quotes:{}};
function send(path){ try{localStorage.setItem(KEY,JSON.stringify(state));}catch(e){}
  try{ location.href='combo://'+path; }catch(e){} }
function verdict(c){ var i=+c.dataset.i, v=parseFloat(state.quotes[i]), el=c.querySelector('.verdict');
  if(!v){ el.style.display='none'; return; } el.style.display='';
  var ok = v >= +c.dataset.min; el.className='verdict '+(ok?'ok':'no');
  el.textContent = ok ? 'Good, take it' : 'Too low: skip or swap a pick'; }
function paint(){ document.querySelectorAll('.card').forEach(function(c){
  var i=+c.dataset.i, on=state.placed.indexOf(i)>=0; c.classList.toggle('done',on);
  c.querySelector('.placed input').checked=on;
  var q=c.querySelector('.quote input'); if(state.quotes[i] && document.activeElement!==q) q.value=state.quotes[i];
  verdict(c); });
  var pc=document.getElementById('placedcount'); if(pc) pc.textContent=state.placed.length; }
function tog(i){ var k=state.placed.indexOf(i); if(k>=0) state.placed.splice(k,1); else state.placed.push(i);
  paint(); send('placed/'+BUILD+'/'+state.placed.join(',')); }
function quote(i,el){ var v=el.value.replace(/[^0-9.]/g,''); if(v) state.quotes[i]=v; else delete state.quotes[i];
  paint(); send('quote/'+BUILD+'/'+i+'/'+(v||'0')); }
function tab(n){ document.querySelectorAll('section').forEach(function(sec){ var t=sec.id;
  sec.classList.toggle('hidden',t!==n);
  var b=document.getElementById('b-'+t); if(b) b.classList.toggle('on',t===n); }); window.scrollTo(0,0); }
function fmt(x){ return '$'+(x>=10? Math.round(x).toLocaleString() : x.toFixed(2).replace('.00','')); }
function stakeOf(i){ var c=document.querySelector('.card[data-i="'+i+'"]'); if(!c) return 0;
  var v=parseFloat((c.querySelector('.amt')||{}).value); return v>0? v : 0; }
function amt(i,el){ var c=document.querySelector('.card[data-i="'+i+'"]'), v=parseFloat(el.value);
  if(!(v>0)){ v=parseFloat(el.defaultValue); el.value=v; }
  c.querySelector('.pay').textContent=fmt(v*+c.dataset.fair1);
  c.querySelector('.minv').textContent=fmt(v*+c.dataset.min1);
  c.dataset.min=(v*+c.dataset.min1).toFixed(0); verdict(c); }
function act(a,i){ var t=document.getElementById('t'+i); if(t) t.innerHTML="<span class='muted'>Working…</span>";
  var extra = a==='buy' ? '/'+stakeOf(i) : '';
  try{ location.href='combo://'+a+'/'+BUILD+'/'+i+extra; }catch(e){} }
function tradeMsg(i,h){ var t=document.getElementById('t'+i); if(t) t.innerHTML=h; }
function act2(a,i,x){ var t=document.getElementById('t'+i); if(t) t.innerHTML="<span class='muted'>Working…</span>";
  try{ location.href='combo://'+a+'/'+BUILD+'/'+i+'/'+encodeURIComponent(x); }catch(e){} }
function picked(){ return Array.prototype.map.call(document.querySelectorAll('.pick:checked'), function(x){return +x.value;}); }
function selCount(){ var b=document.getElementById('getall'); if(b) b.textContent='Get offers for selected ('+picked().length+')'; }
function selAll(){ document.querySelectorAll('.pick').forEach(function(x){ x.checked = state.placed.indexOf(+x.value)<0; }); selCount(); }
function getAll(){ var p=picked(); if(!p.length){ tradeMsg(0,"<span class='muted'>Tick Select on the combos you want first.</span>"); return; }
  var list=p.map(function(i){ return i+':'+stakeOf(i); }).join(',');
  p.forEach(function(i){ tradeMsg(i,"<span class='muted'>Asking Kalshi for a price…</span>"); });
  try{ location.href='combo://batch/'+BUILD+'/0/'+list; }catch(e){} }
function markPlaced(i,pays){ if(state.placed.indexOf(i)<0) state.placed.push(i); state.quotes[i]=pays; paint(); }
paint();
if(FOCUS){ var fc=document.querySelector('.card[data-i="'+FOCUS+'"]');
  if(fc){ fc.scrollIntoView(); fc.style.outline='2px solid var(--accent)'; } }
"""


def exposure_html(combo_picks, title="How much rides on one result"):
    """combo_picks: one list of (ticker, name) per live combo. Shows which picks the
    most combos depend on, and warns above your max-share setting."""
    n = len(combo_picks)
    if n < 2:
        return ""
    count, names = defaultdict(int), {}
    for picks in combo_picks:
        for t, nm in set(picks):
            count[t] += 1
            names[t] = nm
    top = sorted(count, key=lambda t: -count[t])[:6]
    worst = top[0]
    share = count[worst] / n
    over = share > CFG["max_share"] / 100
    head = (f"If <b>{html.escape(names[worst])}</b> loses, <b>{count[worst]} of {n}</b> combos are out.")
    rows = "".join(
        f"<div class='row'><span>{html.escape(names[t])}</span><span class='expbar'>"
        f"<span style='width:{count[t] / n * 100:.0f}%' class='{'hot' if count[t] / n > CFG['max_share'] / 100 else ''}'></span></span>"
        f"<span class='muted' style='min-width:58px;text-align:right'>{count[t]} of {n}</span></div>" for t in top)
    warn = (f"<div class='warn'>That's over your {CFG['max_share']}% limit. Full-slate combos and "
            f"locked picks include every game on purpose, so they push this up.</div>" if over else
            f"<div class='muted' style='font-size:13px'>Within your {CFG['max_share']}% limit.</div>")
    return (f"<div class='batch'><div><b>{title}</b></div><div>{head}</div>{warn}{rows}</div>")


def decision_html(legs):
    """When to check a cash-out: just before the first game with an underdog pick that
    starts after some other pick has been decided."""
    timed = sorted((l for l in legs if start_dt(l["event"])), key=lambda l: start_key(l["event"]))
    if len(timed) < 2:
        return ""
    first = start_dt(timed[0]["event"])
    risky = [l for l in timed if l.get("fair", 1) < 0.5 and start_dt(l["event"]) > first]
    if not risky:
        return ""
    when = start_label(risky[0]["event"])
    return (f"<div class='muted' style='font-size:13px;margin:6px 0 0'>⏱ Decision point: {when}, "
            f"when {html.escape(risky[0].get('pick', 'the underdog'))} plays. If the earlier picks have won, "
            f"check your cash-out offer before then.</div>")


def edge_tag(s):
    if s.get("edge") is None:
        return ""
    cents = round(s["edge"] * 100)
    if cents >= 1:
        return f'<span class="tag good">Bargain +{cents}¢</span>'
    if cents <= -4:
        return f'<span class="tag bad">Pricey {cents}¢</span>'
    return ""


HIDE = " style='display:none'"


def render(build_id, combos, games, all_games, days, sunday, p_any, p_each,
           notes, locks, skipped, news, focus=None, card_notes=None):
    e = html.escape
    order = {ev: i for i, ev in enumerate(all_games)}
    spent = len(combos) * CFG["stake"]
    best = max((c["fair"] for c in combos), default=0)
    out = ["<!doctype html><html><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{LG()['name']} combos</title><style>{CSS}</style></head><body>",
           f"<header><h1>Your combos for {sunday:%b %-d}</h1>"
           f"<div class='sub'>{len(games)} games · {len(combos)} combos at ${CFG['stake']} · "
           f"<span id='placedcount'>0</span> placed</div>" + "<div class='quote' style='margin-top:10px'><button class='btn' onclick=\"location.href='combo://settings'\">"
           "⚙︎ Settings & build more</button></div>" + "</header>",
           "<div class='stats'>"
           f"<div class='stat'><b>{money(spent)}</b><span class='lbl'>total stake</span></div>"
           f"<div class='stat'><b>{p_any:.0%}</b><span class='lbl'>chance one hits</span></div>"
           f"<div class='stat'><b>{money(best)}</b><span class='lbl'>biggest payout</span></div></div>",
           "<div class='top-notes'>" + "".join(f"<div class='note'>{e(n)}</div>" for n in notes) + "</div>",
           "<div style='padding:8px 16px 0'>" + exposure_html(
               [[(l["ticker"], l["pick"]) for l in c["legs"]] for c in combos]) + "</div>",
           "<div class='tabs'><button id='b-combos' class='on' onclick=\"tab('combos')\">Combos</button>"
           "<button id='b-games' onclick=\"tab('games')\">Games</button>"
           "<button id='b-record' onclick=\"tab('record')\">Record</button></div>",
           "<section id='combos'>"]
    if can_trade():
        out.append("<div class='batch'><div><button class='btn' onclick='selAll()'>Select all not placed</button></div>"
                   "<button class='btn go' id='getall' onclick='getAll()'>Get offers for selected (0)</button>"
                   "<div class='trade' id='t0'></div></div>")
    for i, (c, p) in enumerate(zip(combos, p_each), 1):
        chance = f"{p:.1%}" if p >= 0.001 else "under 0.1%"
        out.append(
            f"<div class='card' data-i='{i}' data-min='{c['min']:.0f}' data-fair1='{c['fair'] / CFG['stake']:.6f}' "
            f"data-min1='{c['min'] / CFG['stake']:.6f}'><div class='top'><div>"
            f"<div class='tier'>#{i} · {e(c['tier'])}</div>"
            f"<div class='pay'>{money(c['fair'])}</div>"
            f"<div class='meta'>fair payout · {chance} chance · {len(c['legs'])} picks</div></div>"
            f"<div class='side'><label class='placed'><input type='checkbox' onchange='tog({i})'>Placed</label>"
            + (f"<label class='placed sel'><input type='checkbox' class='pick' value='{i}' onchange='selCount()'>Select</label>" if can_trade() else "")
            + "</div></div>"
            f"<div class='min'>Take Kalshi's offer if it's at least <b class='minv'>{money(c['min'])}</b>"
            f"<div class='quote'{HIDE if can_trade() else ''}><span>Kalshi offers $</span>"
            f"<input inputmode='decimal' placeholder='amount' onchange='quote({i},this)'>"
            f"<span class='verdict' style='display:none'></span></div></div>"
            f"<div class='quote'><span>Bet $</span><input class='amt' inputmode='decimal' value='{CFG['stake']}' "
            f"onchange='amt({i},this)'><button class='btn' onclick='act(\"swap\",{i})'>Swap this one</button>"
            + (f"<button class='btn go' onclick='act(\"buy\",{i})'>Buy on Kalshi</button>" if can_trade() else "")
            + f"</div><div class='trade' id='t{i}'></div>"
            + ((card_notes or {}).get(i) or "") + decision_html(c["legs"]) + "<ol>")
        for n, l in enumerate(sorted(c["legs"], key=lambda l: (start_key(l["event"]), order[l["event"]])), 1):
            other = next(s for s in all_games[l["event"]] if s is not l)
            tags = ""
            if l.get("live"):
                tags += '<span class="tag bad">Live</span> '
            if l["event"] in locks:
                tags += '<span class="tag lock">Your pick</span> '
            if l["fair"] < other["fair"]:
                tags += '<span class="tag dog">Underdog</span> '
            tags += edge_tag(l)
            out.append(f"<li><span class='n'>{n}</span><span class='who'><b>{e(l['pick'])}</b> {tags}"
                       f"<small>to beat {e(other['pick'])} · "
                       f"{' '.join(x for x in (day_tag(days[l['event']]), start_label(l['event'])) if x)}</small></span>"
                       f"<span class='pct'>{l['fair']:.0%}</span>"
                       f"<button class='flip' onclick='act2(\"flip\",{i},\"{e(l['ticker'])}\")'>Flip</button></li>")
        out.append("</ol></div>")
    out.append("</section>")

    on = day_on()
    out.append("<section id='games' class='hidden'>")
    for day in DAY_ORDER:
        evs = sorted((x for x in all_games if days[x] == day), key=lambda x: -fav(all_games[x])["fair"])
        if not evs:
            continue
        status = '<span class="tag good">In combos</span>' if on[day] else '<span class="tag bad">Left out</span>'
        out.append(f"<h2><span>{day} · {len(evs)} game{'s' * (len(evs) != 1)}</span> {status}</h2>")
        for x in evs:
            out.append("<div class='game'>")
            for s in sorted(all_games[x], key=lambda s: -s["fair"]):
                nums = f"Kalshi {s['p'] * 100:.0f}¢"
                if s.get("src") and not s.get("live"):
                    nums += f" · books {s['fair']:.0%}"
                tag = '<span class="tag lock">Locked</span> ' if locks.get(x) == s["ticker"] else ""
                if s.get("live"):
                    tag += '<span class="tag bad">Live</span> '
                    if not pickable(s):
                        tag += f'<span class="tag red">Too unlikely to pick (under {CFG["live_min"]}%)</span> '
                    nums = f"live {s['fair']:.0%} · Kalshi {s['p'] * 100:.0f}¢"
                out.append(f"<div class='row'><span><b>{e(s['pick'])}</b> {tag}{edge_tag(s)}</span>"
                           f"<span class='nums'>{nums}</span></div>")
            if x in skipped:
                out.append(f"<div class='warn'>{e(skipped[x])}</div>")
            elif news.get(x, 0) >= NEWS_GAP:
                out.append(f"<div class='warn'>Kalshi and the sportsbooks disagree by {news[x]:.0%}. "
                           f"Probably breaking news (injury?). Check before betting.</div>")
            out.append("</div>")
    out.append("</section><section id='record' class='hidden'><!--RECORD--></section>")
    out.append("<div class='foot'>Fair payout is what the combo would pay with no house cut. "
               "Kalshi's offer will be lower; the minimum is your cut-off for a fair-ish deal. "
               "Chances assume games are independent.</div>")
    out.append(f"<script>var FOCUS={json.dumps(focus)};</script>")
    out.append(f"<script>var KEY={json.dumps('combos-' + build_id)};var BUILD={json.dumps(build_id)};"
               f"{JS}</script></body></html>")
    return "".join(out)


def show_results(all_games=None, days=None, sunday=None):
    """Results: what actually happened to your combos (from Kalshi). Without a Kalshi
    connection, falls back to the planner's last build."""
    APP["where"] = "results"
    if can_trade() and not RUN_OPTS.pop("show_build", False):
        return present(results_page(sunday), ResultsKeeper())
    return show_build(all_games, days, sunday)


@safe_delegate
class ResultsKeeper:
    def webview_should_start_load(self, webview, url, nav_type):
        if url.startswith("combo://lastbuild"):
            import threading

            def go():
                RUN_OPTS["show_build"] = True
                RUN_OPTS["goto"] = "results"
                run()
            threading.Thread(target=go, daemon=True).start()
            return False
        return not url.startswith("combo://")


def account_breakdown(hours=24):
    """Whole-account profit over the last `hours`, from Kalshi's own numbers:
    settlements (payout minus cost and fees) and positions' realized profit for
    bets closed or sold but not settled yet. Open bets are listed, not valued."""
    import time
    key_id = CFG.get("kalshi_key_id", "").strip()
    if not key_id or not os.path.exists(KEYFILE):
        return None
    with open(KEYFILE, encoding="utf-8") as f:
        key = load_private_key(f.read())
    since = int(time.time() - hours * 3600)
    settles = account_pages(key, key_id, "/portfolio/settlements", "settlements", {"min_ts": since})
    fills = account_pages(key, key_id, "/portfolio/fills", "fills", {"min_ts": since})
    positions = all_positions(key, key_id)
    cache = load_json(LEGS_CACHE, {})
    touched = {f.get("ticker") or f.get("market_ticker") for f in fills} | {s.get("ticker") for s in settles}
    fetch_legs_parallel([t for t in touched if is_combo(t)], cache)
    save_json(LEGS_CACHE, cache)

    def kind(t):
        if is_combo(t):
            legs = combo_legs(t, cache) or []
            return "NFL combos" if legs and all((l["ticker"] or "").startswith(SERIES) for l in legs) \
                else "Other combos"
        return "NFL single bets" if (t or "").startswith(SERIES) else "Other single bets"

    out = defaultdict(lambda: {"pnl": 0.0, "n": 0})
    done = set()
    for s in settles:
        t = s.get("ticker")
        pnl = (dollars(s, "revenue") - dollars(s, "yes_total_cost") - dollars(s, "no_total_cost")
               - dollars(s, "fee_cost"))
        out[kind(t)]["pnl"] += pnl
        out[kind(t)]["n"] += 1
        done.add(t)
    open_n, open_cost = 0, 0.0
    for p in positions:
        t = p.get("ticker") or p.get("market_ticker")
        if t in done:
            continue
        held = abs(float(p.get("position_fp") or p.get("position") or 0))
        realized = dollars(p, "realized_pnl")
        if held > 0.005:
            open_n += 1
            open_cost += dollars(p, "market_exposure")
        if t in touched and realized:
            out[kind(t)]["pnl"] += realized
            out[kind(t)]["n"] += 0 if held > 0.005 else 1
    return {"by": dict(out), "total": sum(v["pnl"] for v in out.values()),
            "open_n": open_n, "open_cost": open_cost, "hours": hours}


def breakdown_html():
    try:
        b = account_breakdown()
    except (PermissionError, ValueError, requests.RequestException, OSError):
        return ""
    if not b:
        return ""
    sign = lambda x: f"<span class='{'pos' if x >= 0 else 'neg'}'>{'+' if x >= 0 else '−'}{money(abs(x))}</span>"
    rows = "".join(f"<div class='row' style='padding:5px 0;border-top:1px solid var(--line)'><span>{k}"
                   f"<br><small class='muted'>{v['n']} settled or sold</small></span>{sign(v['pnl'])}</div>"
                   for k, v in sorted(b["by"].items(), key=lambda x: -abs(x[1]["pnl"])))
    return ("<details class='lostbox' id='acct24'><summary>Whole Kalshi account, last 24 hours: "
            f"{sign(b['total'])}<span class='muted'> · tap for details</span></summary><div class='game'>"
            f"{rows or '<div class=muted>Nothing settled or sold in the last 24 hours.</div>'}"
            f"<div class='muted' style='font-size:13px;margin-top:8px'>From Kalshi's own profit figures for bets "
            f"that settled or that you sold. Still open: {b['open_n']} bet{'s' if b['open_n'] != 1 else ''} "
            f"({money(b['open_cost'])} in). Kalshi's 24-hour number may also include how much those open bets "
            f"have gained or lost in value, so it can differ from this.</div></div></details>")


def results_page(sunday):
    """This week's money and outcomes, then week by week. Kept short."""
    e = html.escape
    loading("Getting your results from Kalshi…")
    acct, balance, note = fetch_account()
    head = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Results</title><style>{CSS}</style></head><body>")
    if acct is None:
        return (head + "<header><h1>Results</h1></header><section><div class='empty'>"
                f"{e(note or 'Connect your Kalshi account in Settings first.')}</div></section></body></html>")
    week = sunday.isoformat() if sunday else None
    this = [a for a in acct if in_week(a, week)]
    # games decided but not paid out yet still count as won/lost here
    pend = [a for a in this if a["status"] in ("pending", "cashed")]
    res = fetch_results({l["ticker"] for a in pend for l in a["legs"] if l["ticker"]}) if pend else {}

    def games_say(a):
        """'won' / 'lost' if the games have decided this combo, else None."""
        rs = [res.get(l["ticker"]) if l.get("side", "yes") == "yes" else
              {"yes": "no", "no": "yes"}.get(res.get(l["ticker"])) for l in a["legs"]]
        if any(r == "no" for r in rs):
            return "lost"
        if rs and all(r == "yes" for r in rs):
            return "won"
        return None

    def outcome(a):
        if a["status"] != "pending":
            return a["status"], a["back"]
        g = games_say(a)
        if g == "lost":
            return "lost", 0.0
        if g == "won":
            return "won", a["pays"]
        return "live", 0.0

    rows, tot = [], defaultdict(float)
    order = {"won": 0, "cashed": 1, "live": 2, "lost": 3}
    for i, a in sorted(enumerate(this, 1), key=lambda x: order.get(outcome(x[1])[0], 9)):
        st, back = outcome(a)
        tot[st] += 1
        tot["staked"] += a["cost"]
        if st != "live":
            tot["decided"] += a["cost"]
            tot["back"] += back
        else:
            tot["live_staked"] += a["cost"]
        tag = {"won": "<span class='tag good'>Won</span>", "cashed": "<span class='tag good'>Cashed out</span>",
               "lost": "<span class='tag red'>Lost</span>", "live": "<span class='tag dog'>Live</span>"}[st]
        net = back - a["cost"]
        hs = ""
        if st == "cashed":
            g = games_say(a)
            full = a.get("full_pays") or 0
            if g == "won":
                tot["hs_won"] += 1
                tot["hs_pay"] += full
                hs = f" · would have paid {money(full)}"
            elif g == "lost":
                tot["hs_lost"] += 1
                hs = " · would have lost, good call"
            else:
                tot["hs_open"] += 1
                hs = f" · would pay {money(full)} if it hits" if full else ""
        money_cell = (f"<span class='muted'>{money(a['cost'])} in</span>" if st == "live" else
                      f"<span class='{'pos' if net >= 0 else 'neg'}'>{'+' if net >= 0 else '−'}{money(abs(net))}</span>")
        rows.append(f"<div class='row' style='padding:7px 0;border-top:1px solid var(--line)'>"
                    f"<span>Combo {i} {tag}<br><small class='muted'>{len(a['legs'])} picks · "
                    f"{money(a['cost'])} → {money(back) if st != 'live' else 'pays ' + money(a['pays'])}{hs}</small></span>"
                    f"<span>{money_cell}</span></div>")
    net = tot["back"] - tot["decided"]
    sub = f"{sunday:%a %b %-d} games" if by_day() else f"Week of {sunday:%b %-d}"
    body = [head, f"<header><h1>{LG()['icon']} Results</h1><div class='sub'>{sub}</div></header>"]
    if this:
        body.append(
            "<div style='padding:0 16px'><div class='batch now'>"
            f"<div class='row'><b>This week so far</b><b class='{'pos' if net >= 0 else 'neg'}' style='font-size:22px'>"
            f"{'+' if net >= 0 else '−'}{money(abs(net))}</b></div>"
            f"<div class='muted' style='font-size:13px'>Put in {money(tot['decided'])} on decided combos, got back "
            f"{money(tot['back'])}."
            + (f" Another {money(tot['live_staked'])} is still live." if tot["live"] else "") + "</div>"
            f"<div style='font-size:14px;margin-top:6px'>{int(tot['won'])} won · {int(tot['cashed'])} cashed out · "
            f"{int(tot['lost'])} lost · {int(tot['live'])} live</div>"
            + (f"<div class='muted' style='font-size:13px;margin-top:4px'>Your cash-outs: "
               + ", ".join(x for x in [
                   f"{int(tot['hs_won'])} would have won ({money(tot['hs_pay'])})" if tot["hs_won"] else "",
                   f"{int(tot['hs_lost'])} would have lost" if tot["hs_lost"] else "",
                   f"{int(tot['hs_open'])} not decided yet" if tot["hs_open"] else ""] if x) + ".</div>"
               if tot["cashed"] else "")
            + "</div></div>"
            f"<section><div class='game'>{''.join(rows)}</div>")
    else:
        body.append("<section><div class='empty'>No combos for this week yet.</div>")
    body.append(breakdown_html())
    # week by week
    weeks = defaultdict(lambda: defaultdict(float))
    for a in acct:
        if a["status"] == "pending" or not a["week"]:
            continue
        w = weeks[a.get("first_week") or a["week"]]
        w["n"] += 1
        w["in"] += a["cost"]
        w["back"] += a["back"]
        w["won"] += a["status"] in ("won", "cashed") and a["back"] > a["cost"]
    if weeks:
        all_in = sum(w["in"] for w in weeks.values())
        all_net = sum(w["back"] - w["in"] for w in weeks.values())
        lines = "".join(
            f"<div class='row' style='padding:6px 0;border-top:1px solid var(--line)'><span>"
            f"{dt.date.fromisoformat(k):%b %-d}<br><small class='muted'>{int(w['n'])} combos · "
            f"{int(w['won'])} paid off · {money(w['in'])} in</small></span>"
            f"<span class='{'pos' if w['back'] >= w['in'] else 'neg'}'>{'+' if w['back'] >= w['in'] else '−'}"
            f"{money(abs(w['back'] - w['in']))}</span></div>"
            for k, w in sorted(weeks.items(), reverse=True))
        body.append(f"<h2>Every {'day' if by_day() else 'week'} (settled)</h2><div class='game'><div class='row'><b>All time</b>"
                    f"<b class='{'pos' if all_net >= 0 else 'neg'}'>{'+' if all_net >= 0 else '−'}{money(abs(all_net))}"
                    f"</b></div><div class='muted' style='font-size:13px'>on {money(all_in)} put in</div>{lines}</div>")
    body.append("<div class='quote' style='margin:12px 0 24px'><button class='btn' "
                "onclick=\"location.href='combo://lastbuild'\">See the planner's last suggested combos</button></div>"
                "</section></body></html>")
    return "".join(body)


def show_build(all_games=None, days=None, sunday=None):
    """The planner's latest build page with your placed/offer notes and season record."""
    try:
        with open(LATEST, encoding="utf-8") as f:
            page = f.read()
    except OSError:
        return present(error_page("No results saved yet. Tap Settings & build more, then Build combos."))
    if not CTX and all_games is not None:
        hit0 = re.search(r"var BUILD=\"([^\"]+)\"", page)
        hist0 = load_json(HISTORY, {"builds": []})
        b0 = next((b for b in hist0["builds"] if hit0 and b["id"] == hit0.group(1)), None)
        loading("Getting today's prices…")
        ctx = ctx_from_history(b0, all_games, days, sunday)
        if ctx:
            CTX.update(ctx)
    page = inject_state(page)

    @safe_delegate
    class Keeper:
        def webview_should_start_load(self, webview, url, nav_type):
            if not url.startswith("combo://"):
                return True
            parts = unquote(url[len("combo://"):]).split("/")
            if parts[0] == "settings":
                reopen_settings(webview)
                return False
            if parts[0] in ("swap", "buy", "accept", "decline", "batch", "flip"):
                handle_action(webview, parts)
                return False
            hist = load_json(HISTORY, {"builds": []})
            b = next((x for x in hist["builds"] if len(parts) > 1 and x["id"] == parts[1]), None)
            if b is not None:
                if parts[0] == "placed":
                    b["placed"] = [int(i) for i in parts[2].split(",") if i.isdigit()]
                elif parts[0] == "quote" and len(parts) == 4:
                    try:
                        v = float(parts[3])
                    except ValueError:
                        v = 0
                    if v > 0:
                        b.setdefault("quotes", {})[parts[2]] = v
                    else:
                        b.setdefault("quotes", {}).pop(parts[2], None)
                save_json(HISTORY, hist)
            return False

    present(page, Keeper())


def inject_state(page, quiet=False):
    """Fill the saved page with your placed ticks, offers, Kalshi account and record.
    quiet=True: refresh in place (no loading screen), e.g. after a Swap."""
    say = (lambda m: None) if quiet else loading
    history = load_json(HISTORY, {"builds": []})
    say("Checking results…")
    if settle(history):
        save_json(HISTORY, history)
    hit = re.search(r"var BUILD=\"([^\"]+)\"", page)
    build = next((b for b in history["builds"] if hit and b["id"] == hit.group(1)), None)
    state = {"placed": build.get("placed", []), "quotes": build.get("quotes", {})} if build else None
    if CFG.get("kalshi_key_id") and os.path.exists(KEYFILE):
        say("Reading your Kalshi account…")
    acct, balance, note = fetch_account()
    if acct is not None:
        bets = bets_from_account(acct, history)
        # Tick the combos you actually bought, and fill in what they pay.
        bought = {leg_key(a["legs"]): a for a in acct}
        if build and state is not None:
            for i, c in enumerate(build["combos"], 1):
                a = bought.get(frozenset(l["ticker"] for l in c["legs"]))
                if a:
                    if i not in state["placed"]:
                        state["placed"].append(i)
                    state["quotes"][str(i)] = a["pays"]   # each contract pays $1
    else:
        bets = bets_from_history(history)
    page = page.replace("/*STATE*/null", json.dumps(state)).replace(
        "<!--RECORD-->", render_record(bets, note))
    return page


LOADING_PAGE = """<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><style>%s
.sk{padding:calc(env(safe-area-inset-top) + 64px) 16px 16px}.bar{background:var(--card);border-radius:12px;margin:0 0 12px;
 animation:pl 1.2s ease-in-out infinite alternate}@keyframes pl{from{opacity:.45}to{opacity:1}}
#msg{position:fixed;left:0;right:0;top:calc(env(safe-area-inset-top) + 18px);text-align:center;font-size:15px;font-weight:600;color:var(--muted)}
</style></head><body><div id='msg'>Loading…</div><div class='sk'>
<div class='bar' style='height:26px;width:55%%'></div><div class='bar' style='height:120px'></div>
<div class='bar' style='height:90px'></div><div class='bar' style='height:90px'></div><div class='bar' style='height:90px'></div></div>
<script>function setMsg(m){document.getElementById('msg').textContent=m;}
window.__load=function(h){var m=h.match(/<head[^>]*>([\\s\\S]*)<\\/head>/i),b=h.match(/<body[^>]*>([\\s\\S]*)<\\/body>/i);
 if(m)document.head.innerHTML=m[1];document.body.innerHTML=b?b[1]:h;
 document.querySelectorAll('body script').forEach(function(s){var n=document.createElement('script');n.text=s.text;s.parentNode.replaceChild(n,s);});
 window.scrollTo(0,0);};</script></body></html>"""

APP = {"web": None, "page": None}


def in_pythonista():
    try:
        import ui  # noqa: F401
        return True
    except ImportError:
        return False


def console_note(msg):
    """Print only when not running in Pythonista's window (keeps the console hidden)."""
    if not in_pythonista():
        print(msg)


def window_open():
    """True until you close the window with its X."""
    return APP.get("web") is not None and not APP.get("closed")


TAB_H = 82          # native tab bar height, including room for the home indicator


def _colors():
    return ("#0f1115", "#1a1d23", "#eceef2", "#9aa1ad", "#5b9dff") if CFG.get("dark") else \
           ("#f4f5f7", "#ffffff", "#16181d", "#6b7280", "#1f6feb")


def _web():
    """The one window everything shows in. Created once, then reused, so pages
    swap in place and the code never shows between them. The title bar and the tab bar
    are real iPhone controls, so they never move when you scroll."""
    import ui
    if window_open():
        return APP["web"]
    bg, card, ink, muted, accent = _colors()

    class Window(ui.View):            # a plain view can notice when it's closed;
        def will_close(self):         # Pythonista's web view can't be customised
            for closer in list(getattr(self, "closers", [])):
                try:
                    closer()
                except Exception:
                    pass

        def layout(self):
            w, h = self.width, self.height
            APP["web"].frame = (0, 0, w, h - TAB_H)
            bar = APP.get("bar")
            if bar is not None:
                bar.frame = (0, h - TAB_H, w, TAB_H)
                btns = [x for x in bar.subviews if not x.hidden]
                for i, x in enumerate(btns):
                    x.frame = (i * w / max(1, len(btns)), 0, w / max(1, len(btns)), 52)

    win = Window(name="Combos", background_color=bg)
    win.closers = [_window_closed]
    win.frame = (0, 0, 375, 667)
    web = ui.WebView(frame=(0, 0, 375, 667 - TAB_H), flex="WH")
    web.background_color = bg
    win.add_subview(web)
    bar = ui.View(frame=(0, 667 - TAB_H, 375, TAB_H), flex="WT", background_color=card)
    for key, icon, label in TABS:
        btn = ui.Button(title=f"{icon}  {label}", name=key)
        btn.font = ("<system-bold>", 13)
        bar.add_subview(btn)
    win.add_subview(bar)
    bind_controls(win, bar)
    APP.update(web=web, win=win, bar=bar, page=None, closed=False)
    update_bars()
    win.present("fullscreen", hide_title_bar=False, title_bar_color=bg, title_color=ink)
    return web


def update_bars():
    """Highlight the current tab and league in the native bars."""
    bar, win = APP.get("bar"), APP.get("win")
    if bar is None or win is None:
        return
    _, _, ink, muted, accent = _colors()
    where = APP.get("where") or ("mine" if can_trade() else "build")
    try:
        for btn in bar.subviews:
            btn.hidden = btn.name == "mine" and not can_trade()
            btn.tint_color = accent if btn.name == where else muted
        for item, code in zip(win.left_button_items or [], LEAGUES):
            item.tint_color = accent if code == LEAGUE["code"] else muted
        win.layout()
    except Exception:
        pass


def native_nav(target):
    """A tap on the native tab bar or title bar. On Settings/Build the page saves first."""
    if APP.get("settings_wait") and target != "refresh":
        js = {"mine": "mine", "results": "show", "build": "tab-build", "settings": "tab-settings"}.get(target, target)
        try:
            APP["web"].evaluate_javascript(f"go({json.dumps(js)})")
            return
        except Exception:
            pass
    go_to(target)


def _window_closed():
    APP["closed"] = True
    MINE["live"] = False


def bind_controls(win, bar):
    """Point the tab bar and title-bar buttons at this copy of the planner. After an update,
    an adopted window's buttons would otherwise still call the old copy, which then opened a
    fresh (white) window of its own on every tap."""
    import ui
    for btn in bar.subviews:
        btn.action = lambda sender: native_nav(sender.name)
    win.left_button_items = [ui.ButtonItem(title=f"{v['icon']} {v['short']}",
                                           action=(lambda code: (lambda sender: native_nav("lg-" + code)))(k))
                             for k, v in LEAGUES.items()]
    win.right_button_items = [ui.ButtonItem(title="⟳", action=lambda sender: native_nav("refresh"))]


def adopt_window(old_app, notice):
    """Called on a freshly updated copy: take over the open window so the update
    starts without closing anything, then open on Settings."""
    win = old_app["win"]
    if old_app.get("bar") is None:      # an older window: no title bar / tab bar. Open a fresh one.
        import time
        try:
            win.close()
        except Exception:
            pass
        time.sleep(1.2)                 # let the old window finish closing
        APP.update(web=None, win=None, bar=None, page=None, closed=True)
        RUN_OPTS["goto"] = "settings"
        RUN_OPTS["smode"] = "settings"
        RUN_OPTS["notice"] = notice
        return
    APP.update(web=old_app["web"], win=win, bar=old_app.get("bar"), page=None, closed=False)
    win.closers = [_window_closed]      # closing now tells this new copy, not the old one
    try:
        bind_controls(win, old_app["bar"])
        update_bars()
    except Exception:
        pass
    RUN_OPTS["goto"] = "settings"
    RUN_OPTS["notice"] = notice


def relaunch():
    """Start the version just installed in this same window. False if it can't."""
    import importlib.util, time
    if not window_open() or APP.get("win") is None:
        return False
    try:
        name = "nfl_combo_planner_%d" % time.time_ns()
        spec = importlib.util.spec_from_file_location(name, ENGINE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "adopt_window"):
            return False
        sys.modules[name] = mod
        MINE["live"] = False
        mod.adopt_window(APP, f"Updated to version {mod.VERSION}. You're all set.")
    except Exception:
        return False
    APP["closed"] = True              # this old copy stands down
    mod.run()
    return True


def loading(msg):
    """Show (or update) the loading screen in the same window. Prints outside Pythonista."""
    if not in_pythonista():
        print(msg)
        return
    import time
    web = _web()
    if APP.get("quiet") and APP.get("page") == "page":
        try:
            web.evaluate_javascript(f"toast({json.dumps(msg)})")
            return
        except Exception:
            pass
    if APP["page"] != "loading":
        web.delegate = None
        if not (APP.get("page") == "page" and replace_page(web, themed(LOADING_PAGE % CSS))):
            web.load_html(themed(LOADING_PAGE % CSS))
            time.sleep(0.25)      # let the page load before updating its text
        APP["page"] = "loading"
    web.evaluate_javascript(f"setMsg({json.dumps(msg)})")


TABS = [("mine", "●", "Live"), ("build", "＋", "Build"), ("results", "▤", "Results"), ("settings", "⚙︎", "Settings")]

APP_CSS = """
.appbar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:8px;
 padding:calc(env(safe-area-inset-top) + 6px) 12px 8px;background:var(--bg);border-bottom:1px solid var(--line)}
.abtn{min-width:44px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:10px;
 color:var(--ink);text-decoration:none;font:600 17px -apple-system,sans-serif}
.segc{flex:1;display:flex;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:2px;max-width:260px;margin:0 auto}
.segc a{flex:1;text-align:center;padding:7px 0;border-radius:8px;color:var(--muted);text-decoration:none;font:600 14px -apple-system,sans-serif}
.segc a.on{background:var(--accent);color:#fff}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:30;display:flex;background:var(--card);border-top:1px solid var(--line);
 padding:6px 4px calc(env(safe-area-inset-bottom) + 6px)}
.tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;min-height:44px;justify-content:center;
 color:var(--muted);text-decoration:none;font:600 11px -apple-system,sans-serif}
.tabbar a b{font-size:20px;line-height:22px;font-weight:600}.tabbar a.on{color:var(--accent)}
body{padding-bottom:24px}
.btn{min-height:44px}.klink{display:inline-block;padding:8px 2px}
.sheetbg{position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.45);display:none}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:51;background:var(--card);border-radius:18px 18px 0 0;
 padding:18px 18px calc(env(safe-area-inset-bottom) + 18px);transform:translateY(110%);transition:transform .22s ease}
.sheet.up{transform:none}.sheet h3{margin:0 0 6px;font-size:19px}.sheet p{margin:0 0 16px;color:var(--muted)}
.sheet .btn{width:100%;margin-top:8px;font-size:17px}
.ptr{height:0;overflow:hidden;text-align:center;color:var(--muted);font-size:13px;transition:height .15s}
.toast{position:fixed;left:50%;top:12px;transform:translateX(-50%);z-index:60;
 background:var(--ink);color:var(--bg);padding:9px 16px;border-radius:20px;font:600 14px -apple-system,sans-serif;
 box-shadow:0 4px 18px rgba(0,0,0,.3)}
@keyframes fl{from{background:rgba(91,157,255,.35)}to{background:transparent}}.flash{animation:fl 1.6s ease-out}
details.card>summary{list-style:none;cursor:pointer}details.card>summary::-webkit-details-marker{display:none}
details.card:not([open])>summary .chev::after{content:'›'}details.card[open]>summary .chev::after{content:'⌄'}
.chev{color:var(--muted);font-size:18px;margin-left:6px}
.strip{display:flex;gap:10px;align-items:center;
 justify-content:space-between;margin:0 -16px;padding:9px 16px;background:var(--bg);border-bottom:1px solid var(--line);
 font-size:14px;text-decoration:none;color:var(--ink)}
.inote{font-size:13px;color:var(--muted);margin:0 0 8px}.ib{color:var(--accent);font-size:15px;margin-left:6px;cursor:pointer}
input.sw{-webkit-appearance:none;appearance:none;width:51px;height:31px;flex:none;border-radius:16px;background:var(--line);
 position:relative;transition:background .2s;margin:0;cursor:pointer}
input.sw:checked{background:#34c759}
input.sw::after{content:'';position:absolute;top:2px;left:2px;width:27px;height:27px;border-radius:50%;background:#fff;
 box-shadow:0 1px 3px rgba(0,0,0,.35);transition:left .2s}
input.sw:checked::after{left:22px}
"""

APP_JS = r"""
window.__load=function(h){var m=h.match(/<head[^>]*>([\s\S]*)<\/head>/i),b=h.match(/<body[^>]*>([\s\S]*)<\/body>/i);
 if(m)document.head.innerHTML=m[1];document.body.innerHTML=b?b[1]:h;
 document.querySelectorAll('body script').forEach(function(s){var n=document.createElement('script');n.text=s.text;s.parentNode.replaceChild(n,s);});
 window.scrollTo(0,0);};
function sheet(title, sub, url, label){location.href='combo://confirm/'+encodeURIComponent(JSON.stringify([title,sub,url,label||'Confirm']));}
function toast(m){var t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.className='toast';
 document.body.appendChild(t);}t.textContent=m;t.style.display=m?'block':'none';}
window.__swap=function(h){var y=window.scrollY,open={},old={},anon=[];
 document.querySelectorAll('details[id]').forEach(function(d){open[d.id]=d.open;});
 document.querySelectorAll('details:not([id])').forEach(function(d){anon.push(d.open);});
 document.querySelectorAll('[data-k]').forEach(function(e){old[e.dataset.k]=e.textContent;});
 var vis=document.querySelector('section[id]:not(.hidden)');var tabSel=vis?vis.id:null;
 document.body.innerHTML=h;
 document.querySelectorAll('body script').forEach(function(s){var n=document.createElement('script');n.text=s.text;s.parentNode.replaceChild(n,s);});
 document.querySelectorAll('details[id]').forEach(function(d){if(d.id in open)d.open=open[d.id];});
 document.querySelectorAll('details:not([id])').forEach(function(d,i){if(anon[i])d.open=true;});
 if(tabSel&&window.tab&&document.getElementById(tabSel)&&tabSel!=='combos')tab(tabSel);
 document.querySelectorAll('[data-k]').forEach(function(e){var o=old[e.dataset.k];if(o!==undefined&&o!==e.textContent)e.classList.add('flash');});
 window.scrollTo(0,y);};
(function(){var y0=null,pull=0;
 document.addEventListener('touchstart',function(e){y0=(window.scrollY<=0)?e.touches[0].clientY:null;pull=0;},{passive:true});
 document.addEventListener('touchmove',function(e){if(y0===null)return;pull=e.touches[0].clientY-y0;var p=document.getElementById('ptr');
  if(p&&pull>0){p.style.height=Math.min(pull/2,44)+'px';p.textContent=pull>110?'Release to refresh':'Pull to refresh';}},{passive:true});
 document.addEventListener('touchend',function(){var p=document.getElementById('ptr');if(y0!==null&&pull>110&&window.REFRESH){
  if(p)p.textContent='Refreshing…';location.href='combo://nav/refresh';}else if(p){p.style.height='0';}y0=null;});})();
"""


def fallback_nav(page):
    """Plain buttons inside the page, only for a window without the native bars."""
    on_settings = "var SL =" in page
    go_for = {"mine": "mine", "results": "show", "build": "tab-build", "settings": "tab-settings", "close": None}
    items = [(k, lab) for k, _, lab in TABS if can_trade() or k != "mine"] + [("close", "✕ Close")]
    links = "".join(
        f"<a class='navb' href='combo://nav/{k}'"
        + (f" onclick=\"if(window.go){{go('{go_for[k]}');return false;}}\"" if on_settings and go_for[k] else "")
        + f">{lab}</a>" for k, lab in items)
    return ("<style>.fnav{display:flex;flex-wrap:wrap;gap:6px;padding:10px 16px 0}.navb{flex:1;text-align:center;"
            "padding:10px 4px;border-radius:10px;background:var(--card);border:1px solid var(--line);color:var(--ink);"
            "font:600 13px -apple-system,sans-serif;text-decoration:none;min-width:60px}</style>"
            f"<nav class='fnav'>{links}</nav>")


def app_frame(page):
    """Page extras inside the web view: pull-to-refresh, the in-place swap and confirm dialogs.
    The title bar and tab bar are native controls (see _web)."""
    if "<body>" not in page or "id='ptr'" in page:
        return page
    refresh = (APP.get("where") or "") in ("mine", "results")
    page = page.replace("</head>", f"<style>{APP_CSS}</style></head>", 1)
    page = page.replace("<body>", "<body><div class='ptr' id='ptr'></div>" + ("" if APP.get("bar") is not None
                        or not in_pythonista() else fallback_nav(page)), 1)
    page = page.replace("</body>", f"<script>{APP_JS}window.REFRESH={'true' if refresh else 'false'};</script></body>", 1)
    update_bars()
    return page


KALSHI_WEB = "https://kalshi.com"
GAME_SLUG = {"KXNFLGAME": "nfl-game", "KXNBAGAME": "nba-game"}


def game_url(leg_ticker):
    """Kalshi's web page for a pick's game (opens the Kalshi app if it's installed)."""
    parts = (leg_ticker or "").split("-")
    if len(parts) < 2:
        return f"{KALSHI_WEB}/portfolio"
    series, event = parts[0], "-".join(parts[:2])
    slug = GAME_SLUG.get(series)
    if slug:
        return f"{KALSHI_WEB}/markets/{series.lower()}/{slug}/{event.lower()}"
    return f"{KALSHI_WEB}/markets/{series.lower()}"


def combo_url(ticker):
    """A combo's own Kalshi page, e.g. kalshi.com/markets/kxmvecrosscategory/combo/<event>?marketTicker=<market>.
    (The middle part is only a readable name on Kalshi's links.)"""
    if not is_combo(ticker) or ticker.count("-") < 2:
        return f"{KALSHI_WEB}/portfolio"
    event = ticker.rsplit("-", 1)[0]
    series = event.split("-")[0].lower()
    return f"{KALSHI_WEB}/markets/{series}/combo/{event}?marketTicker={ticker}"


def haptic(kind="success"):
    """A tap you can feel: success, warning or error (iPhone only, silently skipped elsewhere)."""
    try:
        from objc_util import ObjCClass, on_main_thread

        @on_main_thread
        def buzz():
            g = ObjCClass("UINotificationFeedbackGenerator").new()
            g.prepare()
            g.notificationOccurred_({"success": 0, "warning": 1, "error": 2}.get(kind, 0))
        buzz()
    except Exception:
        pass


def open_outside(url):
    """Open a link in the Kalshi app (or Safari), never inside the planner's window."""
    try:
        from objc_util import UIApplication, nsurl
        UIApplication.sharedApplication().openURL_(nsurl(url))
        return
    except Exception:
        pass
    try:
        import webbrowser
        webbrowser.open("safari-" + url if in_pythonista() else url)
    except Exception:
        pass


def native_confirm(webview, title, sub, then, label):
    """The iPhone's own confirm dialog; carries out `then` only if you tap the button."""
    try:
        import console
        console.alert(title, sub, label)          # Cancel raises KeyboardInterrupt
    except KeyboardInterrupt:
        return
    except Exception:
        pass                                      # no dialog available (not on the phone)
    d = webview.delegate
    if d is not None:
        d.webview_should_start_load(webview, then, 0)


class NavKeeper:
    """Handles the nav bar on any page, then hands everything else to the page's own handler."""
    def __init__(self, inner=None):
        self.inner = inner

    def webview_should_start_load(self, webview, url, nav_type):
        if url.startswith("combo://confirm/"):
            import threading
            try:
                title, sub, then, label = json.loads(unquote(url[len("combo://confirm/"):]))
            except ValueError:
                return False
            threading.Thread(target=native_confirm, args=(webview, title, sub, then, label), daemon=True).start()
            return False
        if url.startswith("combo://open/"):
            target = unquote(url[len("combo://open/"):])
            if target.startswith(KALSHI_WEB):
                open_outside(target)
            return False
        if url.startswith("combo://nav/"):
            try:
                go_to(url[len("combo://nav/"):].strip("/"))
            except Exception:
                pass
            return False
        if self.inner is not None:
            return self.inner.webview_should_start_load(webview, url, nav_type)
        return not url.startswith("combo://")


def go_to(target):
    """Switch to My combos, Results or Settings in the same window."""
    import threading
    MINE["live"] = False
    waiting = APP.get("settings_wait")
    if target == "close":
        try:
            APP["win"].close()
        except Exception:
            pass
        return
    if waiting:                                   # on the settings page: just answer it
        result, done = waiting
        result["go"] = {"mine": "mine", "results": "show", "build": "tab-build",
                        "settings": "tab-settings"}.get(target, target if target.startswith("lg-") else None)
        if result["go"]:
            done.set()
        return
    if target == "league":
        target = "lg-" + next_league()
    if target.startswith("lg-"):                  # switch league and stay on the same kind of page
        save_json(LEAGUE_FILE, {"league": target[3:]})
        target = APP.get("where") or ("mine" if can_trade() else "build")
    if target == "refresh":
        target = APP.get("where") or "mine"
        APP["quiet"] = True
    if target in ("build", "settings"):
        RUN_OPTS["smode"] = target
        target = "settings"
    RUN_OPTS["goto"] = target
    threading.Thread(target=run, daemon=True).start()


DARK_CSS = ("<style>:root{color-scheme:dark;--bg:#0f1115;--card:#1a1d23;--ink:#eceef2;--muted:#9aa1ad;"
            "--line:#2a2e36;--accent:#5b9dff;--good:#4ade80;--goodbg:#14301f;--bad:#fbbf24;--badbg:#3a2c0b;"
            "--red:#f87171;--redbg:#3b1416;--dogbg:#2a2140;--dog:#c4b5fd;--done:#15241a}"
            "body{background:var(--bg);color:var(--ink)}</style>")
LIGHT_CSS = ("<style>:root{color-scheme:light;--bg:#f4f5f7;--card:#fff;--ink:#16181d;--muted:#6b7280;"
             "--line:#e5e7eb;--accent:#1f6feb;--good:#15803d;--goodbg:#dcfce7;--bad:#b45309;--badbg:#fef3c7;"
             "--red:#b91c1c;--redbg:#fee2e2;--dogbg:#ede9fe;--dog:#6d28d9;--done:#eef6ee}</style>")


def themed(page):
    """Dark or light pages, per Settings (doesn't depend on the phone's own setting)."""
    if "</head>" in page and "color-scheme:" not in page.split("</head>")[0][-1200:]:
        page = page.replace("</head>", (DARK_CSS if CFG.get("dark") else LIGHT_CSS) + "</head>", 1)
    return page


def with_nav(page):
    """Every page gets the app frame and the chosen colours."""
    return app_frame(themed(page))


def replace_page(web, page):
    """Put a whole new page into the one already showing (no blank white reload).
    False if the current page can't do that, so the caller loads it normally."""
    try:
        if web.evaluate_javascript("typeof window.__load") == "function":
            web.evaluate_javascript("window.__load(%s)" % json.dumps(page))
            return True
    except Exception:
        pass
    return False


def swap_page(webview, page):
    """Redraw the page you're on without jumping to the top (falls back to a full reload)."""
    page = with_nav(page)
    body = page.split("<body>", 1)[1].rsplit("</body>", 1)[0] if "<body>" in page else None
    try:
        if body is None:
            raise ValueError
        webview.evaluate_javascript("window.__swap(%s)" % json.dumps(body))
    except Exception:
        webview.load_html(page)


def present(page, keeper=None):
    """Show a page in the same window (no sliding away). Browser outside Pythonista."""
    page = with_nav(page)
    if not in_pythonista():
        import webbrowser
        path = os.path.join(HERE, "combos_view.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        print(f"Page saved to {path}")
        webbrowser.open("file://" + path)
        return
    web = _web()
    web.delegate = NavKeeper(keeper)
    screen = (APP.get("where"), (re.search(r"<title>([^<]*)</title>", page) or re.search(r"<h1>([^<]*)", page) or [None, ""])[1])
    body = page.split("<body>", 1)[1].rsplit("</body>", 1)[0] if "<body>" in page else None
    if APP.get("page") == "page" and APP.get("screen") == screen and body is not None:
        try:
            web.evaluate_javascript("window.__swap(%s)" % json.dumps(body))
            APP["quiet"] = False
            return
        except Exception:
            pass
    if not (APP.get("page") in ("page", "loading") and replace_page(web, page)):
        web.load_html(page)
    APP["page"] = "page"
    APP["screen"] = screen
    APP["quiet"] = False


MINE = {"live": False, "thread": None, "hold": {}, "cash": {}}


def show_mine(all_games, days, sunday):
    """Your combos already placed on Kalshi for this week, with optional live alerts."""
    APP["where"] = "mine"
    book, notes = {}, []
    if CFG["odds_key"]:
        loading("Getting sportsbook odds…")
        book, n = fetch_book_odds(CFG["odds_key"])
        notes.append(n)
    MINE.update({"all_games": all_games, "days": days, "sunday": sunday, "book": book,
                 "notes": notes, "live": False, "last": None})
    page, MINE["snap"] = mine_page()

    present(page, MineKeeper())
    if CFG.get("auto_live", True) and MINE.get("hold") and APP.get("web") is not None and in_pythonista():
        set_live(APP["web"], True)


@safe_delegate
class MineKeeper:
    def webview_should_start_load(self, webview, url, nav_type):
        if url.startswith("combo://live/"):
            set_live(webview, url.endswith("/on"))
            return False
        if url.startswith("combo://cash/"):
            import threading
            action, _, ticker = url[len("combo://cash/"):].partition("/")
            threading.Thread(target=cash_action, args=(action, ticker.strip("/")), daemon=True).start()
            return False
        if url.startswith("combo://settings"):
            MINE["live"] = False
            reopen_settings(webview)
            return False
        return not url.startswith("combo://")


def set_live(webview, on):
    """Turn game-day alerts on/off. While on: check every 2 minutes, refresh, notify."""
    import threading
    MINE["live"] = on
    try:
        import console
        console.set_idle_timer_disabled(on)      # keep the screen awake while watching
    except Exception:
        pass
    if on and not (MINE["thread"] and MINE["thread"].is_alive()):
        MINE["thread"] = threading.Thread(target=live_loop, args=(webview,), daemon=True)
        MINE["thread"].start()
    elif not on:
        webview.evaluate_javascript("liveState(false, '')")


def live_loop(webview):
    import time
    first = True
    while MINE["live"] and window_open():
        if not first:
            for _ in range(max(5, int(CFG.get("refresh_secs", 15)))):   # stop quickly when switched off
                if not MINE["live"] or not window_open():
                    return
                time.sleep(1)
        first = False
        try:
            live_check(webview)
        except Exception as err:
            try:
                webview.evaluate_javascript("liveState(true, %s)" % json.dumps(
                    f"Couldn't check just now ({str(err)[:60]}). Trying again in 2 minutes."))
            except Exception:
                pass


def live_check(webview):
    """One refresh: current prices and results, redraw the page, send any alerts."""
    all_games, days, _ = week_games(fetch_markets(), loose=True)
    MINE["all_games"].update(all_games)    # current prices, keeps finished games
    MINE["days"].update(days)
    MINE["book"] = {}                      # live chances use Kalshi's in-game prices
    if MINE.get("busy"):
        return []
    MINE["last"] = dt.datetime.now().strftime("%-I:%M %p")
    expire_offers()
    cash_alerts = auto_cash_checks()
    APP["quiet"] = True
    page, snap = mine_page(live=True)
    alerts = diff_alerts(MINE.get("snap") or {}, snap) + cash_alerts
    MINE["snap"] = snap
    present(page, MineKeeper())
    for msg in alerts[:4]:
        notify(msg)
    return alerts


def notify(msg):
    try:
        import notification
        notification.schedule(msg, delay=0, sound_name="default")
    except Exception:
        console_note(msg)


def diff_alerts(old, new):
    """Plain-English alerts for picks and combos that were decided since the last check."""
    alerts, leg_news = [], {}
    for t, c in new.items():
        o = old.get(t)
        if not o:
            continue
        if c["status"] != o["status"] and c["status"] in ("won", "lost"):
            if c["status"] == "won":
                alerts.append(f"🎉 {c['label']} hit! Pays {money(c['pays'])}.")
            else:
                why = next((n for lt, (n, r) in c["legs"].items() if r == "no" and o["legs"].get(lt, (n, None))[1] != "no"), None)
                alerts.append(f"❌ {c['label']} is out" + (f": {why} lost." if why else "."))
        elif c["status"] == "pending":
            for lt, (name, r) in c["legs"].items():
                if r == "yes" and o["legs"].get(lt, (name, None))[1] != "yes":
                    left = sum(1 for _, (_, rr) in c["legs"].items() if not rr)
                    leg_news.setdefault(name, []).append((c["label"], left))
    for name, combos in leg_news.items():
        alive = ", ".join(f"{lab} ({left} left)" for lab, left in combos[:3])
        alerts.append(f"✅ {name} won. Still alive: {alive}.")
    return alerts


# ================================================================ cash out
OFFER_LIFE = 150      # minimum seconds a cash-out offer is kept (see offer_life)


def offer_life():
    """Keep each offer until the next fresh one is due, so there's always one to confirm."""
    return max(OFFER_LIFE, int(CFG.get("cash_every", 2) * 60) + 45)


def single_value(p, pays, W):
    """What a p chance of `pays` is worth to you as a sure amount, given money W
    (your bankroll plus what's locked in). Bigger amounts get discounted more."""
    if pays <= 0 or p <= 0:
        return 0.0
    return math.exp(p * math.log(W + pays) + (1 - p) * math.log(W)) - W


def fresh_offer(t):
    import time
    o = MINE["cash"].get(t)
    if o and o.get("offer") and o.get("rfq") and time.time() - o["at"] <= offer_life() and t in MINE["hold"]:
        return o
    return None


def weekend_stats(acts):
    """Average, guaranteed part and chance of nothing more, for a hold/cash choice per combo."""
    live, pats = MINE["hold"], MINE.get("patterns") or {}
    W = max(CFG["bankroll"], 1) + MINE.get("locked", 0)
    sure = sum(f * live[t]["pays"] * acts_price(t) for t, f in acts.items() if f)
    n = sum(pats.values()) or 1
    eu = mean = zero = 0.0
    for pat, c in pats.items():
        x = sure + sum((1 - acts.get(t, 0)) * live[t]["pays"] for t in pat if t in live)
        eu += c * math.log(W + x)
        mean += c * x
        zero += c if x - sure < 0.005 else 0
    return {"eu": eu / n, "mean": mean / n, "sure": sure, "nothing": zero / n,
            "worth": math.exp(eu / n) - W}


def acts_price(t):
    o = fresh_offer(t)
    return o["offer"] / o["contracts"] if o and o["contracts"] else 0.0


def plan_cashout():
    """Best mix of hold / cash out half / cash out all across your live combos, judged
    together (combos that need the same team rise and fall together) and weighed for
    your bankroll. Only combos with a fresh Kalshi offer can be cashed."""
    offers = [t for t in MINE["hold"] if fresh_offer(t)]
    if not offers or not MINE.get("patterns"):
        return None
    acts = {t: 0.0 for t in offers}
    best = weekend_stats(acts)["worth"]
    for _ in range(3):
        changed = False
        for t in sorted(offers, key=lambda x: -MINE["hold"][x]["hold"]):
            for f in (0.0, 0.5, 1.0):
                if f == acts[t]:
                    continue
                trial = dict(acts, **{t: f})
                v = weekend_stats(trial)["worth"]
                if v > best + 0.10:               # ignore changes worth only pennies
                    best, acts, changed = v, trial, True
        if not changed:
            break
    return {"acts": acts, "plan": weekend_stats(acts), "hold": weekend_stats({t: 0.0 for t in offers})}


def plan_words(t, f, o, h, W):
    """One short reason for the verdict on one combo."""
    p, pays = h["p"], h["pays"]
    shared = any(sum(1 for x in MINE["hold"].values() if k in dict(x["need"])) > 1 for k, _ in h["need"])
    if f == 1:
        return f"A sure {money(o['offer'])} beats a {p:.0%} shot at {money(pays)} for you." + \
            (" Also spreads risk off a game your other combos need." if shared else "")
    if f == 0.5:
        return f"Locks in half and keeps a {p:.0%} shot at {money(pays / 2)}."
    return f"Holding is worth about {money(single_value(p, pays, W))} to you, more than this offer."

def confirm_parts(t, h, o):
    """(title, details, url, button) for the confirm sheet: exactly what happens."""
    what = "half of " if o.get("frac", 1.0) < 1 else ""
    title = f"Cash out {what}{h['label']} for {money(o['offer'])}?"
    sub = (f"You paid {money(h['cost'] * o.get('frac', 1.0))}. If you hold instead: "
           f"{h['p']:.0%} chance of {money(h['pays'] * o.get('frac', 1.0))}.")
    return title, sub, f"combo://cash/go/{t}", f"Cash out for {money(o['offer'])}"


def confirm_cash(t, h, o):
    """onclick for a Cash out button: a bottom sheet that says exactly what happens."""
    args = ",".join(json.dumps(x) for x in confirm_parts(t, h, o))
    return html.escape(f"sheet({args})")


def action_button(t, f, h):
    """The button that carries out the plan for one combo (needs an offer of the right size)."""
    o = fresh_offer(t)
    te = html.escape(t)
    if not o or f == 0:
        return ""
    if abs(o.get("frac", 1.0) - f) < 0.01:
        what = "half of " if f < 1 else ""
        return (f"<button class='btn go cashb' onclick=\"{confirm_cash(t, h, o)}\">Cash out {what}"
                f"{html.escape(h['label'])} for {money(o['offer'])}</button>")
    # Kalshi quotes one size at a time, so this price is worked out from the offer in hand;
    # tapping gets the exact offer for this size and asks you to confirm it.
    est = acts_price(t) * h["pays"] * f
    act = "askhalfgo" if f < 1 else "askgo"
    return (f"<button class='btn go cashb' onclick=\"cash('{act}','{te}')\">Cash out "
            f"{'half of ' if f < 1 else ''}{html.escape(h['label'])} · about {money(est)}</button>")


def cash_block(ticker, plan):
    """The short hold-or-cash-out box on a live combo card."""
    h = MINE["hold"].get(ticker)
    if not h:
        return ""
    t = html.escape(ticker)
    W = max(CFG["bankroll"], 1) + MINE.get("locked", 0)
    p, pays = h["p"], h["pays"]
    pct = f"{p:.0%}" if p >= 0.01 or p == 0 else f"{p:.1%}"
    out = [f"<div class='min cashbox'>If you hold: <b>{pct}</b> chance of <b>{money(pays)}</b>"
           f" <span class='muted'>· worth a sure {money(single_value(p, pays, W))} to you</span>"
           + ("<div class='muted' style='font-size:12px;margin-top:4px'>Chance from Kalshi's price for the whole "
              "combo: its picks are in the same game and move together.</div>" if h.get("rough") else "")]
    tp = (MINE.get("tp") or {}).get(ticker)
    if tp:
        o0 = tp[0]
        price = dollars(o0, "yes_price")
        left = count_of({"count_fp": o0.get("remaining_count_fp") or o0.get("remaining_count")}) or pays
        out.append(f"<div style='margin-top:6px'>🎯 Auto-sell on Kalshi: sells if a buyer pays "
                   f"<b>{money(price * left)}</b> <button class='btn cashb' style='padding:3px 8px' "
                   f"onclick=\"cash('tpx','{t}')\">Cancel</button></div>")
    elif can_trade():
        target, why = tp_target(h["cost"], pays, worth_now(ticker))
        if target:
            out.append(f"<div class='quote'><button class='btn cashb' onclick=\"cash('tp','{t}')\">"
                       f"Set auto-sell at {money(target)} {why}</button></div>")
    raw = MINE["cash"].get(ticker)
    o = fresh_offer(ticker)
    if raw and raw.get("error"):
        out.append(f"<div class='muted' style='font-size:13px;margin-top:6px'>{html.escape(raw['error'])}</div>")
    if o:
        f = (plan or {}).get("acts", {}).get(ticker, 0.0)
        word, cls = {1.0: ("Cash out", "ok"), 0.5: ("Cash out half", "ok")}.get(f, ("Hold", "no"))
        size = " for half" if o.get("frac", 1.0) < 1 else ""
        main = action_button(ticker, f, h) if f else ""
        if not main:
            main = (f"<button class='btn cashb' onclick=\"{confirm_cash(ticker, h, o)}\">Cash out"
                    f"{' half' if size else ''} for {money(o['offer'])}</button>")
        out.append(f"<div style='margin-top:8px'>Kalshi offers <b>{money(o['offer'])}</b>{size} "
                   f"<span class='verdict {cls}'>{word}</span></div>"
                   f"<div class='muted' style='font-size:13px;margin-top:4px'>{plan_words(ticker, f, o, h, W)}</div>"
                   f"<div class='quote'>{main}<button class='btn cashb' onclick=\"cash('no','{t}')\">Keep it</button></div>")
    else:
        tag = "<span class='tag good'>Worth checking</span> " if h["worth"] else ""
        out.append(f"<div class='quote'>{tag}<button class='btn cashb' onclick=\"cash('ask','{t}')\">"
                   f"Get cash-out offer</button></div>")
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------- scores
SCORES_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SCORES = {"at": 0, "by_team": {}}


def fetch_scores(max_age=45):
    """Live scores by full team name (ESPN's free scoreboard). Empty if it can't be reached."""
    import time
    if time.time() - SCORES["at"] < max_age:
        return SCORES["by_team"]
    by = {}
    try:
        q = dict(LG()["espn_q"])
        if LG()["slate"] == "day":              # teams play most nights: get yesterday to 3 days out
            today = dt.date.today()
            q.update(dates=f"{today - dt.timedelta(days=1):%Y%m%d}-{today + dt.timedelta(days=3):%Y%m%d}", limit=200)
        r = requests.get(SCORES_URL, params=q, timeout=8)
        events = r.json().get("events", []) if r.ok else []
        if not events and "dates" in q:
            r = requests.get(SCORES_URL, params=LG()["espn_q"], timeout=8)
            events = r.json().get("events", []) if r.ok else []
        for ev in events:
            comp = (ev.get("competitions") or [{}])[0]
            st = comp.get("status") or ev.get("status") or {}
            typ = st.get("type") or {}
            state = typ.get("state", "")
            if state == "post":
                detail = "Final" + (" OT" if (st.get("period") or 0) > LG()["periods"] else "")
            elif state == "in":
                per, n_per = st.get("period") or 0, LG()["periods"]
                label = ("OT" if per > n_per else ("Q" if n_per == 4 else "H") + str(per))
                detail = ("Half" if "HALFTIME" in typ.get("name", "") else
                          f"{label} {st.get('displayClock', '')}".strip())
            else:
                detail = typ.get("shortDetail", "")
            sit = comp.get("situation") or {}
            teams = comp.get("competitors") or []
            if len(teams) != 2:
                continue
            for me, opp in ((teams[0], teams[1]), (teams[1], teams[0])):
                name = (me.get("team") or {}).get("displayName")
                if not name:
                    continue
                info = {"me": int(float(me.get("score") or 0)), "opp": int(float(opp.get("score") or 0)),
                            "abbr": (me.get("team") or {}).get("abbreviation", ""),
                            "opp_abbr": (opp.get("team") or {}).get("abbreviation", ""),
                            "opp_name": (opp.get("team") or {}).get("displayName", ""),
                            "state": state, "detail": detail,
                            "ball": str(sit.get("possession", "")) == str(me.get("id") or (me.get("team") or {}).get("id")),
                            "redzone": bool(sit.get("isRedZone")),
                            "game": ev.get("id"), "day": espn_day(ev.get("date"))}
                tm = me.get("team") or {}
                for alt in {name, norm_team(name), norm_team(tm.get("shortDisplayName") or ""),
                            norm_team(tm.get("location") or "")} - {""}:
                    by.setdefault(alt, []).append(info)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return SCORES["by_team"]
    SCORES.update(at=time.time(), by_team=by)
    return by


def espn_day(iso):
    """US game date of an ESPN start time (ESPN gives UTC; a 10 PM Eastern tip-off is 3 AM UTC)."""
    try:
        t = dt.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        return (t - dt.timedelta(hours=5)).date()
    except ValueError:
        return None


def ticker_day(ticker):
    """Game date written in a Kalshi ticker, e.g. KXNBAGAME-26NOV16PHIIND -> 2026-11-16."""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", ticker or "")
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2).title() + m.group(3), "%y%b%d").date()
    except ValueError:
        return None


def pick_game(games, day):
    """The game in the list played on `day` (the pick's own game), never another night's."""
    if not games:
        return None
    if day is None:
        return games[0] if len({g["game"] for g in games}) == 1 else None
    return next((g for g in games if g["day"] == day), None)


def leg_score(l):
    """Score of the game this pick is on, from the point of view of the team it needs, or None.
    Only that exact game: a team's result from another night is never shown."""
    abbr = (l["ticker"] or "").rsplit("-", 1)[-1]
    name = TEAMS.get(abbr) or PICK_NAME.get(l["ticker"] or "", "")
    by = SCORES["by_team"]
    games = (by.get(name) or by.get(norm_team(name)) or by.get(norm_team(" ".join(name.split()[-2:])))
             or by.get(norm_team(name.split()[-1]))) if name else None
    sc = pick_game(games, ticker_day(l["ticker"]))
    if not sc:
        return None
    if l.get("side", "yes") == "no":           # betting against this team
        sc = next((g for g in by.get(sc["opp_name"], []) if g["game"] == sc["game"]), sc)
    return sc


def score_line(sc):
    if not sc or sc["state"] == "pre":
        return ""
    lead = sc["me"] - sc["opp"]
    cls = "pos" if lead > 0 else "neg" if lead < 0 else "muted"
    ball = " 🏈" if sc["ball"] and sc["state"] == "in" else ""
    return (f"<span class='{cls}'>{sc['abbr']} {sc['me']}–{sc['opp']} {sc['opp_abbr']}</span>"
            f" <span class='muted'>{html.escape(sc['detail'])}{ball}</span>")


def right_now_html(mine, infos, snap, plan):
    """Top of My combos, kept short: the games that matter, the money, and what to do."""
    e = html.escape
    live = MINE["hold"]
    if not live and not MINE.get("locked"):
        return ""
    out = ["<div class='batch now'><b>Right now</b>"]
    seen, rows = set(), []
    for a, inf in zip(mine, infos):
        if a["ticker"] not in live:
            continue
        for l, (nm, _, _, r) in zip(a["legs"], inf):
            sc = leg_score(l)
            if r or not sc or (sc["abbr"], sc["opp_abbr"]) in seen:
                continue
            seen.add((sc["abbr"], sc["opp_abbr"]))
            n = sum(1 for x in live.values() if any(nm2 == nm for _, nm2 in x["need"]))
            line = score_line(sc) or f"<span class='muted'>{e(sc['detail'])}</span>"
            rows.append((sc["state"] != "in", f"<div class='row' style='font-size:14px'><span>Need <b>{e(nm)}</b>"
                         f" <span class='muted'>· {n} combo{'s' if n != 1 else ''}</span></span><span>{line}</span></div>"))
    rows.sort(key=lambda x: x[0])                     # games being played first
    out += [r for _, r in rows[:6]]
    locked = MINE.get("locked", 0)
    worth = sum(h["hold"] for h in live.values())
    out.append(f"<div class='muted' style='font-size:13px;margin-top:6px'>Locked in {money(locked)} · "
               f"{len(live)} live combo{'s' if len(live) != 1 else ''} worth about {money(worth)}</div>")
    if live and plan:
        todo = sorted(((t, f) for t, f in plan["acts"].items() if f), key=lambda x: -live[x[0]]["hold"])
        if todo:
            out += [f"<div class='quote'>{action_button(t, f, live[t])}</div>" for t, f in todo[:3]]
            ho = plan["hold"]
            out.append(f"<div class='muted' style='font-size:13px;margin-top:4px'>Locks in "
                       f"{money(plan['plan']['sure'])}. Holding everything instead: {ho['nothing']:.0%} chance "
                       f"of nothing more.</div>")
        else:
            out.append("<div style='margin-top:8px'><span class='verdict no'>Hold everything</span> "
                       "<span class='muted' style='font-size:13px'>Today's offers are worth less to you than holding.</span></div>")
    missing = [t for t in live if not fresh_offer(t)]
    if missing and can_trade():
        out.append(f"<div class='quote'><button class='btn cashb' onclick=\"cash('askall','all')\">"
                   f"Get cash-out offers{' for the rest' if len(missing) < len(live) else ''}</button></div>")
    out.append("</div>")
    return "".join(out)


def risk_html(mine, infos, snap):
    """Which single game most of your live money rides on, in dollars."""
    need = defaultdict(lambda: {"n": 0, "hold": 0.0, "pays": 0.0, "name": ""})
    for a, inf in zip(mine, infos):
        h = MINE["hold"].get(a["ticker"])
        if not h or snap.get(a["ticker"], {}).get("status") != "pending":
            continue
        for l, (nm, _, _, r) in zip(a["legs"], inf):
            if r:
                continue
            k = (l.get("side", "yes"), l["ticker"])
            need[k]["n"] += 1
            need[k]["hold"] += h["hold"]
            need[k]["pays"] += h["pays"]
            need[k]["name"] = nm
    if not need:
        return ""
    top = sorted(need.values(), key=lambda d: -d["hold"])[:3]
    rows = "".join(f"<div class='row'><span>If <b>{html.escape(d['name'])}</b> loses</span>"
                   f"<span>{d['n']} combo{'s' if d['n'] != 1 else ''} · <b>{money(d['hold'])}</b></span></div>"
                   for d in top)
    total = sum(h["hold"] for h in MINE["hold"].values())
    return (f"<div class='batch'><div><b>Money riding on one game</b></div>"
            f"<div class='muted' style='font-size:13px'>Your live combos are worth about {money(total)} "
            f"right now. This is how much of that goes to $0 if one pick loses.</div>{rows}</div>")


def resting_sells():
    """Your auto-sell orders waiting on Kalshi: {combo ticker: [order, ...]}."""
    try:
        data = kalshi_send("GET", "/portfolio/orders", params={"status": "resting", "limit": 200}) or {}
    except Exception:
        return {}
    out = defaultdict(list)
    for o in data.get("orders", []):
        if o.get("action") == "sell" and is_combo(o.get("ticker")):
            out[o["ticker"]].append(o)
    return dict(out)


def tp_target(cost, pays, worth_now=0.0):
    """The auto-sell amount: your multiple of what you paid, but never near or above what the
    combo pays (it can't sell for more than that), and always well above what it's worth right
    now (a lower standing order could sell it cheap). Returns (amount, label) or (None, '')."""
    floor = max(1.3 * cost, 1.25 * worth_now)
    want = cost * CFG["tp_mult"]
    if floor <= want <= 0.9 * pays:
        return want, f"({CFG['tp_mult']}×)"
    cap = 0.9 * pays                              # 90% of the payout: most of the win, without waiting
    if cap >= floor:
        return cap, "(90% of the payout)"
    return None, ""


def worth_now(ticker):
    """What a live combo is worth right now: the better of its average value and a fresh offer."""
    h = MINE["hold"].get(ticker) or {}
    o = fresh_offer(ticker) if ticker in MINE["hold"] else None
    return max(h.get("hold", 0.0), (o or {}).get("offer", 0.0) / max((o or {}).get("frac", 1.0), 0.01))


def place_take_profit(ticker, contracts, cost):
    """Put a standing sell order on Kalshi at tp_mult x what you paid. Kalshi keeps it
    working with your phone closed; it only fills if a buyer pays that much."""
    n = math.floor(contracts * 100 + 1e-6) / 100
    if n < 1:
        return "Auto-sell needs at least 1 contract."
    total, why = tp_target(cost, n, worth_now(ticker))
    if not total:
        return ("No auto-sell for this one: it's already worth close to what it pays, or it doesn't pay "
                "enough above what you paid. Hold it, or cash out when you like the offer.")
    target = total / n                                    # per contract
    import uuid
    tries = [{"count_fp": f"{n:.2f}", "yes_price_dollars": f"{max(target, 0.0001):.4f}"},
             {"count": int(n), "yes_price_dollars": f"{max(math.ceil(target * 100) / 100, 0.01):.2f}"}]
    last = ""
    for extra in tries:
        body = dict({"ticker": ticker, "action": "sell", "side": "yes", "type": "limit",
                     "time_in_force": "good_till_canceled", "reduce_only": True,
                     "client_order_id": str(uuid.uuid4())}, **extra)
        try:
            kalshi_send("POST", "/portfolio/orders", body)
            price = float(extra["yes_price_dollars"])
            cnt = float(extra.get("count_fp") or extra.get("count"))
            return (f"🎯 Auto-sell order placed: Kalshi will sell if a buyer pays {money(price * cnt)} "
                    f"{why}. It stays on Kalshi with your phone closed.")
        except PermissionError:
            return "Kalshi refused. Your API key needs write (trading) access for auto-sell orders."
        except (RuntimeError, requests.RequestException) as err:
            last = str(err)[:120]
    return f"Kalshi didn't accept the auto-sell order ({last}). It may not allow resting orders on this combo."


def cancel_take_profit(ticker):
    n = 0
    for o in resting_sells().get(ticker, []):
        try:
            kalshi_send("DELETE", f"/portfolio/orders/{o.get('order_id')}")
            n += 1
        except Exception:
            pass
    return n


def drop_cash(ticker):
    o = MINE["cash"].pop(ticker, None)
    if o and o.get("rfq"):
        try:
            kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
        except Exception:
            pass


def expire_offers():
    import time
    for t, o in list(MINE["cash"].items()):
        if o.get("rfq") and time.time() - o["at"] > offer_life():
            try:
                kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
            except Exception:
                pass
            o["rfq"] = None


def clear_my_rfqs(ticker):
    """Cancel your own open price requests for one combo (e.g. left over after a restart).
    Kalshi allows only one at a time per combo."""
    try:
        data = kalshi_send("GET", "/communications/rfqs",
                           params={"market_ticker": ticker, "status": "open", "user_filter": "self"}) or {}
    except Exception:
        return
    for r in data.get("rfqs", []):
        if r.get("market_ticker") == ticker and r.get("id"):
            try:
                kalshi_send("DELETE", f"/communications/rfqs/{r['id']}")
            except Exception:
                pass


def get_cash_offer(ticker, frac=1.0):
    """Ask Kalshi what it will pay for the contracts you hold (or half). Nothing is sold here."""
    import time
    h = MINE["hold"].get(ticker)
    if not h:
        return {"error": "That combo isn't live any more.", "at": time.time()}
    n = math.floor(h["pays"] * frac * 100 + 1e-6) / 100   # never offer more than you hold
    if n < 0.01:
        return {"error": "Nothing left to cash out on this combo.", "at": time.time()}
    drop_cash(ticker)
    clear_my_rfqs(ticker)
    try:
        rfq = kalshi_send("POST", "/communications/rfqs",
                          {"market_ticker": ticker, "contracts_fp": f"{n:.2f}",
                           "rest_remainder": False, "replace_existing": False})["id"]
        best, start = None, time.time()
        while time.time() - start < 20:
            time.sleep(1.5)
            quotes = kalshi_send("GET", "/communications/quotes",
                                 params={"rfq_id": rfq, "rfq_user_filter": "self"}).get("quotes", [])
            for q in quotes:
                if q.get("status") != "open" or not q.get("yes_bid_dollars"):
                    continue
                price = float(q["yes_bid_dollars"])        # they buy your YES at this price
                if 0 < price < 1 and (best is None or price > best[0]):
                    best = (price, q)
            if best and time.time() - start > 5:
                break
    except PermissionError:
        return {"error": "Kalshi refused. Your API key needs write (trading) access to cash out.", "at": time.time()}
    except (RuntimeError, requests.RequestException, KeyError) as err:
        return {"error": f"Couldn't get an offer just now ({str(err)[:90]}). Try again, or cash out in the Kalshi app.",
                "at": time.time()}
    if not best:
        try:
            kalshi_send("DELETE", f"/communications/rfqs/{rfq}")
        except Exception:
            pass
        return {"error": "No cash-out offers came in. Try again in a minute, or check the Kalshi app.",
                "at": time.time()}
    price, q = best
    return {"rfq": rfq, "quote": q["id"], "price": price, "contracts": n, "offer": round(n * price, 2),
            "frac": frac, "at": time.time()}


def accept_cash(ticker):
    """Sell: hit their YES bid with the contracts you hold. Only runs after you tap Cash out."""
    import time
    o = MINE["cash"].pop(ticker, None)
    label = (MINE["hold"].get(ticker) or {}).get("label", "That combo")
    if o and o.get("frac", 1.0) < 1:
        label = "Half of " + label
    if not o or not o.get("rfq") or time.time() - o["at"] > offer_life():
        return f"{label}: that offer expired. Tap Get cash-out offer for a fresh one."
    if (MINE.get("tp") or {}).get(ticker):
        cancel_take_profit(ticker)
    try:
        kalshi_send("PUT", f"/communications/rfqs/{o['rfq']}/quotes/{o['quote']}/accept",
                    {"accepted_side": "yes"})
    except (RuntimeError, PermissionError, requests.RequestException) as err:
        MINE["cash"][ticker] = get_cash_offer(ticker, o.get("frac", 1.0))
        new = MINE["cash"][ticker].get("offer")
        return (f"{label}: that offer had expired, so nothing was sold. "
                + (f"Fresh offer: {money(new)}. Tap Cash out again to confirm." if new else
                   f"No fresh offer came in yet. ({str(err)[:60]})"))
    status, start = "accepted", time.time()
    while time.time() - start < 15 and status not in ("executed", "cancelled"):
        time.sleep(1)
        try:
            q = kalshi_send("GET", f"/communications/rfqs/{o['rfq']}/quotes/{o['quote']}") or {}
            status = (q.get("quote") or q).get("status", status)
        except Exception:
            pass
    try:
        kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
    except Exception:
        pass
    ACCT_CACHE["at"] = 0
    if status == "executed":
        haptic("success")
        return f"✅ {label} cashed out for about {money(o['offer'])}."
    if status == "cancelled":
        return f"{label}: the buyer backed out before confirming, so nothing was sold. Get a fresh offer."
    return (f"{label}: still waiting on Kalshi. Check this page again in a minute before trying again, "
            "so you don't sell twice.")


def cash_action(action, ticker):
    """Buttons on a combo card: ask for an offer, cash out, or keep it."""
    MINE["busy"] = True                     # the 2-minute refresh waits until this is done
    APP["quiet"] = True                      # update the page in place, no loading screen
    confirm_after = None
    try:
        if action == "tp":
            loading("Placing your auto-sell order on Kalshi…")
            h = MINE["hold"].get(ticker) or {}
            MINE["flash"] = place_take_profit(ticker, h.get("pays", 0), h.get("cost", 0))
        elif action == "tpx":
            loading("Cancelling the auto-sell order…")
            n = cancel_take_profit(ticker)
            MINE["flash"] = "Auto-sell order cancelled." if n else "No auto-sell order to cancel."
        elif action in ("ask", "askhalf", "askgo", "askhalfgo"):
            loading("Getting Kalshi's exact offer…" if action.endswith("go") else "Asking Kalshi for a cash-out offer…")
            MINE["cash"][ticker] = get_cash_offer(ticker, 0.5 if "half" in action else 1.0)
            if action.endswith("go"):
                confirm_after = ticker
        elif action == "askall":
            from concurrent.futures import ThreadPoolExecutor
            want = [t for t in MINE["hold"] if not fresh_offer(t)]
            loading(f"Asking Kalshi for offers on {len(want)} combo{'s' if len(want) != 1 else ''}…")
            with ThreadPoolExecutor(max_workers=4) as pool:
                for t, o in zip(want, pool.map(get_cash_offer, want)):
                    MINE["cash"][t] = o
        elif action == "go":
            loading("Cashing out…")
            MINE["flash"] = accept_cash(ticker)
        else:
            drop_cash(ticker)
        redraw_mine()
    except Exception as err:
        present(error_page(f"Something went wrong: {type(err).__name__}: {err}"))
        confirm_after = None
    finally:
        MINE["busy"] = False
    o = fresh_offer(confirm_after) if confirm_after else None
    if o and APP.get("web") is not None:          # straight to "Cash out for $X?" with the exact price
        native_confirm(APP["web"], *confirm_parts(confirm_after, MINE["hold"][confirm_after], o))


def redraw_mine():
    page, MINE["snap"] = mine_page(live=MINE["live"])
    if MINE["live"]:
        page = page.replace("var LIVE=false", "var LIVE=true")
    present(page, MineKeeper())


def before_risky_game():
    """Live combos whose next undecided game starts within 20 minutes, after at least one
    pick has already won: the moment to look at a cash-out. {ticker: (game label, start)}"""
    out = {}
    now = dt.datetime.now(dt.timezone.utc)
    for t, h in MINE["hold"].items():
        if not h.get("won_some"):
            continue
        starts = [(start_dt(ev), nm) for (side, lt), nm in h["need"]
                  for ev in [(lt or "").rsplit("-", 1)[0]] if start_dt(ev)]
        future = sorted((s, nm) for s, nm in starts if s > now)
        if future and future[0][0] - now <= dt.timedelta(minutes=20):
            out[t] = (future[0][1], future[0][0])
    return out


def auto_cash_checks():
    """While Live is open: keep a fresh cash-out offer on every live combo (every few minutes,
    per Settings) so Cash out is always one confirm away, and alert when the plan says to
    cash something out. Never sells on its own."""
    import time
    if not CFG["auto_cash"] or not can_trade():
        return []
    soon = before_risky_game()
    for t, (nm, when) in soon.items():
        if MINE.setdefault("warned", {}).get(t):
            continue
        MINE["warned"][t] = True
        o = get_cash_offer(t)
        MINE["cash"][t] = o
        h = MINE["hold"][t]
        if o.get("offer"):
            MINE.setdefault("pre_alerts", []).append(
                f"⏱ {h['label']}: {nm} starts at {when.astimezone():%-I:%M %p}. Kalshi offers "
                f"{money(o['offer'])} to cash out now (holding: {h['p']:.0%} chance of {money(h['pays'])}).")
    due = [t for t, h in MINE["hold"].items() if h.get("left", 1) > 0
           and not (MINE["cash"].get(t) and time.time() - MINE["cash"][t]["at"] < CFG["cash_every"] * 60 - 10)]
    fresh = []
    if due:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            for t, o in zip(due, pool.map(get_cash_offer, due)):
                MINE["cash"][t] = o
                fresh.append(t)
    plan = plan_cashout() if fresh else None
    alerts = MINE.pop("pre_alerts", [])
    if not plan:
        return alerts
    # Push only when cashing out clearly pays (worth at least $1, or 5% of what it locks in, more
    # to you than holding), and only once per recommendation: again only if the offer has
    # risen 20%+ or the advice grows from half to all, never more than every 10 minutes.
    gain = plan["plan"]["worth"] - plan["hold"]["worth"]
    if gain < max(1.0, 0.05 * plan["plan"]["sure"]):
        return alerts
    told = MINE.setdefault("alerted", {})
    news = []
    for t, f in plan["acts"].items():
        o, h = fresh_offer(t), MINE["hold"].get(t)
        if not (f and o and h):
            continue
        amt = acts_price(t) * h["pays"] * f
        last = told.get(t)
        if last and (time.time() - last["at"] < 600 or (amt < last["amt"] * 1.2 and f <= last["f"])):
            continue
        told[t] = {"f": f, "amt": amt, "at": time.time()}
        news.append(f"{'half of ' if f < 1 else ''}{h['label']} for {money(amt)}")
    if news:
        alerts.append(f"💰 Good time to cash out {', '.join(news)}: worth about {money(gain)} more "
                      "to you than holding. Open the planner to confirm.")
    return alerts

def mine_page(live=False):
    """Build the My Kalshi combos page. Returns (page, snapshot for alerts)."""
    all_games, sunday = MINE["all_games"], MINE["sunday"]
    e = html.escape
    if not live:
        loading("Reading your Kalshi account…")
    acct, balance, note = fetch_account()
    head = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>My Kalshi combos</title><style>{CSS}</style></head><body>")
    if acct is None:
        msg = note or "Connect your Kalshi account in settings first."
        return (head + f"<header><h1>My Kalshi combos</h1></header>"
                f"<section id='combos'><div class='empty'>{e(msg)}</div></section></body></html>"), {}

    notes = [note] + ([] if live else MINE["notes"]) + ([MINE["notice"]] if MINE.get("notice") else [])
    if live:
        notes.append("Live chances use Kalshi's current in-game prices.")
    attach_fair(all_games, MINE["book"])
    pregame = load_json(PREGAME, {}) if live else remember_pregame(all_games)
    side_of = {s["ticker"]: s for v in all_games.values() for s in v}

    mine = [a for a in acct if in_week(a, sunday.isoformat())] or \
        [a for a in acct if a["status"] == "pending"]
    if not live:
        loading("Checking game results…")
    results = fetch_results({l["ticker"] for a in mine for l in a["legs"] if l["ticker"]}
                            | {a["ticker"] for a in mine if not a.get("winners", True) and a["status"] == "pending"})
    rough = {a["ticker"]: (MARKET_INFO.get(a["ticker"]) or {}).get("live")
             for a in mine if not a.get("winners", True)}   # same-game stat combos: Kalshi's price
    if not live:
        loading("Working out your chances…")

    def leg_info(l):
        """(name, opponent, chance, result) for one pick, from the bettor's side."""
        s = side_of.get(l["ticker"])
        res = results.get(l["ticker"])
        abbr = (l["ticker"] or "").rsplit("-", 1)[-1]
        if l.get("side", "yes") == "no":            # betting a team NOT to win
            res = {"yes": "no", "no": "yes"}.get(res)
            if s:
                other = next(x for x in all_games[s["event"]] if x is not s)
                return other["pick"], s["pick"], other["fair"], res
            return f"Against {TEAMS.get(abbr, abbr)}", "", None, res
        if s:
            other = next(x for x in all_games[s["event"]] if x is not s)
            return s["pick"], other["pick"], s["fair"], res
        info = MARKET_INFO.get(l["ticker"]) or {}
        lp = info.get("live")
        if not (l["ticker"] or "").startswith(WINNER_SERIES):
            nm = info.get("name") or l["ticker"]
            if l.get("side", "yes") == "no":
                nm = "Not: " + nm
                lp = 1 - lp if lp is not None else None
            return nm, "", lp, res
        return TEAMS.get(abbr, abbr), "", lp, res

    rng = random.Random(1)
    cards, hits_any = [], 0
    infos = [[leg_info(l) for l in a["legs"]] for a in mine]
    for a in mine:
        a["_hits"] = 0                          # the account list is cached, so start fresh each time
    from collections import Counter
    patterns = Counter()
    trials = 8000 if live else 20000
    for _ in range(trials):                     # play the rest of the weekend out
        won = {ev: (s[0] if rng.random() < s[0]["fair"] else s[1])["ticker"] for ev, s in all_games.items()}
        hit = False
        hit_now = []
        for a, inf in zip(mine, infos):
            if a["status"] == "cashed":
                continue
            ok = True
            if a["ticker"] in rough and not any(r == "no" for *_, r in inf):
                if all(r == "yes" for *_, r in inf):
                    ok = True
                else:                             # picks move together: use the combo's own price
                    ok = rng.random() < (rough[a["ticker"]] or 0.0)
                if ok:
                    hit = True
                    a.setdefault("_hits", 0)
                    a["_hits"] += 1
                    hit_now.append(a["ticker"])
                continue
            for l, (_, _, ch, res) in zip(a["legs"], inf):
                if res:
                    ok = res == "yes"
                else:
                    s = side_of.get(l["ticker"])
                    if not s:
                        ok = rng.random() < (ch or 0.5)
                    else:
                        took = won[s["event"]] == s["ticker"]
                        ok = took if l.get("side", "yes") == "yes" else not took
                if not ok:
                    break
            if ok:
                hit = True
                a.setdefault("_hits", 0)
                a["_hits"] += 1
                hit_now.append(a["ticker"])
        patterns[frozenset(hit_now)] += 1
        hits_any += hit
    MINE["patterns"] = patterns
    fetch_scores()

    order = {ev: i for i, ev in enumerate(all_games)}
    snap = {}
    MINE["hold"] = {}
    MINE["tp"] = resting_sells() if can_trade() and any(a["status"] == "pending" for a in mine) else {}
    for i, (a, inf) in enumerate(zip(mine, infos), 1):
        p = a.get("_hits", 0) / trials
        st = "cashed" if a["status"] == "cashed" else \
            "won" if a["status"] == "won" or all(r == "yes" for *_, r in inf) else \
            "lost" if a["status"] == "lost" or any(r == "no" for *_, r in inf) else "pending"
        snap[a["ticker"]] = {"label": f"Combo {i}", "pays": a["pays"], "status": st,
                             "legs": {l["ticker"]: (nm, r) for l, (nm, _, _, r) in zip(a["legs"], inf)}}
        lost = any(r == "no" for *_, r in inf)
        done = all(r == "yes" for *_, r in inf)
        pre, missing = [], []
        for l, (nm, _, ch, r) in zip(a["legs"], inf):
            t = l["ticker"]
            if l.get("side", "yes") == "no":
                s0 = side_of.get(t)
                other = next((x for x in all_games[s0["event"]] if x is not s0), None) if s0 else None
                t = other["ticker"] if other else None
            v = pregame.get(t) if t else None
            if v is None and t in side_of and not started(side_of[t]) and not r:
                v = side_of[t]["fair"]
            (pre.append(v) if v else missing.append(nm))
        fair_pay = a["cost"] / math.prod(pre) if not missing and pre else None
        left = sum(1 for *_, r in inf if not r)
        if st == "pending":
            MINE["hold"][a["ticker"]] = {"label": f"Combo {i}", "p": p, "pays": a["pays"], "cost": a["cost"],
                                         "hold": p * a["pays"], "left": left, "rough": a["ticker"] in rough,
                                         "won_some": any(r == "yes" for *_, r in inf),
                                         "need": [((l.get("side", "yes"), l["ticker"]), nm)
                                                  for l, (nm, _, _, r) in zip(a["legs"], inf) if not r],
                                         "worth": left <= 3 and p * a["pays"] >= 2 * a["cost"]}
        if st == "cashed":
            gain = a["back"] - a["cost"]
            status = f"<span class='tag {'good' if gain >= 0 else 'bad'}'>Cashed out</span>"
        elif a["status"] == "won" or done:
            status = "<span class='tag good'>Won</span>"
        elif a["status"] == "lost" or lost:
            status = "<span class='tag red'>Lost</span>"
        else:
            status = f"<span class='tag dog'>{p:.1%} to hit</span>" if p >= 0.001 else "<span class='tag dog'>under 0.1% to hit</span>"
        if st == "cashed":
            gain = a["back"] - a["cost"]
            full = a.get("full_pays") or 0
            hs = (f"Would have paid {money(full)} if you'd held." if done else
                  "Would have lost. Good call." if lost else
                  f"Would pay {money(full)} if it hits." if full else "")
            value = (f"<div class='min'>Cashed out for <b>{money(a['back'])}</b> · cost {money(a['cost'])} · "
                     f"<span class='{'pos' if gain >= 0 else 'neg'}'>{'+' if gain >= 0 else '−'}{money(abs(gain))}</span>"
                     + (f"<div class='muted' style='font-size:13px;margin-top:4px'>{hs}</div>" if hs else "") + "</div>")
        elif fair_pay:
            pct = a["pays"] / fair_pay
            cls = "ok" if pct >= CFG["accept_pct"] / 100 else "no"
            value = (f"<div class='min'>Fair value {money(fair_pay)} · "
                     f"Kalshi pays <b>{money(a['pays'])}</b> "
                     f"<span class='verdict {cls}'>{pct:.0%} of fair</span>"
                     f"<div class='muted' style='font-size:12px;margin-top:4px'>Based on pre-game chances.</div></div>")
        else:
            names = ", ".join(e(n) for n in missing[:3]) + (f" and {len(missing) - 3} more" if len(missing) > 3 else "")
            value = (f"<div class='min muted' style='font-size:13px'>Fair value not available: no pre-game "
                     f"price saved for {names} (that game had already started when the planner first "
                     f"saw it). From next week, prices are saved before kickoff.</div>")
        rows = []
        legs_sorted = sorted(zip(a["legs"], inf), key=lambda x: (start_key(x[0].get("event") or ""),
                                                                 order.get((side_of.get(x[0]["ticker"]) or {}).get("event"), 99)))
        for n, (l, (name, opp, ch, res)) in enumerate(legs_sorted, 1):
            tag = {"yes": "<span class='tag good'>Won</span>", "no": "<span class='tag red'>Lost</span>"}.get(res, "")
            sub = f"to beat {e(opp)}" if opp else ""
            pct = f"{ch:.0%}" if ch and not res else ""
            if not res:
                state = pick_state(l, side_of)
                if state == "over":
                    tag, pct = "<span class='tag bad'>Game over · settling</span>", ""
                elif state == "live":
                    lp = (MARKET_INFO.get(l["ticker"]) or {}).get("live")
                    if lp is not None and l.get("side", "yes") == "no":
                        lp = 1 - lp
                    tag = "<span class='tag bad'>In progress</span>"
                    pct = f"<span style='font-size:12px;font-weight:500' class='muted'>live</span> {lp:.0%}" if lp else ""
            sline = score_line(leg_score(l)) if not res else ""
            if sline:
                sub = sline
            elif not res and start_label(l.get("event") or "") and pick_state(l, side_of) not in ("live", "over"):
                sub = (sub + " · " if sub else "") + "starts " + start_label(l["event"])
            if (l["ticker"] or "").startswith(tuple(GAME_SLUG)):
                tag += (f" <a class='klink' href='combo://open/{quote(game_url(l['ticker']), safe='')}'>"
                        f"game ↗</a>")
            rows.append(f"<li><span class='n'>{n}</span><span class='who'><b>{e(name)}</b> {tag}"
                        f"<small>{sub}</small></span><span class='pct'>{pct}</span></li>")
        group = snap.get(a["ticker"], {}).get("status", "pending")
        if group == "pending":
            value = f"@@CASH:{a['ticker']}@@"
        pay_line = (f"<div class='pay'>{money(a['back'])}</div><div class='meta'>cashed out · cost {money(a['cost'])}</div>"
                    if group == "cashed" else
                    f"<div class='pay'>{money(a['pays'])}</div><div class='meta'>pays if it hits · cost {money(a['cost'])}</div>")
        marks = {"yes": "✓", "no": "✗"}
        preview = " · ".join(f"{nm}{(' ' + marks[r]) if r in marks else ''}"
                             for _, (nm, _, _, r) in legs_sorted[:3]) + (f" · +{len(legs_sorted) - 3}" if len(legs_sorted) > 3 else "")
        cards.append((group, f"<details class='card' id='c-{e(a['ticker'])}'@@OPEN:{e(a['ticker'])}@@><summary><div class='top'><div>"
                     f"<div class='tier'>Combo {i} · {len(a['legs'])} picks</div>{pay_line}"
                     f"<div class='muted' style='font-size:13px;margin-top:2px'>{e(preview)}</div></div>"
                     f"<div style='text-align:right'><span data-k='p-{e(a['ticker'])}'>{status}</span><span class='chev'></span>"
                     f"<br><a class='klink' href='combo://open/{quote(KALSHI_WEB + '/portfolio', safe='')}'>Open in Kalshi ↗</a>"
                     f"</div></div></summary>{value}<ol>{''.join(rows)}</ol></details>"))

    live_picks = []
    for a, inf in zip(mine, infos):
        if snap.get(a["ticker"], {}).get("status") != "pending":
            continue
        live_picks.append([(l["ticker"] if l.get("side", "yes") == "yes" else "NO:" + (l["ticker"] or ""), nm)
                           for l, (nm, _, _, r) in zip(a["legs"], inf) if not r])
    exposure = exposure_html(live_picks, "Still riding on one result")
    flash = MINE.pop("flash", None)
    staked = sum(a["cost"] for a in mine)
    MINE["locked"] = round(sum(a["back"] for a in mine if a["status"] in ("cashed", "won"))
                           + sum(a["pays"] for a in mine if a["status"] == "pending"
                                 and snap.get(a["ticker"], {}).get("status") == "won"), 2)
    plan = plan_cashout()
    MINE["plan"] = plan
    cards = [(g, re.sub(r"@@CASH:([^@]+)@@", lambda m: cash_block(m.group(1), plan), c)) for g, c in cards]
    act_on = {t for t, f in ((plan or {}).get("acts") or {}).items() if f} | {t for t in MINE["hold"] if fresh_offer(t)}
    cards = [(g, re.sub(r"@@OPEN:([^@]+)@@", lambda m: " open" if html.unescape(m.group(1)) in act_on else "", c))
             for g, c in cards]
    now_box = right_now_html(mine, infos, snap, plan)
    n_act = sum(1 for f in ((plan or {}).get("acts") or {}).values() if f)
    strip = (f"<a class='strip' href='#now' onclick=\"document.getElementById('now').scrollIntoView({{behavior:'smooth'}});return false;\">"
             f"<span>Locked <b data-k='lk'>{money(MINE.get('locked', 0))}</b> · Live <b data-k='lv'>"
             f"{money(sum(h['hold'] for h in MINE['hold'].values()))}</b></span>"
             + (f"<span class='tag good'>{n_act} to do ›</span>" if n_act else "<span class='muted'>›</span>") + "</a>"
             if MINE["hold"] or MINE.get("locked") else "")
    alive = [a for a in mine if snap.get(a["ticker"], {}).get("status") in ("pending", "won")]
    best = max((a["pays"] for a in alive), default=0)      # lost combos can't pay out
    n_alive = sum(1 for a in mine if snap.get(a["ticker"], {}).get("status") == "pending")
    n_cashed = sum(1 for a in mine if a["status"] == "cashed")
    alerts_row = ("<div class='batch' style='padding:8px 12px'><div class='row'><span class='muted' id='livemsg' "
                  "style='font-size:13px'>"
                  + (f"Alerts on · checked {MINE['last']}" if live and MINE.get("last") else
                     "Alerts off. Turn on for game-day notifications.") +
                  "</span><button class='btn go' id='livebtn' onclick='toggleLive()'>"
                  + ("Turn off" if live else "Turn on") + "</button></div></div>")
    details = ("<details class='lostbox' id='moredet'><summary>More details<span class='muted'> · tap to show</span></summary>"
               "<div class='stats'>"
               f"<div class='stat'><b>{money(staked)}</b><span class='lbl'>staked</span></div>"
               f"<div class='stat'><b>{hits_any / trials:.0%}</b><span class='lbl'>chance one hits</span></div>"
               + (f"<div class='stat'><b>{money(best)}</b><span class='lbl'>biggest payout still possible</span></div></div>"
                  if alive else "<div class='stat'><b>—</b><span class='lbl'>no combos still alive</span></div></div>")
               + "".join(f"<div class='note'>{e(n)}</div>" for n in notes if n)
               + f"<div style='padding-top:8px'>{exposure}</div>"
               "<div class='note'>Alerts work while this page is open and keep the screen awake. "
               "\"Worth a sure $X to you\" weighs a chance at a big payout against your betting bankroll "
               "(Settings → Cash out): the bigger the amount next to your bankroll, the more a sure thing is worth.</div>"
               "</details>")
    body = [head, f"<header><h1>My combos · {sunday:%b %-d}</h1>"
                  f"<div class='sub'>{LG()['icon']} {len(mine)} placed · {n_alive} still alive"
                  + (f" · {n_cashed} cashed out" if n_cashed else "") + "</div></header>",
            (f"<div style='padding:0 16px'><div class='batch' style='border:2px solid var(--good)'><b>{e(flash)}</b></div></div>" if flash else ""),
            f"<div style='padding:0 16px'>{strip}<div id='now'>{now_box}</div>{alerts_row}</div>",
            "<div class='tabs'><button id='b-combos' class='on' onclick=\"tab('combos')\">My combos</button>"
            "<button id='b-record' onclick=\"tab('record')\">Record</button></div>",
            "<section id='combos'>"]
    # live combos first, then winners; lost ones tucked into a collapsed section at the bottom
    alive_cards = [c for g, c in cards if g == "pending"] + [c for g, c in cards if g == "won"]
    lost_cards = [c for g, c in cards if g == "lost"]
    cashed_cards = [c for g, c in cards if g == "cashed"]
    if not cards:
        body.append(f"<div class='empty'>No {LG()['name']} combos found in your Kalshi account for "
                    f"{'this day' if by_day() else 'this week'}.</div>")
    elif not alive_cards:
        body.append("<div class='empty'>No combos still alive this week.</div>")
    body += alive_cards
    if cashed_cards:
        body.append(f"<details class='lostbox' id='cashedbox'><summary>Cashed out ({len(cashed_cards)})"
                    f"<span class='muted'> · tap to show</span></summary>{''.join(cashed_cards)}</details>")
    if lost_cards:
        body.append(f"<details class='lostbox' id='lostbox'><summary>Lost combos ({len(lost_cards)})"
                    f"<span class='muted'> · tap to show</span></summary>{''.join(lost_cards)}</details>")
    body.append(details)
    history = load_json(HISTORY, {"builds": []})
    body.append(f"</section><section id='record' class='hidden'>"
                f"{render_record(bets_from_account(acct, history))}</section>")
    body.append("<script>function tab(n){document.querySelectorAll('section').forEach(function(s){"
                "s.classList.toggle('hidden',s.id!==n);var b=document.getElementById('b-'+s.id);"
                "if(b)b.classList.toggle('on',s.id===n);});window.scrollTo(0,0);}"
                f"var LIVE={'true' if live else 'false'};"
                "function liveState(on,msg){LIVE=on;document.getElementById('livebtn').textContent=on?'Turn off':'Turn on';"
                "document.getElementById('livemsg').textContent=msg||(on?'On · checking now…':'Off.');}"
                "function toggleLive(){liveState(!LIVE,'');try{location.href='combo://live/'+(LIVE?'on':'off');}catch(e){}}"
                "function cash(a,t){document.querySelectorAll('.cashb').forEach(function(b){b.disabled=true;});"
                "location.href='combo://cash/'+a+'/'+t;}"
                "</script></body></html>")
    return "".join(body), snap



def diagnose():
    """Step-by-step check of the Kalshi connection, shown as a page."""
    e = html.escape
    steps = []

    def add(ok, title, detail=""):
        icon = {True: "<span class='tag good'>OK</span>", False: "<span class='tag red'>Problem</span>",
                None: "<span class='tag bad'>Info</span>"}[ok]
        steps.append(f"<div class='game'><div class='row'><b>{e(title)}</b>{icon}</div>"
                     f"<div class='muted' style='word-break:break-all'>{detail}</div></div>")

    key_id = CFG.get("kalshi_key_id", "").strip()
    loading("Checking your Kalshi connection…")
    add(bool(key_id), "Key ID saved", e(key_id[:6] + "…" if key_id else "No key ID. Paste it in settings, then tap any button at the top or Build."))
    key = None
    if not os.path.exists(KEYFILE):
        why = KEY_ERROR["msg"] or "Nothing was pasted in the private key box."
        add(False, "Private key saved", e(why) + "<br><br>Another way: save Kalshi's key file into "
            "Pythonista's folder using the Files app, then run this check again.")
    else:
        try:
            with open(KEYFILE, encoding="utf-8") as fh:
                key = load_private_key(fh.read())
            add(True, "Private key saved", describe_key(key) + ".")
        except ValueError as err:
            add(False, "Private key saved", e(str(err)))
    if key_id and key:
        try:
            bal = account_get(key, key_id, "/portfolio/balance")
            add(True, "Kalshi accepted the key", f"Balance {money(dollars(bal, 'balance'))}")
            fills = account_pages(key, key_id, "/portfolio/fills", "fills",
                                  {"min_ts": int((dt.datetime.now() - dt.timedelta(days=200)).timestamp())})
            tick = sorted({f.get("ticker") or f.get("market_ticker") or "?" for f in fills})
            others = [t for t in tick if is_combo(t)]
            add(None, f"Trades found: {len(fills)}", f"{len(others)} of them are combos.")
            if fills:
                add(None, "Fields in your latest trade", e(", ".join(sorted(fills[0].keys()))))
            pos = all_positions(key, key_id)
            pt = [p.get("ticker") or "?" for p in pos]
            add(None, f"Positions: {len(pos)}", e(", ".join(pt[:8])))
            combo_fills = [f for f in fills if is_combo(f.get("ticker") or f.get("market_ticker"))][:10]
            if combo_fills:
                pmap = {(p.get("ticker") or p.get("market_ticker")): p for p in pos}

                def fmt(f):
                    t = f.get("ticker") or f.get("market_ticker") or "?"
                    pz = pmap.get(t) or {}
                    when = str(f.get("created_time") or f.get("ts") or "")[5:16].replace("T", " ")
                    return (f"{when} …{t[-8:]} · {f.get('action')} {f.get('side')}"
                            f"{' (' + str(f.get('outcome_side')) + ')' if f.get('outcome_side') else ''} {count_of(f):g} "
                            f"@ yes {dollars(f, 'yes_price'):.2f} / no {dollars(f, 'no_price'):.2f} · "
                            f"now hold {pz.get('position_fp', pz.get('position', '–'))}, "
                            f"realized {pz.get('realized_pnl_dollars', pz.get('realized_pnl', '–'))}")
                add(None, "Your latest combo trades (newest first)",
                    "<br>".join(e(fmt(f)) for f in combo_fills))
            cache = load_json(LEGS_CACHE, {})
            sample = (others + [p for p in locals().get("pt", []) if is_combo(p)])[:6]
            fetch_legs_parallel(sample, cache)
            for t in sample:
                legs = combo_legs(t, cache)
                if legs is None:
                    add(False, f"Combo {t}", "Kalshi didn't list this market's picks (mve_selected_legs missing).")
                else:
                    nfl = [l["ticker"] for l in legs if (l["ticker"] or "").startswith(SERIES)]
                    if nfl:
                        add(True, f"Combo {t}", f"{len(legs)} picks, {len(nfl)} {LG()['name']}: " + e(", ".join(nfl[:4])))
                    else:
                        add(None, f"Combo {t}", f"Not a {LG()['name']} combo, so it's skipped here.")
            save_json(LEGS_CACHE, cache)
            bets, _, _ = fetch_account()
            add(bool(bets), f"{LG()['name']} combos the planner can show: {len(bets or [])}",
                e(", ".join(sorted({b['week'] or '?' for b in bets or []}))) + " (weeks)")
        except PermissionError as err:
            add(False, "Kalshi accepted the key", e(str(err)))
        except requests.RequestException as err:
            add(False, "Reaching Kalshi", e(str(err)[:200]))
    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Kalshi check</title><style>{CSS}</style></head><body>"
            "<header><h1>Kalshi connection check</h1><div class='sub'>Screenshot this and send it "
            "over if something's marked Problem.</div></header><section>" + "".join(steps) +
            "</section></body></html>")
    present(page)


# ================================================================ swap & buy (from the results page)
CTX = {}   # this session's slate: games, combos, build id, pending offers


def kalshi_send(method, path, body=None, params=None):
    """Signed request with your key (used for buying). Returns JSON or None."""
    import base64, time
    key_id = CFG.get("kalshi_key_id", "").strip()
    with open(KEYFILE, encoding="utf-8") as f:
        key = load_private_key(f.read())
    full = "/trade-api/v2" + path
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(sign(key, (ts + method + full).encode())).decode()
    headers = {"KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
               "KALSHI-ACCESS-SIGNATURE": sig}
    if body is not None:
        headers["Content-Type"] = "application/json"
    r = requests.request(method, KALSHI + path, params=params or {}, timeout=20, headers=headers,
                         data=json.dumps(body) if body is not None else None)
    if r.status_code in (401, 403):
        raise PermissionError("Kalshi refused. Your API key needs write (trading) access for buying.")
    if not r.ok:
        try:
            msg = r.json().get("message") or r.text[:120]
        except ValueError:
            msg = r.text[:120]
        raise RuntimeError(f"Kalshi said: {msg} ({r.status_code})")
    return r.json() if r.content else None


def can_trade():
    return bool(CFG.get("kalshi_key_id")) and os.path.exists(KEYFILE)


def combo_rules(events):
    """Which of these games Kalshi accepts in one combo, and how many picks it allows.
    Returns (allowed games, most picks, fewest picks), or None if Kalshi can't be asked."""
    try:
        colls, cursor = [], None
        for _ in range(10):
            params = {"status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(f"{KALSHI}/multivariate_event_collections", timeout=20, params=params)
            r.raise_for_status()
            data = r.json()
            colls += data.get("multivariate_contracts", [])
            cursor = data.get("cursor")
            if not cursor:
                break
    except (requests.RequestException, ValueError):
        return None
    if not colls:
        return None                                   # nothing listed: can't tell, so don't block
    want, best = set(events), None
    for c in colls:
        inside = {a.get("ticker") for a in c.get("associated_events", [])} or \
            set(c.get("associated_event_tickers") or [])
        got = want & inside
        if got and (best is None or len(got) > len(best[0])):
            best = (got, int(c.get("size_max") or 99), int(c.get("size_min") or 2))
    return best or (set(), 0, 2)


def find_collection(legs):
    """The Kalshi combo collection that accepts all these games."""
    events = {l["event"] for l in legs}
    first = sorted(events)[0]
    r = requests.get(f"{KALSHI}/multivariate_event_collections", timeout=20,
                     params={"associated_event_ticker": first, "status": "open", "limit": 200})
    r.raise_for_status()
    best = None
    for c in r.json().get("multivariate_contracts", []):
        inside = {a.get("ticker") for a in c.get("associated_events", [])} or \
            set(c.get("associated_event_tickers") or [])
        lo, hi = c.get("size_min") or 1, c.get("size_max") or 99
        if events <= inside and lo <= len(legs) <= hi:
            if best is None or len(inside) > best[1]:
                best = (c["collection_ticker"], len(inside))
    if not best:
        raise RuntimeError("Kalshi doesn't offer this exact combo (too many picks, or a game "
                           "isn't available for combos). Try Swap.")
    return best[0]


def week_spend():
    """What you've already spent on this week's NFL combos (from your account)."""
    acct, _, _ = fetch_account()
    week = CTX.get("sunday").isoformat() if CTX.get("sunday") else None
    return sum(a["cost"] for a in acct or [] if (a.get("first_week") or a["week"]) == week)


def get_offer(i, amount=None, check_cap=True):
    """Steps 1-3: make the combo market, ask for a price, wait for the best offer."""
    import time
    c = CTX["combos"][i - 1]
    stake = round(float(amount), 2) if amount else CTX["stake"]
    if stake < 1:
        return {"error": "Use at least $1 per combo."}
    if stake > CFG["budget"]:
        return {"error": f"{money(stake)} is more than your whole {money(CFG['budget'])} {slate_word()} cap."}
    spent = week_spend() if check_cap else 0
    if check_cap and spent + stake > CFG["budget"] + 0.01:
        return {"error": f"That would take this {slate_word()} to {money(spent + stake)}, over your "
                         f"{money(CFG['budget'])} cap. Raise the cap in settings to go ahead."}
    legs = [{"market_ticker": l["ticker"], "event_ticker": l["event"], "side": "yes"} for l in c["legs"]]
    coll = find_collection(c["legs"])
    made = kalshi_send("POST", f"/multivariate_event_collections/{coll}",
                       {"selected_markets": legs, "with_market_payload": False})
    market = made["market_ticker"]
    clear_my_rfqs(market)
    rfq = kalshi_send("POST", "/communications/rfqs",
                      {"market_ticker": market, "target_cost_dollars": f"{stake:.2f}",
                       "rest_remainder": False, "replace_existing": False})["id"]
    best, start = None, time.time()
    while time.time() - start < 20:
        time.sleep(1.5)
        quotes = kalshi_send("GET", "/communications/quotes",
                             params={"rfq_id": rfq, "rfq_user_filter": "self"}).get("quotes", [])
        for q in quotes:
            if q.get("status") != "open" or not q.get("no_bid_dollars"):
                continue
            yes_price = 1 - float(q["no_bid_dollars"])     # buying YES = hitting their NO bid
            if 0 < yes_price < 1 and (best is None or yes_price < best[0]):
                best = (yes_price, q)
        if best and time.time() - start > 5:
            break
    if not best:
        kalshi_send("DELETE", f"/communications/rfqs/{rfq}")
        return {"error": "No offers came in for this combo. Try again in a minute, or Swap it."}
    yes_price, q = best
    pays = stake / yes_price
    minimum = c["min"] * stake / CTX["stake"]
    CTX["offers"][i] = {"rfq": rfq, "quote": q["id"], "pays": pays, "market": market,
                        "price": yes_price, "stake": stake}
    return {"pays": pays, "price": yes_price, "min": minimum, "ok": pays >= minimum, "stake": stake}


def accept_offer(i):
    """Step 4: accept. 'no' is correct: it hits the seller's NO bid, which buys you YES."""
    import time
    o = CTX["offers"].pop(i, None)
    if not o:
        return {"error": "That offer is gone. Tap Buy on Kalshi to get a fresh one."}
    try:
        kalshi_send("PUT", f"/communications/rfqs/{o['rfq']}/quotes/{o['quote']}/accept",
                    {"accepted_side": "no"})
    except RuntimeError as err:
        return {"error": f"Couldn't accept, probably expired. Get a fresh offer. ({err})"}
    status, start = "accepted", time.time()
    while time.time() - start < 15 and status not in ("executed", "cancelled"):
        time.sleep(1)
        q = kalshi_send("GET", f"/communications/rfqs/{o['rfq']}/quotes/{o['quote']}") or {}
        status = (q.get("quote") or q).get("status", status)
    try:
        kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
    except Exception:
        pass
    if status == "executed":
        ACCT_CACHE["at"] = 0
        haptic("success")
        if CFG.get("tp_auto"):
            place_take_profit(o["market"], o["pays"], o["stake"])
        hist = load_json(HISTORY, {"builds": []})
        b = next((x for x in hist["builds"] if x["id"] == CTX["build_id"]), None)
        if b is not None:
            if i not in b["placed"]:
                b["placed"].append(i)
            b.setdefault("quotes", {})[str(i)] = round(o["pays"], 2)
            save_json(HISTORY, hist)
        return {"done": True, "pays": o["pays"]}
    if status == "cancelled":
        return {"error": "The seller backed out before confirming, so nothing was bought. Try again."}
    return {"error": "Still waiting on Kalshi. Check Show my Kalshi combos in a minute before "
                     "trying again, so you don't buy it twice."}


def decline_offer(i):
    o = CTX["offers"].pop(i, None)
    if o:
        try:
            kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
        except Exception:
            pass


def swap_combo(i):
    """Replace combo i with a new one of the same type that isn't already on the list."""
    games, locks = CTX["games"], CTX["locks"]
    old = CTX["combos"][i - 1]
    seen = {frozenset(l["ticker"] for l in c["legs"]) for c in CTX["combos"]}
    free = [e for e in games if e not in locks]
    locked = [next(s for s in games[e] if s["ticker"] == t) for e, t in locks.items()]
    rng, legs = random.Random(), None
    if old["kind"] == "full":
        n = sum(1 for l in old["legs"] if l["event"] in free and l is dog(games[l["event"]]))
        for ups in underdog_sets(games, free, n, len(seen) + 40):
            cand = locked + [dog(games[e]) if e in ups else fav(games[e]) for e in free]
            if frozenset(l["ticker"] for l in cand) not in seen:
                legs = cand
                break
    else:
        usage = defaultdict(int)
        partial = [c for k, c in enumerate(CTX["combos"], 1) if c["kind"] != "full"]
        for k, c in enumerate(CTX["combos"], 1):
            if c["kind"] != "full" and k != i:
                for l in c["legs"]:
                    if l["event"] not in locks:
                        usage[l["ticker"]] += 1
        limit = share_limit(len(partial))
        for _ in range(300):
            size = rng.randint(CFG[f"{old['kind']}_min"], CFG[f"{old['kind']}_max"])
            cand = pick_partial(games, free, locked, size, rng, usage, limit)
            if cand and frozenset(l["ticker"] for l in cand) not in seen:
                legs = cand
                break
    if not legs:
        return False
    stake = CTX["stake"]
    fair_pay = stake / math.prod(l["fair"] for l in legs)
    n_dogs = sum(l["fair"] < 0.5 for l in legs)
    tier = f"Full slate · {n_dogs} underdog{'s' * (n_dogs != 1)}" if old["kind"] == "full" else old["tier"]
    new = {"kind": old["kind"], "tier": tier, "legs": legs, "fair": fair_pay,
           "min": fair_pay * CFG["accept_pct"] / 100, "kalshi": stake / math.prod(l["p"] for l in legs)}
    CTX["combos"][i - 1] = new
    CTX["offers"].pop(i, None)
    CTX.get("card_notes", {}).pop(i, None)
    hist = load_json(HISTORY, {"builds": []})
    b = next((x for x in hist["builds"] if x["id"] == CTX["build_id"]), None)
    if b is not None:
        b["combos"][i - 1] = {"kind": new["kind"], "tier": new["tier"], "fair": round(fair_pay, 2),
                              "min": round(new["min"], 2),
                              "legs": [{"ticker": l["ticker"], "pick": l["pick"], "dog": l["fair"] < 0.5} for l in legs]}
        b["placed"] = [x for x in b.get("placed", []) if x != i]
        b.get("quotes", {}).pop(str(i), None)
        save_json(HISTORY, hist)
    return True


def save_combo(i, new):
    """Write a changed combo back to the saved history (and clear its Placed/offer)."""
    hist = load_json(HISTORY, {"builds": []})
    b = next((x for x in hist["builds"] if x["id"] == CTX["build_id"]), None)
    if b is not None:
        b["combos"][i - 1] = {"kind": new["kind"], "tier": new["tier"], "fair": round(new["fair"], 2),
                              "min": round(new["min"], 2),
                              "legs": [{"ticker": l["ticker"], "pick": l["pick"], "dog": l["fair"] < 0.5}
                                       for l in new["legs"]]}
        b["placed"] = [x for x in b.get("placed", []) if x != i]
        b.get("quotes", {}).pop(str(i), None)
        save_json(HISTORY, hist)


def flip_pick(i, ticker):
    """Switch one pick in combo i to the other team and explain what changed.
    Returns (ok, html note)."""
    e = html.escape
    old = CTX["combos"][i - 1]
    leg = next((l for l in old["legs"] if l["ticker"] == ticker), None)
    if leg is None:
        return False, "That pick isn't in this combo any more. Tap Results to refresh."
    other = next(x for x in CTX["all_games"][leg["event"]] if x["ticker"] != ticker)
    if not pickable(other):
        return False, (f"{e(other['pick'])} is only {other['fair']:.0%} live with the game under way, "
                       f"below your {CFG['live_min']}% minimum, so it can't be picked.")
    legs = [other if l is leg else l for l in old["legs"]]
    key = frozenset(l["ticker"] for l in legs)
    for k, c in enumerate(CTX["combos"], 1):
        if k != i and frozenset(l["ticker"] for l in c["legs"]) == key:
            return False, f"Flipping it would make this the same as combo #{k}."
    stake = CTX["stake"]
    fair_pay = stake / math.prod(l["fair"] for l in legs)
    new = dict(old, legs=legs, fair=fair_pay, min=fair_pay * CFG["accept_pct"] / 100,
               kalshi=stake / math.prod(l["p"] for l in legs))
    if old["kind"] == "full":
        n = sum(l["fair"] < 0.5 for l in legs)
        new["tier"] = f"Full slate · {n} underdog{'s' * (n != 1)}"
    _, (p_old, p_new) = simulate([old, new], CTX["games"])
    v_old, v_new = old["kalshi"] / old["fair"], new["kalshi"] / new["fair"]
    likely = ("more likely to hit" if p_new > p_old * 1.05 else
              "less likely to hit" if p_new < p_old * 0.95 else "about as likely to hit")
    value = ("better value" if v_new >= v_old + 0.01 else
             "slightly worse value" if v_new <= v_old - 0.01 else "about the same value")
    good = p_new > p_old * 1.05 and v_new >= v_old - 0.01
    bad = p_new < p_old * 0.95 and v_new <= v_old + 0.01
    head = ("<span class='verdict ok'>Good flip</span>" if good else
            "<span class='verdict no'>Worse bet</span>" if bad else
            "<span class='verdict ok' style='background:var(--badbg);color:var(--bad)'>Trade-off</span>")
    extra = []
    edge = other.get("edge")
    if edge is not None and edge * 100 >= 1:
        extra.append(f"Kalshi prices {e(other['pick'])} as a bargain (+{round(edge * 100)}¢).")
    elif edge is not None and edge * 100 <= -4:
        extra.append(f"Kalshi charges extra for {e(other['pick'])} ({round(edge * 100)}¢).")
    if other.get("live"):
        extra.append("Live pick: its price moves fast, so get an offer soon.")
    note = (f"<div class='min'>{head} Flipped <b>{e(leg['pick'])}</b> → <b>{e(other['pick'])}</b>: "
            f"{likely} ({p_old:.1%} → {p_new:.1%}), fair payout {money(old['fair'])} → {money(new['fair'])}, "
            f"{value} at Kalshi's prices ({v_old:.0%} → {v_new:.0%} of fair). " + " ".join(extra) +
            " Tap Flip again to undo. Buy on Kalshi shows whether the real offer is good.</div>")
    CTX["combos"][i - 1] = new
    CTX["offers"].pop(i, None)
    CTX.setdefault("card_notes", {})[i] = note
    save_combo(i, new)
    return True, note


def rerender(focus=None):
    """Re-score and redraw the results page after a swap."""
    p_any, p_each = simulate(CTX["combos"], CTX["games"])
    page = render(CTX["build_id"], CTX["combos"], CTX["games"], CTX["all_games"], CTX["days"],
                  CTX["sunday"], p_any, p_each, CTX["notes"], CTX["locks"], CTX["skipped"],
                  CTX["news"], focus=focus, card_notes=CTX.get("card_notes"))
    with open(LATEST, "w", encoding="utf-8") as f:
        f.write(page)


def ctx_from_history(build, all_games, days, sunday):
    """Rebuild the session slate for 'Show last results' so Swap and Buy work there too.
    Combos whose games have started can't be rebuilt and are left as they are."""
    if not build or build["week"] != sunday.isoformat() or build.get("league", "nfl") != LEAGUE["code"]:
        return None
    book = {}
    if CFG["odds_key"]:
        book, _ = fetch_book_odds(CFG["odds_key"])
    _, news = attach_fair(all_games, book)
    side_of = {s["ticker"]: s for v in all_games.values() for s in v}
    on = day_on()
    games = {e: s for e, s in all_games.items() if on[days[e]] and CFG["picks"].get(e) != "skip"}
    combos = []
    for c in build["combos"]:
        legs = [side_of.get(l["ticker"]) for l in c["legs"]]
        if not all(legs):
            return None                      # a game has started; keep the saved page as is
        combos.append({"kind": c["kind"], "tier": c["tier"], "legs": legs, "fair": c["fair"],
                       "min": c["min"], "kalshi": c["fair"]})
    locks = {e: t for e, t in CFG["picks"].items() if e in games and t != "skip"}
    return {"games": games, "all_games": all_games, "days": days, "sunday": sunday, "locks": locks,
            "skipped": {}, "news": news, "notes": [], "combos": combos, "build_id": build["id"],
            "stake": build["stake"], "offers": {}}


def handle_action(webview, parts):
    """Runs Swap / Buy / Accept / No thanks in the background and updates the page."""
    import threading
    action, i = parts[0], int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    if not CTX or (not i and action != "batch"):
        webview.evaluate_javascript("tradeMsg(%d, %s)" % (i, json.dumps(
            "<span class='verdict no'>Swap and Buy work on this week's combos. Tap Build for a fresh set.</span>")))
        return
    busy = CTX.setdefault("busy_set", set())
    if i in busy:
        return
    busy.add(i)

    def say(html_text, k=None):
        webview.evaluate_javascript("tradeMsg(%d, %s)" % (i if k is None else k, json.dumps(html_text)))

    def work():
        try:
            if action == "batch":
                from concurrent.futures import ThreadPoolExecutor
                wanted = []
                for item in (parts[3] if len(parts) > 3 else "").split(","):
                    k, _, amt = item.partition(":")
                    if k.isdigit() and 1 <= int(k) <= len(CTX["combos"]):
                        try:
                            wanted.append((int(k), float(amt)))
                        except ValueError:
                            wanted.append((int(k), CTX["stake"]))
                total = sum(a for _, a in wanted)
                spent = week_spend()
                if spent + total > CFG["budget"] + 0.01:
                    say(f"<span class='verdict no'>Those add up to {money(total)}, which would take this "
                        f"{slate_word()} to {money(spent + total)}, over your {money(CFG['budget'])} cap. "
                        "Untick some or lower the amounts.</span>", 0)
                    for k, _ in wanted:
                        say("", k)
                    return
                say(f"<span class='muted'>Getting {len(wanted)} offers at once… (up to 25 seconds)</span>", 0)

                def one(item):
                    k, amt = item
                    try:
                        o = get_offer(k, amt, check_cap=False)
                        say(offer_html(k, o), k)
                        return "error" not in o
                    except Exception as err:
                        say(f"<span class='verdict no'>{html.escape(str(err)[:160])}</span>", k)
                        return False
                with ThreadPoolExecutor(max_workers=4) as pool:
                    got = sum(pool.map(one, wanted))
                say(f"<span class='muted'>{got} of {len(wanted)} offers in. Accept or decline each "
                    "one on its card. Offers can expire after a minute or two.</span>", 0)
            elif action == "flip":
                ok, note = flip_pick(i, unquote(parts[3]) if len(parts) > 3 else "")
                if ok:
                    rerender(focus=i)
                    with open(LATEST, encoding="utf-8") as f:
                        swap_page(webview, inject_state(f.read(), quiet=True))
                else:
                    say(f"<span class='verdict no'>{note}</span>")
            elif action == "swap":
                say("<span class='muted'>Finding a new combo…</span>")
                if swap_combo(i):
                    rerender(focus=i)
                    with open(LATEST, encoding="utf-8") as f:
                        swap_page(webview, inject_state(f.read(), quiet=True))   # same page, nav + buttons keep working
                else:
                    say("<span class='verdict no'>No other combo of this type fits your settings.</span>")
            elif action == "buy":
                if not can_trade():
                    say("<span class='verdict no'>Connect your Kalshi account in settings first.</span>")
                    return
                say("<span class='muted'>Asking Kalshi for a price… (up to 20 seconds). Nothing is bought until you tap Accept.</span>")
                amount = parts[3] if len(parts) > 3 else None
                try:
                    amount = float(amount) if amount else None
                except ValueError:
                    amount = None
                say(offer_html(i, get_offer(i, amount)))
            elif action == "accept":
                say("<span class='muted'>Buying… waiting for Kalshi to confirm.</span>")
                r = accept_offer(i)
                if r.get("done"):
                    say(f"<span class='verdict ok'>Bought! Pays about {money(r['pays'])} if it hits.</span>")
                    webview.evaluate_javascript(f"markPlaced({i}, {r['pays']:.2f})")
                else:
                    say(f"<span class='verdict no'>{html.escape(r['error'])}</span>")
            elif action == "decline":
                decline_offer(i)
                say("<span class='muted'>Offer declined. Nothing was bought.</span>")
        except PermissionError as err:
            say(f"<span class='verdict no'>{html.escape(str(err))}</span>")
        except Exception as err:
            say(f"<span class='verdict no'>Something went wrong: {html.escape(str(err)[:160])}. "
                "Nothing was bought unless it says Bought.</span>")
        finally:
            busy.discard(i)

    threading.Thread(target=work, daemon=True).start()


def offer_html(i, o):
    if "error" in o:
        return f"<span class='verdict no'>{html.escape(o['error'])}</span>"
    verdict = ("<span class='verdict ok'>Above your minimum</span>" if o["ok"] else
               f"<span class='verdict no'>Below your {money(o['min'])} minimum</span>")
    return (f"<div>Kalshi offers <b>{money(o['pays'])}</b> if it hits, for your "
            f"{money(o['stake'])} ({o['price'] * 100:.2f}¢ a contract). {verdict}</div>"
            f"<div class='quote'><button class='btn go' onclick='act(\"accept\",{i})'>"
            f"{'Accept' if o['ok'] else 'Accept anyway'}</button>"
            f"<button class='btn' onclick='act(\"decline\",{i})'>No thanks</button></div>")


# ================================================================ settings screen (a page in the same window)
SETTINGS_JS = r"""
var SL = %s;
function label(k){ var s=document.getElementById(k), d=SL[k]; if(!s) return;
  var v=+s.value, txt = d.unit==='$' ? '$'+v : v+(d.unit||'');
  document.getElementById('v-'+k).textContent = txt; budget(); }
function val(k){ var el=document.getElementById(k); return el ? +el.value : 0; }
function budget(){ var n=val('full_count')+val('safer_count')+val('middle_count')+val('moonshot_count');
  var st=val('stake'), cap=val('budget'), b=document.getElementById('budgetline'); if(!b) return;
  b.textContent = n+' combos x $'+st+' = $'+(n*st)+(n*st>cap ? '  (over your cap!)' : '  (cap $'+cap+')');
  b.className = n*st>cap ? 'neg' : ''; }
function txtval(k){ var el=document.getElementById(k); return el ? el.value : ''; }
function collect(){ var out={};
  Object.keys(SL).forEach(function(k){ var el=document.getElementById(k); if(el) out[k]=+el.value; });
  document.querySelectorAll('input.sw').forEach(function(el){ out[el.id]=el.checked; });
  if(document.getElementById('odds_key')) out.odds_key=txtval('odds_key').trim();
  if(document.getElementById('kalshi_key_id')) out.kalshi_key_id=txtval('kalshi_key_id').trim();
  if(document.getElementById('pem')) out.pem=txtval('pem');
  var picks={}; document.querySelectorAll('.seg input:checked').forEach(function(r){ if(r.value) picks[r.name]=r.value; });
  out.picks=picks; return out; }
function go(choice){ var btns=document.querySelectorAll('button'); btns.forEach(function(b){b.disabled=true;});
  var data='';
  try{ data=encodeURIComponent(JSON.stringify(collect())); }catch(e){ data=''; }
  location.href='combo://settings/'+choice+'/'+data; }
Object.keys(SL).forEach(label);
"""


def settings_page(all_games, days, counts):
    """Settings as a page in the main window. Returns 'build', 'show', 'mine', 'check' or None."""
    if not in_pythonista():
        return "build"
    import threading
    e = html.escape
    sliders = {}

    def slider(key, title, lo, hi, step=1, unit=""):
        sliders[key] = {"unit": unit}
        v = min(max(CFG[key], lo), hi)
        return (f"<div class='srow'><div class='row'><span>{title}</span><b id='v-{key}'></b></div>"
                f"<input type='range' id='{key}' min='{lo}' max='{hi}' step='{step}' value='{v}' "
                f"oninput=\"label('{key}')\"></div>")

    def switch(key, title):
        return (f"<label class='row swrow'><span>{title}</span>"
                f"<input type='checkbox' class='sw' id='{key}' {'checked' if CFG[key] else ''}></label>")

    def section(title, inner, note=""):
        if not note:
            return f"<h2>{title}</h2><div class='game'>{inner}</div>"
        return (f"<h2>{title}<span class='ib' onclick=\"var n=this.parentNode.nextElementSibling.querySelector('.inote');"
                f"n.style.display=n.style.display==='block'?'none':'block'\">ⓘ</span></h2>"
                f"<div class='game'><div class='inote' style='display:none'>{note}</div>{inner}</div>")

    top = []
    lg_btns = "".join(
        f"<button class='btn {'go' if k == LEAGUE['code'] else ''}' style='flex:1' "
        f"onclick=\"go('lg-{k}')\">{v['icon']} {v['short']}</button>"
        for k, v in LEAGUES.items())
    pass
    notice = RUN_OPTS.pop("notice", None)
    if notice:
        good = notice.startswith(("Updated", "You already", "Saved"))
        top.append(f"<div class='game' style='border-color:{'#15803d' if good else '#b45309'}'>"
                   f"<b class='{'pos' if good else ''}'>{html.escape(notice)}</b></div>")
    latest = RUN_OPTS.get("latest")
    if latest and version_tuple(latest) > version_tuple(VERSION):
        top.append(f"<button class='btn go big' style='background:#b45309;border-color:#b45309' "
                   f"onclick=\"go('update')\">Update to version {latest}</button>")
    else:
        top.append("<button class='btn big' onclick=\"go('update')\">Check for updates</button>")
    if CFG.get("kalshi_key_id") or os.path.exists(KEYFILE):
        top.append("<button class='btn big' onclick=\"go('check')\">Check Kalshi connection</button>")

    picks = []
    for ev, (a, b) in all_games.items():
        cur = CFG["picks"].get(ev)
        opts = [(a["ticker"], a["abbr"]), ("", "Auto"), (b["ticker"], b["abbr"]), ("skip", "Skip")]
        radios = "".join(
            f"<label><input type='radio' name='{e(ev)}' value='{e(v)}' "
            f"{'checked' if (cur == v if v else cur is None) else ''}><span>{e(t)}</span></label>"
            for v, t in opts)
        picks.append(f"<div class='pickrow'><div>{e(a['pick'])} vs {e(b['pick'])}{' · ' + day_tag(days[ev]) if day_tag(days[ev]) else ''}</div>"
                     f"<div class='seg'>{radios}</div></div>")

    have_key = os.path.exists(KEYFILE)
    mode = RUN_OPTS.pop("smode", None) or APP.get("smode") or "build"
    APP["smode"] = mode
    APP["where"] = mode
    sec = {
        "money": section("Money", slider("stake", "Per combo", 1, 20, unit="$") +
                         slider("budget", "Daily cap" if by_day() else "Weekend cap", 10, 200, 10, "$") +
                         slider("accept_pct", "Minimum offer to accept", 50, 100, 5, "% of fair"),
                         "Minimum offer: Buy on Kalshi flags offers below this share of the fair payout."),
        "mix": "<details class='game' id='mix'><summary><b>Combo mix</b> <span class='muted'>· how many of each type</span></summary>"
               + ("" if not LG().get("full") else
                  section("Full slate (every game)", slider("full_count", "Combos", 0, 10) +
                          slider("upsets_min", "Fewest underdogs", 0, 8) + slider("upsets_max", "Most underdogs", 0, 8)))
               + "".join(section(t.capitalize(), slider(f"{t}_count", "Combos", 0, 10) +
                                 slider(f"{t}_min", "Fewest games", 2, top_) + slider(f"{t}_max", "Most games", 2, top_))
                         for t, top_ in [("safer", 8), ("middle", 12), ("moonshot", 16)]) + "</details>",
        "days": section("Day", switch("next_day", "Use tomorrow's games instead of today's"),
                        f"{len(all_games)} game{'' if len(all_games) == 1 else 's'} on Kalshi for "
                        f"{'tomorrow' if CFG.get('next_day') else 'today'}.") if by_day() else
                section("Days", "".join(switch(k, f"{d} ({counts.get(d, 0)} game{'' if counts.get(d, 0) == 1 else 's'} this week)")
                                        for k, d in [("thursday", "Thursday"), ("saturday", "Saturday"), ("monday", "Monday")]),
                        "Sunday is always in."),
        "picks": section("Your picks", ("".join(picks) if len(picks) <= 6 else
                                        f"<details id='pk'><summary class='muted'>{len(picks)} games · tap to lock or skip</summary>"
                                        f"{''.join(picks)}</details>") or "<div class='muted'>No games listed yet.</div>",
                         "Lock a team to put it in every combo, or skip a game."),
        "look": section("Look", switch("dark", "Dark mode")),
        "order": section("Game order", switch("dogs_late", "Underdogs late: favourites in the early games"),
                         "Underdog picks go in the latest games. If the early favourites win, your combo is worth "
                         "more before the risky game starts, so you can cash out then. It doesn't change a combo's "
                         "chance or average value, only when you find out."),
        "overlap": section("Overlap", slider("max_share", "Max share of combos for one pick", 20, 100, 10, "%")
                           + switch("hedge_close", "Split coin-flip games between both sides"),
                           "Keeps one result from sinking most of your combos. Every-game combos and locked "
                           "picks are exempt, since they include those games on purpose."),
        "midday": section("Mid-day", switch("include_live", "Include games already in progress")
                          + slider("live_min", "Live picks: minimum chance", 10, 50, 5, "%"),
                          "Building after games have started uses only games still to play. Games under way are "
                          "included at Kalshi's live price, except ones nearly decided, jumpy, or where Kalshi "
                          "and live sportsbook odds disagree."),
        "cash": section("Cash out", slider("bankroll", "Your betting bankroll", 100, 5000, 100, "$")
                        + switch("auto_cash", "Keep a cash-out offer ready on every live combo")
                        + slider("refresh_secs", "Live updates every", 10, 120, 5, "s")
                + slider("cash_every", "Fresh cash-out offers every", 1, 10, 1, " min")
                        + slider("tp_mult", "Auto-sell at", 2, 10, 1, "×")
                        + switch("tp_auto", "Add an auto-sell order to combos I buy here"),
                        "Bankroll: the bigger a cash-out offer is next to this, the more the planner favours "
                        "taking the sure money. Auto-sell puts a standing sell order on Kalshi; it works with "
                        "your phone closed but only fills if a buyer pays that much. Nothing sells unless you "
                        "confirm or set auto-sell."),
        "kalshi": section("Kalshi account",
                          f"<input class='txt' id='kalshi_key_id' placeholder='Key ID' autocapitalize='off' autocorrect='off' "
                          f"spellcheck='false' value='{e(CFG['kalshi_key_id'])}'>"
                          + ("<div class='pos' style='font-size:13px;margin:8px 0'>Private key saved on this phone.</div>"
                             if have_key else "<div class='muted' style='font-size:13px;margin:8px 0'>Paste the whole private key.</div>")
                          + "<textarea class='txt' id='pem' rows='3' autocapitalize='off' autocorrect='off' spellcheck='false' "
                            "placeholder='-----BEGIN PRIVATE KEY-----'></textarea>"
                            "<button class='btn' style='margin-top:8px' onclick=\"go('check')\">Save key &amp; check connection</button>",
                          "From Kalshi → Account → API keys. With a read + write key, the planner can buy and cash "
                          "out (only when you confirm). Paste a new private key only to replace the saved one."),
        "odds": section("Sportsbook odds",
                        f"<input class='txt' id='odds_key' placeholder='Paste key here' autocapitalize='off' autocorrect='off' "
                        f"spellcheck='false' value='{e(CFG['odds_key'])}'>"
                        + "<button class='btn' style='margin-top:8px' onclick=\"go('save')\">Save</button>"
                        + switch("skip_news", "Leave out games where Kalshi and the books disagree a lot"),
                        "Free key from the-odds-api.com. Without it, chances use Kalshi's prices only."),
        "home": section("Home Screen", "<button class='btn' onclick=\"go('homescreen')\">Add to Home Screen…</button>"
                        f"<div class='muted' style='font-size:12px;margin-top:8px;word-break:break-all'>Shortcut link: "
                        f"{e(launch_url())}</div>",
                        "Opens the planner with one tap from your Home Screen, without the Pythonista editor."),
    }
    vline = (f"<div class='muted' style='text-align:center;font-size:13px;margin:14px 0 30px'>Version {VERSION} · "
             + ("up to date" if latest and version_tuple(latest) <= version_tuple(VERSION) else
                "update available" if latest else "couldn't check for updates") + "</div>")
    if mode == "build":
        upd = (f"<div class='note'>Update available: see the Settings tab.</div>"
               if latest and version_tuple(latest) > version_tuple(VERSION) else "")
        notice_html = [x for x in top if "class='game'" in x]
        body = "".join([
            f"<header><h1>Build {LG()['name']} combos</h1><div class='sub' id='budgetline'></div></header><section>",
            upd, "".join(notice_html),
            sec["days"], sec["money"], sec["mix"], sec["picks"],
            "<button class='btn go big' style='margin:18px 0 8px' onclick=\"go('build')\">Build combos</button>",
            "</section>"])
    else:
        body = "".join([
            "<header><h1>Settings</h1></header><section>",
            "<div class='stack'>" + "".join(x for x in top if "go('lg-" not in x) + "</div>",
            sec["look"], sec["cash"], sec["order"], sec["midday"], sec["overlap"], sec["kalshi"], sec["odds"],
            sec["home"],
            "<button class='btn go big' style='margin:18px 0 4px' onclick=\"go('save')\">Save settings</button>",
            vline, "</section>"])
    css_extra = (".stack{display:flex;flex-direction:column;gap:8px;margin-top:8px}.big{width:100%;padding:13px;font-size:16px}"
                 ".srow{padding:6px 0}.srow input[type=range]{width:100%}.swrow{padding:8px 0;gap:12px}"
                 ".sw{width:22px;height:22px;flex:none}.txt{width:100%;font:15px -apple-system,sans-serif;padding:10px;"
                 "border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--ink)}"
                 "textarea.txt{font:12px Menlo,monospace}.pickrow{padding:8px 0;border-top:1px solid var(--line)}"
                 ".pickrow:first-of-type{border-top:0}.seg{display:flex;margin-top:6px;border:1px solid var(--line);"
                 "border-radius:9px;overflow:hidden}.seg label{flex:1}.seg input{display:none}.seg span{display:block;"
                 "text-align:center;padding:7px 0;font-size:14px;font-weight:600}.seg input:checked+span"
                 "{background:var(--accent);color:#fff}button:disabled{opacity:.6}")
    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<style>{CSS}{css_extra}</style></head><body>{body}"
            f"<script>{SETTINGS_JS % json.dumps(sliders)}</script></body></html>")

    done = threading.Event()
    result = {"go": None}

    @safe_delegate
    class SettingsKeeper:
        def webview_should_start_load(self, webview, url, nav_type):
            if not url.startswith("combo://settings/"):
                return True
            choice, _, data = url[len("combo://settings/"):].partition("/")
            try:
                vals = json.loads(unquote(data)) if data else {}
            except ValueError:
                vals = {}
            pem = vals.pop("pem", "")
            cleared = []
            for k in KEY_FIELDS:
                if k in vals and not str(vals[k]).strip() and CFG.get(k):
                    if "settings" == APP.get("smode") and choice == "save":
                        cleared.append(k)          # you blanked it and tapped Save on Settings
                    else:
                        vals.pop(k)                # anything else never clears a saved key
            for k, v in vals.items():
                if k in CFG:
                    CFG[k] = type(CFG[k])(v) if isinstance(CFG[k], (int, bool)) and not isinstance(v, dict) else v
            save_cfg(cleared)
            if pem.strip():
                save_private_key(pem)
            result["go"] = choice
            done.set()
            return False

    APP["settings_wait"] = (result, done)
    try:
        present(page, SettingsKeeper())
        while not done.wait(0.5):
            if not window_open():
                return None            # closed with the X
    finally:
        APP["settings_wait"] = None
    return result["go"]


# ================================================================ main
RUN_OPTS = {}


def this_week(sunday):
    """Has this week already been set? 'account' (combos on Kalshi), 'planner'
    (combos ticked Placed in the planner), or None."""
    if can_trade():
        loading("Checking your Kalshi account…")
        acct, _, _ = fetch_account()
        if acct and any(in_week(a, sunday.isoformat()) for a in acct):
            return "account"
    hist = load_json(HISTORY, {"builds": []})
    if os.path.exists(LATEST) and any(b["week"] == sunday.isoformat() and b.get("placed")
                                      and b.get("league", "nfl") == LEAGUE["code"]
                                      for b in hist["builds"]):
        return "planner"
    return None


def reopen_settings(webview):
    """'Settings & build more': switch to the settings page in the same window."""
    import threading

    def go():
        RUN_OPTS["force_settings"] = True
        run()
    threading.Thread(target=go, daemon=True).start()


def main():
    set_league(load_json(LEAGUE_FILE, {}).get("league", LEAGUE["code"]))
    loading(f"Loading {'the ' + LG()['name'].lower() if by_day() else 'this week'}'s games from Kalshi…")
    RUN_OPTS["latest"] = latest_version()
    all_games, days, sunday = week_games(fetch_markets())
    CFG["picks"] = {e: v for e, v in CFG["picks"].items() if e in all_games}  # drop old weeks
    import_key_file()
    counts = defaultdict(int)
    for d in days.values():
        counts["Thursday" if d == "Friday" else d] += 1

    goto = RUN_OPTS.pop("goto", None)
    APP["where"] = goto if goto in ("mine", "results", "settings") else APP.get("where")
    if goto == "mine":
        return show_mine(all_games, days, sunday)
    if goto == "results":
        return show_results(all_games, days, sunday)
    if goto == "settings":
        RUN_OPTS["force_settings"] = True
    if not RUN_OPTS.pop("force_settings", False):
        already = this_week(sunday)
        if already and RUN_OPTS.get("latest") and version_tuple(RUN_OPTS["latest"]) > version_tuple(VERSION):
            MINE["notice"] = f"Update available (version {RUN_OPTS['latest']}): tap Settings & build more, then Update."
        if already == "account":
            return show_mine(all_games, days, sunday)
        if already == "planner":
            return show_results(all_games, days, sunday)

    choice = settings_page(all_games, days, counts)
    if choice == "show":
        return show_results(all_games, days, sunday)
    if choice == "mine":
        return show_mine(all_games, days, sunday)
    if choice == "save":
        RUN_OPTS["notice"] = "Saved." + ("" if CFG.get("odds_key") else " (No sportsbook key: chances use Kalshi's prices.)")
        RUN_OPTS["smode"] = "settings"
        RUN_OPTS["goto"] = "settings"
        return main()
    if choice in ("tab-build", "tab-settings"):
        RUN_OPTS["smode"] = choice[4:]
        RUN_OPTS["goto"] = "settings"
        return main()
    if choice == "homescreen":
        RUN_OPTS["notice"] = home_screen_help()
        RUN_OPTS["smode"] = "settings"
        RUN_OPTS["goto"] = "settings"
        return main()
    if choice and choice.startswith("lg-"):
        save_json(LEAGUE_FILE, {"league": choice[3:]})
        set_league(choice[3:])
        RUN_OPTS["goto"] = "settings"
        return main()
    if choice == "mine":
        APP["where"] = "mine"
    if choice == "show":
        APP["where"] = "results"
    if choice == "check":
        return diagnose()
    if choice == "update":
        loading("Checking for updates…")
        ok, msg = install_update()
        if ok:
            loading("Starting the new version…")
            if relaunch():
                return None
            return present(update_page(ok, msg))
        RUN_OPTS["notice"] = msg
        RUN_OPTS["goto"] = "settings"
        return main()
    if choice != "build":
        return console_note("Closed without building.")

    notes = []
    book = {}
    if CFG["odds_key"]:
        loading("Getting sportsbook odds…")
        book, note = fetch_book_odds(CFG["odds_key"])
        notes.append(note)
    else:
        notes.append("Chances use Kalshi's prices. Add a sportsbook key in settings for sharper fair payouts.")
    matched, news = attach_fair(all_games, book)
    remember_pregame(all_games)
    if book and matched < len(all_games):
        notes.append(f"{len(all_games) - matched} game(s) had no sportsbook match and use Kalshi's prices.")

    on = day_on()
    book_fair = {e: [x["fair"] for x in sides] for e, sides in all_games.items() if sides[0].get("src")}
    skipped, live = screen_live(all_games, book_fair)
    for e in all_games:
        if e in live:
            if CFG["picks"].get(e) == "skip":
                skipped[e] = "You skipped this game."
            continue
        if CFG["picks"].get(e) == "skip":
            skipped[e] = "You skipped this game."
        elif CFG["skip_news"] and news.get(e, 0) >= NEWS_GAP and on[days[e]] \
                and CFG["picks"].get(e) is None:
            skipped[e] = (f"Left out: Kalshi and the sportsbooks disagree by {news[e]:.0%}, "
                          "probably breaking news. Lock a team to include it anyway.")
    if any("disagree" in v for v in skipped.values()):
        n = sum("disagree" in v for v in skipped.values())
        notes.append(f"Left out {n} game(s) with likely breaking news. See the Games tab.")
    live_in = [e for e in live if e not in skipped and on[days[e]]]
    live_out = [e for e in live if e in skipped and on[days[e]]]
    if live:
        notes.append(f"Mid-day build: {len(live_in)} game(s) in progress included at Kalshi's live prices"
                     + (f", {len(live_out)} left out as bad bets right now (see the Games tab)" if live_out else "")
                     + ". Live prices move fast, so get offers soon. Kalshi may not offer combos that "
                       "include games already under way.")
    games = {e: s for e, s in all_games.items() if on[days[e]] and e not in skipped}
    if len(games) < 4:
        off = [e for e in all_games if not on[days[e]]]
        offdays = sorted({days[e] for e in off})
        why = [f"Only {len(games)} game{'s' if len(games) != 1 else ''} can be picked right now, "
               "and a combo plan needs at least 4."]
        if live_out:
            why.append(f"{len(live_out)} game(s) in progress were left out as bad bets: nearly decided, "
                       f"prices jumping too much, or no team with at least a {CFG['live_min']}% live chance.")
        if off:
            why.append(f"{len(off)} game(s) are on days you have switched off ({', '.join(offdays)}).")
        if any(v == "You skipped this game." for v in skipped.values()):
            why.append("Some games are set to Skip in Settings.")
        why.append("Games that have already finished aren't listed.")
        tips = []
        if off:
            tips.append(f"switch on {' and '.join(offdays)} in Settings")
        if live_out:
            tips.append("lower Live picks: minimum chance in Settings → Mid-day")
        tips.append("or switch to tomorrow's games in Settings → Day" if by_day() else
                    "or come back for next week's games, which usually open on Kalshi by Tuesday")
        why.append("To get more games: " + ", ".join(tips) + ".")
        raise Stop("Not enough games right now", " ".join(why))
    # Only build combos Kalshi will actually take: its allowed games and number of picks.
    loading("Checking which games Kalshi takes in combos…")
    rules = combo_rules(games)
    if rules is not None:
        ok, most, fewest = rules
        if len(ok) < 2:
            raise Stop("Kalshi doesn't offer combos on these games",
                       f"None of the {len(games)} games here can go into a Kalshi combo right now. "
                       + ("Kalshi may not offer college basketball combos, or not on these games. "
                          "Try tomorrow's games, or switch to NFL with the 🏈 button." if by_day() else
                          "Try again later, or check Kalshi's combo builder in the app."))
        left_out = [e for e in games if e not in ok]
        if left_out:
            notes.append(f"Kalshi only takes {len(ok)} of these {len(games)} games in combos, "
                         f"so {len(left_out)} were left out.")
            games = {e: s for e, s in games.items() if e in ok}
        if most < 99:
            for t in TIERS:
                CFG[f"{t}_max"] = min(CFG[f"{t}_max"], most)
                CFG[f"{t}_min"] = min(CFG[f"{t}_min"], most)
            if CFG["full_count"] and len(games) > most:
                notes.append(f"Kalshi allows at most {most} picks in a combo, so there are no "
                             f"every-game combos this time.")
                CFG["full_count"] = 0
        if len(games) < 2:
            raise Stop("Not enough games Kalshi takes in combos",
                       f"Only {len(games)} game here can go into a Kalshi combo right now.")
    locks = {e: t for e, t in CFG["picks"].items() if e in games and t != "skip"}
    clean_cfg(len(games))

    loading("Building your combos…")
    combos, trimmed = build_combos(games, locks, random.Random(SEED))
    if trimmed:
        notes.append(f"Trimmed to stay under your ${CFG['budget']} cap.")
    short = sum(1 for c in combos if c["kind"] != "full" and len(c["legs"]) < CFG[f"{c['kind']}_min"])
    made = len(combos)
    asked = min(CFG["full_count"] + sum(CFG[f"{t}_count"] for t in TIERS), int(CFG["budget"] // CFG["stake"]))
    if short or made < asked:
        notes.append(f"Your overlap limit ({CFG['max_share']}%) is tight for this slate: "
                     + (f"{short} combo(s) have fewer games than you asked for" if short else "")
                     + (" and " if short and made < asked else "")
                     + (f"only {made} of {asked} combos fit" if made < asked else "")
                     + ". Raise the limit in Settings → Overlap if you want more.")
    loading(f"Playing out 20,000 {slate_word()}s…")
    p_any, p_each = simulate(combos, games)

    build_id = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    history = load_json(HISTORY, {"builds": []})
    # An earlier build this week with nothing placed is just replaced.
    history["builds"] = [b for b in history["builds"]
                         if b.get("placed") or b["week"] != sunday.isoformat()
                         or b.get("league", "nfl") != LEAGUE["code"]]
    history["builds"].append({
        "id": build_id, "week": sunday.isoformat(), "stake": CFG["stake"], "league": LEAGUE["code"],
        "placed": [], "quotes": {}, "results": {},
        "combos": [{"kind": c["kind"], "tier": c["tier"], "fair": round(c["fair"], 2),
                    "min": round(c["min"], 2),
                    "legs": [{"ticker": l["ticker"], "pick": l["pick"], "dog": l["fair"] < 0.5} for l in c["legs"]]}
                   for c in combos]})
    save_json(HISTORY, history)

    page = render(build_id, combos, games, all_games, days, sunday, p_any, p_each,
                  notes, locks, skipped, news)
    with open(LATEST, "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(HERE, f"combos_{dt.date.today().isoformat()}.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "type", "picks", "fair_payout", "min_to_accept", "win_chance", "teams"])
        for i, (c, p) in enumerate(zip(combos, p_each), 1):
            w.writerow([i, c["tier"], len(c["legs"]), round(c["fair"]), round(c["min"]),
                        f"{p:.3%}", " | ".join(l["pick"] for l in c["legs"])])
    CTX.clear()
    CTX.update({"games": games, "all_games": all_games, "days": days, "sunday": sunday,
                "locks": locks, "skipped": skipped, "news": news, "notes": notes, "combos": combos,
                "build_id": build_id, "stake": CFG["stake"], "offers": {}})
    console_note(f"Built {len(combos)} combos (${len(combos) * CFG['stake']}). Opening results...")
    show_build()


# ================================================================ updates
def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return (0,)


def latest_version():
    """Newest published version, or None if it can't be checked right now."""
    try:
        r = requests.get(UPDATE_URL + "/version.txt", timeout=6, headers={"Cache-Control": "no-cache"})
        if r.ok and re.fullmatch(r"[0-9.]+", r.text.strip()):
            return r.text.strip()
    except requests.RequestException:
        pass
    return None


def install_update():
    """Download the newest version, check it, keep a backup, swap it in.
    Returns (ok, message). Your settings, keys and history are separate files and stay put."""
    try:
        r = requests.get(UPDATE_URL + "/nfl_combo_planner.py", timeout=30, headers={"Cache-Control": "no-cache"})
        if not getattr(r, "ok", False):
            return False, "Couldn't download the update. Check your connection and try again."
        src = r.content.decode("utf-8", errors="strict")
    except (requests.RequestException, UnicodeDecodeError, AttributeError):
        return False, "Couldn't download the update. Check your connection and try again."
    found = re.search(r'^VERSION = "([0-9.]+)"', src, re.M)
    if not found or "def main():" not in src or len(src) < 50000:
        return False, "The download didn't look like a complete planner, so nothing was changed."
    try:
        compile(src, "nfl_combo_planner.py", "exec")      # must run on this phone's Python
    except SyntaxError as err:
        return False, f"The new version has a problem (line {err.lineno}), so nothing was changed."
    if version_tuple(found.group(1)) <= version_tuple(VERSION):
        return False, f"You already have the latest version ({VERSION})."
    me = ENGINE                                   # never the file you tap
    try:
        with open(SCRIPT_PATH, encoding="utf-8") as fh:
            current = fh.read()
        with open(os.path.join(HERE, "combo_planner_engine_backup.txt"), "w", encoding="utf-8") as fh:
            fh.write(current)                     # .txt so the editor never opens a big backup
        tmp = me + ".new"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(src)
        os.replace(tmp, me)
    except OSError as err:
        return False, f"Couldn't save the update ({err}). Your current version is unchanged."
    return True, (f"Updated to version {found.group(1)}. Close this window with the X at the top left, "
                  "then tap Run. (The previous version is saved as combo_planner_engine_backup.txt.)")
    # (that message only shows if the new version can't start in this window by itself)


def update_page(ok, msg):
    color = "pos" if ok else "muted"
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<style>{CSS}</style></head><body><header><h1>{'Updated' if ok else 'Update'}</h1></header>"
            f"<section><div class='empty'><span class='{color}'>{html.escape(msg)}</span></div></section></body></html>")


class Stop(Exception):
    """A planned stop with a message to show (not a crash)."""
    def __init__(self, title, msg):
        super().__init__(msg)
        self.title = title


def run():
    """main(), but any failure shows a readable page instead of a stuck spinner."""
    try:
        main()
    except Stop as stop:
        present(error_page(str(stop), stop.title, crash=False))
    except KeyboardInterrupt as stop:      # Pythonista turns exit() into this
        msg = str(stop)
        if msg.startswith("Exit:") and APP["web"] is not None and window_open():
            present(error_page(msg[5:].strip(), "Stopped", crash=False))
    except SystemExit as stop:
        if APP["web"] is not None and stop.code:
            present(error_page(str(stop.code)))
        elif stop.code:
            console_note(stop.code)
    except Exception as err:
        import traceback
        console_note(traceback.format_exc())
        if isinstance(err, requests.RequestException):
            msg = "Couldn't reach Kalshi. Check your connection and try again."
        else:
            msg = f"Something went wrong: {type(err).__name__}: {err}"
        present(error_page(msg))


def error_page(msg, title="Hmm.", crash=True):
    tail = ("<br><br>Use the buttons above to try again. If it keeps happening, send me a screenshot."
            if crash else "")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<style>{CSS}</style></head><body><header><h1>{html.escape(title)}</h1></header><section>"
            f"<div class='empty' style='text-align:left;line-height:1.5'>{html.escape(msg)}{tail}</div>"
            "</section></body></html>")


LAUNCH_URL = "pythonista3://nfl_combo_planner?action=run"


def launch_url():
    """The pythonista3:// link that runs the file you tap, wherever it lives (this phone's
    Pythonista folder, a subfolder, or Pythonista's iCloud folder)."""
    target = os.path.join(HERE, "nfl_combo_planner.py")
    real = os.path.realpath(target)
    marker = "iCloud~com~omz-software~Pythonista3/Documents"
    if marker in real:
        rel, root = real.split(marker, 1)[1].lstrip("/"), "icloud"
    else:
        base = os.path.realpath(os.path.expanduser("~/Documents"))
        rel = os.path.relpath(real, base) if real.startswith(base) else os.path.basename(real)
        root = None
    rel = rel[:-3] if rel.endswith(".py") else rel
    return f"pythonista3://{quote(rel)}?action=run" + (f"&root={root}" if root else "")


def home_screen_help():
    """Copy the launch link and open the Shortcuts app, with the steps to finish."""
    try:
        import clipboard
        clipboard.set(launch_url())
        copied = True
    except Exception:
        copied = False
    open_outside("shortcuts://create-shortcut")
    return ("Home Screen icon: in Shortcuts, tap Add Action, search for \"Open URLs\", and paste "
            + ("the link I copied for you (" + launch_url() + ")" if copied else launch_url())
            + ". Name it Combos, then tap the share icon → Add to Home Screen.")


def file_version(path):
    try:
        with open(path, encoding="utf-8") as fh:
            hit = re.search(r'^VERSION = "([0-9.]+)"', fh.read(4000), re.M)
        return hit.group(1) if hit else None
    except OSError:
        return None


def launch():
    """Run the newest code: the engine file if it's newer than the file you tapped."""
    if os.path.abspath(SCRIPT_PATH) != os.path.abspath(ENGINE):
        v = file_version(ENGINE)
        if v and version_tuple(v) > version_tuple(VERSION):
            import runpy
            try:
                runpy.run_path(ENGINE, run_name="__main__")
                return
            except Exception:
                pass                              # a broken engine: fall back to this version
    run()


if __name__ == "__main__":
    launch()
