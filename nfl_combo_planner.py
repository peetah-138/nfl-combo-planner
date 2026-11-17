#!/usr/bin/env python3
"""
nfl_combo_planner.py - plan Kalshi NFL combos for a weekend slate.
Read-only: uses Kalshi's public market data (and, optionally, sportsbook odds
from the-odds-api.com). It never places a bet.

Pythonista on iPhone: tap Run, set the sliders and switches, tap Build.
Everything is remembered. No need to edit anything in this file.
"""
import csv, datetime as dt, html, itertools, json, math, os, random, re, statistics, sys, time
from collections import defaultdict
from urllib.parse import quote, unquote
import requests

SEED = None  # leave as is
VERSION = "2026.11.17.57"
UPDATE_URL = "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main"   # new versions (your GitHub repo)

# Starting values. The settings screen changes these for you and remembers them.
CFG = {
    "stake": 5, "budget": 100, "accept_pct": 90,
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
    "tp_mult": 3,         # (old fixed auto-sell multiple, no longer used)
    "ride": 2,            # auto-sell "Let it ride" level: 0 Cautious ... 4 Ride it out (see RIDE)
    "tp_follow": True,    # move auto-sell orders as chances change, while the planner is open
    "tp_ladder": True,    # auto-sell in thirds, from the wait-one-more-game price up toward the payout
    "tp_auto": False,     # put an auto-sell order on every live combo (every league)
    "auto_sell": False,   # cash out by itself when the plan says to (Let it ride level), while open
    "auto_cap": 5,        # at most this many automatic cash-outs a day (per device)
    "auto_hedge": True,   # with Auto cash-out on: hedge instead when that locks in more (a purchase)
    "hedge_cap": 100,     # ...spending at most this much on one hedge; above it, cash out instead
    "notify_value": True, # Mac: tell me when a combo quotes at a fair price (bundled, max 1 per 30 min)
    "notify_price": True, # Mac: a combo's price just got noticeably better
    "notify_cash": True,  # Mac: cash-outs and hedges worth taking or done
    "notify_news": True,  # Mac: sportsbooks moved sharply on a game you hold or might pick
    "prefer_hedge": True, # hedge even when it locks in up to 5% less than the cash-out (no 10% buyer's cut)
    "size_auto": True,    # bet more when Kalshi's price is good: $3 near the cut-off up to $10 above fair
    "size_min": 3, "size_max": 10,
    "mix_v3": False,      # (one-time move to mostly 2-4 pick combos + 2 moonshots)
    "cut_v2": False,      # (one-time move of the fair-price cut-off to 90%)
    "mix_window": 0,
    "mix_v2": False,      # (one-time move of Mix to longer combos, if you hadn't changed its mix)      # Mixed sports: 0 same day, 1 through the weekend (Monday), 2 next 7 days
    "watcher_code": "",   # pairing code for the Raspberry Pi watcher (its ntfy topic + signing secret)
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
MIX_DAYS = []    # the Mix mode's day labels, in order (filled by week_games)
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

NHL_TEAMS = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames",
    "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche",
    "CBJ": "Columbus Blue Jackets", "CLB": "Columbus Blue Jackets", "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LA": "Los Angeles Kings",
    "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "MON": "Montreal Canadiens",
    "NSH": "Nashville Predators", "NJ": "New Jersey Devils", "NJD": "New Jersey Devils",
    "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJ": "San Jose Sharks", "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TB": "Tampa Bay Lightning", "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Mammoth", "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WAS": "Washington Capitals",
    "WPG": "Winnipeg Jets",
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
    # Hockey favourites rarely top 70%, so combos run shorter than basketball's.
    "nhl": {"name": "NHL", "short": "NHL", "icon": "🏒", "series": "KXNHLGAME", "odds": "icehockey_nhl",
            "espn": "hockey/nhl", "espn_q": {}, "slate": "day", "game_hours": 2.75, "periods": 3,
            "full": True, "teams": "nhl",
            "settings": "combo_settings_nhl.json", "latest": "combos_latest_nhl.html",
            "defaults": {"budget": 50, "full_count": 1, "upsets_min": 1, "upsets_max": 2,
                         "safer_count": 4, "safer_min": 2, "safer_max": 2,
                         "middle_count": 3, "middle_min": 3, "middle_max": 4,
                         "moonshot_count": 2, "moonshot_min": 4, "moonshot_max": 6}},
    # College football: big Saturday slates, many lopsided games. Kalshi's names are used for teams.
    "ncaaf": {"name": "College football", "short": "CFB", "icon": "🎓", "series": "KXNCAAFGAME",
              "odds": "americanfootball_ncaaf", "espn": "football/college-football", "espn_q": {"groups": "80"},
              "slate": "week", "game_hours": 3.5, "periods": 4, "full": False, "teams": None,
              "settings": "combo_settings_ncaaf.json", "latest": "combos_latest_ncaaf.html",
              "defaults": {"budget": 50, "thursday": True, "saturday": True, "monday": False, "full_count": 0,
                           "safer_count": 3, "safer_min": 2, "safer_max": 3,
                           "middle_count": 3, "middle_min": 3, "middle_max": 5,
                           "moonshot_count": 2, "moonshot_min": 5, "moonshot_max": 8}},
    # College basketball: huge daily slates and the softest lines; games without a sportsbook line
    # are left out (Kalshi alone isn't a reliable fair price for small-conference games).
    "ncaamb": {"name": "Men's college basketball", "short": "CBB", "icon": "🏀", "series": "KXNCAAMBGAME",
               "odds": "basketball_ncaab", "espn": "basketball/mens-college-basketball", "espn_q": {"groups": "50"},
               "slate": "day", "game_hours": 2.25, "periods": 2, "full": False, "teams": None, "require_line": True,
               "settings": "combo_settings_ncaamb.json", "latest": "combos_latest_ncaamb.html",
               "defaults": {"budget": 40, "full_count": 0, "mix_v3": True,
                            "safer_count": 3, "safer_min": 2, "safer_max": 3, "middle_count": 3, "middle_min": 3,
                            "middle_max": 4, "moonshot_count": 2, "moonshot_min": 6, "moonshot_max": 9}},
    "ncaawb": {"name": "Women's college basketball", "short": "WCBB", "icon": "🏀", "series": "KXNCAAWBGAME",
               "odds": "basketball_wncaab", "espn": "basketball/womens-college-basketball", "espn_q": {"groups": "50"},
               "slate": "day", "game_hours": 2.25, "periods": 4, "full": False, "teams": None, "require_line": True,
               "settings": "combo_settings_ncaawb.json", "latest": "combos_latest_ncaawb.html",
               "defaults": {"budget": 30, "full_count": 0, "mix_v3": True,
                            "safer_count": 2, "safer_min": 2, "safer_max": 3, "middle_count": 2, "middle_min": 3,
                            "middle_max": 4, "moonshot_count": 2, "moonshot_min": 5, "moonshot_max": 8}},
    # EuroLeague: overtime decides every game (no draws); strong home court is already in the lines.
    "euroleague": {"name": "EuroLeague", "short": "Euro", "icon": "🏀", "series": "KXEUROLEAGUEGAME",
                   "odds": "basketball_euroleague", "espn": None, "espn_q": {}, "slate": "day", "game_hours": 2.25,
                   "periods": 4, "full": False, "teams": None, "require_line": True,
                   "settings": "combo_settings_euroleague.json", "latest": "combos_latest_euroleague.html",
                   "defaults": {"budget": 25, "full_count": 0, "mix_v3": True, "next_day": False,
                                "safer_count": 2, "safer_min": 2, "safer_max": 2, "middle_count": 2, "middle_min": 3,
                                "middle_max": 3, "moonshot_count": 1, "moonshot_min": 4, "moonshot_max": 5}},
    # UFC: one card a week, ~12 fights; big favourites are common but upsets land about a third of the
    # time, so favourites under 60% count as coin flips. The main card (the late fights) goes last.
    "ufc": {"name": "UFC", "short": "UFC", "icon": "🥊", "series": "KXUFCFIGHT", "odds": "mma_mixed_martial_arts",
            "espn": None, "espn_q": {}, "slate": "week", "game_hours": 0.5, "periods": 3, "full": False, "teams": None,
            "require_line": True, "close": 0.60,
            "settings": "combo_settings_ufc.json", "latest": "combos_latest_ufc.html",
            "defaults": {"budget": 25, "full_count": 0, "mix_v3": True, "saturday": True, "thursday": True, "monday": False,
                         "safer_count": 2, "safer_min": 2, "safer_max": 3, "middle_count": 2, "middle_min": 3,
                         "middle_max": 4, "moonshot_count": 1, "moonshot_min": 5, "moonshot_max": 7}},
    # Soccer: a "to win" pick loses on a draw (about 1 in 4 games), so near-even games are traps:
    # favourites under 50% count as close, picks under 30% are skipped, combos stay short.
    "soccer": {"name": "Soccer", "short": "Soccer", "icon": "⚽", "series": "KXEPLGAME,KXLALIGAGAME,KXSERIEAGAME,KXBUNDESLIGAGAME,KXLIGUE1GAME,KXMLSGAME,KXLIGAMXGAME",
               "odds": ["soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a", "soccer_germany_bundesliga",
                        "soccer_france_ligue_one", "soccer_usa_mls", "soccer_mexico_ligamx"], "regions": "eu",
               "espn": ["soccer/eng.1", "soccer/esp.1", "soccer/ita.1", "soccer/ger.1", "soccer/fra.1",
                        "soccer/usa.1", "soccer/mex.1"], "espn_q": {},
               "slate": "week", "game_hours": 2.0, "periods": 2, "full": False, "teams": None, "require_line": True,
               "close": 0.50, "min_pick": 0.30,
               "settings": "combo_settings_soccer.json", "latest": "combos_latest_soccer.html",
               "defaults": {"budget": 30, "full_count": 0, "mix_v3": True, "saturday": True, "thursday": True, "monday": True,
                            "safer_count": 3, "safer_min": 2, "safer_max": 2, "middle_count": 3, "middle_min": 3,
                            "middle_max": 3, "moonshot_count": 2, "moonshot_min": 4, "moonshot_max": 6}},
    # ATP tennis: two outcomes (a retirement settles by Kalshi's rules); start times follow the order of
    # play, so "underdogs late" is off. The odds feed lists tennis tournament by tournament.
    "tennis": {"name": "ATP tennis", "short": "Tennis", "icon": "🎾", "series": "KXATPMATCH", "odds": "tennis_atp",
               "espn": None, "espn_q": {}, "slate": "day", "game_hours": 2.5, "periods": 3, "full": False,
               "teams": None, "require_line": True,
               "settings": "combo_settings_tennis.json", "latest": "combos_latest_tennis.html",
               "defaults": {"budget": 25, "full_count": 0, "mix_v3": True, "dogs_late": False,
                            "safer_count": 2, "safer_min": 2, "safer_max": 3, "middle_count": 2, "middle_min": 3,
                            "middle_max": 4, "moonshot_count": 1, "moonshot_min": 5, "moonshot_max": 6}},
    # Every sport at once: combos that mix NFL, NBA, NHL and college football (Kalshi's cross-sport combos).
    "mix": {"name": "Mixed sports", "short": "Mix", "icon": "🎲", "series": "KXNFLGAME,KXNBAGAME,KXNHLGAME,KXNCAAFGAME",
            "odds": "mixed", "espn": "football/nfl", "espn_q": {}, "slate": "mix", "game_hours": 3.5, "periods": 4,
            "full": False, "teams": None,
            "settings": "combo_settings_mix.json", "latest": "combos_latest_mix.html",
            "defaults": {"budget": 50, "full_count": 0,
                         "safer_count": 2, "safer_min": 2, "safer_max": 3,
                         "middle_count": 3, "middle_min": 4, "middle_max": 5,
                         "moonshot_count": 3, "moonshot_min": 6, "moonshot_max": 9}},
}
MIX_SPORTS = ("nfl", "nba", "nhl", "ncaaf")
MIX_WINDOWS = ["Same day", "Through the weekend", "Next 7 days"]
LEAGUE = {"code": "nfl"}
PRIMARY_SPORTS = ("nfl", "nba", "nhl", "ncaaf")        # on the sport picker; the rest are under More


def sport_rule(ticker, key, default):
    """A betting rule for the sport this pick is in (e.g. soccer's draw-aware thresholds)."""
    return (LEAGUES.get(ticker_sport(ticker)) or LG()).get(key, default)
SHARED_KEYS = ("kalshi_key_id", "odds_key", "bankroll", "auto_cash", "cash_every", "ride", "tp_follow", "tp_auto", "tp_ladder", "watcher_code", "auto_sell", "auto_cap", "auto_hedge", "hedge_cap", "prefer_hedge", "size_auto", "notify_value", "notify_price", "notify_cash", "notify_news")


def next_league():
    """The next league in the list (NFL -> NBA -> NHL -> NFL)."""
    order = list(LEAGUES)
    return order[(order.index(LEAGUE["code"]) + 1) % len(order)]


def sport_seg(via="nav"):
    """The sport picker: a segmented control at the top of Build and Results (NFL, NBA, NHL, Mix).
    via='form' saves the Build page's settings before switching."""
    tap = lambda k: (f"go('lg-{k}')" if via == "form" else f"location.href='combo://nav/lg-{k}'")
    more = [k for k in LEAGUES if k not in PRIMARY_SPORTS and k != "mix"]
    cur = LEAGUE["code"]
    btns = "".join(f"<button class='{'on' if k == cur else ''}' onclick=\"{tap(k)}\">{LEAGUES[k]['short']}</button>"
                   for k in list(PRIMARY_SPORTS) + ["mix"])
    btns += (f"<button class='{'on' if cur in more else ''}' onclick=\"var m=document.getElementById('moresp');"
             f"m.style.display=m.style.display==='flex'?'none':'flex'\">"
             f"{LEAGUES[cur]['short'] if cur in more else 'More'} ▾</button>")
    chips = "".join(f"<button class='btn {'go' if k == cur else 'quiet'}' style='flex:none;min-height:0;padding:7px 12px' "
                    f"onclick=\"{tap(k)}\">{LEAGUES[k]['icon']} {LEAGUES[k]['name']}</button>" for k in more)
    return (f"<div class='tabs seg'>{btns}</div><div id='moresp' style='display:none;flex-wrap:wrap;gap:8px;"
            f"margin:0 0 6px'>{chips}</div>")


def LG():
    return LEAGUES[LEAGUE["code"]]


def by_day():
    """True for daily slates (college basketball), False for the NFL's Thursday-Monday week."""
    return LG()["slate"] == "day" or (LG()["slate"] == "mix" and not CFG.get("mix_window"))


def is_mix():
    return LG()["slate"] == "mix"


def day_seq():
    """The order day labels are shown in (the Mix mode makes its own)."""
    return MIX_DAYS or DAY_ORDER


def slate_word():
    return "day" if by_day() else "weekend"


def day_on():
    """Which day labels are switched on (every day in the Mix mode's window)."""
    if is_mix():
        return defaultdict(lambda: True)
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
    TEAMS = {"nfl": NFL_TEAMS, "nba": NBA_TEAMS, "nhl": NHL_TEAMS}.get(lg.get("teams"), {})
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
    if not CFG.get("mix_v3"):                     # mostly 2-4 pick combos at good prices + 2 moonshots
        CFG.update(full_count=0, safer_count=4, safer_min=2, safer_max=3,
                   middle_count=4, middle_min=3, middle_max=4, moonshot_count=2, mix_v3=True, mix_v2=True)
    if code == "mix" and not CFG.get("mix_v2"):
        if (CFG.get("middle_max"), CFG.get("moonshot_max"), CFG.get("moonshot_min")) == (4, 6, 4):
            CFG.update({k: v for k, v in LEAGUES["mix"]["defaults"].items() if k != "budget"})
        CFG["mix_v2"] = True
    if not CFG.get("cut_v2"):                     # the fair-price cut-off moved from 80% to 90% of fair
        if CFG.get("accept_pct") == 80:
            CFG["accept_pct"] = 90
        CFG["cut_v2"] = True
    keys = load_json(KEYS_SAVED, {})             # a saved key is never lost to a blank
    for k in KEY_FIELDS:
        if not str(CFG.get(k, "")).strip() and keys.get(k):
            CFG[k] = keys[k]
    if any(str(CFG.get(k, "")).strip() and not keys.get(k) for k in KEY_FIELDS):
        save_json(KEYS_SAVED, dict(keys, **{k: CFG[k].strip() for k in KEY_FIELDS if str(CFG.get(k, "")).strip()}))


KEY_FIELDS = ("kalshi_key_id", "odds_key", "watcher_code")


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
        if len(sides) == 2:                       # ESPN's live model (football) as a second opinion
            wps = [(leg_score({"ticker": x["ticker"], "side": "yes"}) or {}).get("wp") for x in sides]
            if all(w is not None for w in wps):
                w0 = wps[0] / (wps[0] + wps[1])
                live_fair = [(live_fair[0] + w0) / 2, (live_fair[1] + 1 - w0) / 2]
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
    if "," in SERIES:
        return [m for ser in SERIES.split(",") for m in fetch_series(ser)]
    return fetch_series(SERIES)


def fetch_series(series):
    out, cursor = [], None
    while True:
        params = {"series_ticker": series, "status": "open", "limit": 1000}
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
                    - dt.timedelta(hours=game_hours(event)))
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


def is_tie_market(m):
    """A soccer game's draw market (it can't be picked: the planner bets on teams)."""
    t = (m.get("ticker") or "").upper()
    return t.endswith(("-TIE", "-DRAW")) or (m.get("yes_sub_title") or "").strip().lower() in ("tie", "draw")


def other_side(sides, s):
    """The opposing team (never the draw)."""
    return next((x for x in sides if x is not s and not x.get("tie")), None) or next(x for x in sides if x is not s)


def draw_result(sides, r):
    """Which side wins in one simulated game, for 2 or 3 outcomes, from a random r in [0, 1)."""
    tot = sum(x["fair"] for x in sides) or 1
    acc = 0.0
    for x in sides:
        acc += x["fair"] / tot
        if r < acc:
            return x
    return sides[-1]


def team_name(m):
    """Kalshi's name for a pick, made clear where it's cut short ("New York I" -> "New York Islanders")."""
    name = m.get("yes_sub_title") or m["ticker"]
    if re.search(r" [A-Z]$", name):
        full = sport_teams(ticker_sport(m["ticker"])).get(m["ticker"].rsplit("-", 1)[-1].upper())
        if full:
            return full
    return name


def sport_icon(ticker):
    """The sport's emoji for a pick (shown in the Mix mode, where combos mix sports)."""
    return (SPORTS.get(ticker_sport(ticker)) or {}).get("icon", "")


def when_text(event, day):
    """'Wed 4:45 PM' without the day twice."""
    t, d = start_label(event), day_tag(day)
    return t if (t and d and t.startswith(d)) else " ".join(x for x in (d, t) if x)


def week_games(markets, loose=False):
    """This NFL week's games (Thu-Mon around the coming Sunday), or for daily leagues today's
    (or tomorrow's) games, keyed by game. Returns (games, day label per game, slate date).
    loose=True keeps near-certain prices (games nearly over) for live updates."""
    today = dt.date.today()
    MIX_DAYS.clear()
    if is_mix():
        w = CFG.get("mix_window", 0)
        first = 1 if (w == 0 and CFG.get("next_day")) else 0
        last = first if w == 0 else (6 if w == 2 else max(1, (7 - today.weekday()) % 7 or 7))
        day_of = {}
        for k in range(first, last + 1):
            d = today + dt.timedelta(days=k)
            day_of[d] = "Today" if k == 0 else "Tomorrow" if k == 1 else f"{d:%A}"
            MIX_DAYS.append(day_of[d])
        sunday = today + dt.timedelta(days=first)
    elif by_day():
        sunday = today + dt.timedelta(days=1 if CFG.get("next_day") else 0)
        day_of = {sunday: "Tomorrow" if CFG.get("next_day") else "Today"}
    else:
        sunday = today + dt.timedelta(days=(6 - today.weekday()) % 7)
        day_of = {sunday + dt.timedelta(days=d): n for d, n in zip(range(-3, 2), DAY_ORDER)}
        if today.weekday() == 0:                 # Monday: tonight's game still belongs to the
            day_of.setdefault(today, "Monday")   # week that just ended, so keep it in view
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
                "pick": team_name(m), "p": p, "tie": is_tie_market(m),
                "bid": live_bid(m), "exp": m.get("expected_expiration_time") or ""})
    games = {e: s for e, s in games.items()
             if len(s) == 2 or (len(s) == 3 and sum(1 for x in s if x.get("tie")) == 1)}   # soccer: + a draw
    order = sorted(games, key=lambda e: (day_seq().index(days[e]), games[e][0]["exp"]))
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


SHARP_BOOKS = ("betfair_ex_eu", "betfair_ex_uk", "matchbook", "lowvig", "betonlineag", "circasports")


def fetch_book_odds(key):
    """{full team name: (fair win chance, source)} plus a note. Sharp lines from the odds service when
    there's a key (Pinnacle first), filled in and cross-checked with free sources (ESPN's sportsbook
    line and Polymarket). With the Mac hub, the Mac does all of this and shares one cache."""
    if hub_up():
        got = hub_call("odds", timeout=60, league=LEAGUE["code"], key=key or "")
        if got and isinstance(got.get("snap"), dict):
            return load_book_state(got["snap"]), got["snap"].get("note", "")
    sharp = sharp_snapshot(key) if key else empty_snapshot()
    snap = merge_books(sharp, free_snapshot(league_codes()))
    return load_book_state(snap), snap["note"]


def league_codes():
    return list(MIX_SPORTS) if is_mix() else [LEAGUE["code"]]


def empty_snapshot(note=""):
    return {"fair": {}, "games": {}, "opp": {}, "kick": {}, "note": note}


def sharp_snapshot(key):
    """The odds service's lines for the league on screen (uses free credits)."""
    BOOK_GAMES.clear()
    BOOK_OPP.clear()
    TEAM_KICKOFF.clear()
    fair, note = _sharp_book_odds(key)
    games = {t: [dict(g, fair=list(g["fair"]), day=str(g["day"]) if g.get("day") else None) for g in gs]
             for t, gs in BOOK_GAMES.items()}
    return {"fair": {k: list(v) for k, v in fair.items()}, "games": games,
            "opp": dict(BOOK_OPP), "kick": dict(TEAM_KICKOFF), "note": note}


def merge_books(sharp, free):
    """Sharp lines win; free sources fill in games the odds service doesn't list."""
    out = empty_snapshot()
    out["parts"] = {t: dict(v) for t, v in (free.get("parts") or {}).items()}
    for t, v in sharp["fair"].items():
        out["parts"].setdefault(t, {})["pinnacle" if v[1] == "Pinnacle" else "odds service"] = v[0]
    for part in (free, sharp):                     # sharp second, so it overrides
        out["fair"].update(part["fair"])
        out["games"].update(part["games"])
        out["opp"].update(part["opp"])
        out["kick"].update(part["kick"])
    n_free = len(set(free["fair"]) - set(sharp["fair"]))
    notes = [sharp["note"]] if sharp["note"] else []
    if free["fair"]:
        notes.append(f"Free lines ({free['note']}) cover {len(free['fair'])} teams"
                     + (f", {n_free} the odds service didn't list." if sharp["fair"] else "."))
    out["note"] = " ".join(notes) or "No sportsbook lines found, so chances use Kalshi's prices."
    return out


def load_book_state(snap):
    """Put a snapshot into the planner's sportsbook tables; returns {team: (chance, source)}."""
    BOOK_GAMES.clear()
    for t, gs in snap.get("games", {}).items():
        BOOK_GAMES[t] = [dict(g, fair=tuple(g["fair"]), day=_as_date(g.get("day"))) for g in gs]
    BOOK_OPP.clear()
    BOOK_OPP.update(snap.get("opp", {}))
    TEAM_KICKOFF.update(snap.get("kick", {}))
    return {t: tuple(v) for t, v in snap.get("fair", {}).items()}


def _as_date(x):
    if isinstance(x, dt.date) or not x:
        return x or None
    try:
        return dt.date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def american_chance(x):
    """'-150' / 130 / 'EVEN' -> implied chance (with the book's cut still in), or None."""
    try:
        s = str(x).strip().upper()
        v = 100.0 if s in ("EVEN", "EV", "PK") else float(s.replace("+", ""))
    except (TypeError, ValueError):
        return None
    if v == 0 or -100 < v < 100 and s not in ("EVEN", "EV", "PK"):
        return None
    return -v / (-v + 100) if v < 0 else 100 / (v + 100)


def espn_moneyline(comp):
    """(home chance, away chance, draw chance or None, book name) with the cut removed, or None."""
    for o in comp.get("odds") or []:
        ml = o.get("moneyline") or {}
        def pick(side):
            d = ml.get(side) or {}
            for when in ("close", "current", "open"):
                c = american_chance(((d.get(when) or {}).get("odds")))
                if c:
                    return c
            return american_chance((o.get(f"{side}TeamOdds") or {}).get("moneyLine")) if side != "draw" else \
                american_chance((o.get("drawOdds") or {}).get("moneyLine"))
        h, a, d = pick("home"), pick("away"), pick("draw")
        if h and a:
            tot = h + a + (d or 0)
            return h / tot, a / tot, (d / tot if d else None), (o.get("provider") or {}).get("name") or "ESPN"
    return None


POLY_TAGS = {"nfl": ["nfl"], "nba": ["nba"], "nhl": ["nhl"], "ncaaf": ["cfb", "college-football"],
             "ncaamb": ["cbb", "ncaab"], "ncaawb": ["wncaab"], "ufc": ["ufc"], "euroleague": ["euroleague"]}


def poly_games(code):
    """Polymarket's two-way game markets for a league: [(name A, name B, chance A)], mid-price, liquid only."""
    out = []
    for tag in POLY_TAGS.get(code, []):
        try:
            r = requests.get("https://gamma-api.polymarket.com/events", timeout=12,
                             params={"tag_slug": tag, "closed": "false", "active": "true", "limit": 200})
            evs = r.json() if r.ok else []
        except (requests.RequestException, ValueError):
            evs = []
        for ev in evs if isinstance(evs, list) else []:
            for m in ev.get("markets") or []:
                if m.get("sportsMarketType") not in (None, "moneyline") or m.get("closed"):
                    continue
                try:
                    names, prices = json.loads(m.get("outcomes") or "[]"), json.loads(m.get("outcomePrices") or "[]")
                    liq = float(m.get("liquidityNum") or m.get("liquidity") or 0)
                except (TypeError, ValueError):
                    continue
                if len(names) != 2 or len(prices) != 2 or liq < 2000 or "yes" in (str(names[0]).lower(), str(names[1]).lower()):
                    continue
                bid, ask = m.get("bestBid"), m.get("bestAsk")
                p = (float(bid) + float(ask)) / 2 if bid and ask and float(ask) - float(bid) <= 0.06 else float(prices[0])
                if 0.02 < p < 0.98:
                    out.append((str(names[0]), str(names[1]), p))
        if out:
            break
    return out


def _team_is(name, team):
    n = norm_team(name)
    return n and any(n == norm_team(team.get(k) or "") for k in
                     ("displayName", "shortDisplayName", "name", "abbreviation", "location", "nickname"))


def free_snapshot(codes):
    """Free sportsbook-style lines: ESPN's posted moneyline (book cut removed) and Polymarket's
    price, averaged when both have the game. Team names follow ESPN, like the odds service."""
    snap = empty_snapshot()
    used = set()
    for code in codes:
        sp = SPORTS.get(code)
        if not sp or not sp.get("espn"):
            continue
        poly = poly_games(code)
        today = dt.date.today()
        for path in (sp["espn"] if isinstance(sp["espn"], list) else [sp["espn"]]):
            q = dict(sp.get("q") or {}, limit=400)
            q["dates"] = f"{today:%Y%m%d}-{today + dt.timedelta(days=7):%Y%m%d}"
            try:
                r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard", params=q, timeout=12)
                evs = r.json().get("events", []) if r.ok else []
            except (requests.RequestException, ValueError):
                evs = []
            for ev in evs:
                comp = (ev.get("competitions") or [{}])[0]
                if ((comp.get("status") or {}).get("type") or {}).get("state", "pre") != "pre":
                    continue
                teams = {c.get("homeAway"): (c.get("team") or {}) for c in comp.get("competitors") or []}
                home, away = teams.get("home"), teams.get("away")
                if not home or not away or not home.get("displayName") or not away.get("displayName"):
                    continue
                ml = espn_moneyline(comp)
                pm = next(((p if _team_is(a, home) else 1 - p) for a, b, p in poly
                           if (_team_is(a, home) and _team_is(b, away)) or (_team_is(a, away) and _team_is(b, home))), None)
                w_book, w_poly = source_weights()
                if ml and ml[2] is None and pm is not None:
                    ph, src = (w_book * ml[0] + w_poly * pm) / (w_book + w_poly), f"{ml[3]} + Polymarket"
                    used.update((ml[3], "Polymarket"))
                elif ml:
                    ph, src = ml[0], ml[3]
                    used.add(ml[3])
                elif pm is not None:
                    ph, src = pm, "Polymarket"
                    used.add("Polymarket")
                else:
                    continue
                pa = ml[1] if ml and ml[2] is not None else 1 - ph   # with a draw, the two don't add to 1
                start = ev.get("date") or comp.get("date") or ""
                parts = {"home": {}, "away": {}}
                if ml:
                    parts["home"]["sportsbook"], parts["away"]["sportsbook"] = ml[0], ml[1]
                if pm is not None:
                    parts["home"]["polymarket"], parts["away"]["polymarket"] = pm, 1 - pm
                for me, other, p, side in ((home, away, ph, "home"), (away, home, pa, "away")):
                    nm, op = me["displayName"], other["displayName"]
                    snap.setdefault("parts", {})[nm] = parts[side]
                    snap["fair"].setdefault(nm, [p, src])
                    snap["games"].setdefault(nm, []).append({"fair": [p, src], "start": start,
                                                             "day": str(espn_day(start) or "") or None, "opp": op})
                    snap["opp"].setdefault(nm, op)
                    snap["kick"].setdefault(nm, start)
    snap["note"] = " + ".join(sorted(used)) or "none"
    return snap


def _sharp_book_odds(key):
    """{full team name: (fair win chance, source)} plus a note for the report. The Mix mode asks
    for each sport and merges them (team names don't repeat across leagues)."""
    odds = LG().get("odds")
    if isinstance(odds, list) or odds == "tennis_atp":
        keys = odds if isinstance(odds, list) else tennis_keys(key)
        fair, notes = {}, []
        BOOK_GAMES.clear()
        for k in keys:
            f, n = fetch_book_odds_one(key, f"https://api.the-odds-api.com/v4/sports/{k}/odds", keep=True,
                                       regions=LG().get("regions", "us,eu"))
            fair.update(f)
            notes.append(n)
        return fair, (notes[-1] if notes else "No tennis tournaments are listed by the sportsbooks right now.")
    if not is_mix():
        return fetch_book_odds_one(key, ODDS_URL)
    fair, notes = {}, []
    BOOK_GAMES.clear()
    for code in MIX_SPORTS:
        f, n = fetch_book_odds_one(key, f"https://api.the-odds-api.com/v4/sports/{LEAGUES[code]['odds']}/odds", keep=True)
        fair.update(f)
        notes.append(n)
    return fair, notes[-1] if notes else ""


def tennis_keys(key):
    """The ATP tournaments the odds feed lists right now (asking costs no credits)."""
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": key}, timeout=15)
        return [x["key"] for x in (r.json() if r.ok else []) if str(x.get("key", "")).startswith("tennis_atp")
                and x.get("active")][:3]
    except (requests.RequestException, ValueError):
        return []


def fetch_book_odds_one(key, url, keep=False, regions="us,eu"):
    try:
        r = requests.get(url, timeout=20, params={
            "apiKey": key, "regions": regions, "markets": "h2h", "oddsFormat": "decimal"})
    except requests.RequestException:
        return {}, "Couldn't reach the sportsbook service, so chances use Kalshi's prices."
    if r.status_code == 401:
        return {}, "Your sportsbook key wasn't accepted. Check it on the settings screen."
    if r.status_code == 429:
        return {}, "Sportsbook service is out of free credits this month. Using Kalshi's prices."
    if not r.ok:
        return {}, f"Sportsbook service error ({r.status_code}). Using Kalshi's prices."
    fair = {}
    if not keep:
        BOOK_GAMES.clear()
    for ev in sorted(r.json(), key=lambda ev: ev.get("commence_time") or "~"):
        home, away = ev.get("home_team"), ev.get("away_team")
        if home and away:
            BOOK_OPP.setdefault(home, away)       # a team's soonest game
            BOOK_OPP.setdefault(away, home)
        if ev.get("commence_time"):
            for team in (home, away):
                if team:
                    TEAM_KICKOFF.setdefault(team, ev["commence_time"])
        books, pinnacle, sharp = defaultdict(list), {}, defaultdict(list)
        for b in ev.get("bookmakers", []):
            for mk in b.get("markets", []):
                outs = mk.get("outcomes", [])
                if mk.get("key") != "h2h" or len(outs) not in (2, 3):
                    continue
                inv = [1 / o["price"] for o in outs]
                for o, i in zip(outs, inv):
                    if o.get("name", "").lower() == "draw":
                        continue                  # teams only; the draw is 1 minus the two
                    p = i / sum(inv)
                    books[o["name"]].append(p)
                    if b.get("key") == "pinnacle":
                        pinnacle[o["name"]] = p
                    elif b.get("key") in SHARP_BOOKS:
                        sharp[o["name"]].append(p)
        for team, ps in books.items():
            f = ((pinnacle[team], "Pinnacle") if team in pinnacle else
                 (statistics.median(sharp[team]), "sharp books") if sharp.get(team) else
                 (statistics.median(ps), f"{len(ps)} books"))
            fair.setdefault(team, f)              # the soonest game, for anything that only knows the team
            BOOK_GAMES.setdefault(team, []).append({   # every game, so a pick can be matched by date
                "fair": f, "start": ev.get("commence_time") or "",
                "day": espn_day(ev.get("commence_time")), "opp": away if team == home else home})
    left = r.headers.get("x-requests-remaining")
    note = "Chances and fair payouts use sportsbook lines (Pinnacle when available)."
    if left:
        note += f" {left} free credits left this month."
        try:
            if float(left) < 60:
                note += " Running low: build less often, or soccer (7 leagues) only on weekends."
        except ValueError:
            pass
    return fair, note


BOOK_OPP = {}   # sportsbook team name -> its opponent (soonest game)
BOOK_GAMES = {}  # sportsbook team name -> [{fair, start, day, opp}, ...] every game in the feed


def book_game(name, day, opp=None):
    """The sportsbook's game for this team on this date (a team can have tonight's game and
    Sunday's in the feed at once), or None."""
    games = BOOK_GAMES.get(name) or []
    for g in games:
        if g["day"] == day and (opp is None or g["opp"] == opp):
            return g
    if opp is not None and day:                   # time zones can shift a late game by a day
        for g in games:
            if g["opp"] == opp and g["day"] and abs((g["day"] - day).days) <= 1:
                return g
    return None


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
    for e, sides_all in games.items():
        kal_all = [s["p"] / sum(x["p"] for x in sides_all) for s in sides_all]
        sides = [x for x in sides_all if not x.get("tie")]       # match the two teams; a draw follows
        kal = [k for x, k in zip(sides_all, kal_all) if not x.get("tie")]
        names = []
        for s in sides:
            full = (sport_teams(ticker_sport(s["ticker"])) or TEAMS).get(s["abbr"])
            if full not in book:
                full = match_book(full or s["pick"], book) or match_book(s["pick"], book)
            names.append(full if full in book else None)
        day = game_date({"event_ticker": e})
        bg = [book_game(n, day, names[1 - i]) if n else None for i, n in enumerate(names)] if all(names) else [None, None]
        if BOOK_GAMES and not all(bg):
            bg = [book_game(n, day) if n else None for n in names]
        if BOOK_GAMES and not all(bg):
            names = [None, None]                  # the books don't list this date's game: Kalshi's prices
        elif not BOOK_GAMES and not TEAMS and all(names) and BOOK_OPP.get(names[0]) != names[1]:
            names = [None, None]                  # not the same game: use Kalshi's prices
        kick = next((g["start"] for g in bg if g and g.get("start")), None) if BOOK_GAMES else \
            next((TEAM_KICKOFF[n] for n in names if n in TEAM_KICKOFF), None)
        if kick:
            KICKOFF[e] = kick
        if all(names):
            raw = [g["fair"][0] for g in bg] if BOOK_GAMES and all(bg) else [book[n][0] for n in names]
            src = (bg[0]["fair"][1] if BOOK_GAMES and all(bg) else book[names[0]][1])
            matched += 1
        else:
            raw, src = kal, None
        ties = [x for x in sides_all if x.get("tie")]
        if ties:                                  # 3-way: the books' team chances already leave room for a draw
            total = 1.0 if src else sum(kal_all)
            raw = list(raw) if src else kal
            tie_raw = max(0.02, total - sum(raw)) if src else kal_all[sides_all.index(ties[0])]
            norm = sum(raw) + tie_raw
            for s, r in zip(sides, raw):
                s["fair"] = r / norm
            ties[0]["fair"] = tie_raw / norm
            for s in sides_all:
                s["src"] = src
                s["edge"] = s["fair"] - s["p"] if src else None
        else:
            for s, r, k in zip(sides, raw, kal):
                s["fair"] = r / sum(raw)
                s["src"] = src
                s["edge"] = s["fair"] - s["p"] if src else None
        for s, n in zip(sides, names):
            s["book_name"] = n if src else None
        news[e] = max(abs(s["fair"] - k) for s, k in zip(sides_all, kal_all)) if src else 0
    return matched, news


# ================================================================ combos
def fav(sides):
    return max([x for x in sides if not x.get("tie")] or sides, key=lambda s: s["fair"])


def dog(sides):
    return min([x for x in sides if not x.get("tie")] or sides, key=lambda s: s["fair"])


VALUE_EDGE = 0.01     # Kalshi this much cheaper than the sharp line = a bargain pick
PRICEY_EDGE = -0.02   # this much dearer = overpriced: used only when nothing better fits


def weight(s, usage):
    """Bargains first: Kalshi pricing a team under the sharp sportsbook line scores much higher,
    overpriced picks much lower; then likelier picks and picks not used much yet."""
    edge = max(-0.1, min(0.1, s["edge"] or 0))
    value = math.exp(25 * edge) * (0.05 if edge <= PRICEY_EDGE else 1)
    return max(1e-4, s["fair"] ** 2 * value) / (1 + usage[s["ticker"]])


def game_value(sides):
    """How much a game is worth including: one with a bargain side counts triple, one that's
    overpriced on both sides barely counts (no sportsbook line = neutral)."""
    edges = [x["edge"] for x in sides if x.get("edge") is not None]
    if not edges:
        return 1.0
    return 3.0 if max(edges) >= VALUE_EDGE else 0.15 if max(edges) <= PRICEY_EDGE else 1.0


def pickable(side):
    """Teams in games under way need a real chance left (Kalshi's live price reflects
    the score and the clock). Teams in games not started yet are always pickable."""
    if side.get("tie"):
        return False                              # the planner bets on teams, not draws
    if side["fair"] < sport_rule(side["ticker"], "min_pick", 0):
        return False                              # e.g. soccer: long-shot "to win" picks lose to draws too
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
    gw = {e: game_value(games[e]) / (1 + sum(usage[s["ticker"]] for s in games[e])) for e in eligible}
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
        if e not in late and CFG.get("dogs_late") and fav(games[e])["fair"] >= sport_rule(e, "close", CLOSE_GAME):
            f = fav(games[e])
            if f in opts and (f.get("edge") is None or f["edge"] > PRICEY_EDGE):
                legs.append(f)                    # early games: take the favourite (unless it's overpriced)
            continue                              # favourite used up or pricey: leave this game out
        if CFG["hedge_close"] and len(opts) == 2 and fav(games[e])["fair"] < sport_rule(e, "close", CLOSE_GAME) \
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
        won = {draw_result(s, rng.random())["ticker"] for s in games.values()}
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
    if hub_up():
        return hub_kalshi("GET", path, params=params)
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


def combo_leagues(legs):
    """The one league page a combo shows on: the league most of its picks are in (a tie goes to
    the league of its latest game). Combos with no league picks go with the NFL."""
    from collections import Counter
    n, last = Counter(), {}
    for l in legs:
        t = (l["ticker"] or "").upper()
        for code, pre in SPORT_PREFIX:
            if t.startswith(pre) and code in LEAGUES:
                n[code] += 1
                d = game_date({"event_ticker": t})
                last[code] = max(last.get(code) or dt.date.min, d or dt.date.min)
    if not n:
        return ["nfl"]
    main = [max(n, key=lambda c: (n[c], last.get(c) or dt.date.min))]
    return main + ["mix"] if len(n) > 1 else main     # a cross-sport combo also shows under Mix


def combo_league(legs):
    """The sport a combo belongs to (its first covered pick's), or 'other'."""
    for l in legs:
        code = ticker_sport(l["ticker"])
        if code in LEAGUES:
            return code
    return "other"


WINNER_SERIES = ("KXNFLGAME", "KXNCAAMBGAME", "KXNBAGAME", "KXNHLGAME", "KXNCAAFGAME", "KXNCAAWBGAME",
                 "KXEUROLEAGUEGAME", "KXUFCFIGHT", "KXATPMATCH") + tuple(['KXEPLGAME', 'KXLALIGAGAME', 'KXSERIEAGAME', 'KXBUNDESLIGAGAME', 'KXLIGUE1GAME', 'KXMLSGAME', 'KXLIGAMXGAME'])


def winners_only(legs):
    return all((l["ticker"] or "").startswith(WINNER_SERIES) for l in legs)


def week_of(ticker):
    d = game_date({"event_ticker": ticker})
    if not d:
        return None
    if (ticker or "").upper().startswith(("KXNCAAMB", "KXNBA", "KXNHL", "KXNCAAWB", "KXEUROLEAGUE", "KXATP")):
        return d                                  # daily leagues: the game's own day
    return d - dt.timedelta(days=1) if d.weekday() == 0 else d + dt.timedelta(days=(6 - d.weekday()) % 7)


ACCT_CACHE = {"at": 0, "value": None}


def in_week(a, week):
    """A combo belongs to every NFL week it has a game in (one can mix this week and next)."""
    if not week or not a.get("week"):
        return False
    return (a.get("first_week") or a["week"]) <= week <= a["week"]


def on_live(a, week):
    """Shown on Live: this week's combos, plus any still live from an earlier week (an NFL
    combo waiting on Monday night counts for the week that just ended)."""
    return in_week(a, week) or (a["status"] == "pending" and bool(a.get("week")) and a["week"] < (week or ""))


def fetch_account(max_age=60, every_league=False):
    """Your combo bets from Kalshi (cached for a minute), for the league on screen unless
    every_league. Returns (bets, balance, note)."""
    import time
    if ACCT_CACHE["value"] and time.time() - ACCT_CACHE["at"] < max_age:
        value = ACCT_CACHE["value"]
    else:
        value = _fetch_account()
        if value[0] is not None:
            ACCT_CACHE.update(at=time.time(), value=value)
    bets, balance, note = value
    if bets is None or every_league:
        return value
    return [a for a in bets if LEAGUE["code"] in a.get("lgs", [a.get("lg", "nfl")])], balance, note


def _fetch_account():
    if hub_up():
        got = hub_call("account", timeout=30)
        if got and isinstance(got.get("value"), list):
            return tuple(got["value"])
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
                     "winners": winners_only(legs),
                     "lg": lg if lg in LEAGUES else "nfl",    # other combos are shown with the NFL
                     "lgs": combo_leagues(legs)})
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


def game_hours(ticker):
    """How long a game runs, by its sport (the Mix mode has several)."""
    return (SPORTS.get(ticker_sport(ticker)) or {}).get("hours") or LG()["game_hours"]


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
    return now >= end - dt.timedelta(hours=game_hours(side.get("event") or side.get("ticker") or ""))


CLOSING = os.path.join(HERE, "closing_chances.json")   # each pick's last chance seen before kickoff


def record_closing(all_games):
    """Keep each pick's latest chance until its game starts: the market's final word before
    kickoff, which the edge report compares your price against."""
    saved = load_json(CLOSING, {})
    changed = False
    for sides in all_games.values():
        for s in sides:
            v = s.get("fair") or s.get("p")
            if v and not started(s) and saved.get(s["ticker"]) != round(v, 4):
                saved[s["ticker"]] = round(v, 4)
                changed = True
    if changed:
        cutoff = dt.date.today() - dt.timedelta(days=150)
        saved = {t: v for t, v in saved.items() if (game_date({"event_ticker": t}) or cutoff) >= cutoff}
        save_json(CLOSING, saved)
    return saved


def remember_pregame(all_games):
    """Save each pick's chance the first time we see it before kickoff."""
    record_closing(all_games)
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
function myPick(r){ var on=!r.classList.contains('sel');
  document.querySelectorAll('.mypick[data-e="'+r.dataset.e+'"]').forEach(function(x){x.classList.remove('sel');x.style.background='';});
  if(on){ r.classList.add('sel'); r.style.background='var(--accentbg, rgba(10,132,255,.15))'; }
  var n=document.querySelectorAll('.mypick.sel').length, bar=document.getElementById('mybar');
  bar.style.display=n?'flex':'none'; document.getElementById('mybtn').textContent='Price my '+n+' pick'+(n===1?'':'s'); }
function myClear(){ document.querySelectorAll('.mypick.sel').forEach(function(x){x.classList.remove('sel');x.style.background='';});
  document.getElementById('mybar').style.display='none'; myMsg(''); }
function myMsg(h){ var m=document.getElementById('mymsg'); if(m) m.innerHTML=h; }
function myPrice(){ var t=Array.prototype.map.call(document.querySelectorAll('.mypick.sel'),function(x){return x.dataset.t;});
  if(t.length<2){ myMsg("<span class='muted'>Pick at least 2 teams.</span>"); return; }
  myMsg("<span class='muted'>Adding your combo…</span>");
  try{ location.href='combo://custom/'+BUILD+'/0/'+encodeURIComponent(t.join(',')); }catch(e){} }
function autoQuotes(){ var all=Array.prototype.map.call(document.querySelectorAll('.card[data-i]'),function(c){return +c.dataset.i;})
  .filter(function(i){ return state.placed.indexOf(i)<0; });
  if(!all.length) return;
  all.forEach(function(i){ tradeMsg(i,"<span class='muted'>Getting Kalshi's price…</span>"); });
  try{ location.href='combo://batch/'+BUILD+'/0/'+all.map(function(i){ return i+':'+stakeOf(i); }).join(',')+'/auto'; }catch(e){} }
function setStake(i,v){ var c=document.querySelector('.card[data-i="'+i+'"]'); if(!c) return;
  var el=c.querySelector('.amt'); if(el){ el.value=v; amt(i,el); } }
function markPlaced(i,pays){ if(state.placed.indexOf(i)<0) state.placed.push(i); state.quotes[i]=pays; paint(); }
paint();
if(window.AUTOQ){ setTimeout(autoQuotes, 300); }
if(FOCUS){ var fc=document.querySelector('.card[data-i="'+FOCUS+'"]');
  if(fc){ fc.scrollIntoView(); fc.style.outline='2px solid var(--accent)'; } }
"""


def exposure_html(combo_picks, title="How much rides on one result", folded=False):
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
    if folded:                                    # one line that opens: value first, risk one tap away
        return (f"<details class='lostbox' id='expo' style='margin:0'><summary><span>{head}"
                + (f" <span class='neg' style='font-weight:600'>Over your {CFG['max_share']}% limit</span>" if over else "")
                + f"</span></summary><div style='padding:0 16px 12px'>{warn}{rows}</div></details>")
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
           f"<header><h1>Suggested combos</h1>"
           f"<div class='sub'>{LG()['icon']} {sunday:%a %b %-d} · {len(games)} games · {len(combos)} combos at "
           f"${CFG['stake']} · <span id='placedcount'>0</span> placed</div>"
           "<button class='btn quiet' style='padding:6px 0;min-height:0;margin-top:4px' "
           "onclick=\"location.href='combo://settings'\">Change settings and rebuild</button></header>",
           "<div class='stats'>"
           f"<div class='stat'><b>{money(spent)}</b><span class='lbl'>total stake</span></div>"
           f"<div class='stat'><b>{p_any:.0%}</b><span class='lbl'>chance one hits</span></div>"
           f"<div class='stat'><b>{money(best)}</b><span class='lbl'>biggest payout</span></div></div>",
           "<div style='padding:8px 16px 0'>" + exposure_html(
               [[(l["ticker"], l["pick"]) for l in c["legs"]] for c in combos], folded=True) + "</div>",
           "<div class='tabs'><button id='b-combos' class='on' onclick=\"tab('combos')\">Combos</button>"
           "<button id='b-games' onclick=\"tab('games')\">Games</button>"
           "<button id='b-record' onclick=\"tab('record')\">Record</button></div>",
           "<section id='combos'>"]
    if can_trade():
        out.append("<div class='quote' style='margin:0 16px 4px;justify-content:space-between'>"
                   "<div class='trade' id='t0' style='flex:1;font-size:13px'></div>"
                   "<button class='btn quiet' style='flex:none;min-height:0;padding:6px 0' onclick='autoQuotes()'>"
                   "Refresh prices</button></div>")
    under = []
    for i, (c, p) in enumerate(zip(combos, p_each), 1):
        chance = f"{p:.1%}" if p >= 0.001 else "under 0.1%"
        est_pays, est_pct = est_offer(c)
        est_line = (f"<div class='muted' style='font-size:13px;margin-top:4px'>Kalshi will likely pay about "
                    f"{money(est_pays)} ({est_pct:.0%} of fair) · expected {signed_money(CFG['stake'] * (est_pct - 1))} "
                    f"per {money(CFG['stake'])}</div>" if est_pct else "")
        start_i = len(out)
        if est_pct and est_pct < CFG["accept_pct"] / 100 and not (card_notes or {}).get(i):
            under.append(start_i)
        out.append(
            f"<div class='card' data-i='{i}' data-min='{c['min']:.0f}' data-fair1='{c['fair'] / CFG['stake']:.6f}' "
            f"data-min1='{c['min'] / CFG['stake']:.6f}'><div class='top'><div>"
            f"<div class='tier'>#{i} · {e(c['tier'])}</div>"
            f"<div class='pay'>{money(c['fair'])}</div>"
            f"<div class='meta'>fair payout · {chance} chance · {len(c['legs'])} picks</div>{est_line}"
            + (f"<div class='muted' style='font-size:12px;margin-top:2px'>Your {CFG['accept_pct']}% cut-off: "
               f"<span class='minv'>{money(c['min'])}</span></div>" if can_trade() else "") + "</div>"
            f"<div class='side'>"
            + ("" if can_trade() else f"<label class='placed'><input type='checkbox' onchange='tog({i})'><span>Placed</span></label>")
            + "</div></div>"
            f"<div class='min'{HIDE if can_trade() else ''}>Take Kalshi's offer if it's at least <b class='{'minv0' if can_trade() else 'minv'}'>{money(c['min'])}</b>"
            f"<div class='quote'{HIDE if can_trade() else ''}><span>Kalshi offers $</span>"
            f"<input inputmode='decimal' placeholder='amount' onchange='quote({i},this)'>"
            f"<span class='verdict' style='display:none'></span></div></div>"
            f"<div class='quote'><span>Bet $</span><input class='amt' inputmode='decimal' value='{CFG['stake']}' "
            f"onchange='amt({i},this)'>"
            + (f"<button class='btn' onclick='act(\"buy\",{i})'>New price</button>" if can_trade() else "")
            + f"<button class='btn quiet' onclick='act(\"swap\",{i})'>Swap</button>"
            + f"</div><div class='trade' id='t{i}'></div>"
            + ((card_notes or {}).get(i) or "")
            + f"<details class='picks'><summary><span>{len(c['legs'])} picks"
            + (lambda nd: f" · {nd} underdog{'s' * (nd != 1)}" if nd else "")(
                sum(1 for l in c['legs'] if l['fair'] < other_side(all_games[l['event']], l)['fair']))
            + (" · " + " ".join(sorted({sport_icon(l["ticker"]) for l in c["legs"]})) if is_mix() else "")
            + f"<span class='muted' style='font-weight:400'> · see all</span></span></summary>" + decision_html(c["legs"]) + "<ol>")
        for n, l in enumerate(sorted(c["legs"], key=lambda l: (start_key(l["event"]), order[l["event"]])), 1):
            other = other_side(all_games[l["event"]], l)
            tags = ""
            if l.get("live"):
                tags += '<span class="tag bad">Live</span> '
            if l["event"] in locks:
                tags += '<span class="tag lock">Your pick</span> '
            if l["fair"] < other["fair"]:
                tags += '<span class="tag dog">Underdog</span> '
            tags += edge_tag(l)
            sp = (sport_icon(l["ticker"]) + " ") if is_mix() else ""
            out.append(f"<li><span class='n'>{n}</span><span class='who'><b>{sp}{e(l['pick'])}</b> {tags}"
                       f"<small>to beat {e(other['pick'])} · {when_text(l['event'], days[l['event']])}</small></span>"
                       f"<span class='pct'>{l['fair']:.0%}</span>"
                       f"<button class='flip' onclick='act2(\"flip\",{i},\"{e(l['ticker'])}\")'>Flip</button></li>")
        out.append("</ol></details></div>")
        if under and under[-1] == start_i:
            under[-1] = (start_i, len(out))
    if under:                                    # likely under the cut-off: folded away, still there
        cards = []
        for a, b in reversed(under):
            cards = out[a:b] + cards
            del out[a:b]
        out.append(f"<details class='lostbox' id='underbox' style='margin:12px 16px 0'><summary><b>{len(under)} "
                   f"combo{'s' * (len(under) != 1)} likely under your {CFG['accept_pct']}% cut-off</b>"
                   "<span class='muted' style='font-weight:400'> · estimated from your past quotes</span></summary>"
                   + "".join(cards) + "</details>")
    out.append("</section>")

    on = day_on()
    out.append("<section id='games' class='hidden'><div class='muted' style='font-size:13px;margin:4px 4px 8px'>"
               "Building your own combo? Tap the teams you want (one per game), then Price my picks to see the fair "
               "payout and Kalshi's quote before you buy.</div><div id='mybar' style='display:none;position:sticky;"
               "top:8px;z-index:5;margin-bottom:8px' class='quote'><button class='btn go' onclick='myPrice()' id='mybtn'>"
               "Price my picks</button><button class='btn quiet' onclick='myClear()'>Clear</button></div>"
               "<div id='mymsg'></div>")
    for day in day_seq():
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
                if s.get("tie"):                  # soccer draw: shown for context, never picked
                    out.append(f"<div class='row'><span style='color:var(--muted)'>Draw · not pickable (a draw loses either team)</span>"
                               f"<span class='nums'>{nums}</span></div>")
                    continue
                out.append(f"<div class='row mypick' data-t='{e(s['ticker'])}' data-e='{e(x)}' onclick='myPick(this)'>"
                           f"<span><b>{(sport_icon(s['ticker']) + ' ') if is_mix() else ''}{e(s['pick'])}</b> {tag}{edge_tag(s)}</span>"
                           f"<span class='nums'>{nums}</span></div>")
            if x in skipped:
                out.append(f"<div class='warn'>{e(skipped[x])}</div>")
            elif news.get(x, 0) >= NEWS_GAP:
                out.append(f"<div class='warn'>Kalshi and the sportsbooks disagree by {news[x]:.0%}. "
                           f"Probably breaking news (injury?). Check before betting.</div>")
            out.append("</div>")
    out.append("</section><section id='record' class='hidden'><!--RECORD--></section>")
    out.append("<div class='foot'>" + "".join(f"<div>{e(n)}</div>" for n in notes) + "</div>")
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


def ticker_cashflows(fills):
    """Money in and out per market from your fills: {ticker: {"cost", "back", "fees", "net", "last"}}.
    Kalshi nets YES and NO, so the side you first bought is your bet; buying it adds cost, and any
    other fill (selling it, Kalshi's "sell no" for app cash-outs, or buying the other side) is
    money back at your side's price."""
    out = {}
    for f in sorted(fills, key=lambda f: str(f.get("created_time") or "")):
        t = f.get("ticker") or f.get("market_ticker")
        if not t:
            continue
        n = count_of(f)
        side, act = f.get("side", "yes"), f.get("action", "buy")
        yes_px = dollars(f, "yes_price")
        no_px = dollars(f, "no_price") or (1 - yes_px if yes_px else 0.0)
        yes_px = yes_px or (1 - no_px if no_px else 0.0)
        c = out.setdefault(t, {"side": side if act != "sell" else ("no" if side == "yes" else "yes"),
                               "cost": 0.0, "back": 0.0, "fees": 0.0, "net": 0.0, "last": ""})
        px = yes_px if c["side"] == "yes" else no_px
        if act != "sell" and side == c["side"]:
            c["cost"] += n * px
            c["net"] += n
        else:
            c["back"] += n * px
            c["net"] -= n
        c["fees"] += dollars(f, "fee_cost")
        c["last"] = str(f.get("created_time") or c["last"])
    return out


def account_breakdown(hours=24):
    """Whole-account profit on bets that finished in the last `hours` (settled, or sold off
    completely): what came back (sales and payouts) minus what they cost, fees included.
    Worked out from every fill on those markets, so a bet bought days ago counts in full.
    Open bets are listed, not valued."""
    import time
    key_id = CFG.get("kalshi_key_id", "").strip()
    if not key_id or not os.path.exists(KEYFILE):
        return None
    with open(KEYFILE, encoding="utf-8") as f:
        key = load_private_key(f.read())
    since = int(time.time() - hours * 3600)
    since_iso = dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    settles = account_pages(key, key_id, "/portfolio/settlements", "settlements", {"min_ts": since})
    fills = account_pages(key, key_id, "/portfolio/fills", "fills",
                          {"min_ts": int(time.time() - 200 * 86400)})
    positions = all_positions(key, key_id)
    flows = ticker_cashflows(fills)
    settled = {s.get("ticker"): s for s in settles}
    held = {(p.get("ticker") or p.get("market_ticker")): abs(float(p.get("position_fp") or p.get("position") or 0))
            for p in positions}
    finished = set(settled) | {t for t, c in flows.items() if c["last"][:19] >= since_iso and c["cost"] > 0
                               and c["net"] <= 0.005 and held.get(t, 0) <= 0.005}
    cache = load_json(LEGS_CACHE, {})
    fetch_legs_parallel([t for t in finished if is_combo(t)], cache)
    save_json(LEGS_CACHE, cache)

    def kind(t):
        if is_combo(t):
            legs = combo_legs(t, cache) or []
            return "NFL combos" if legs and all((l["ticker"] or "").startswith(SERIES) for l in legs) \
                else "Other combos"
        return "NFL single bets" if (t or "").startswith(SERIES) else "Other single bets"

    out = defaultdict(lambda: {"pnl": 0.0, "n": 0})
    for t in finished:
        c, st = flows.get(t), settled.get(t)
        if c and c["cost"] > 0:
            pnl = c["back"] + (dollars(st, "revenue") if st else 0.0) - c["cost"] - c["fees"]
        elif st:                                 # no fills on record: use the settlement's own figures
            pnl = (dollars(st, "revenue") - dollars(st, "yes_total_cost") - dollars(st, "no_total_cost")
                   - dollars(st, "fee_cost"))
        else:
            continue
        out[kind(t)]["pnl"] += pnl
        out[kind(t)]["n"] += 1
    open_n, open_cost = 0, 0.0
    for p in positions:
        if abs(float(p.get("position_fp") or p.get("position") or 0)) > 0.005:
            open_n += 1
            open_cost += dollars(p, "market_exposure")
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
            f"<div class='muted' style='font-size:13px;margin-top:8px'>Bets that finished in the last 24 hours "
            f"(paid out, lost, or cashed out): everything they paid back minus everything they cost, even if "
            f"you bought them earlier. Still open: {b['open_n']} bet{'s' if b['open_n'] != 1 else ''} "
            f"({money(b['open_cost'])} in). Kalshi's own 24h number is the change in your whole portfolio's "
            f"value instead: it counts open bets at today's prices and leaves out what bets finishing today "
            f"cost before yesterday, so the two won't match exactly.</div></div></details>")


# ================================================================ edge report
CAL_BUCKETS = (("Under 5%", 0, 0.05), ("5–15%", 0.05, 0.15), ("15–30%", 0.15, 0.30), ("30% or more", 0.30, 1.01))


def edge_stats(acct, days=150):
    """The numbers that say whether this is profitable: your price vs the kickoff price, how often
    combos hit vs the chance the market gave them, returns by picks and sport, and what cash-outs
    earned vs holding. Plain numbers (JSON-safe), so the Pi can send them to the phone."""
    import time
    close = load_json(CLOSING, {})
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    mine = [a for a in acct or [] if (a.get("week") or "9") >= since]
    cashed = [a for a in mine if a["status"] == "cashed"]
    res = fetch_results({l["ticker"] for a in cashed for l in a["legs"] if l["ticker"]}) if cashed else {}

    def games_say(a):
        rs = [res.get(l["ticker"]) if l.get("side", "yes") == "yes" else
              {"yes": "no", "no": "yes"}.get(res.get(l["ticker"])) for l in a["legs"]]
        return "lost" if "no" in rs else "won" if rs and all(r == "yes" for r in rs) else None

    st = {"at": int(time.time()), "days": days, "clv": [0.0, 0.0, 0], "cal": {b[0]: [0, 0.0, 0] for b in CAL_BUCKETS},
          "picks": {}, "sport": {}, "cash": [0, 0.0, 0.0, 0], "week": [0, 0.0, 0.0, 0, 0], "season": [0.0, 0.0]}
    for a in mine:
        probs = []
        for l in a["legs"]:
            v = close.get(l["ticker"] or "")
            if v is None:
                probs = None
                break
            probs.append(v if l.get("side", "yes") == "yes" else 1 - v)
        fair = math.prod(probs) if probs else None
        full = a.get("full_pays") or a["pays"]
        if fair and a["cost"] > 0:
            st["clv"][0] += a["cost"]
            st["clv"][1] += full * fair
            st["clv"][2] += 1
        hit = {"won": 1, "lost": 0}.get(a["status"])
        g = games_say(a) if a["status"] == "cashed" else None
        if hit is None and g:
            hit = 1 if g == "won" else 0
        if fair is not None and hit is not None:
            b = next(k for k, lo, hi in CAL_BUCKETS if lo <= fair < hi)
            st["cal"][b][0] += 1
            st["cal"][b][1] += fair
            st["cal"][b][2] += hit
        if a["status"] == "pending":
            continue
        n = len(a["legs"])
        k = "2 picks" if n <= 2 else "3 picks" if n == 3 else "4 picks" if n == 4 else "5–6 picks" if n <= 6 else "7+ picks"
        for key, bucket in ((k, st["picks"]), (LEAGUES.get(a.get("lg"), {}).get("name", "Other"), st["sport"])):
            row = bucket.setdefault(key, [0, 0.0, 0.0])
            row[0] += 1
            row[1] += a["cost"]
            row[2] += a["back"]
        st["season"][0] += a["cost"]
        st["season"][1] += a["back"]
        if a["status"] == "cashed":
            st["cash"][0] += 1
            st["cash"][1] += a["back"]
            if g == "won":
                st["cash"][2] += full
            elif g is None:
                st["cash"][3] += 1
        if (a.get("week") or "") >= week_ago:
            w = st["week"]
            w[0] += 1
            w[1] += a["cost"]
            w[2] += a["back"]
            w[3] += a["status"] in ("won", "cashed") and a["back"] > a["cost"]
            w[4] += a["status"] == "cashed"
    return st


def signed_money(x):
    return ("+" if x >= 0 else "−") + money(abs(x))


def edge_html(st, source=""):
    """Results: the edge report, from the Pi's numbers when it's running (it sees every kickoff)."""
    if not st:
        return ""
    paid, worth, n = st["clv"]
    out = ["<h2>Your edge</h2><div class='game'>"]
    if n:
        clv = worth / paid - 1 if paid else 0
        out.append(f"<div class='row'><b>Your prices vs. kickoff</b><b class='{'pos' if clv >= 0 else 'neg'}' "
                   f"style='font-size:22px'>{'+' if clv >= 0 else '−'}{abs(clv):.1%}</b></div>"
                   f"<div class='muted' style='font-size:13px'>{n} combo{'s' * (n != 1)}: you paid {money(paid)} for "
                   f"combos the market valued at {money(worth)} just before kickoff. Above 0% means you buy better than "
                   "the market's final price, the clearest sign of a long-term edge.</div>")
    else:
        out.append("<div class='muted' style='font-size:13px'>No kickoff prices yet. They're recorded while the "
                   "planner or the Pi is watching before games start.</div>")
    cal = [(k, *st["cal"][k]) for k, _, _ in CAL_BUCKETS if st["cal"].get(k, [0])[0]]
    if cal:
        out.append("<div style='margin-top:10px'><b>Did combos hit as often as priced?</b></div>")
        for k, cnt, psum, hits in cal:
            out.append(f"<div class='row' style='padding:4px 0;border-top:1px solid var(--line)'><span>{k} chance "
                       f"<small class='muted'>{cnt} combo{'s' * (cnt != 1)}</small></span><span>expected "
                       f"{psum / cnt:.0%} · hit <b>{hits / cnt:.0%}</b></span></div>")
    for title, key in (("By number of picks", "picks"), ("By sport", "sport")):
        rows = st.get(key) or {}
        if not rows:
            continue
        order = ["2 picks", "3 picks", "4 picks", "5–6 picks", "7+ picks"] if key == "picks" else sorted(rows)
        out.append(f"<div style='margin-top:10px'><b>{title}</b> <small class='muted'>(settled)</small></div>")
        for k in order:
            if k not in rows:
                continue
            cnt, cost, back = rows[k]
            r = back / cost - 1 if cost else 0
            out.append(f"<div class='row' style='padding:4px 0;border-top:1px solid var(--line)'><span>{k} "
                       f"<small class='muted'>{cnt} · {money(cost)} in</small></span><span class='{'pos' if r >= 0 else 'neg'}'>"
                       f"{signed_money(back - cost)} ({'+' if r >= 0 else '−'}{abs(r):.0%})</span></div>")
    cn, got, would, still = st["cash"]
    if cn:
        decided = cn - still
        out.append(f"<div style='margin-top:10px'><b>Cash-outs</b></div><div class='muted' style='font-size:13px'>"
                   f"{cn} cashed out for {money(got)}." + (f" Of the {decided} now decided, holding would have paid "
                   f"{money(would)}." if decided else "") + (f" {still} not decided yet." if still else "") + "</div>")
    if source:
        out.append(f"<div class='muted' style='font-size:12px;margin-top:8px'>{source}</div>")
    out.append("</div>")
    return "".join(out)


def weekly_text(st):
    """The Monday push: last 7 days, plus the price-vs-kickoff number for the season."""
    n, cost, back, paid_off, cashed = st["week"]
    paid, worth, k = st["clv"]
    clv = (f" Prices vs. kickoff, season: {'+' if worth >= paid else '−'}{abs(worth / paid - 1):.1%}." if k and paid else "")
    if not n:
        return "📊 Weekly report: no combos settled in the last 7 days." + clv
    return (f"📊 Last 7 days: {n} combo{'s' * (n != 1)} settled, {money(cost)} in, {money(back)} back "
            f"({signed_money(back - cost)}). {paid_off} paid off, {cashed} cashed out." + clv +
            " Details in the planner under Results.")


def seal(secret, obj):
    """Encrypt + sign a small JSON object with the pairing secret (for numbers sent through ntfy)."""
    import hmac, hashlib, base64
    raw = json.dumps(obj, separators=(",", ":")).encode()
    nonce = os.urandom(16)
    key = hashlib.sha256((secret + "|seal").encode()).digest()
    stream = b"".join(hashlib.sha256(key + nonce + i.to_bytes(4, "big")).digest() for i in range(len(raw) // 32 + 1))
    ct = bytes(a ^ b for a, b in zip(raw, stream))
    mac = hmac.new(secret.encode(), nonce + ct, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + ct).decode()


def unseal(secret, blob):
    import hmac, hashlib, base64
    try:
        data = base64.urlsafe_b64decode(blob.encode())
        nonce, mac, ct = data[:16], data[16:48], data[48:]
        if not hmac.compare_digest(mac, hmac.new(secret.encode(), nonce + ct, hashlib.sha256).digest()):
            return None
        key = hashlib.sha256((secret + "|seal").encode()).digest()
        stream = b"".join(hashlib.sha256(key + nonce + i.to_bytes(4, "big")).digest() for i in range(len(ct) // 32 + 1))
        return json.loads(bytes(a ^ b for a, b in zip(ct, stream)))
    except (ValueError, TypeError):
        return None


def pi_report():
    """The Pi's latest edge numbers (it records every kickoff price), or None."""
    c = watcher_conf()
    if not c:
        return None
    try:
        r = requests.get(f"{NTFY}/{c['topic']}-report/json", params={"poll": "1", "since": "24h"}, timeout=6)
        msgs = [json.loads(x) for x in r.text.splitlines() if x.strip()] if r.ok else []
        return unseal(c["secret"], msgs[-1]["message"]) if msgs else None
    except (requests.RequestException, ValueError, KeyError):
        return None


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
    if sunday and not by_day() and dt.date.today().weekday() in (0, 1):
        last = dt.date.today() - dt.timedelta(days=dt.date.today().weekday() + 1)
        if any(in_week(a, last.isoformat()) for a in acct):
            sunday = last                        # Mon/Tue: the week just played, if you had combos in it
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
    body = [head, f"<header><h1>Results</h1>{sport_seg()}<div class='sub'>{sub}</div></header>"]
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
    if hub_up():
        got = hub_call("shadow", timeout=10) or {}
        body.append(shadow_html(got.get("summary")))
        if got.get("accuracy") is not None:
            body.append("<section><h2><span>🎯 Which odds are most accurate</span></h2><div class='game'><div class='row'>"
                        f"<span>{html.escape(accuracy_text(got['accuracy']))}</span></div></div></section>")
    pi = pi_report()
    if pi and pi.get("stats"):
        body.append(edge_html(pi["stats"], "From your Pi, which records every kickoff price · updated "
                              + dt.datetime.fromtimestamp(pi["stats"]["at"]).strftime("%-I:%M %p")))
    else:
        body.append(edge_html(edge_stats(acct), "From this phone: kickoff prices are recorded only while the "
                              "planner is open before games, so the Pi's report is more complete."))
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
            f"{dt.date.fromisoformat(k):%b %-d}<br><small class='muted'>{int(w['n'])} combo{'s' * (int(w['n']) != 1)} · "
            f"{int(w['won'])} paid off · {money(w['in'])} in</small></span>"
            f"<span class='{'pos' if w['back'] >= w['in'] else 'neg'}'>{'+' if w['back'] >= w['in'] else '−'}"
            f"{money(abs(w['back'] - w['in']))}</span></div>"
            for k, w in sorted(weeks.items(), reverse=True))
        body.append(f"<h2>Every {'day' if by_day() else 'week'} (settled)</h2><div class='game'><div class='row'><b>All time</b>"
                    f"<b class='{'pos' if all_net >= 0 else 'neg'}'>{'+' if all_net >= 0 else '−'}{money(abs(all_net))}"
                    f"</b></div><div class='muted' style='font-size:13px'>on {money(all_in)} put in</div>{lines}</div>")
    body.append("<div class='quote' style='margin:12px 0 24px'><button class='btn' "
                "onclick=\"location.href='combo://lastbuild'\">Last suggested combos</button></div>"
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
    if CTX.pop("autoq", False) and can_trade():          # a fresh build: get Kalshi's price for every combo
        page = page.replace("<script>var FOCUS=", "<script>var AUTOQ=1;var FOCUS=", 1)

    @safe_delegate
    class Keeper:
        def webview_should_start_load(self, webview, url, nav_type):
            if not url.startswith("combo://"):
                return True
            parts = unquote(url[len("combo://"):]).split("/")
            if parts[0] == "settings":
                reopen_settings(webview)
                return False
            if parts[0] in ("swap", "buy", "accept", "decline", "batch", "flip", "custom"):
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
.sk{padding:calc(env(safe-area-inset-top) + 70px) 16px 16px}.bar{border-radius:20px;margin:0 0 12px;
 background:linear-gradient(100deg,var(--card) 40%%,var(--card2,var(--card)) 50%%,var(--card) 60%%);background-size:200%% 100%%;
 animation:sh 1.3s linear infinite}@keyframes sh{from{background-position:120%% 0}to{background-position:-80%% 0}}
#msg{position:fixed;left:0;right:0;top:calc(env(safe-area-inset-top) + 22px);text-align:center;
 font:600 15px -apple-system,system-ui,sans-serif;color:var(--muted)}
</style></head><body><div id='msg'>Loading…</div><div class='sk'>
<div class='bar' style='height:34px;width:45%%;border-radius:10px'></div><div class='bar' style='height:120px'></div>
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


class _NoWindow:
    """Stands in for the window in a copy that has handed it to a newer copy: everything is a no-op."""
    def __getattr__(self, name):
        return lambda *a, **k: None


def _web():
    """The one window everything shows in. Created once, then reused, so pages
    swap in place and the code never shows between them. The title bar and the tab bar
    are real iPhone controls, so they never move when you scroll."""
    import ui
    if window_open():
        return APP["web"]
    if APP.get("superseded"):        # a newer copy owns the window; this one must never open another
        return _NoWindow()
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

    win = Window(name="", background_color=bg)   # the league buttons fill the title bar
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
    win.name = ""
    for btn in bar.subviews:
        btn.action = lambda sender: native_nav(sender.name)
    win.left_button_items = []                 # the sport is chosen on Build and Results, not up here
    win.right_button_items = [ui.ButtonItem(title="⟳", action=lambda sender: native_nav("refresh"))]


def adopt_window(old_app, notice):
    """Called on a freshly updated copy: take over the open window so the update
    starts without closing anything, then open on Settings."""
    old_app["superseded"] = True        # the old copy's background jobs stop
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
    old_app["closed"] = True            # the old copy's live updates stop drawing into this window
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
@keyframes tk{0%{color:var(--accent)}100%{}}.tick{animation:tk 1.2s ease-out}
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
""" + r"""
/* ---------- design system ---------- */
html{-webkit-tap-highlight-color:transparent}
body{font:16px/1.45 -apple-system,'SF Pro Text',system-ui,sans-serif;font-feature-settings:"tnum" 1;
 -webkit-font-smoothing:antialiased;letter-spacing:-.005em}
header{padding:22px 20px 6px}h1{font-size:32px;line-height:1.1;font-weight:800;letter-spacing:-.025em;margin:0 0 4px}
.sub{font-size:15px}.muted{color:var(--muted)}
section{padding:0 16px 48px}
h2{font-size:13px;font-weight:650;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:26px 4px 8px}
h2 .ib{font-size:15px}
.card,.batch,.empty,.game,.stat{border:0!important;border-radius:20px;background:var(--card);box-shadow:var(--shadow)}
.card{padding:16px 16px 6px;margin:0 0 12px}.batch{padding:16px;gap:10px}.game{padding:6px 16px;border-radius:16px}
.game>.row,.game>.swrow,.game>.srow,.game>label.row{min-height:50px;border-bottom:1px solid var(--line)}
.game>:last-child{border-bottom:0!important}.srow{padding:10px 0}.srow .row{padding:0 0 4px}
.quote.pair{flex-direction:column;align-items:stretch;gap:6px}.quote.pair .btn{width:100%}.quote.pair .btn:not(.go){background:transparent;min-height:40px}
.btn.two{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;padding:9px 14px}
.btn.two .bt{font-weight:700;font-size:16px}.btn.two .bs{font-weight:500;font-size:13px;opacity:.85}
.placed{border:0;background:var(--card2);border-radius:12px}.flip{border:0;background:var(--accentbg);color:var(--accent);
 border-radius:999px;padding:6px 12px;font-size:13px}
.tier{font-size:13px;font-weight:600;color:var(--muted);text-transform:none;letter-spacing:0;display:flex;align-items:center;gap:6px}
.pay{font-size:30px;line-height:1.15;font-weight:800;letter-spacing:-.03em;margin-top:2px}
.meta{font-size:14px;color:var(--muted)}
.stat{padding:12px 14px;border-radius:16px}.stat b{font-size:22px;font-weight:750;letter-spacing:-.02em}
.btn{font:600 16px/1.1 -apple-system,system-ui,sans-serif;border:0!important;border-radius:14px;padding:12px 18px;
 min-height:48px;background:var(--accentbg);color:var(--accent);transition:transform .12s ease,opacity .12s ease;
 -webkit-user-select:none;user-select:none}
.btn.go{background:var(--accent);color:#fff}.btn:active{transform:scale(.97);opacity:.82}.btn:disabled{opacity:.4}
.btn.quiet{background:transparent;color:var(--accent);min-height:40px;padding:8px 4px}
.quote{gap:10px;margin-top:10px}.now .quote .btn{width:100%}
.tag,.verdict{font-size:12px;font-weight:650;padding:3px 9px;border-radius:999px;vertical-align:1px;letter-spacing:0}
.verdict{font-size:13px;padding:4px 10px}
.min{background:var(--card2);border-radius:16px;padding:14px;font-size:15px;margin-top:12px}
ol{margin:10px 0 0}li{padding:12px 0;border-top:1px solid var(--line);gap:12px}
.n{width:18px;text-align:center;font-size:15px;line-height:1;color:var(--muted)}
.n.w{color:var(--good)}.n.l{color:var(--red)}.n.o::before{content:'';display:inline-block;width:9px;height:9px;border-radius:50%;
 box-shadow:inset 0 0 0 1.6px var(--muted)}.n.live::before{content:'';display:inline-block;width:9px;height:9px;border-radius:50%;
 background:var(--red);animation:pulse 1.4s ease-in-out infinite}
.who b{font-weight:650}.who small{font-size:13px;margin-top:1px}.pct{font-size:15px;font-weight:650}
.tabs{margin:14px 16px 12px;padding:3px;gap:0;background:var(--track);border-radius:12px}
.tabs button{background:transparent!important;color:var(--muted)!important;border-radius:9px;padding:9px 4px;font-size:14px;
 transition:background .2s,color .2s}.tabs button.on{background:var(--thumb)!important;color:var(--ink)!important;
 box-shadow:0 1px 3px rgba(0,0,0,.18)}
.tabs.seg{margin:10px 0 6px}
.fbar{display:flex;flex-direction:column;gap:10px;margin:0 0 14px}
.fchips{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;margin:0 -16px;padding:0 16px}
.fchips::-webkit-scrollbar{display:none}.fchips:empty{display:none}
.fchip{flex:none;border:0;border-radius:999px;padding:9px 15px;font:600 14px -apple-system,system-ui,sans-serif;
 background:var(--card);color:var(--ink);box-shadow:var(--shadow);transition:background .15s,color .15s}
.fchip.on{background:var(--ink);color:var(--bg)}
.seg{display:flex;background:var(--track);border-radius:10px;padding:2px}
.schip{flex:1;border:0;background:transparent;color:var(--muted);font:600 13px -apple-system,system-ui,sans-serif;
 padding:7px 0;border-radius:8px;transition:background .15s,color .15s}
.schip.on{background:var(--thumb);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.18)}
.chips{display:flex;gap:6px;align-items:center;margin:0 0 6px;flex-wrap:wrap}
.sport{font-size:12px;font-weight:650;color:var(--ink);background:var(--card2);padding:3px 9px;border-radius:999px}
.when{font-size:12px;font-weight:650;color:var(--muted)}
.when.on{color:var(--red)}.when.on::before{content:'';display:inline-block;width:7px;height:7px;border-radius:50%;
 background:var(--red);margin-right:5px;vertical-align:1px;animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{50%{opacity:.35}}
.dots{display:inline-flex;gap:3px}.d{width:7px;height:7px;border-radius:50%;display:inline-block}
.d.w{background:var(--good)}.d.l{background:var(--red)}.d.o{box-shadow:inset 0 0 0 1.5px var(--muted)}
.cardfoot{display:flex;justify-content:flex-end;padding:6px 0 4px;border-top:1px solid var(--line);margin-top:4px}
.now{background:var(--card)!important;box-shadow:inset 0 0 0 1.5px var(--accentbg),var(--shadow)!important}
.now>b:first-child{font-size:17px}
.strip{margin:0 -16px 12px;padding:2px 20px 10px;border:0;font-size:15px;color:var(--muted)}
.strip b{color:var(--ink);font-size:17px;font-weight:750}
.lostbox{margin:4px 0 12px}.lostbox summary{border:0;border-radius:16px;padding:15px 16px;font-weight:650;box-shadow:var(--shadow)}
.lostbox .card{opacity:.82}
.empty{padding:26px 20px;text-align:center;color:var(--muted);font-size:15px}
.empty b{display:block;color:var(--ink);font-size:17px;margin-bottom:4px}
.swrow{display:flex;justify-content:space-between;align-items:center;gap:12px}
.alertrow{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--card);border-radius:16px;
 padding:12px 16px;margin:0 0 12px;box-shadow:var(--shadow)}.alertrow b{font-size:15px;font-weight:650;display:block}
.alertrow span{font-size:13px;color:var(--muted)}
.wline{font-size:13px;color:var(--muted);margin:0 4px 10px}.wline.bad{color:var(--bad)}
.gstrip{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;margin:2px -16px 6px;padding:2px 16px 4px}
.gstrip::-webkit-scrollbar{display:none}
.gchip{flex:none;display:flex;flex-direction:column;align-items:flex-start;gap:3px;border:0;border-radius:14px;
 padding:9px 12px;background:var(--card);color:var(--ink);font:14px -apple-system,system-ui,sans-serif;box-shadow:var(--shadow);
 transition:box-shadow .15s,transform .12s}.gchip:active{transform:scale(.97)}
.gchip .gt{white-space:nowrap}.gchip .gb{font-size:12px;color:var(--muted);white-space:nowrap}
.gchip.sel{box-shadow:inset 0 0 0 2px var(--accent)}
.lv{color:var(--red);font-weight:650}.lv::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;
 background:var(--red);margin-right:5px;vertical-align:2px;animation:pulse 1.4s ease-in-out infinite}
.gchip .gb .lv::before{width:5px;height:5px}
.ghead{display:none;align-items:center;justify-content:space-between;margin:8px 4px 0}.ghead.on{display:flex}
.ghead span{font-size:13px;font-weight:650;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.list{background:var(--card);border-radius:18px;padding:0 14px;box-shadow:var(--shadow)}
.list:empty{display:none}
details.crow{border-top:1px solid var(--line)}.list>details.crow:first-child,.nitem:first-child details.crow{border-top:0}
details.crow>summary{display:flex;align-items:center;gap:10px;padding:12px 0;list-style:none;cursor:pointer}
details.crow>summary::-webkit-details-marker{display:none}
.ci{width:22px;text-align:center;font-size:17px;flex:none}
.cg{flex:1;min-width:0}.cg b{font-size:15px}.cg .dots{margin-left:4px}
.cl{display:block;font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.cn{display:flex;flex-direction:column;align-items:flex-end;flex:none}.cn b{font-size:15px}.cn span{font-size:12px;color:var(--muted)}
details.crow[open]>summary .chev{transform:rotate(180deg)}
.cexp{padding:2px 0 4px}.cexp .chips{margin-bottom:8px}
.nitem{border-top:1px solid var(--line);padding-bottom:12px}.nitem:first-child{border-top:0}
.nitem .quote{margin-top:0}.nitem .quote .btn{width:100%}
#combos h2{margin:20px 4px 8px}
.quietbox{margin:14px 0 12px}.quietbox>summary{display:flex;align-items:center;justify-content:space-between;gap:10px;
 background:var(--card);border-radius:18px;padding:14px 16px;list-style:none;cursor:pointer;box-shadow:var(--shadow)}
.quietbox>summary::-webkit-details-marker{display:none}.quietbox>summary b{display:block;font-size:16px}
.quietbox>summary .muted{font-size:13px}.quietbox[open]>summary{border-radius:18px 18px 0 0}
.quietbox[open]>summary .chev{transform:rotate(180deg)}.quietbox .list{border-radius:0 0 18px 18px;border-top:1px solid var(--line)}
/* ---- iOS polish: system type sizes, inset grouped lists, hairlines, press states ---- */
body{font-size:17px;letter-spacing:-.01em}
header{padding:12px 20px 2px}h1{font-size:34px;font-weight:700;letter-spacing:.01em;line-height:1.2}
.sub{font-size:15px;color:var(--muted)}
#combos h2,h2{font-size:13px;font-weight:400;letter-spacing:.02em;text-transform:uppercase;color:var(--muted);margin:24px 16px 7px}
.list,.quietbox>summary,.alertrow,.lostbox>summary{border-radius:12px!important;box-shadow:none!important}
.list{padding:0 0 0 16px}
details.crow{border-top:0;position:relative}
details.crow+details.crow::before,.nitem+.nitem::before{content:'';position:absolute;left:44px;right:0;top:0;height:.5px;background:var(--line)}
.nitem{position:relative;border-top:0;padding:0 16px 14px 0}.nitem details.crow{position:static}
details.crow>summary{min-height:60px;padding:10px 16px 10px 0;margin-left:-16px;padding-left:16px;gap:12px;
 transition:background .2s ease}
details.crow>summary:active,.quietbox>summary:active,.lostbox>summary:active{background:var(--press);transition:none}
.ci{width:30px;height:30px;border-radius:8px;background:var(--tile);display:flex;align-items:center;justify-content:center;font-size:17px}
.cg b{font-size:17px;font-weight:600}.cl{font-size:15px}
.cn b{font-size:17px;font-weight:600}.cn span{font-size:13px}
.chev{width:8px;height:8px;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(-45deg);
 opacity:.55;margin-left:2px;flex:none;transition:transform .2s ease}
details.crow[open]>summary .chev,.quietbox[open]>summary .chev{transform:rotate(45deg)}
.dots .d{width:6px;height:6px}
.btn{border-radius:14px;min-height:50px;font-size:17px;font-weight:600}
.btn.two .bt{font-size:17px;font-weight:600}.btn.two .bs{font-size:13px}
.quietbox>summary{padding:12px 16px;min-height:60px}.quietbox>summary b{font-size:17px;font-weight:600}
.quietbox>summary .muted{font-size:15px;display:block}
.quietbox .list{border-radius:0 0 12px 12px!important;border-top:.5px solid var(--line)}
.quietbox[open]>summary{border-radius:12px 12px 0 0!important}
.lostbox>summary{font-size:17px;font-weight:600}
.alertrow{padding:10px 16px;min-height:60px}.alertrow b{font-size:17px;font-weight:400}.alertrow span{font-size:13px}
.tabs{margin:10px 16px 6px;padding:2px;border-radius:9px}.tabs button{font-size:13px;font-weight:600;padding:6px 4px;border-radius:7px}
.gstrip{gap:10px;margin:8px -16px 2px;padding:4px 16px 6px;scroll-snap-type:x proximity}
.gstrip{align-items:flex-start}
.gchip{scroll-snap-align:start;flex:none;width:142px;height:auto;display:flex;flex-direction:column;align-items:stretch;gap:3px;
 border-radius:14px;padding:9px 12px 8px;background:var(--card);box-shadow:none;text-align:left;cursor:pointer;
 -webkit-user-select:none;user-select:none}
.gchip:active{transform:scale(.97)}
.gr.you span{color:var(--ink);font-weight:600}
.gr i{font-style:normal;font-size:9px;font-weight:700;letter-spacing:.04em;color:var(--accent);background:var(--accentbg);
 padding:1px 4px;border-radius:4px;margin-left:5px;vertical-align:2px}
.gr.you{position:relative}.gr.you::before{content:'';position:absolute;left:-12px;top:3px;bottom:3px;width:3px;border-radius:2px;background:var(--accent)}
.gtop{display:flex;justify-content:space-between;align-items:center;font-size:12px;font-weight:600;color:var(--muted)}
.gtop .gsp{font-size:13px}
.gr{display:flex;justify-content:space-between;font-size:15px;color:var(--muted);line-height:1.25}
.gr b{font-weight:600}.gr.w{color:var(--ink)}.gr.w b{font-weight:700}
.gmine{font-size:12px;color:var(--accent);font-weight:600;margin-top:2px}
.gchip.sel{box-shadow:inset 0 0 0 2px var(--accent)}
.ghead{margin:14px 16px 0}
.cexp{padding:4px 16px 8px 0}.cardfoot{margin-right:16px}
details.crow>ol,details.crow>.min{margin-right:16px}
.min{border-radius:12px;background:var(--card2)}
.tag,.verdict{font-size:12px;font-weight:600}
/* disclosure rows (Combo mix, picks, a combo's picks) */
details.disc>summary,details.picks>summary{list-style:none;display:flex;align-items:center;justify-content:space-between;
 gap:10px;cursor:pointer;min-height:44px}
details.disc>summary::-webkit-details-marker,details.picks>summary::-webkit-details-marker{display:none}
details.disc>summary::after,details.picks>summary::after{content:'';width:8px;height:8px;border-right:2px solid var(--muted);
 border-bottom:2px solid var(--muted);transform:rotate(-45deg);opacity:.55;flex:none;transition:transform .2s}
details.disc[open]>summary::after,details.picks[open]>summary::after{transform:rotate(45deg)}
details.disc>summary>span{display:flex;flex-direction:column}details.disc>summary b{font-size:17px;font-weight:600}
details.disc>summary .muted{font-size:13px}
#mix.game{padding:6px 16px}#mix[open]{padding-bottom:12px}#pk>summary{padding:2px 0}
details.picks{margin-top:10px;border-top:.5px solid var(--line)}details.picks>summary{font-size:15px;font-weight:600}
h2 .ib{font-size:13px;opacity:.8}
/* suggested combos */
.card .side{display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.placed{display:inline-flex;align-items:center;gap:6px;border:0!important;background:transparent!important;font-size:15px;
 color:var(--muted);padding:2px 0}
.placed input{appearance:none;-webkit-appearance:none;width:22px;height:22px;border-radius:50%;margin:0;
 box-shadow:inset 0 0 0 1.5px var(--muted);transition:background .15s}
.placed input:checked{background:var(--accent);box-shadow:none}
.placed input:checked::after{content:'';display:block;width:6px;height:11px;margin:3px 0 0 7px;border:solid #fff;
 border-width:0 2px 2px 0;transform:rotate(45deg)}
.placed input:checked+span{color:var(--ink)}
.card .quote input.amt{width:64px;text-align:center;border-radius:10px;border:0;background:var(--card2);color:var(--ink);
 font:600 17px -apple-system,system-ui;padding:12px 6px}
.card .quote .btn.go{flex:1;white-space:nowrap;font-size:16px}.card .quote .btn.quiet{padding:12px 8px}.batch .btn{width:100%}
.stats{gap:10px}.stat{border-radius:12px!important}
.hidegame{display:none!important}
input.txt,textarea{border-radius:12px!important;border:1px solid var(--line)!important;background:var(--card2)!important;
 color:var(--ink);font-size:16px}
input[type=range]{accent-color:var(--accent)}
.klink{font-size:13px}
.toast{top:auto;bottom:18px;border-radius:14px;padding:12px 18px;font-size:15px;max-width:88%;text-align:center;
 background:rgba(30,33,41,.92);color:#fff;-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
body.enter>*:not(script):not(.toast){animation:enter .24s cubic-bezier(.2,.7,.3,1) both}
@keyframes enter{from{opacity:0;transform:translateY(8px)}}
details.card[open]>.min,details.card[open]>ol{animation:reveal .2s ease both}
@keyframes reveal{from{opacity:0;transform:translateY(-4px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

APP_JS = r"""
window.__load=function(h){var m=h.match(/<head[^>]*>([\s\S]*)<\/head>/i),b=h.match(/<body[^>]*>([\s\S]*)<\/body>/i);
 if(m)document.head.innerHTML=m[1];document.body.innerHTML=b?b[1]:h;
 document.querySelectorAll('body script').forEach(function(s){var n=document.createElement('script');n.text=s.text;s.parentNode.replaceChild(n,s);});
 window.scrollTo(0,0);window.__enter();};
window.__enter=function(){document.body.classList.add('enter');clearTimeout(window.__et);
 window.__et=setTimeout(function(){document.body.classList.remove('enter');},420);};
if(!window.__entered){window.__entered=1;window.__enter();}
if(!window.__ta){window.__ta=1;document.addEventListener('touchstart',function(){},{passive:true});}
function sheet(title, sub, url, label){location.href='combo://confirm/'+encodeURIComponent(JSON.stringify([title,sub,url,label||'Confirm']));}
function toast(m){var t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.className='toast';
 document.body.appendChild(t);}t.textContent=m;t.style.display=m?'block':'none';}
window.__morph=function(a,b){
 if(a.nodeType!==b.nodeType||a.nodeName!==b.nodeName){var n=window.__fresh(b);a.parentNode.replaceChild(n,a);return n;}
 if(a.nodeType!==1){if(a.nodeValue!==b.nodeValue)a.nodeValue=b.nodeValue;return a;}
 if(a.nodeName==='SCRIPT'){if(a.text!==b.text){var s=document.createElement('script');s.text=b.text;a.parentNode.replaceChild(s,a);return s;}return a;}
 var keep={};if(a.nodeName==='DETAILS')keep.open=1;if(a.hasAttribute('data-lg'))keep.style=1;
 for(var i=a.attributes.length-1;i>=0;i--){var nm=a.attributes[i].name;if(!keep[nm]&&!b.hasAttribute(nm))a.removeAttribute(nm);}
 for(i=0;i<b.attributes.length;i++){var at=b.attributes[i];if(!keep[at.name]&&a.getAttribute(at.name)!==at.value)a.setAttribute(at.name,at.value);}
 if(a.nodeName==='INPUT'&&a.type==='checkbox')a.checked=b.hasAttribute('checked');
 if(a.hasAttribute('data-k')&&a.textContent!==b.textContent){if(!b.children.length){window.__tick(a,a.textContent,b.textContent);return a;}
  a.classList.remove('tick');void a.offsetWidth;a.classList.add('tick');}
 window.__kids(a,b);return a;};
window.__fresh=function(n){if(n.nodeType!==1)return n;var c=document.importNode(n,true);
 (c.nodeName==='SCRIPT'?[c]:[].slice.call(c.querySelectorAll('script'))).forEach(function(o){var s=document.createElement('script');s.text=o.text;
  if(o===c)c=s;else o.parentNode.replaceChild(s,o);});return c;};
window.__kids=function(a,b){
 var old=[].slice.call(a.childNodes),byId={},free=[],fi=0,out=[];
 old.forEach(function(c){if(c.nodeType===1&&c.id)byId[c.id]=c;else free.push(c);});
 [].slice.call(b.childNodes).forEach(function(nb){var m=null;
  if(nb.nodeType===1&&nb.id){m=byId[nb.id]||null;delete byId[nb.id];}
  else if(fi<free.length&&free[fi].nodeType===nb.nodeType&&free[fi].nodeName===nb.nodeName){m=free[fi++];}
  out.push(m?window.__morph(m,nb):window.__fresh(nb));});
 var keepOrder=a.id==='alive';            /* the sort on the page decides this order, not the server */
 old.forEach(function(c){if(out.indexOf(c)<0&&c.id!=='toast'&&c.parentNode===a)a.removeChild(c);});
 out.forEach(function(n,i){if(n.parentNode!==a)a.appendChild(n);else if(!keepOrder&&a.childNodes[i]!==n)a.insertBefore(n,a.childNodes[i]||null);});};
window.__tick=function(el,from,to){el.textContent=to;
 var m1=/^([^0-9-]*)(-?[0-9,]+(?:\.[0-9]+)?)(.*)$/.exec(from),m2=/^([^0-9-]*)(-?[0-9,]+(?:\.[0-9]+)?)(.*)$/.exec(to);
 if(m1&&m2&&m1[1]===m2[1]&&m1[3]===m2[3]&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
  var x=parseFloat(m1[2].replace(/,/g,'')),y=parseFloat(m2[2].replace(/,/g,'')),dec=(m2[2].split('.')[1]||'').length,t0=null;
  var fmt=function(v){return m2[1]+v.toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec})+m2[3];};
  var step=function(ts){if(!t0)t0=ts;var k=Math.min(1,(ts-t0)/450),e=1-Math.pow(1-k,3);el.textContent=fmt(x+(y-x)*e);
   if(k<1)requestAnimationFrame(step);else el.textContent=to;};requestAnimationFrame(step);}
 el.classList.remove('tick');void el.offsetWidth;el.classList.add('tick');};
window.__swap=function(h){var t=document.createElement('template');t.innerHTML=h;
 var vis=document.querySelector('section[id]:not(.hidden)');var tabSel=vis?vis.id:null;
 window.__kids(document.body,t.content);
 if(tabSel&&window.tab&&document.getElementById(tabSel)&&tabSel!=='combos')tab(tabSel);
 if(window.__after)try{window.__after();}catch(e){}};
if(!window.__ptr)(function(){window.__ptr=1;var y0=null,pull=0;
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


TOUR_SLIDES = [
    ("🏠", "Live is home base",
     "Every combo you hold, in every sport, with live scores. The dots show each pick: "
     "<b class='pos'>green</b> won, <b style='color:var(--red)'>red</b> lost, hollow still to play. Tap a card for the details."),
    ("👆", "Right now tells you what to do",
     "When something's worth doing, like cashing out a combo, it shows up at the top as one button. "
     "Nothing is ever bought or sold until you tap and confirm."),
    ("＋", "Build makes the combos",
     "Pick your budget and tap <b>Build combos</b>. The planner suggests a mix of safer and long-shot combos, "
     "and you choose which to place. The defaults are a good start."),
    ("🎯", "Let it ride, or lock it in",
     "Turn on alerts on the Live page to hear when a combo is worth cashing out. In Settings, <b>Let it ride</b> "
     "sets how long the planner waits before saying so. Everything else in Settings can wait."),
]


def tour_html():
    """A four-card swipeable introduction, shown once after setup (and from Settings any time)."""
    cards = "".join(
        f"<div class='tslide'><div class='ticon'>{icon}</div><h2>{title}</h2><p>{text}</p></div>"
        for icon, title, text in TOUR_SLIDES)
    dots = "".join("<i></i>" for _ in TOUR_SLIDES)
    return ("<div id='tour' class='tour'><div class='tsheet'>"
            f"<button class='tskip' onclick='tourEnd(0)'>Skip</button><div class='ttrack' id='ttrack'>{cards}</div>"
            f"<div class='tdots' id='tdots'>{dots}</div>"
            "<button class='btn go big' id='tnext' onclick='tourNext()'>Next</button></div></div>"
            "<script>(function(){if(window.__tourDone){var t=document.getElementById('tour');if(t)t.remove();return;}"
            "var tr=document.getElementById('ttrack'),n=tr.children.length;"
            "function cur(){return Math.round(tr.scrollLeft/tr.clientWidth);}"
            "function paint(){var i=cur();[].forEach.call(document.querySelectorAll('#tdots i'),function(d,k){d.className=k===i?'on':'';});"
            "document.getElementById('tnext').textContent=i===n-1?'Build my first combos':'Next';}"
            "tr.addEventListener('scroll',function(){clearTimeout(window.__ts);window.__ts=setTimeout(paint,60);},{passive:true});"
            "window.tourNext=function(){var i=cur();if(i>=n-1)return tourEnd(1);tr.scrollTo({left:(i+1)*tr.clientWidth,behavior:'smooth'});};"
            "window.tourEnd=function(build){window.__tourDone=1;var t=document.getElementById('tour');"
            "if(t){t.classList.add('out');setTimeout(function(){t.remove();},260);}"
            "location.href='combo://nav/'+(build?'tour-build':'tourdone');};paint();})();</script>")


TOUR_CSS = """
.tour{position:fixed;inset:0;z-index:50;background:rgba(5,7,12,.55);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);
 display:flex;align-items:flex-end;animation:tin .28s ease both}
.tour.out{animation:tout .26s ease both}@keyframes tin{from{opacity:0}}@keyframes tout{to{opacity:0}}
.tsheet{position:relative;width:100%;background:var(--card);border-radius:26px 26px 0 0;
 padding:22px 0 calc(22px + env(safe-area-inset-bottom));animation:tup .34s cubic-bezier(.2,.7,.3,1) both}
@keyframes tup{from{transform:translateY(40px)}}
.tskip{position:absolute;right:16px;top:14px;border:0;background:transparent;color:var(--muted);font:600 15px -apple-system,system-ui;padding:8px}
.ttrack{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}.ttrack::-webkit-scrollbar{display:none}
.tslide{flex:0 0 100%;scroll-snap-align:start;padding:18px 26px 4px;box-sizing:border-box}
.ticon{width:56px;height:56px;border-radius:16px;background:var(--accentbg);display:flex;align-items:center;justify-content:center;
 font-size:28px;margin-bottom:14px}
.tslide h2{all:unset;display:block;font:800 24px/1.15 -apple-system,system-ui;letter-spacing:-.02em;margin-bottom:8px;color:var(--ink)}
.tslide p{margin:0;font-size:16px;line-height:1.5;color:var(--muted)}.tslide p b{color:var(--ink)}.tslide p b.pos{color:var(--good)}
.tdots{display:flex;gap:6px;justify-content:center;margin:18px 0 14px}.tdots i{width:7px;height:7px;border-radius:50%;
 background:var(--line);transition:width .2s,background .2s}.tdots i.on{width:20px;border-radius:4px;background:var(--accent)}
.tsheet .btn{display:block;width:calc(100% - 52px);margin:0 26px}
.tip{background:var(--accentbg);border-radius:16px;padding:14px 16px;font-size:15px;margin:0 0 14px}
.tip b{color:var(--accent)}
"""


def app_frame(page):
    """Page extras inside the web view: pull-to-refresh, the in-place swap and confirm dialogs.
    The title bar and tab bar are native controls (see _web)."""
    if "<body>" not in page or "id='ptr'" in page:
        return page
    refresh = (APP.get("where") or "") in ("mine", "results")
    page = page.replace("</head>", f"<style>{APP_CSS}{TOUR_CSS}</style></head>", 1)
    if CFG.get("tour_pending") and "<h1>Welcome</h1>" not in page and "id='tour'" not in page and can_trade():
        page = page.replace("</body>", tour_html() + "</body>", 1)
    page = page.replace("<body>", "<body><div class='ptr' id='ptr'></div>" + ("" if APP.get("bar") is not None
                        or not in_pythonista() else fallback_nav(page)), 1)
    page = page.replace("</body>", f"<script>{APP_JS}window.REFRESH={'true' if refresh else 'false'};</script></body>", 1)
    update_bars()
    return page


KALSHI_WEB = "https://kalshi.com"
GAME_SLUG = {"KXNFLGAME": "nfl-game", "KXNBAGAME": "nba-game", "KXNHLGAME": "nhl-game"}


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


def tap_haptic():
    """The light 'selection' tick iOS uses for pickers and segmented controls."""
    try:
        from objc_util import ObjCClass, on_main_thread

        @on_main_thread
        def tick():
            g = ObjCClass("UISelectionFeedbackGenerator").new()
            g.selectionChanged()
        tick()
    except Exception:
        pass


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
        if url.startswith("combo://haptic/"):
            tap_haptic()
            return False
        if url.startswith("combo://copy/catalog"):
            try:
                import clipboard
                clipboard.set(CATALOG.get("text", ""))
                webview.evaluate_javascript("toast('Copied. Paste it into your chat with Claude.');"
                                            "setTimeout(function(){toast('')},2500)")
            except Exception:
                pass
            return False
        if self.inner is not None:
            return self.inner.webview_should_start_load(webview, url, nav_type)
        return not url.startswith("combo://")


def go_to(target):
    """Switch to My combos, Results or Settings in the same window."""
    import threading
    if target in ("tourdone", "tour-build", "tour"):
        CFG["tour_pending"] = target == "tour"
        save_cfg()
        if target == "tourdone":
            return
        target = "build" if target == "tour-build" else "refresh"
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


DARK_CSS = ("<style>:root{color-scheme:dark;--bg:#000000;--card:#1c1c1e;--card2:#2c2c2e;--ink:#ffffff;"
            "--muted:#98989f;--line:rgba(84,84,88,.6);--accent:#0a84ff;--accentbg:rgba(10,132,255,.18);"
            "--good:#30d158;--goodbg:rgba(48,209,88,.16);--bad:#ff9f0a;--badbg:rgba(255,159,10,.16);"
            "--red:#ff453a;--redbg:rgba(255,69,58,.16);--dogbg:rgba(191,90,242,.18);--dog:#bf5af2;--done:#0f2416;"
            "--track:rgba(118,118,128,.24);--thumb:#636366;--shadow:none;--press:#2c2c2e;--tile:#2c2c2e}"
            "body{background:var(--bg);color:var(--ink)}</style>")
LIGHT_CSS = ("<style>:root{color-scheme:light;--bg:#f2f2f7;--card:#ffffff;--card2:#f2f2f7;--ink:#000000;"
             "--muted:#8a8a8e;--line:rgba(60,60,67,.22);--accent:#007aff;--accentbg:rgba(0,122,255,.12);"
             "--good:#248a3d;--goodbg:rgba(52,199,89,.14);--bad:#c93400;--badbg:rgba(255,149,0,.16);"
             "--red:#d70015;--redbg:rgba(255,59,48,.12);--dogbg:rgba(175,82,222,.12);--dog:#8944ab;--done:#eaf7ee;"
             "--track:rgba(118,118,128,.12);--thumb:#ffffff;--shadow:none;--press:#e5e5ea;--tile:#f2f2f7}"
             "body{background:var(--bg);color:var(--ink)}</style>")


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
    try:
        attach_fair(all_games, {})             # Kalshi's prices, for the kickoff record
        record_closing(all_games)
    except Exception:
        pass
    MINE["days"].update(days)
    MINE["book"] = {}                      # live chances use Kalshi's in-game prices
    if MINE.get("busy"):
        return []
    MINE["last"] = dt.datetime.now().strftime("%-I:%M %p")
    expire_offers()
    pre_alerts = auto_cash_checks()
    APP["quiet"] = True
    page, snap = mine_page(live=True)
    pi = in_pythonista() and watcher_alive()
    if AUTOSELL and CFG.get("tp_follow", True) and MINE.get("tp") and can_trade() and not pi:
        try:
            if retarget_take_profits():
                MINE["tp"] = resting_sells()
                page, snap = mine_page(live=True)
        except Exception:
            pass
    if pi:
        MINE["pi_was_alive"] = True
    elif MINE.get("pi_was_alive") and watcher_conf():
        MINE["pi_was_alive"] = False             # the Pi went quiet: say so once, the phone takes over
        notify("🖥 Your Pi watcher stopped checking in. This phone is handling alerts and auto cash-out "
               "while the planner is open. Check the Pi's power and network.")
    sold = [] if pi else auto_sell_now(MINE.get("plan"))     # with the Pi on, only the Pi sells
    if sold:
        ACCT_CACHE["at"] = 0
        MINE["flash"] = " ".join(sold)
        page, snap = mine_page(live=True)
        for msg in sold:
            notify(msg)
    cash_alerts_now = [] if sold else cash_alerts(MINE.get("plan"))
    alerts = diff_alerts(MINE.get("snap") or {}, snap) + pre_alerts + cash_alerts_now
    MINE["snap"] = snap
    present(page, MineKeeper())
    for msg in ([] if pi else alerts[:4]):        # the Pi sends these when it's running
        notify(msg)
    return alerts


SELL_LOG = os.path.join(HERE, "combo_autosell_log.jsonl")   # every automatic cash-out decision, one per line


def log_decision(rec):
    """One line per automatic cash-out decision (sold, or skipped and why), trimmed to the last 1,000."""
    import time
    rec = dict(rec, at=int(time.time()), when=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
               by="phone" if in_pythonista() else "pi", ride=ride_level()[0])
    try:
        with open(SELL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        if os.path.getsize(SELL_LOG) > 300000:
            with open(SELL_LOG, encoding="utf-8") as f:
                lines = f.readlines()[-1000:]
            with open(SELL_LOG, "w", encoding="utf-8") as f:
                f.writelines(lines)
    except OSError:
        pass
    console_note("auto cash-out: " + json.dumps(rec))


def sold_today():
    """Automatic cash-outs made by this device today."""
    today = dt.date.today().isoformat()
    try:
        with open(SELL_LOG, encoding="utf-8") as f:
            return sum(1 for x in f if ('"result": "sold"' in x or '"result": "hedged"' in x) and f'"when": "{today}' in x)
    except OSError:
        return 0


def turning_against(h):
    """A game in this combo is on and going the wrong way (your pick under 50% live)."""
    return any(live and c < 0.5 for c, live, _ in h.get("legs_left") or [])


def auto_sell_now(plan):
    """Auto cash-out (Settings, off by default): sells what the plan says to cash out, by itself,
    the same advice the card shows as Cash out. That already means a pick has won and Kalshi's
    offer is at least the Let it ride price for waiting another game; both are checked again here.
    Uses Kalshi's cash-out offers (the only way it buys combos back), so it runs while the planner
    is open. Returns the messages to send."""
    if not (CFG.get("auto_sell") and plan and can_trade()) or MINE.get("busy"):
        return []
    out = []
    MINE["busy"] = True
    try:
        for t, f in sorted(plan["acts"].items(), key=lambda x: -x[1]):
            h, o = MINE["hold"].get(t), fresh_offer(t)
            if not (f and h and o and h.get("won_some")) or t in MINE.get("selling", set()):
                continue
            thr = wait_threshold(t)
            if o["offer"] / max(o.get("frac", 1.0), 0.01) < thr:
                continue
            if f < 1 or o.get("frac", 1.0) < 1 or o.get("rfq") == "estimate":   # the Pi only estimates
                o = get_cash_offer(t, f)
                MINE["cash"][t] = o
                if not o.get("offer") or o["offer"] / max(o.get("frac", 1.0), 0.01) < CASH_SLIP * thr:
                    continue
            held = {a["ticker"]: a for a in (fetch_account(max_age=0, every_league=True)[0] or [])}
            a = held.get(t)
            if not a or a.get("status") != "pending" or a.get("pays", 0) < o.get("contracts", 0) - 0.01:
                drop_cash(t)                    # already sold (by you, the Pi or the phone): leave it
                continue
            rec = {"combo": h["label"], "ticker": t, "offer": round(o["offer"], 2), "cut_off": round(thr, 2),
                   "chance": round(h["p"], 4), "cost": round(h["cost"], 2), "pays": h["pays"],
                   "picks_left": [round(c, 3) for c, _, _ in h.get("legs_left") or []]}
            if sold_today() >= int(CFG.get("auto_cap", 5)):
                log_decision(dict(rec, result="skipped", why="daily cap reached"))
                if MINE.get("cap_told") != dt.date.today().isoformat():
                    MINE["cap_told"] = dt.date.today().isoformat()
                    out.append(f"🤖 Auto cash-out reached today's cap of {CFG.get('auto_cap', 5)} sales. "
                               f"{h['label']} qualifies too: open the planner to cash it out yourself.")
                continue
            if o["offer"] < h["cost"] * o.get("frac", 1.0) and not turning_against(h):
                log_decision(dict(rec, result="skipped", why="below what you paid"))
                continue
            hg = hedge_for(t) if CFG.get("auto_hedge") else None
            whole = o["offer"] / max(o.get("frac", 1.0), 0.01)
            better = hg["locked"] >= whole * (0.95 if CFG.get("prefer_hedge", True) else 1.0) + (0 if CFG.get("prefer_hedge", True) else 0.5) \
                if hg and hg.get("n") else False
            if better:
                if hg["cost"] > float(CFG.get("hedge_cap", 100)):
                    rec["hedge_skipped"] = f"hedge would cost {money(hg['cost'])}, over the {money(CFG.get('hedge_cap', 100))} cap"
                else:
                    if t in MINE["cash"]:
                        drop_cash(t)            # not selling: release the cash-out request
                    msg = place_hedge(t)
                    ok = msg.startswith("✅")
                    log_decision(dict(rec, result="hedged" if ok else "hedge failed", hedge_cost=round(hg["cost"], 2),
                                      locked=round(hg["locked"], 2), note=msg[:140]))
                    if ok:
                        vs = ("more than" if hg["locked"] > whole + 0.5 else "about the same as")
                        out.append(f"🤖 Auto-hedge (Let it ride: {ride_level()[0]}): locks in {vs} the "
                                   f"{money(whole)} cash-out, without the buyer's cut. " + msg)
                        continue
            msg = accept_cash(t)
            log_decision(dict(rec, result="sold" if msg.startswith("✅") else "failed", note=msg[:140]))
            out.append(("🤖 Auto cash-out (Let it ride: " + ride_level()[0] + "). ") + msg)
    finally:
        MINE["busy"] = False
    return out


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
        MINE["advised"] = set()
        return None
    acts = {t: 0.0 for t in offers}
    best = weekend_stats(acts)["worth"]
    for _ in range(3):
        changed = False
        for t in sorted(offers, key=lambda x: -MINE["hold"][x]["hold"]):
            h = MINE["hold"][t]
            if not h.get("won_some"):
                continue        # nothing won yet: you bought it for the upside, so hold it
            bar = wait_threshold(t) * (0.97 if t in MINE.get("advised", set()) else 1.0)
            if acts_price(t) * h["pays"] < bar:
                continue        # waiting at least one more game is worth more than this offer
            for f in (0.0, 0.5, 1.0):
                if f == acts[t]:
                    continue
                trial = dict(acts, **{t: f})
                v = weekend_stats(trial)["worth"]
                if v > best + 0.25:               # ignore changes worth only pennies
                    best, acts, changed = v, trial, True
        if not changed:
            break
    MINE["advised"] = {t for t, f in acts.items() if f}      # sticky: needs a 3% drop to flip back
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
    thr = wait_threshold(t)
    if h.get("won_some") and thr > o["offer"] / max(o.get("frac", 1.0), 0.01):
        nxt = (h.get("legs_left") or [(0, False, 0)])[0]
        return (f"Waiting is worth more: {'the game under way' if nxt[1] else 'the next game'} "
                f"({nxt[0]:.0%} to go your way) makes this combo worth more to sell after. "
                f"Worth cashing out at about {money(thr)}.")
    return f"Holding is worth about {money(single_value(p, pays, W))} to you, more than this offer."

def confirm_parts(t, h, o):
    """(title, details, url, button) for the confirm sheet: exactly what happens."""
    what = "half of " if o.get("frac", 1.0) < 1 else ""
    title = (f"Cash out {what}{h['label']} for {money(o['offer'])}? "
             f"({gain_words(o['offer'], h['cost'] * o.get('frac', 1.0))})")
    sub = (f"You paid {money(h['cost'] * o.get('frac', 1.0))}. If you hold instead: "
           f"{h['p']:.0%} chance of {money(h['pays'] * o.get('frac', 1.0))}.")
    return title, sub, f"combo://cash/go/{t}", f"Cash out for {money(o['offer'])}"


def confirm_cash(t, h, o):
    """onclick for a Cash out button: a bottom sheet that says exactly what happens."""
    args = ",".join(json.dumps(x) for x in confirm_parts(t, h, o))
    return html.escape(f"sheet({args})")


def gain_words(amount, paid):
    """'+$10 profit' / '$2 loss' / 'break even' for getting `amount` back on `paid`."""
    d = amount - paid
    if abs(d) < 0.5:
        return "break even"
    return f"+{money(d)} profit" if d > 0 else f"{money(-d)} loss"


def cash_label(name, f, amount, paid, about=False):
    """Two-line cash-out button: what you'd make first, then what you get back and paid."""
    return (f"<span class='bt'>Cash out {'half of ' if f < 1 else ''}{name} · {'about ' if about else ''}"
            f"{gain_words(amount, paid)}</span>"
            f"<span class='bs'>get {money(amount)} · you paid {money(paid)}</span>")


def action_button(t, f, h):
    """The button that carries out the plan for one combo (needs an offer of the right size)."""
    o = fresh_offer(t)
    te = html.escape(t)
    if not o or f == 0:
        return ""
    if abs(o.get("frac", 1.0) - f) < 0.01:
        what = "half of " if f < 1 else ""
        return (f"<button class='btn go cashb two' onclick=\"{confirm_cash(t, h, o)}\">"
                f"{cash_label(html.escape(h['label']), f, o['offer'], h['cost'] * f)}</button>")
    # Kalshi quotes one size at a time, so this price is worked out from the offer in hand;
    # tapping gets the exact offer for this size and asks you to confirm it.
    est = acts_price(t) * h["pays"] * f
    act = "askhalfgo" if f < 1 else "askgo"
    return (f"<button class='btn go cashb two' onclick=\"cash('{act}','{te}')\">"
            f"{cash_label(html.escape(h['label']), f, est, h['cost'] * f, about=True)}</button>")


def cash_block(ticker, plan):
    """The short hold-or-cash-out box on a live combo card."""
    h = MINE["hold"].get(ticker)
    if not h:
        return ""
    t = html.escape(ticker)
    W = max(CFG["bankroll"], 1) + MINE.get("locked", 0)
    p, pays = h["p"], h["pays"]
    pct = f"{p:.0%}" if p >= 0.01 or p == 0 else f"{p:.1%}"
    out = [f"<div class='min cashbox'>If you hold: <b>{pct}</b> chance of <b>{gain_words(pays, h['cost'])}</b>"
           f" <span class='muted'>({money(pays)} back)</span>"
           + ("<div class='muted' style='font-size:12px;margin-top:4px'>Chance from Kalshi's price for the whole "
              "combo: its picks are in the same game and move together.</div>" if h.get("rough") else "")]
    if CFG.get("auto_sell") and can_trade() and not h.get("rough"):
        thr = wait_threshold(ticker)
        who = "your Pi " if in_pythonista() and watcher_alive() else ""
        out.append(f"<div class='muted' style='font-size:13px;margin-top:6px'>🤖 Auto cash-out is on: {who}"
                   + (f"sells by itself if Kalshi offers about {money(thr)} or more." if h.get("won_some") and thr
                      else "it waits until a pick in this combo has won.") + "</div>")
    tp = (MINE.get("tp") or {}).get(ticker)
    if tp:
        st = order_steps(tp)
        left = sum(k for k, _ in st) or pays
        what = (" / ".join(money(pr * left) for _, pr in st) + " <span class='muted'>(thirds, whole-combo prices)</span>"
                if len(st) > 1 else money(st[0][1] * left))
        guard = any(live for _, live, _ in (MINE["hold"].get(ticker) or {}).get("legs_left", []))
        out.append(f"<div class='quote' style='justify-content:space-between'><span style='font-size:14px'>🎯 <b>Auto-sell is on</b>: Kalshi sells it if a buyer pays "
                   f"<b>{what}</b>" + ("<br><span class='muted' style='font-size:12px'>A game is on: priced as if "
                                        "your pick wins, so no one can buy cheap off a swing.</span>" if guard else "")
                   + f"</span><button class='btn quiet cashb' onclick=\"cash('tpx','{t}')\">Cancel</button></div>")
    elif AUTOSELL and can_trade():
        target, why = tp_target(h["cost"], pays, ticker)
        if target:
            at = ("starting at " if "thirds" in why else "at ") + money(target)
            out.append(f"<div class='quote' style='display:block'><div style='font-size:14px;margin-bottom:8px'>"
                       f"<b>Auto-sell is off</b> for this combo. <span class='muted'>Turn it on and Kalshi sells it "
                       f"for you if a buyer pays {at}, even while you're away.</span></div>"
                       f"<button class='btn cashb' onclick=\"cash('tp','{t}')\">Turn on auto-sell {at}</button>"
                       f"<div class='muted' style='font-size:13px;margin-top:6px'>{html.escape(why.strip('()'))}"
                       f" · cancel any time</div></div>")
    raw = MINE["cash"].get(ticker)
    o = fresh_offer(ticker)
    if raw and raw.get("error"):
        out.append(f"<div class='muted' style='font-size:13px;margin-top:6px'>{html.escape(raw['error'])}</div>")
    if o:
        f = (plan or {}).get("acts", {}).get(ticker, 0.0)
        word, cls = {1.0: ("Cash out", "ok"), 0.5: ("Cash out half", "ok")}.get(f, ("Hold", "no"))
        size = " for half" if o.get("frac", 1.0) < 1 else ""
        main = action_button(ticker, f, h) if f else ""
        if main:                                  # inside its own card the combo's name is implied
            main = re.sub(r"(Cash out(?: half)?)(?: of)? " + re.escape(html.escape(h["label"])) + r"\b", r"\1", main)
        if not main:
            main = (f"<button class='btn cashb' onclick=\"{confirm_cash(ticker, h, o)}\">Cash out"
                    f"{' half' if size else ''} for {money(o['offer'])}</button>")
        out.append(f"<div style='margin-top:8px'>Kalshi offers <b>{money(o['offer'])}</b>{size} "
                   f"<span class='verdict {cls}'>{word}</span></div>"
                   f"<div class='muted' style='font-size:13px;margin-top:4px'>{plan_words(ticker, f, o, h, W)}</div>"
                   + insurance_words(h, o) +
                   f"<div class='quote pair'>{main}<button class='btn cashb' onclick=\"cash('no','{t}')\">Keep it</button></div>"
                   + hedge_block(ticker, h, o))
    else:
        tag = "<span class='tag good'>Worth checking</span> " if h["worth"] else ""
        out.append(f"<div class='quote'>{tag}<button class='btn cashb' onclick=\"cash('ask','{t}')\">"
                   f"Get cash-out offer</button></div>" + hedge_block(ticker, h, None))
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------- hedging
HEDGES = os.path.join(HERE, "combo_hedges.json")   # combo -> contracts of the other side already bought
FEE_RATE = 0.07                                     # Kalshi's trading fee: about 7% x price x (1 - price)


def qty(x):
    """A contract count as Kalshi shows it: 41.67, 42."""
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def hedge_for(ticker):
    """For a combo down to its last pick: buying the other side of that game so you collect about
    the same whichever team wins. {ticker, name, price, n, cost, locked, done} or None."""
    h = MINE["hold"].get(ticker) or {}
    need = h.get("need") or []
    if len(need) != 1:
        return None
    (side, leg_t), _ = need[0]
    for sides in (MINE.get("all_games") or {}).values():
        mine = next((x for x in sides if x["ticker"] == leg_t), None)
        if mine:
            if any(x.get("tie") for x in sides):
                return None                       # a draw is possible: no single hedge covers it (yet)
            other = next((x for x in sides if x is not mine), None)
            buy = other if side == "yes" else mine
            break
    else:
        return None
    q = buy.get("p") if buy else None
    if not q or not 0.01 <= q <= 0.97:
        return None
    done = (load_json(HEDGES, {}).get(ticker) or {}).get("n", 0.0)
    n = math.floor((h["pays"] - done) * 100) / 100
    if n < 1:
        return {"ticker": buy["ticker"], "name": buy["pick"], "done": done, "n": 0}
    fee = math.ceil(FEE_RATE * n * q * (1 - q) * 100) / 100
    cost = n * q + fee
    return {"ticker": buy["ticker"], "name": buy["pick"], "price": q, "n": n, "fee": fee,
            "cost": cost, "locked": n - cost, "done": done}


def place_hedge(ticker):
    """Buy the other side of the last pick's game, at today's price or not at all (fills now or
    cancels). Only runs after you confirm. Returns a message."""
    import uuid
    h = MINE["hold"].get(ticker) or {}
    hg = hedge_for(ticker)
    if not hg or not hg.get("n"):
        return "Nothing to hedge on this combo now."
    body = {"ticker": hg["ticker"], "side": "bid", "count": f"{hg['n']:.2f}", "price": f"{hg['price']:.4f}",
            "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": str(uuid.uuid4())}
    try:
        r = kalshi_send("POST", "/portfolio/events/orders", body) or {}
        filled = float(r.get("fill_count") or 0)
    except RuntimeError as err:
        if "(404)" not in str(err):
            return f"Kalshi didn't take the hedge: {err}"
        legacy = {"ticker": hg["ticker"], "action": "buy", "side": "yes", "type": "limit",
                  "count": int(hg["n"]), "yes_price": int(round(hg["price"] * 100)),
                  "time_in_force": "immediate_or_cancel", "client_order_id": str(uuid.uuid4())}
        try:
            o = (kalshi_send("POST", "/portfolio/orders", legacy) or {}).get("order") or {}
        except RuntimeError as err2:
            return f"Kalshi didn't take the hedge: {err2}"
        filled = float(o.get("fill_count_fp") or o.get("fill_count") or
                       (legacy["count"] - float(o.get("remaining_count") or 0) if o.get("status") == "executed" else 0))
    except PermissionError:
        return "Kalshi refused. Your API key needs write (trading) access to hedge."
    ACCT_CACHE["at"] = 0
    if filled <= 0:
        return f"No one was selling {hg['name']} at {hg['price'] * 100:.0f}¢ just now. Nothing was bought."
    d = load_json(HEDGES, {})
    d[ticker] = {"n": round(hg["done"] + filled, 2), "ticker": hg["ticker"], "name": hg["name"]}
    save_json(HEDGES, d)
    haptic("success")
    locked = filled * (1 - hg["price"]) - hg["fee"] * filled / hg["n"]
    if filled + 0.01 < hg["n"]:
        return (f"✅ Hedged part of {h.get('label', 'the combo')}: bought {qty(filled)} of {qty(hg['n'])} {hg['name']} at "
                f"{hg['price'] * 100:.0f}¢. Tap Hedge again for the rest at the new price.")
    return (f"✅ Hedged {h.get('label', 'the combo')}: bought {qty(filled)} {hg['name']} at {hg['price'] * 100:.0f}¢. "
            f"You collect about {money(filled)} whichever team wins: about {money(locked)} locked in after the hedge.")


def hedge_block(ticker, h, o):
    """Card lines: what hedging locks in, next to the cash-out offer, with its own confirm."""
    hg = hedge_for(ticker)
    if not hg:
        return ""
    if not hg.get("n"):
        return (f"<div class='muted' style='font-size:13px;margin-top:6px'>🛡 Hedged with {qty(hg['done'])} "
                f"{html.escape(hg['name'])}: you collect about the same whichever team wins.</div>")
    if hg["locked"] <= 0:
        return ""
    vs = ""
    if o:
        diff = hg["locked"] - o["offer"] / max(o.get("frac", 1.0), 0.01)
        vs = (f" That's <b>{money(diff)} more</b> than cashing out." if diff > 0.5 else
              f" Cashing out gets {money(-diff)} more." if diff < -0.5 else " About the same as cashing out.")
    title = (f"Hedge {h['label']}: buy {qty(hg['n'])} {hg['name']} at {hg['price'] * 100:.0f}¢ "
             f"({money(hg['cost'])})?")
    sub = (f"You'd collect about {money(hg['n'])} whichever team wins, so about {money(hg['locked'])} is locked in "
           f"({gain_words(hg['locked'], h['cost'])}). Buys now at {hg['price'] * 100:.0f}¢ or not at all; fee about "
           f"{money(hg['fee'])}.")
    args = ",".join(json.dumps(x) for x in (title, sub, f"combo://cash/hedgego/{ticker}", f"Hedge · lock in {money(hg['locked'])}"))
    return (f"<div style='margin-top:10px;font-size:14px'>🛡 <b>Or hedge:</b> buy {qty(hg['n'])} {html.escape(hg['name'])} at "
            f"{hg['price'] * 100:.0f}¢ ({money(hg['cost'])}) and collect about {money(hg['n'])} either way: locks in "
            f"<b>{money(hg['locked'])}</b>.{vs}</div><div class='quote'><button class='btn quiet cashb' "
            f"onclick=\"{html.escape(f'sheet({args})')}\">Hedge · lock in {money(hg['locked'])}</button></div>")


def insurance_words(h, o):
    """What cashing out gives up vs holding, on average: the price of a sure thing."""
    if not o:
        return ""
    whole = o["offer"] / max(o.get("frac", 1.0), 0.01)
    gap = h["p"] * h["pays"] - whole
    if gap < 0.5:
        return ""
    return (f"<div class='muted' style='font-size:13px;margin-top:4px'>Cashing out gives up about {money(gap)} "
            f"on average vs. holding, in exchange for a sure {money(whole)}.</div>")


# ---------------------------------------------------------------- scores
SCORES_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SCORES = {"at": 0, "by_team": {}}
SCORES_BY = {}            # league -> {"at": time, "by": {team key: [game info, ...]}}

# Every sport the Live page can show, including leftover college-basketball combos.
SPORTS = {
    "nfl": {"icon": "🏈", "name": "NFL", "espn": "football/nfl", "q": {}, "periods": 4, "day": False, "hours": 3.5},
    "nba": {"icon": "🏀", "name": "NBA", "espn": "basketball/nba", "q": {}, "periods": 4, "day": True, "hours": 2.5},
    "nhl": {"icon": "🏒", "name": "NHL", "espn": "hockey/nhl", "q": {}, "periods": 3, "day": True, "hours": 2.75},
    "ncaamb": {"icon": "🏀", "name": "College", "espn": "basketball/mens-college-basketball",
               "q": {"groups": "50"}, "periods": 2, "day": True, "hours": 2.25},
    "ncaaf": {"icon": "🎓", "name": "College football", "espn": "football/college-football",
              "q": {"groups": "80"}, "periods": 4, "day": False, "hours": 3.5},
    "ncaawb": {"icon": "🏀", "name": "Women's college", "espn": "basketball/womens-college-basketball",
               "q": {"groups": "50"}, "periods": 4, "day": True, "hours": 2.25},
    "euroleague": {"icon": "🏀", "name": "EuroLeague", "espn": None, "q": {}, "periods": 4, "day": True, "hours": 2.25},
    "ufc": {"icon": "🥊", "name": "UFC", "espn": None, "q": {}, "periods": 3, "day": False, "hours": 0.5},
    "soccer": {"icon": "⚽", "name": "Soccer", "espn": ["soccer/eng.1", "soccer/esp.1", "soccer/ita.1", "soccer/ger.1",
                                                       "soccer/fra.1", "soccer/usa.1", "soccer/mex.1"],
               "q": {}, "periods": 2, "day": False, "hours": 2.0},
    "tennis": {"icon": "🎾", "name": "Tennis", "espn": None, "q": {}, "periods": 3, "day": True, "hours": 2.5},
}
SPORT_PREFIX = (("ncaamb", "KXNCAAMB"), ("ncaawb", "KXNCAAWB"), ("ncaaf", "KXNCAAF"), ("nba", "KXNBA"),
                ("nhl", "KXNHL"), ("nfl", "KXNFL"), ("euroleague", "KXEUROLEAGUE"), ("ufc", "KXUFC"),
                ("tennis", "KXATP")) + tuple(("soccer", x[:-4]) for x in ['KXEPLGAME', 'KXLALIGAGAME', 'KXSERIEAGAME', 'KXBUNDESLIGAGAME', 'KXLIGUE1GAME', 'KXMLSGAME', 'KXLIGAMXGAME'])


def ticker_sport(ticker):
    t = (ticker or "").upper()
    return next((code for code, pre in SPORT_PREFIX if t.startswith(pre)), None)


def sport_teams(code):
    return {"nfl": NFL_TEAMS, "nba": NBA_TEAMS, "nhl": NHL_TEAMS}.get(code, {})     # college: Kalshi's names


SCORES_MAX_AGE = 45     # seconds; the Mac lowers this so live scores are near real time


def fetch_scores(max_age=None, code=None):
    """Live scores for one league (default: the one on screen), by team (ESPN's free scoreboard).
    Keeps the last good copy if ESPN can't be reached."""
    import time
    code = code or LEAGUE["code"]
    max_age = SCORES_MAX_AGE if max_age is None else max_age
    sp = SPORTS.get(code)
    got = SCORES_BY.get(code) or {"at": 0, "by": {}}
    if not sp or not sp.get("espn") or time.time() - got["at"] < max_age:
        return got["by"]
    by = {}
    try:
        events = []
        for path in (sp["espn"] if isinstance(sp["espn"], list) else [sp["espn"]]):
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
            q = dict(sp["q"])
            if sp["day"]:                        # teams play most nights: yesterday to 3 days out
                today = dt.date.today()
                q.update(dates=f"{today - dt.timedelta(days=1):%Y%m%d}-{today + dt.timedelta(days=3):%Y%m%d}",
                         limit=400)
            r = requests.get(url, params=q, timeout=8)
            evs = r.json().get("events", []) if r.ok else []
            if not evs and "dates" in q:
                r = requests.get(url, params=sp["q"], timeout=8)
                evs = r.json().get("events", []) if r.ok else []
            events += evs
        for ev in events:
            comp = (ev.get("competitions") or [{}])[0]
            st = comp.get("status") or ev.get("status") or {}
            typ = st.get("type") or {}
            state = typ.get("state", "")
            n_per = sp["periods"]
            if state == "post":
                detail = "Final" + (" OT" if (st.get("period") or 0) > n_per else "")
            elif state == "in":
                per = st.get("period") or 0
                label = ("OT" if per > n_per else {4: "Q", 3: "P"}.get(n_per, "H") + str(per))
                detail = ("Half" if "HALFTIME" in typ.get("name", "") else
                          f"{label} {st.get('displayClock', '')}".strip())
            else:
                detail = typ.get("shortDetail", "")
            sit = comp.get("situation") or {}
            prob = (sit.get("lastPlay") or {}).get("probability") or {}
            teams = comp.get("competitors") or []
            if len(teams) != 2:
                continue
            for me, opp in ((teams[0], teams[1]), (teams[1], teams[0])):
                tm = me.get("team") or {}
                name = tm.get("displayName")
                if not name:
                    continue
                info = {"me": int(float(me.get("score") or 0)), "opp": int(float(opp.get("score") or 0)),
                        "abbr": tm.get("abbreviation", ""),
                        "opp_abbr": (opp.get("team") or {}).get("abbreviation", ""),
                        "opp_name": (opp.get("team") or {}).get("displayName", ""),
                        "state": state, "detail": detail, "start": ev.get("date") or "",
                        "ball": str(sit.get("possession", "")) == str(me.get("id") or tm.get("id")),
                        "redzone": bool(sit.get("isRedZone")), "sport": code,
                        "game": ev.get("id"), "day": espn_day(ev.get("date")),
                        "wp": _wp(prob, me.get("homeAway")) if state == "in" else None}
                for alt in {name, norm_team(name), norm_team(tm.get("shortDisplayName") or ""),
                            norm_team(tm.get("location") or ""),
                            "@" + (tm.get("abbreviation") or "").upper()} - {"", "@"}:
                    by.setdefault(alt, []).append(info)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return got["by"]
    SCORES_BY[code] = {"at": time.time(), "by": by}
    if code == LEAGUE["code"]:
        SCORES.update(at=time.time(), by_team=by)
    return by


def _wp(prob, side):
    """ESPN's live win chance for one side (football has it on the scoreboard), or None."""
    try:
        v = prob.get(f"{side}WinPercentage")
        return min(0.995, max(0.005, float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None


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
    Only that exact game: a team's result from another night is never shown. Works for any
    sport the pick is in."""
    abbr = (l["ticker"] or "").rsplit("-", 1)[-1]
    code = ticker_sport(l["ticker"]) or LEAGUE["code"]
    name = (sport_teams(code).get(abbr) or PICK_NAME.get(l["ticker"] or "")
            or (MARKET_INFO.get(l["ticker"]) or {}).get("name") or "")
    by = (SCORES_BY.get(code) or {}).get("by") or (SCORES["by_team"] if code == LEAGUE["code"] else {})
    games = ((by.get(name) or by.get(norm_team(name)) or by.get(norm_team(" ".join(name.split()[-2:])))
              or by.get(norm_team(name.split()[-1]))) if name else None) or by.get("@" + abbr.upper())
    sc = pick_game(games, ticker_day(l["ticker"]))
    if not sc:
        return None
    if l.get("side", "yes") == "no":           # betting against this team
        sc = next((g for g in by.get(sc["opp_name"], []) if g["game"] == sc["game"]), sc)
    return sc


def legs_left_of(legs, inf, side_of):
    """Each unfinished pick as (chance now, playing now?, start timestamp), in the order the
    games are played. Chances are Kalshi's in-game prices for games under way."""
    out = []
    for l, (_, _, ch, r) in zip(legs, inf):
        if r:
            continue
        live = pick_state(l, side_of) == "live"
        t = leg_start(l, side_of)
        out.append((min(max(ch if ch is not None else 0.5, 0.001), 0.999), live,
                    0 if live else (t.timestamp() if t else 9e12)))
    return sorted(out, key=lambda x: x[2])


def leg_start(l, side_of):
    """When this pick's game starts (any sport), or None."""
    s = side_of.get(l["ticker"])
    if s:
        t = start_dt(s["event"])
        if t:
            return t
    sc = leg_score(l)
    try:
        if sc and sc.get("start"):
            return dt.datetime.fromisoformat(sc["start"].replace("Z", "+00:00"))
        exp = (MARKET_INFO.get(l["ticker"]) or {}).get("exp")
        if exp:
            hours = (SPORTS.get(ticker_sport(l["ticker"])) or {}).get("hours", 3)
            return dt.datetime.fromisoformat(exp.replace("Z", "+00:00")) - dt.timedelta(hours=hours)
    except ValueError:
        pass
    return None


def when_label(t):
    """'Live', 'Tonight 7:10 PM', 'Tue 4:00 PM', 'Nov 29' for a start time."""
    if not t:
        return ""
    t = t.astimezone()
    now = dt.datetime.now().astimezone()
    if t <= now:
        return "Live now"
    days = (t.date() - now.date()).days
    clock = t.strftime("%-I:%M %p").replace(":00 ", " ")
    if days == 0:
        return ("Tonight " if t.hour >= 17 else "Today ") + clock
    if days == 1:
        return "Tomorrow " + clock
    return t.strftime("%a ") + clock if days < 7 else t.strftime("%b %-d")


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
            out += [f"<div class='quote'>{action_button(t, f, live[t]) if k == 0 else action_button(t, f, live[t]).replace('btn go cashb', 'btn cashb')}</div>"
                    for k, (t, f) in enumerate(todo[:3])]
            ho = plan["hold"]
            out.append(f"<div class='muted' style='font-size:13px;margin-top:4px'>Locks in "
                       f"{money(plan['plan']['sure'])}. Holding everything instead: {ho['nothing']:.0%} chance "
                       f"of nothing more.</div>")
        else:
            out.append("<div style='margin-top:8px'><span class='verdict no'>Hold everything</span> "
                       "<span class='muted' style='font-size:13px'>Today's offers are worth less to you than holding.</span></div>")
    missing = [t for t in live if not fresh_offer(t)]
    if missing and can_trade():
        out.append(f"<div class='quote'><button class='btn quiet cashb' onclick=\"cash('askall','all')\">"
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


# "Let it ride" levels for auto-sell: how big a bankroll to act as if you had. The bigger,
# the more risk the planner carries before selling. None = only at the combo's full value.
RIDE = [("Cautious", 1), ("Steady", 2), ("Balanced", 4), ("Bold", 10), ("Ride it out", None)]


def ride_level():
    return RIDE[min(max(int(CFG.get("ride", 2)), 0), len(RIDE) - 1)]


DISCOUNT_FILE = os.path.join(HERE, "combo_discount.json")   # what Kalshi buyers really pay vs fair


def note_discount(offer, fair, live):
    """Remember how a real cash-out offer compared with the combo's fair value."""
    if not fair or fair <= 0 or not offer:
        return
    d = load_json(DISCOUNT_FILE, {"pre": [], "live": []})
    key = "live" if live else "pre"
    d.setdefault(key, []).append(round(min(max(offer / fair, 0.3), 1.2), 4))
    d[key] = d[key][-60:]
    save_json(DISCOUNT_FILE, d)


def kalshi_discount(live=False):
    """Typical offer as a share of fair value, learned from your own quotes (median of the last
    60). Before there are 5, a cautious guess: 88% between games, 82% during them."""
    d = load_json(DISCOUNT_FILE, {})
    xs = sorted(d.get("live" if live else "pre") or [])
    if len(xs) < 5:
        return 0.82 if live else 0.88
    return min(max(xs[len(xs) // 2], 0.5), 1.0)


def model_cushion(n_left):
    """Room for error in the chances: 2% per pick still to play, at most 15%."""
    return min(0.15, 0.02 * max(n_left, 0))


def wait_value(pays, legs, mult, locked=0.0):
    """What holding on is worth to you right now, if from here on you sell or hold at each step
    in the best way: after each game (in the order they're played) you can sell at Kalshi's usual
    discount to fair value, or keep going. Worked backward from the last game. legs: chances of
    the picks still to play, in game order. mult: your "Let it ride" bankroll multiple (None =
    full value only). Returns the price above which selling now beats waiting."""
    if not legs:
        return pays
    W = max(CFG["bankroll"], 1) * (mult or 1) + max(locked, 0)
    d = kalshi_discount(False)

    def ce(p, win):                               # certainty equivalent of "win with p, else 0"
        if mult is None:
            return p * win
        return math.exp(p * math.log(W + win) + (1 - p) * math.log(W)) - W

    v = pays                                      # every pick won: paid in full
    for j in range(len(legs) - 1, 0, -1):         # after the j-th game: sell or keep going
        wait = ce(legs[j], v)
        sell = d * math.prod(legs[j:]) * pays
        v = max(wait, sell)
    return ce(legs[0], v)                         # now: the value of waiting at least one game


def tp_ladder(cost, pays, ticker=None, p=None, guard=True):
    """Auto-sell prices for a combo: [(contracts, total price), ...] and a label.
    - Price: the point where selling beats waiting another game (wait_value), plus room for
      error in the chances. Never below halfway (on a multiplying scale) from what you paid to
      the payout; never above 97% of the payout.
    - Live-game guard: a pick whose game is under way is priced as if it wins, so with your phone
      closed nobody can buy cheaply off a game swinging your way.
    - Ladder: in thirds, from that price up toward the payout (one order if too small)."""
    name, mult = ride_level()
    floor = max(1.3 * cost, math.sqrt(max(cost, 0) * pays))
    cap = 0.97 * pays
    if cost <= 0 or floor > cap:
        return [], ""
    h = (MINE.get("hold") or {}).get(ticker) if ticker else None
    if h and h.get("legs_left") is not None and not h.get("rough"):
        legs = [(c, live) for c, live, _ in h["legs_left"]]
    elif p:
        legs = [(p, False)]
    else:
        legs = []
    if guard:
        legs = [(1.0 if live else c, live) for c, live in legs]
    chances = [c for c, _ in legs if c < 0.9999]
    base = wait_value(pays, chances, mult, MINE.get("locked", 0)) * (1 + model_cushion(len(chances)))
    t1 = min(max(base, floor), cap)
    if not CFG.get("tp_ladder", True) or pays < 3 or t1 >= cap * 0.98:
        return [(pays, t1)], f"({name} · {t1 / cost:.0f}× what you paid)"
    t3 = min(math.sqrt(t1 * cap), cap)
    t2 = math.sqrt(t1 * t3)
    n1 = math.floor(pays / 3 * 100) / 100
    n2 = n1
    n3 = round(pays - n1 - n2, 2)
    steps = [(n1, t1 * n1 / pays), (n2, t2 * n2 / pays), (n3, t3 * n3 / pays)]
    return steps, f"({name} · from {t1 / cost:.0f}× what you paid, in thirds)"


def tp_target(cost, pays, ticker=None, p=None):
    """The whole-combo price of the first auto-sell step, for showing. (amount, label)."""
    steps, label = tp_ladder(cost, pays, ticker, p)
    if not steps:
        return None, ""
    n, total = steps[0]
    return total * pays / n, label


def wait_threshold(ticker):
    """For cash-out advice: the offer (whole combo) that beats waiting another game, using the
    games as they stand right now (no live-game guard), with room for error."""
    h = MINE["hold"].get(ticker) or {}
    if not h.get("legs_left") or h.get("rough"):
        return 0.0
    _, mult = ride_level()
    chances = [c for c, _, _ in h["legs_left"]]
    return wait_value(h["pays"], chances, mult, MINE.get("locked", 0)) * (1 + model_cushion(len(chances)))


def worth_now(ticker):
    """What a live combo is worth right now: the better of its average value and a fresh offer."""
    h = MINE["hold"].get(ticker) or {}
    o = fresh_offer(ticker) if ticker in MINE["hold"] else None
    return max(h.get("hold", 0.0), (o or {}).get("offer", 0.0) / max((o or {}).get("frac", 1.0), 0.01))


def post_sell(ticker, n, per):
    """One resting sell order: n contracts at `per` dollars each. Returns None or an error."""
    import uuid
    tries = [{"count_fp": f"{n:.2f}", "yes_price_dollars": f"{min(max(per, 0.0001), 0.9999):.4f}"},
             {"count": int(n), "yes_price_dollars": f"{min(max(math.ceil(per * 100) / 100, 0.01), 0.99):.2f}"}]
    last = ""
    for extra in tries:
        if extra.get("count") == 0:
            continue
        body = dict({"ticker": ticker, "action": "sell", "side": "yes", "type": "limit",
                     "time_in_force": "good_till_canceled", "reduce_only": True,
                     "client_order_id": str(uuid.uuid4())}, **extra)
        try:
            kalshi_send("POST", "/portfolio/orders", body)
            return None
        except PermissionError:
            return "Kalshi refused. Your API key needs write (trading) access for auto-sell orders."
        except (RuntimeError, requests.RequestException) as err:
            last = str(err)[:120]
    return f"Kalshi didn't accept the auto-sell order ({last}). It may not allow resting orders on this combo."


def place_take_profit(ticker, contracts, cost, p=None, steps=None):
    """Put standing sell orders on Kalshi (a ladder in thirds, or one) at the wait-one-more-game
    price. Kalshi keeps them working with your phone closed; each fills only if a buyer pays it."""
    n = math.floor(contracts * 100 + 1e-6) / 100
    if n < 1:
        return "Auto-sell needs at least 1 contract."
    why = ""
    if steps is None:
        steps, why = tp_ladder(cost, n, ticker, p)
    if not steps:
        return ("No auto-sell for this one: it's already worth close to what it pays, or it doesn't pay "
                "enough above what you paid. Hold it, or cash out when you like the offer.")
    done = []
    for k, total in steps:
        if k < 0.01:
            continue
        err = post_sell(ticker, k, total / k)
        if err:
            return err if not done else f"Placed {len(done)} of {len(steps)} auto-sell orders. {err}"
        done.append(total * n / k)                 # as a whole-combo price, to compare with offers
    prices = " / ".join(money(x) for x in done)
    return (f"🎯 Auto-sell placed: {'a third each at ' if len(done) > 1 else 'sells at '}{prices} "
            f"(whole-combo prices) {why}. It stays on Kalshi with your phone closed.")


def order_steps(orders):
    """Your resting sell orders on one combo as sorted [(contracts left, price each), ...]."""
    out = []
    for o in orders:
        k = count_of({"count_fp": o.get("remaining_count_fp") or o.get("remaining_count")})
        out.append((k, dollars(o, "yes_price")))
    return sorted(out, key=lambda x: x[1])


def retarget_one(t, orders, cost_full, pays_full, p=None):
    """Move one combo's auto-sell ladder to its current price as games are won, lost or under way.
    At most once a minute per combo, and only for a 5%+ change. Returns (old, new) if moved."""
    import time
    moved_at = MINE.setdefault("tp_moved", {})
    if not orders or time.time() - moved_at.get(t, 0) < 60:
        return None
    cur = order_steps(orders)
    left = round(sum(k for k, _ in cur), 2) or pays_full
    cost = cost_full * left / max(pays_full, 1e-9)
    steps, _ = tp_ladder(cost, left, t, p)
    if not steps:
        return None
    new_first = steps[0][1] / steps[0][0]
    old_first = cur[0][1] if cur else 0
    if old_first and abs(new_first - old_first) / old_first < 0.05 and len(cur) == len(steps):
        return None
    moved_at[t] = time.time()
    cancel_take_profit(t)
    place_take_profit(t, left, cost, steps=steps)
    return old_first * left, new_first * left


def retarget_take_profits():
    """Live page: move this league's auto-sells using the full live simulation."""
    moved = []
    for t, orders in (MINE.get("tp") or {}).items():
        h = MINE["hold"].get(t)
        if h:
            r = retarget_one(t, orders, h["cost"], h["pays"])
            if r:
                moved.append((h["label"], *r))
    return moved


def combo_chance_now(a):
    """A combo's chance of hitting right now from each pick's own current Kalshi price
    (in-game prices for games under way, results for finished ones). 0 if a pick lost."""
    res = fetch_results({l["ticker"] for l in a["legs"] if l["ticker"]})
    p = 1.0
    for l in a["legs"]:
        r = res.get(l["ticker"])
        if l.get("side", "yes") == "no":
            r = {"yes": "no", "no": "yes"}.get(r)
        if r == "yes":
            continue
        if r == "no":
            return 0.0
        lp = (MARKET_INFO.get(l["ticker"]) or {}).get("live")
        if lp is None:
            return None
        p *= (1 - lp) if l.get("side", "yes") == "no" else lp
    return p


# Kalshi doesn't take standing sell orders on combos (they trade only through cash-out offers), so
# auto-sell stays off. The code is kept in case Kalshi adds them.
AUTOSELL = False
TP_OFF = os.path.join(HERE, "combo_autosell_off.json")   # combos you cancelled auto-sell on


def autosell_pass():
    """One pass over every league's live combos: put an auto-sell on any without one (if you
    turned that on) and move existing ones to the current "Let it ride" price. The league on
    screen uses the Live page's full simulation; the others use each pick's current price."""
    if not AUTOSELL or not can_trade() or MINE.get("busy") or not (CFG.get("tp_auto") or CFG.get("tp_follow", True)):
        return []
    acct, _, _ = fetch_account(every_league=True)
    resting = resting_sells()
    done = []
    for a in acct or []:
        t = a["ticker"]
        if a["status"] != "pending" or MINE.get("busy") or t in MINE.get("selling", set()):
            continue
        here = t in (MINE.get("hold") or {}) and MINE.get("patterns")
        p = None if here else combo_chance_now(a)
        if not here and not p:
            continue                       # chance unknown, or a pick already lost
        if resting.get(t):
            if CFG.get("tp_follow", True) and retarget_one(t, resting[t], a["cost"], a["pays"], p):
                done.append(t)
        elif CFG.get("tp_auto") and a["pays"] >= 1 and t not in load_json(TP_OFF, {}):
            msg = place_take_profit(t, a["pays"], a["cost"], p=p)
            if msg.startswith("🎯"):
                done.append(t)
    return done


# ---- the Raspberry Pi watcher (see watcher/combo_watcher.py) ----
NTFY = "https://ntfy.sh"
WATCHER_SYNCED = ("bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap",
                  "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news")
PI_APPROVE = os.path.join(HERE, "combo_pi_approve.json")   # the exact files the Pi may update to
WATCH = {"at": 0, "hb": None}


def watcher_conf():
    """{'topic', 'secret'} from the pairing code the Pi's installer printed, or None."""
    import base64
    code = (CFG.get("watcher_code") or "").strip()
    if not code:
        return None
    try:
        c = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode())
        return c if c.get("topic") and c.get("secret") else None
    except (ValueError, TypeError):
        return None


# ================================================================ Mac hub (stage 1)
# When the pairing code includes a Mac hub address, the phone gets its data from the Mac (which keeps
# it fresh all the time) and sends trades there to be placed with the Mac's key. Every request and
# reply is compressed, encrypted and signed with the pairing secret. If the Mac can't be reached, the
# phone checks Kalshi itself and trades with its own backup key, after you confirm.
import threading as _threading
_requests = requests
HUB = {"up": None, "at": 0.0, "info": {}, "ms": None, "why": "", "armed": 0.0}
HUB_PORT = 8765
HUB_RECHECK_UP, HUB_RECHECK_DOWN = 30, 45
HUB_GET_HOSTS = (KALSHI + "/", "https://site.api.espn.com/")
AUTO = _threading.local()          # set while an automatic cash-out/hedge runs (no confirm prompt)


def hub_conf():
    c = watcher_conf()
    return c if c and c.get("hub") else None


def _hub_stream(secret, nonce, n):
    import hashlib
    key = hashlib.sha256((secret + "|hub").encode()).digest()
    return b"".join(hashlib.sha256(key + nonce + i.to_bytes(4, "big")).digest()
                    for i in range(n // 32 + 1))[:n]


def hub_seal(secret, obj):
    """Compress, encrypt and sign one message (bytes)."""
    import zlib, hmac, hashlib
    raw = zlib.compress(json.dumps(obj, separators=(",", ":")).encode(), 6)
    nonce = os.urandom(16)
    ct = (int.from_bytes(raw, "big") ^ int.from_bytes(_hub_stream(secret, nonce, len(raw)), "big")).to_bytes(len(raw), "big")
    return nonce + hmac.new(secret.encode(), b"hub" + nonce + ct, hashlib.sha256).digest() + ct


def hub_unseal(secret, data):
    import zlib, hmac, hashlib
    try:
        nonce, mac, ct = data[:16], data[16:48], data[48:]
        if len(nonce) < 16 or not ct or not hmac.compare_digest(
                mac, hmac.new(secret.encode(), b"hub" + nonce + ct, hashlib.sha256).digest()):
            return None
        raw = (int.from_bytes(ct, "big") ^ int.from_bytes(_hub_stream(secret, nonce, len(ct)), "big")).to_bytes(len(ct), "big")
        return json.loads(zlib.decompress(raw))
    except (ValueError, TypeError, zlib.error):
        return None


def hub_call(op, timeout=10, **kw):
    """Ask the Mac. Returns its reply (a dict) or None if it couldn't be reached."""
    import time
    c = hub_conf()
    if not c:
        return None
    n = os.urandom(8).hex()
    t0 = time.time()
    try:
        r = _requests.post(c["hub"].rstrip("/") + "/v1", data=hub_seal(c["secret"], dict(kw, op=op, ts=t0, n=n)),
                           timeout=timeout, headers={"Content-Type": "application/octet-stream"})
    except _requests.RequestException as err:
        hub_mark(False, "no answer" if "timed out" in str(err).lower() else "can't connect")
        return None
    out = hub_unseal(c["secret"], r.content) if r.status_code == 200 else None
    if not out or out.get("re") != n:
        hub_mark(False, f"the Mac refused the request ({r.status_code})" if r.status_code != 200
                 else "the reply didn't check out (pairing code changed?)")
        return None
    hub_mark(True, ms=(time.time() - t0) * 1000)
    return out


def hub_mark(up, why="", ms=None):
    import time
    HUB.update(up=up, at=time.time(), why=why)
    if ms is not None:
        HUB["ms"] = ms


def hub_up():
    """True if the Mac hub is configured and answering (checked at most every 30-45 s)."""
    import time
    if not hub_conf():
        return False
    wait = HUB_RECHECK_UP if HUB["up"] else HUB_RECHECK_DOWN
    if HUB["up"] is None or time.time() - HUB["at"] > wait:
        got = hub_call("ping", timeout=3)
        if got:
            HUB["info"] = got
    return bool(HUB["up"])


class _HubResp:
    """Enough of a requests.Response for the planner's public GETs."""
    def __init__(self, got, url):
        self.status_code, self.url = int(got.get("status", 0)), url
        self.text = got.get("text") or ""
        self.content, self.headers = self.text.encode(), {}
        self.ok = 200 <= self.status_code < 400

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            raise _requests.HTTPError(f"{self.status_code} from {self.url} (via your Mac)")


class _HubRequests:
    """The planner's `requests`: public Kalshi and ESPN reads come from the Mac when it's up."""
    def __init__(self, real):
        self._r = real

    def __getattr__(self, k):
        return getattr(self._r, k)

    def get(self, url, params=None, **kw):
        if not kw.get("headers") and str(url).startswith(HUB_GET_HOSTS) and hub_up():
            got = hub_call("get", timeout=max(10, kw.get("timeout") or 0), url=url, params=params or {})
            if got and "status" in got:
                return _HubResp(got, url)
        return self._r.get(url, params=params, **kw)


requests = _HubRequests(_requests)


def hub_kalshi(method, path, body=None, params=None):
    """Have the Mac sign and send one Kalshi request with its key."""
    got = hub_call("kalshi", timeout=40, method=method, path=path, body=body, params=params or {})
    if got is None:
        if method == "GET":
            raise _requests.ConnectionError("Your Mac stopped answering.")
        raise RuntimeError("Lost contact with your Mac during this trade, so it may or may not have gone "
                           "through. Check Kalshi before trying again.")
    if got.get("err") == "perm":
        raise PermissionError(got.get("msg") or "Kalshi refused the Mac's key.")
    if got.get("err"):
        raise RuntimeError(got.get("msg") or "The Mac couldn't place that.")
    return got.get("json")


def confirm_backup_trade(method, path):
    """The Mac is paired but unreachable: trades from a tap need a second tap to use the phone's key."""
    import time
    if method == "GET" or getattr(AUTO, "on", False) or not hub_conf():
        return
    if time.time() - HUB["armed"] < 120:
        return
    HUB["armed"] = time.time()
    raise RuntimeError(f"Your Mac isn't answering ({HUB['why'] or 'no connection'}). Tap again within "
                       "2 minutes to place this with your phone's backup key.")


def hub_line():
    """One line for Live/Settings about the Mac hub, or ''."""
    if not hub_conf():
        return ""
    if hub_up():
        ms = f" · {HUB['ms']:.0f} ms" if HUB.get("ms") else ""
        return (f"<div class='wline'>💻 Mac hub connected{ms}. Live data and trades go through your Mac.</div>")
    return (f"<div class='wline bad'>💻 Can't reach your Mac ({html.escape(HUB['why'] or 'no connection')}). "
            "The phone is checking Kalshi itself; trades use its backup key and ask first. "
            "Is Tailscale on?</div>")


def watcher_status(max_age=60):
    """The Pi's latest heartbeat (it sends one every minute), or None."""
    import time
    c = watcher_conf()
    if not c:
        return None
    if time.time() - WATCH["at"] < max_age:
        return WATCH["hb"]
    WATCH["at"] = time.time()
    try:
        r = requests.get(f"{NTFY}/{c['topic']}-hb/json", params={"poll": "1", "since": "10m"}, timeout=6)
        msgs = [json.loads(x) for x in r.text.splitlines() if x.strip()] if r.ok else []
        WATCH["hb"] = json.loads(msgs[-1]["message"]) if msgs else None
    except (requests.RequestException, ValueError, KeyError):
        pass
    return WATCH["hb"]


def watcher_alive():
    """True while the Pi has checked in within the last 3 minutes: it then sends the alerts and
    does auto cash-out, and the phone stays out of its way."""
    import time
    hb = watcher_status()
    return bool(hb and time.time() - hb.get("at", 0) < 180 and not hb.get("err"))


def send_watcher_settings():
    """Send your Let it ride / Auto cash-out settings (and Kalshi's learned discount) to the Pi,
    signed so only your phone can change them. The Pi is listening, so it takes effect within
    seconds. Never sends keys."""
    import hmac, hashlib, time
    c = watcher_conf()
    if not c:
        return False
    body = json.dumps({"at": int(time.time()), "cfg": {k: CFG.get(k) for k in WATCHER_SYNCED},
                       "discount": load_json(DISCOUNT_FILE, {}), "approve": load_json(PI_APPROVE, {})},
                      separators=(",", ":"))
    sig = hmac.new(c["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
    try:
        requests.post(f"{NTFY}/{c['topic']}-cfg", data=json.dumps({"body": body, "sig": sig}).encode(),
                      timeout=8, headers={"Cache": "yes"})
        return True
    except requests.RequestException:
        return False


def approve_pi_update(version, engine_bytes):
    """After this phone updates: tell the Pi it may install exactly this version (the engine and
    watcher files, by their SHA-256), signed like any setting. The Pi installs nothing else."""
    import hashlib
    try:
        w = requests.get(UPDATE_URL + "/watcher/combo_watcher.py", params={"t": int(time.time())}, timeout=20)
        w_sha = hashlib.sha256(w.content).hexdigest() if w.ok else ""
    except requests.RequestException:
        w_sha = ""
    save_json(PI_APPROVE, {"version": version, "engine": hashlib.sha256(engine_bytes).hexdigest(), "watcher": w_sha})
    if watcher_conf():
        send_watcher_settings()


def watcher_line():
    """One line for Live: is the Pi watching?"""
    import time
    if not watcher_conf():
        return ""
    if hub_conf():
        return hub_line() + _watcher_line()
    return _watcher_line()


def _watcher_line():
    import time
    hb = watcher_status()
    if hb and time.time() - hb.get("at", 0) < 180 and hb.get("err"):
        return ("<div class='wline bad'>🖥 Pi watcher is running but its checks are failing: "
                f"{html.escape(hb['err'])}. Your phone is handling alerts and cash-outs while it's open.</div>")
    if hb and time.time() - hb.get("at", 0) < 180:
        t = dt.datetime.fromtimestamp(hb["at"]).strftime("%-I:%M %p")
        extra = (" · ⏸ auto cash-out paused (save Settings with it on to resume)" if hb.get("paused") else "") + \
                (f" · waiting for you to update this phone to {hb['waiting']}" if hb.get("waiting") else "")
        who = hb.get("host") or "Pi"              # older watchers don't say; only the Pi existed then
        return f"<div class='wline'>{'💻' if who == 'Mac' else '🖥'} {who} watcher on · checked {t}{extra}</div>"
    last = ""
    if hb and hb.get("at"):
        t = dt.datetime.fromtimestamp(hb["at"])
        last = (f" Last heard from {t.strftime('%-I:%M %p')}" + ("" if t.date() == dt.date.today() else t.strftime(" %a"))
                + f" on version {hb.get('engine', '?')}.")
    return ("<div class='wline bad'>🖥 Pi watcher hasn't checked in for 3+ minutes." + last +
            " Your phone is handling alerts while it's open.</div>")


def start_autosell_keeper():
    """Runs every minute while the planner is open, whatever league or screen you're on.
    Stops when you close the planner or an update takes over."""
    import threading, time
    if APP.get("keeper"):
        return

    def loop():
        while not APP.get("superseded") and not APP.get("closed"):
            try:
                if not (in_pythonista() and watcher_alive()):
                    autosell_pass()
            except Exception as err:
                console_note(f"Auto-sell check skipped: {type(err).__name__}: {err}")
            for _ in range(60):
                if APP.get("superseded") or APP.get("closed"):
                    break
                time.sleep(1)
        APP["keeper"] = None

    APP["keeper"] = threading.Thread(target=loop, daemon=True)
    APP["keeper"].start()


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
    if o and o.get("rfq") and o["rfq"] != "estimate":
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
    try:
        note_discount(price, h["p"], any(live for _, live, _ in h.get("legs_left") or []))
    except Exception:
        pass
    return {"rfq": rfq, "quote": q["id"], "price": price, "contracts": n, "offer": round(n * price, 2),
            "frac": frac, "at": time.time()}


CASH_RETRIES = 3          # if the buyer backs out, try this many fresh offers
CASH_SLIP = 0.97          # ...accepting one automatically only if it's at least 97% of what you confirmed


def accept_cash(ticker):
    """Sell: hit their YES bid with the contracts you hold. Only runs after you tap Cash out.
    If the buyer backs out, gets a fresh offer and takes it if it's within 3% of the price you
    confirmed, up to 3 more tries; otherwise shows you the new offer to confirm."""
    import time
    o = MINE["cash"].pop(ticker, None)
    h = MINE["hold"].get(ticker) or {}
    label = h.get("label", "That combo")
    frac = (o or {}).get("frac", 1.0)
    if frac < 1:
        label = "Half of " + label
    if not o or not o.get("rfq") or time.time() - o["at"] > offer_life():
        return f"{label}: that offer expired. Tap Get cash-out offer for a fresh one."
    agreed = o["offer"]
    MINE.setdefault("selling", set()).add(ticker)   # the auto-sell keeper keeps its hands off
    try:
        return _accept_with_retries(ticker, o, h, label, frac, agreed)
    finally:
        MINE["selling"].discard(ticker)


def _accept_with_retries(ticker, o, h, label, frac, agreed):
    had_tp = bool((MINE.get("tp") or {}).get(ticker)) or bool(resting_sells().get(ticker))
    if had_tp:
        cancel_take_profit(ticker)          # can't sell the same contracts twice
    why = ""
    for attempt in range(CASH_RETRIES + 1):
        if attempt:
            loading(f"The buyer backed out. Getting a fresh offer (try {attempt} of {CASH_RETRIES})…")
            o = get_cash_offer(ticker, frac)
            if not o.get("offer"):
                why = "no fresh offer came in"
                break
            if o["offer"] < CASH_SLIP * agreed:
                MINE["cash"][ticker] = o
                why = "new"
                break
        status = accept_once(o)
        if status == "executed":
            ACCT_CACHE["at"] = 0
            haptic("success")
            extra = f" (after {attempt} retr{'y' if attempt == 1 else 'ies'})" if attempt else ""
            return f"✅ {label} cashed out for about {money(o['offer'])}{extra}."
        if status not in ("cancelled", "failed"):
            ACCT_CACHE["at"] = 0
            return (f"{label}: still waiting on Kalshi. Check this page again in a minute before trying again, "
                    "so you don't sell twice.")
        why = why or "backed out"
    ACCT_CACHE["at"] = 0
    if had_tp and h:                        # nothing sold: put the auto-sell back
        place_take_profit(ticker, h.get("pays", 0), h.get("cost", 0))
    if why == "new":
        return (f"{label}: the buyer backed out, and the best fresh offer is {money(MINE['cash'][ticker]['offer'])} "
                f"(below the {money(agreed)} you agreed to), so nothing was sold. Tap Cash out to take it.")
    return (f"{label}: buyers backed out {CASH_RETRIES + 1} times, so nothing was sold. "
            "Try again in a minute." + (" Your auto-sell order is back on." if had_tp else ""))


def accept_once(o):
    """Accept one quote. Returns 'executed', 'cancelled', 'failed' or 'waiting'."""
    import time
    try:
        kalshi_send("PUT", f"/communications/rfqs/{o['rfq']}/quotes/{o['quote']}/accept",
                    {"accepted_side": "yes"})
    except (RuntimeError, PermissionError, requests.RequestException):
        return "failed"
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
    return status if status in ("executed", "cancelled") else "waiting"


def cash_action(action, ticker):
    """Buttons on a combo card: ask for an offer, cash out, or keep it."""
    MINE["busy"] = True                     # the 2-minute refresh waits until this is done
    APP["quiet"] = True                      # update the page in place, no loading screen
    confirm_after = None
    try:
        if action == "hedgego":
            loading("Placing the hedge on Kalshi…")
            MINE["flash"] = place_hedge(ticker)
        elif action == "tp" and not AUTOSELL:
            MINE["flash"] = "Auto-sell isn't available: Kalshi only buys combos back through cash-out offers."
        elif action == "tp":
            loading("Placing your auto-sell order on Kalshi…")
            off = load_json(TP_OFF, {})
            if off.pop(ticker, None):
                save_json(TP_OFF, off)
            h = MINE["hold"].get(ticker) or {}
            MINE["flash"] = place_take_profit(ticker, h.get("pays", 0), h.get("cost", 0))
        elif action == "tpx":
            loading("Cancelling the auto-sell order…")
            n = cancel_take_profit(ticker)
            off = load_json(TP_OFF, {})
            off[ticker] = True                  # the auto-sell-everything switch leaves this one alone
            save_json(TP_OFF, off)
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
    if not (CFG["auto_cash"] or CFG.get("auto_sell")) or not can_trade():
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
    return MINE.pop("pre_alerts", [])


def cash_alerts(plan):
    """A push only when cashing out makes real sense, worded like the Right now box (same plan,
    so the alert and the buttons always agree). It needs all of:
      - the plan recommends cashing something out, judged after the latest refresh;
      - each combo in it has a pick already won (before that, you hold: it was bought for the upside);
      - it's worth at least $2, or 3% of what it locks in, more to you than holding;
      - it's new: same advice again only if the offer rose 20%+ or half became all, and never
        within 10 minutes of the last alert for that combo."""
    import time
    if not plan or not CFG["auto_cash"]:
        return []
    gain = plan["plan"]["worth"] - plan["hold"]["worth"]
    if gain < max(2.0, 0.03 * plan["plan"]["sure"]):
        return []
    told = MINE.setdefault("alerted", {})
    news = []
    for t, f in sorted(plan["acts"].items(), key=lambda x: -x[1]):
        o, h = fresh_offer(t), MINE["hold"].get(t)
        if not (f and o and h):
            continue
        amt = acts_price(t) * h["pays"] * f
        last = told.get(t)
        if last and (time.time() - last["at"] < 600 or (amt < last["amt"] * 1.2 and f <= last["f"])):
            continue
        told[t] = {"f": f, "amt": amt, "at": time.time()}
        news.append(f"{'half of ' if f < 1 else ''}{h['label']} ({money(amt)})")
    if not news:
        return []
    slipping = any(live and c < 0.5 for t2, f2 in plan["acts"].items() if f2
                   for c, live, _ in (MINE["hold"].get(t2) or {}).get("legs_left", []))
    head = "📉 A game is turning against you. Cash out" if slipping else "💰 Cash out"
    return [f"{head} {', '.join(news)}? Locks in {money(plan['plan']['sure'])}. Holding everything: "
            f"{plan['hold']['nothing']:.0%} chance of nothing more. Open the planner to confirm."]


LIVE_VIEW_JS = r"""
window.__game=window.__game||'';
function buzz(){try{location.href='combo://haptic/tap';}catch(e){}}
if(!window.__hz){window.__hz=1;document.addEventListener('click',function(ev){
 if(ev.target.closest('details.crow>summary,.quietbox>summary,details.lostbox>summary'))buzz();},true);}
function pickGame(g){buzz();window.__game=(window.__game===g?'':g);applyGame();
 if(window.__game){var el=document.getElementById('ghead');if(el)el.scrollIntoView({behavior:'smooth',block:'start'});}}
function applyGame(){var g=window.__game;
 if(g&&!document.getElementById('g-'+g))g=window.__game='';
 document.querySelectorAll('.gchip').forEach(function(c){c.classList.toggle('sel',c.dataset.g===g);});
 var head=document.getElementById('ghead');if(head){head.classList.toggle('on',!!g);
  var c=g&&document.getElementById('g-'+g);document.getElementById('gname').textContent=c?('Riding on '+[].map.call(c.querySelectorAll('.gr>span:first-child'),function(x){return x.childNodes[0].textContent.trim();}).filter(Boolean).join(' vs ')):'';}
 document.querySelectorAll('details.crow[data-games]').forEach(function(r){var hit=!g||r.dataset.games.split(' ').indexOf(g)>=0;
  var box=r.closest('.nitem')||r;box.classList.toggle('hidegame',!hit);});
 var q=document.getElementById('quietbox');if(q){if(g){if(!q.dataset.was)q.dataset.was=q.open?'1':'0';q.open=true;}
  else if(q.dataset.was){q.open=q.dataset.was==='1';delete q.dataset.was;}
  var qb=q.querySelector('summary b'),qs=q.querySelector('summary .muted');
  if(qb){if(qb.dataset.orig===undefined){qb.dataset.orig=qb.textContent;qs.dataset.orig=qs.textContent;}
   if(g){var n=[].filter.call(q.querySelectorAll('details.crow'),function(r){return !r.classList.contains('hidegame');}).length;
    qb.textContent=n+' combo'+(n===1?'':'s')+' on this game';qs.textContent='Nothing to do';}
   else{qb.textContent=qb.dataset.orig;qs.textContent=qs.dataset.orig;}}}
 if(g){var sel=document.getElementById('g-'+g);if(sel&&sel.scrollIntoView)sel.scrollIntoView({behavior:'smooth',inline:'center',block:'nearest'});}
 ['needs','quiet','won'].forEach(function(id){var l=document.getElementById(id);if(!l)return;
  var any=[].some.call(l.querySelectorAll('details.crow'),function(r){return !(r.closest('.nitem')||r).classList.contains('hidegame');});
  var h=document.getElementById('h-'+id)||(id==='quiet'?q:null);if(h)h.classList.toggle('hidegame',!!g&&!any);
  l.classList.toggle('hidegame',!!g&&!any);});
 var don=document.getElementById('donebox');if(don)don.classList.toggle('hidegame',!!g);}
window.__after=applyGame;applyGame();
"""


def mine_page(live=False):
    """Build the My Kalshi combos page. Returns (page, snapshot for alerts)."""
    all_games, sunday = MINE["all_games"], MINE["sunday"]
    e = html.escape
    if not live:
        loading("Reading your Kalshi account…")
    acct, balance, note = fetch_account(every_league=True)      # Live shows every sport
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

    # every sport: everything still live, plus combos that finished in the last two days
    recent = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    mine = [a for a in acct if a["status"] == "pending" or (a.get("week") or "") >= recent]
    if not live:
        loading("Checking game results…")
    results = fetch_results({l["ticker"] for a in mine for l in a["legs"] if l["ticker"]}
                            | {a["ticker"] for a in mine if not a.get("winners", True) and a["status"] == "pending"})
    rough = {a["ticker"]: (MARKET_INFO.get(a["ticker"]) or {}).get("live")
             for a in mine if not a.get("winners", True)}   # same-game stat combos: Kalshi's price
    if not live:
        loading("Working out your chances…")

    for code in {ticker_sport(l["ticker"]) for a in mine for l in a["legs"]} | {LEAGUE["code"]}:
        if code:
            fetch_scores(code=code)

    def final_result(l):
        """'yes'/'no' for the bettor once ESPN shows the game final, before Kalshi settles it
        (that can take an hour). Game-winner picks only; a tie decides nothing here."""
        if not (l["ticker"] or "").startswith(WINNER_SERIES):
            return None
        sc = leg_score(l)                       # already from the side the pick needs
        if not sc or sc.get("state") != "post" or sc["me"] == sc["opp"]:
            return None
        return "yes" if sc["me"] > sc["opp"] else "no"

    def leg_info(l):
        """(name, opponent, chance, result) for one pick, from the bettor's side."""
        s = side_of.get(l["ticker"])
        res = results.get(l["ticker"])
        abbr = (l["ticker"] or "").rsplit("-", 1)[-1]
        if res is None and final_result(l):
            res = final_result(l)
            if l.get("side", "yes") == "no":        # undo the flip below: the score is already our side's
                res = {"yes": "no", "no": "yes"}[res]
        if l.get("side", "yes") == "no":            # betting a team NOT to win
            res = {"yes": "no", "no": "yes"}.get(res)
            if s and any(x.get("tie") for x in all_games[s["event"]]):   # 3-way: "not X" = other team or a draw
                return f"{s['pick']} doesn't win", "", 1 - s["fair"], res
            if s:
                other = other_side(all_games[s["event"]], s)
                return other["pick"], s["pick"], other["fair"], res
            return f"Against {TEAMS.get(abbr, abbr)}", "", None, res
        if s:
            other = other_side(all_games[s["event"]], s)
            return s["pick"], other["pick"], s["fair"], res
        info = MARKET_INFO.get(l["ticker"]) or {}
        lp = info.get("live")
        if not (l["ticker"] or "").startswith(WINNER_SERIES):
            nm = info.get("name") or l["ticker"]
            if l.get("side", "yes") == "no":
                nm = "Not: " + nm
                lp = 1 - lp if lp is not None else None
            return nm, "", lp, res
        nm = sport_teams(ticker_sport(l["ticker"])).get(abbr) or info.get("name") or abbr
        return nm, "", lp, res

    rng = random.Random(1)
    cards, hits_any = [], 0
    infos = [[leg_info(l) for l in a["legs"]] for a in mine]
    for a in mine:
        a["_hits"] = 0                          # the account list is cached, so start fresh each time
    from collections import Counter
    patterns = Counter()
    trials = 8000 if live else 20000
    for _ in range(trials):                     # play the rest of the weekend out
        won = {ev: draw_result(s, rng.random())["ticker"] for ev, s in all_games.items()}
        drawn = {}                                # other sports' picks: one result per pick per run
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
                    if not s:                     # same pick in several combos wins or loses for all
                        yes_p = ch if l.get("side", "yes") == "yes" else 1 - (ch if ch is not None else 0.5)
                        if l["ticker"] not in drawn:
                            drawn[l["ticker"]] = rng.random() < (yes_p if ch is not None else 0.5)
                        ok = drawn[l["ticker"]] if l.get("side", "yes") == "yes" else not drawn[l["ticker"]]
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
                other = other_side(all_games[s0["event"]], s0) if s0 else None
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
                                         "worth": left <= 3 and p * a["pays"] >= 2 * a["cost"],
                                         "legs_left": legs_left_of(a["legs"], inf, side_of)}
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
            value = ""
        rows = []
        legs_sorted = sorted(zip(a["legs"], inf), key=lambda x: (start_key(x[0].get("event") or ""),
                                                                 order.get((side_of.get(x[0]["ticker"]) or {}).get("event"), 99)))
        for n, (l, (name, opp, ch, res)) in enumerate(legs_sorted, 1):
            tag = ""
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
            mk = ("<span class='n w'>✓</span>" if res == "yes" else "<span class='n l'>✕</span>" if res == "no" else
                  "<span class='n live'></span>" if pick_state(l, side_of) == "live" else "<span class='n o'></span>")
            rows.append(f"<li>{mk}<span class='who'><b>{e(name)}</b> {tag}"
                        f"<small>{sub}</small></span><span class='pct'>{pct}</span></li>")
        group = snap.get(a["ticker"], {}).get("status", "pending")
        if group == "pending":
            value = f"@@CASH:{a['ticker']}@@"
        pay_line = (f"<div class='pay'>{money(a['back'])}</div><div class='meta'>cashed out · cost {money(a['cost'])}</div>"
                    if group == "cashed" else
                    f"<div class='pay'>{money(a['pays'])}</div><div class='meta'>pays if it hits · cost {money(a['cost'])}</div>")
        sports = sorted({ticker_sport(l["ticker"]) or "other" for l in a["legs"]},
                        key=lambda c: -sum(1 for l in a["legs"] if (ticker_sport(l["ticker"]) or "other") == c))
        sp = sports[0]
        chip = "".join(f"<span class='sport'>{SPORTS[c]['icon']} {SPORTS[c]['name']}</span>"
                       for c in sports if c in SPORTS) or "<span class='sport'>🎯 Other</span>"
        upcoming = [x for x in (leg_start(l, side_of) for l, (_, _, _, r) in legs_sorted if not r) if x]
        nxt = min(upcoming) if upcoming else None
        any_live = any(pick_state(l, side_of) == "live" for l, (_, _, _, r) in legs_sorted if not r)
        when = ("Live now" if any_live else when_label(nxt)) if group == "pending" else ""
        dots = "".join({"yes": "<i class='d w'></i>", "no": "<i class='d l'></i>"}.get(r, "<i class='d o'></i>")
                       for _, (_, _, _, r) in legs_sorted)
        sort_t = 0 if any_live else (nxt.timestamp() if nxt else 9e12)
        marks = {"yes": "✓", "no": "✗"}
        need_names = [nm for _, (nm, _, _, r) in legs_sorted if not r]
        lost_names = [nm for _, (nm, _, _, r) in legs_sorted if r == "no"]
        if lost_names:
            preview = "Lost on " + ", ".join(lost_names[:2])
        elif not need_names:
            preview = "Every pick won"
        else:
            preview = ("Needs " if len(need_names) < len(legs_sorted) else "") + " · ".join(need_names[:3]) + (
                f" · +{len(need_names) - 3}" if len(need_names) > 3 else "")
        # what the row says: the live score if a game is on, else what it still needs and when
        live_sc = next((leg_score(l) for l, (_, _, _, r) in legs_sorted if not r and pick_state(l, side_of) == "live"
                        and leg_score(l)), None)
        if group == "pending" and live_sc:
            context = (f"<span class='lv'>{e(live_sc['abbr'])} {live_sc['me']}–{live_sc['opp']} "
                       f"{e(live_sc['opp_abbr'])} · {e(live_sc['detail'])}</span>")
        elif group == "pending":
            context = e(preview) + (f" · {e(when)}" if when and when != "Live now" else "")
        else:
            context = e(preview)
        # the two numbers: what you'd make cashing out now, and the chance it hits
        if group == "pending":
            o = fresh_offer(a["ticker"])
            val = o["offer"] / max(o.get("frac", 1.0), 0.01) if o else kalshi_discount(any_live) * p * a["pays"]
            gnow = val - a["cost"]
            n1 = (f"<b class='{'pos' if gnow >= 0.5 else 'neg' if gnow <= -0.5 else ''}' data-k='g-{e(a['ticker'])}'>"
                  f"{('≈ ' if not o else '') + ('+' if gnow >= 0 else '−')}{money(abs(gnow))}</b>")
            pct_txt = f"{p:.0%}" if p >= 0.01 else f"{p:.1%}" if p >= 0.001 else "<0.1%"
            n2 = f"<span data-k='p-{e(a['ticker'])}'>{pct_txt}</span>"
        elif group == "cashed":
            gain = a["back"] - a["cost"]
            n1 = f"<b class='{'pos' if gain >= 0 else 'neg'}'>{'+' if gain >= 0 else '−'}{money(abs(gain))}</b>"
            n2 = "<span>cashed</span>"
        elif group == "won":
            n1, n2 = f"<b class='pos'>+{money(a['pays'] - a['cost'])}</b>", "<span>won</span>"
        else:
            n1, n2 = f"<b class='neg'>−{money(a['cost'])}</b>", "<span>lost</span>"
        games_of = " ".join(sorted({(l.get("event") or (l["ticker"] or "").rsplit("-", 1)[0])
                                    for l, (_, _, _, r) in legs_sorted if not r}))
        kind = ("playing" if any_live else "quiet") if group == "pending" else group
        cards.append((group, f"<details class='crow' id='c-{e(a['ticker'])}' data-lg='{' '.join(sports)}' "
                     f"data-games='{e(games_of)}' data-kind='{kind}' data-t='{sort_t:.0f}' data-pay='{a['pays']:.2f}' "
                     f"data-p='{p:.5f}' data-i='{i}'><summary>"
                     f"<span class='ci'>{SPORTS.get(sp, {}).get('icon', '🎯')}</span>"
                     f"<span class='cg'><b>Combo {i}</b> <span class='dots'>{dots}</span>"
                     f"<span class='cl'>{context}</span></span>"
                     f"<span class='cn'>{n1}{n2}</span><span class='chev'></span></summary>"
                     f"<div class='cexp'><div class='chips'>{chip}"
                     + (f"<span class='when{' on' if any_live else ''}'>{e(when)}</span>" if when else "")
                     + f"<span style='margin-left:auto'>{status}</span></div>{pay_line}</div>"
                     f"{value}<ol>{''.join(rows)}</ol>"
                     f"<div class='cardfoot'><a class='klink' href='combo://open/{quote(KALSHI_WEB + '/portfolio', safe='')}'>"
                     f"Open in Kalshi ↗</a></div></details>"))

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
    wl = watcher_line() if in_pythonista() else ""
    alerts_row = wl + ("<label class='alertrow'><div><b>Live updates &amp; alerts</b><span id='livemsg'>"
                  + (f"Updated {MINE['last']}" if live and MINE.get("last") else
                     "Off · turn on for scores, offers and alerts") +
                  f"</span></div><input type='checkbox' class='sw' id='livebtn' {'checked' if live else ''} "
                  "onchange='toggleLive()'></label>")
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
    present_sports = [c for c in SPORTS if any(c in (x.split()) for x in
                      (" ".join(sorted({ticker_sport(l["ticker"]) or "other" for l in a["legs"]})) for a in mine))]
    fbar = ""
    if len(mine) > 1:
        chips = ("".join([f"<button class='fchip' data-v='all' onclick=\"view('lg','all')\">All</button>"]
                         + [f"<button class='fchip' data-v='{c}' onclick=\"view('lg','{c}')\">{SPORTS[c]['icon']} "
                            f"{SPORTS[c]['name']}</button>" for c in present_sports])
                 if len(present_sports) > 1 else "")
        fbar = (f"<div class='fbar'><div class='fchips'>{chips}</div>"
                "<div class='seg'><button class='schip' data-v='t' onclick=\"view('sort','t')\">Next game</button>"
                "<button class='schip' data-v='pay' onclick=\"view('sort','pay')\">Payout</button>"
                "<button class='schip' data-v='p' onclick=\"view('sort','p')\">Chance</button></div></div>")
    pend = {a["ticker"]: a for a in mine if snap.get(a["ticker"], {}).get("status") == "pending"}
    by_id = {re.search(r"id='c-([^']+)'", c).group(1): (g, c) for g, c in cards}
    todo = sorted(((t, f) for t, f in ((plan or {}).get("acts") or {}).items() if f and t in MINE["hold"]),
                  key=lambda x: -MINE["hold"][x[0]]["hold"])
    todo_ids = {html.escape(t) for t, _ in todo}
    # game strip: every game your live combos still need, playing ones first
    games = {}
    for a, inf in zip(mine, infos):
        if a["ticker"] not in pend:
            continue
        for l, (nm, _, _, r) in zip(a["legs"], inf):
            if r:
                continue
            ev = l.get("event") or (l["ticker"] or "").rsplit("-", 1)[0]
            sc_l = leg_score(l)
            g = games.setdefault(ev, {"n": set(), "sc": sc_l, "nm": nm, "t": leg_start(l, side_of),
                                      "sp": ticker_sport(l["ticker"]) or "other", "mine": set()})
            g["n"].add(a["ticker"])
            if sc_l:
                g["mine"].add(sc_l["abbr"])           # the team this pick needs to win
    def chip_of(ev, g):
        sc, icon = g["sc"], SPORTS.get(g["sp"], {}).get("icon", "🎯")
        playing = bool(sc and sc["state"] == "in")
        n = len(g["n"])
        if not playing:
            return (False, 0, "")
        both = len(g["mine"]) > 1                  # combos on both sides of this game
        def team(abbr, pts, lead):
            yours = abbr in g["mine"]
            return (f"<div class='gr{' w' if lead else ''}{' you' if yours else ''}'><span>{e(abbr)}"
                    + ("<i>YOU</i>" if yours and not both else "") + f"</span><b>{pts}</b></div>")
        me_first = [(sc["abbr"], sc["me"], sc["me"] > sc["opp"]), (sc["opp_abbr"], sc["opp"], sc["opp"] > sc["me"])]
        teams = "".join(team(*x) for x in me_first)       # your pick is listed first
        return (True, g["t"].timestamp() if g["t"] else 9e12,
                f"<div role='button' class='gchip' id='g-{e(ev)}' data-g='{e(ev)}' onclick=\"pickGame('{e(ev)}')\">"
                f"<div class='gtop'><span class='gsp'>{icon}</span><span class='lv'>{e(sc['detail'])}</span></div>"
                f"{teams}<div class='gmine'>{n} combo{'s' if n != 1 else ''}"
                + (" · both sides" if both else "") + "</div></div>")
    gchips = sorted((c for c in (chip_of(ev, g) for ev, g in games.items()) if c[0]), key=lambda x: x[1])
    n_live_games = sum(1 for c in gchips if c[0])
    summary = f"<div class='gstrip' id='gstrip'>{''.join(c[2] for c in gchips)}</div>" if gchips else ""
    def rows_of(ids):
        return "".join(by_id[i][1] for i in ids if i in by_id)
    pend_ids = sorted((html.escape(t) for t in pend), key=lambda i: float(re.search(r"data-t='([0-9.e+]+)'", by_id[i][1]).group(1))
                      if i in by_id else 9e12)
    quiet = [i for i in pend_ids if i not in todo_ids]           # nothing to do: folded into one line
    n_playing = sum(1 for i in quiet if "data-kind='playing'" in by_id.get(i, ("", ""))[1])
    needs = ""
    if todo:
        items = "".join(f"<div class='nitem' id='n-{html.escape(t)}'>{by_id[html.escape(t)][1]}"
                        f"<div class='quote'>{action_button(t, f, MINE['hold'][t]) if k == 0 else action_button(t, f, MINE['hold'][t]).replace('btn go cashb', 'btn cashb')}</div></div>"
                        for k, (t, f) in enumerate(todo) if html.escape(t) in by_id)
        needs = f"<h2 id='h-needs'>Needs you · {len(todo)}</h2><div class='list' id='needs'>{items}</div>"
    missing = [t for t in MINE["hold"] if not fresh_offer(t)]
    offers_btn = (f"<div class='quote'><button class='btn quiet cashb' onclick=\"cash('askall','all')\">"
                  f"Get cash-out offers{' for the rest' if len(missing) < len(MINE['hold']) else ''}</button></div>"
                  if missing and can_trade() and pend else "")
    nxt_quiet = min((float(re.search(r"data-t='([0-9.e+]+)'", by_id[i][1]).group(1)) for i in quiet), default=9e12)
    quiet_when = when_label(dt.datetime.fromtimestamp(nxt_quiet).astimezone()) if nxt_quiet < 9e11 else ""
    won_ids = [i for i, (g, _) in by_id.items() if g == "won"]
    finished = [i for i, (g, _) in by_id.items() if g in ("cashed", "lost")]
    body = [head, f"<header><h1>Live</h1><div class='sub'>"
                  + (f"<span class='lv'>{n_live_games} game{'s' if n_live_games != 1 else ''} on now</span> · " if n_live_games else "")
                  + f"{len(pend)} combo{'s' if len(pend) != 1 else ''} riding</div></header>",
            (f"<div style='padding:0 16px'><div class='batch' style='border:2px solid var(--good)'><b>{e(flash)}</b></div></div>" if flash else ""),
            "<div class='tabs'><button id='b-combos' class='on' onclick=\"tab('combos')\">Live</button>"
            "<button id='b-record' onclick=\"tab('record')\">Record</button></div>",
            "<section id='combos'>", summary,
            "<div class='ghead' id='ghead'><span id='gname'></span><button class='btn quiet' onclick=\"pickGame('')\">Show all</button></div>",
            needs,
            (f"<details class='quietbox' id='quietbox'><summary><span><b>Riding quietly · {len(quiet)} combo"
             f"{'s' if len(quiet) != 1 else ''}</b><span class='muted'>Nothing to do"
             + (f" · {n_playing} playing now" if n_playing else f" · next game {e(quiet_when)}" if quiet_when else "")
             + f"</span></span><span class='chev'></span></summary>"
             f"<div class='list' id='quiet'>{rows_of(quiet)}</div></details>" if quiet else ""),
            (f"<h2>Won · {len(won_ids)}</h2><div class='list' id='won'>{rows_of(won_ids)}</div>" if won_ids else ""),
            offers_btn]
    if not cards:
        body.append("<div class='empty'><b>No live combos</b><br>Combos you place on Kalshi, in any sport, "
                    "show up here with live scores and cash-out offers.</div>")
    elif not pend:
        body.append("<div class='empty'><b>Nothing still riding</b><br>Your finished combos are below.</div>")
    if finished:
        body.append(f"<details class='lostbox' id='donebox'><summary>Finished · {len(finished)}"
                    f"<span class='muted'> · cashed out and lost</span></summary>"
                    f"<div class='list'>{rows_of(finished)}</div></details>")
    body.append(alerts_row)
    body.append(details)
    history = load_json(HISTORY, {"builds": []})
    body.append(f"</section><section id='record' class='hidden'>"
                f"{render_record(bets_from_account(acct, history))}</section>")
    body.append("<script>function tab(n){document.querySelectorAll('section').forEach(function(s){"
                "s.classList.toggle('hidden',s.id!==n);var b=document.getElementById('b-'+s.id);"
                "if(b)b.classList.toggle('on',s.id===n);});window.scrollTo(0,0);}"
                f"var LIVE={'true' if live else 'false'};"
                "function liveState(on,msg){LIVE=on;var b=document.getElementById('livebtn');if(b)b.checked=on;"
                "document.getElementById('livemsg').textContent=msg||(on?'On · checking now…':'Off');}"
                "function toggleLive(){liveState(!LIVE,'');try{location.href='combo://live/'+(LIVE?'on':'off');}catch(e){}}"
                "function cash(a,t){document.querySelectorAll('.cashb').forEach(function(b){b.disabled=true;});"
                "location.href='combo://cash/'+a+'/'+t;}"
                + LIVE_VIEW_JS +
                "</script></body></html>")
    return "".join(body), snap



CATALOG = {}


def combos_catalog_html():
    """Every kind of event Kalshi allows in combos right now (its open combo collections), grouped
    by series, with what the planner already covers. A screenshot of this is what's needed to add more."""
    e = html.escape
    series, colls, cursor = defaultdict(set), [], None
    try:
        for _ in range(15):
            params = {"status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(f"{KALSHI}/multivariate_event_collections", timeout=20, params=params)
            r.raise_for_status()
            data = r.json()
            for c in data.get("multivariate_contracts", []):
                evs = [a.get("ticker") for a in c.get("associated_events", [])] or list(c.get("associated_event_tickers") or [])
                colls.append((c.get("title") or c.get("collection_ticker", ""), len(evs), c.get("size_max")))
                for ev in evs:
                    if ev:
                        series[ev.split("-", 1)[0]].add(ev)
            cursor = data.get("cursor")
            if not cursor:
                break
    except (requests.RequestException, ValueError) as err:
        return error_page(f"Couldn't ask Kalshi just now ({err}). Try again in a minute.", "What can go in combos?", crash=False)
    covered = set(WINNER_SERIES)
    winners = {k: v for k, v in series.items() if k.endswith(("GAME", "MATCH", "WINNER", "FIGHT", "BOUT"))}
    others = {k: v for k, v in series.items() if k not in winners}
    order = lambda d: sorted(d.items(), key=lambda kv: (kv[0] not in covered, -len(kv[1])))

    def row(k, v):
        return (f"<div class='row' style='padding:7px 0;border-top:1px solid var(--line)'><span><b>{e(k)}</b>"
                f"<br><small class='muted'>{len(v)} event{'s' * (len(v) != 1)} open now</small></span>"
                f"<span class='{'pos' if k in covered else 'muted'}'>{'✓ in the planner' if k in covered else 'not yet'}</span></div>")
    rows = ("<div class='muted' style='font-size:13px;margin:2px 0 4px'>Game and match winners: what the planner "
            "builds with</div>" + "".join(row(k, v) for k, v in order(winners))
            + f"<details class='disc' style='margin-top:8px'><summary><span><b>{len(others)} other kinds</b><span class='muted'>"
              "spreads, totals, halves, player props</span></span></summary>"
            + "".join(row(k, v) for k, v in order(others)) + "</details>")
    CATALOG["text"] = "Kalshi combo events (" + dt.datetime.now().strftime("%b %-d %-I:%M %p") + "):\n" + "\n".join(
        f"{k}: {len(v)} open{' (in planner)' if k in covered else ''} e.g. {sorted(v)[0]}" for k, v in order(series)) + \
        "\nGroups: " + "; ".join(f"{t} ({n} events, max {m})" for t, n, m in colls)
    cl = "".join(f"<div class='row' style='padding:5px 0;border-top:1px solid var(--line)'><span>{e(t)}</span>"
                 f"<span class='muted'>{n} events{f' · up to {m} picks' if m else ''}</span></div>"
                 for t, n, m in sorted(colls, key=lambda x: -x[1])[:40])
    return themed("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
                  f"initial-scale=1'><title>Combo events</title><style>{CSS}</style></head><body><header><h1>What can go in "
                  f"combos?</h1><div class='sub'>{len(series)} kinds of events in {len(colls)} Kalshi combo groups, right now"
                  "</div></header><section><button class='btn go big' style='margin:0 0 12px' "
                  "onclick=\"location.href='combo://copy/catalog'\">Copy list to send Claude</button><div class='game'>" + (rows or "<div class='empty'>"
                  "Kalshi returned no open combo groups.</div>") + "</div><h2>Combo groups</h2><div class='game'>" + cl +
                  "</div></section></body></html>")


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
    if hub_up():
        return hub_kalshi(method, path, body, params)
    confirm_backup_trade(method, path)
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
    return (bool(CFG.get("kalshi_key_id")) and os.path.exists(KEYFILE)) or \
        (hub_up() and bool(HUB["info"].get("trade")))


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
    if is_mix():                                   # mixed combos still to play or playing today
        today = dt.date.today().isoformat()
        return sum(a["cost"] for a in acct or [] if (a.get("week") or "") >= today)
    week = CTX.get("sunday").isoformat() if CTX.get("sunday") else None
    return sum(a["cost"] for a in acct or [] if (a.get("first_week") or a["week"]) == week)


QUOTE_LOG = os.path.join(HERE, "combo_quote_times.json")   # each quote's % of fair and hours before its first game
BUY_WINDOWS = [(48, 1e9, "2 or more days before"), (24, 48, "the day before"), (8, 24, "8 to 24 hours before"),
               (2, 8, "2 to 8 hours before"), (0, 2, "in the last 2 hours")]


def note_quote_time(legs, pct):
    """Remember when this quote came, relative to the combo's first game, to learn the best time to buy."""
    starts = [x for x in (start_dt(l["event"]) for l in legs if l.get("event")) if x]
    if not starts or not pct:
        return
    hrs = (min(starts) - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
    if hrs < 0:
        return
    d = load_json(QUOTE_LOG, [])
    d = (d + [[int(time.time()), round(hrs, 1), round(pct, 4)]])[-400:]
    save_json(QUOTE_LOG, d)


def best_buy_window():
    """(lo, hi, label, gain) for when your combos have priced best vs your usual, once there's
    enough data (20+ quotes, 5+ in that window, 2+ points better), else None."""
    d = load_json(QUOTE_LOG, [])
    if len(d) < 20:
        return None
    overall = statistics.median(x[2] for x in d)
    best = None
    for lo, hi, label in BUY_WINDOWS:
        xs = [x[2] for x in d if lo <= x[1] < hi]
        if len(xs) >= 5:
            m = statistics.median(xs)
            if m - overall >= 0.02 and (best is None or m > best[3] + overall):
                best = (lo, hi, label, m - overall)
    return best


def schedule_buy_nudge(all_games):
    """On a game day, one notification at the time your combos usually price best (learned)."""
    w = best_buy_window()
    if not w or not in_pythonista():
        return
    starts = sorted(x for x in (start_dt(e) for e in all_games) if x and x > dt.datetime.now(dt.timezone.utc))
    if not starts:
        return
    when = starts[0] - dt.timedelta(hours=(w[0] + min(w[1], w[0] + 24)) / 2)
    secs = (when - dt.datetime.now(dt.timezone.utc)).total_seconds()
    key = when.astimezone().strftime("%Y-%m-%d")
    told = load_json(BUY_NUDGE, {})
    if secs < 60 or told.get("day") == key:
        return
    try:
        import notification
        notification.schedule(f"⏰ Your combos usually price best about now ({w[2]} the games, "
                              f"+{w[3]:.0%} of fair). Open Build to get today's prices.", delay=secs, sound_name="default")
        save_json(BUY_NUDGE, {"day": key})
    except Exception:
        pass


BUY_NUDGE = os.path.join(HERE, "combo_buy_nudge.json")


def stake_for(pct):
    """How much to bet on a combo, from Kalshi's price as a share of fair: nothing under your
    cut-off, the least just above it, the most when it's above fair."""
    cut = CFG["accept_pct"] / 100
    if pct < cut:
        return 0
    lo, hi = CFG.get("size_min", 3), CFG.get("size_max", 10)
    steps = [(1.03, hi), (0.99, round(lo + (hi - lo) * 5 / 7)), (0.94, round(lo + (hi - lo) * 2 / 7)), (0, lo)]
    return next(v for edge, v in steps if pct >= edge)


BUY_RATIO = os.path.join(HERE, "combo_buy_ratio.json")   # Kalshi's combo quotes vs single-game prices


def note_buy_ratio(n_legs, ratio):
    """Remember how Kalshi's combo quote compared with the single-game prices, by number of picks."""
    if not 0.2 < ratio < 2:
        return
    d = load_json(BUY_RATIO, {})
    k = str(min(n_legs, 8))
    d[k] = (d.get(k, []) + [round(ratio, 4)])[-30:]
    save_json(BUY_RATIO, d)


def est_quote_ratio(n_legs):
    """Typical combo quote / single-game price for this many picks (None until 3+ quotes)."""
    d = load_json(BUY_RATIO, {})
    near = d.get(str(min(n_legs, 8))) or []
    if len(near) < 3:
        near = [x for v in d.values() for x in v]
    return statistics.median(near) if len(near) >= 3 else None


def est_offer(c, stake=None):
    """(estimated Kalshi payout, share of fair) for a suggested combo, or (None, None)."""
    r = est_quote_ratio(len(c["legs"]))
    if not r or not c.get("kalshi") or not c.get("fair"):
        return None, None
    k = (stake or CFG["stake"]) / CFG["stake"]
    pays = c["kalshi"] * r * k
    return pays, pays / (c["fair"] * k)


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
    if c.get("kalshi"):
        note_buy_ratio(len(c["legs"]), pays / (c["kalshi"] * stake / CTX["stake"]))
    pct = pays / (c["fair"] * stake / CTX["stake"]) if c.get("fair") else None
    note_quote_time(c["legs"], pct)
    CTX["offers"][i] = {"rfq": rfq, "quote": q["id"], "pays": pays, "market": market,
                        "price": yes_price, "stake": stake, "p": CTX["stake"] / c["fair"] if c.get("fair") else None}
    return {"pays": pays, "price": yes_price, "min": minimum, "ok": pays >= minimum, "stake": stake, "pct": pct}


def accept_offer(i):
    """Step 4: accept. 'no' is correct: it hits the seller's NO bid, which buys you YES."""
    import time
    o = CTX["offers"].get(i)
    if not o:
        return {"error": "That offer expired. Tap New price for a fresh one."}
    spent = week_spend()
    if spent + o["stake"] > CFG["budget"] + 0.01:
        return {"error": f"That would take this {slate_word()} to {money(spent + o['stake'])}, over your "
                         f"{money(CFG['budget'])} cap. Raise the cap in Settings to go ahead."}
    CTX["offers"].pop(i, None)
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
        if AUTOSELL and CFG.get("tp_auto"):
            place_take_profit(o["market"], o["pays"], o["stake"], p=o.get("p"))
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


def add_own_combo(tickers):
    """A combo you pick yourself on the Games list: priced like the planner's own (fair payout,
    Kalshi's quote, % of fair) before you buy. Returns (its number, None) or (0, why not)."""
    pool = {s["ticker"]: s for sides in CTX["all_games"].values() for s in sides}
    legs = [pool[t] for t in tickers if t in pool]
    if len(legs) < 2:
        return 0, "Pick at least 2 teams, one per game."
    if len({l["event"] for l in legs}) != len(legs):
        return 0, "Pick one team per game."
    for l in legs:                                    # games outside the slate join the simulation
        CTX["games"].setdefault(l["event"], CTX["all_games"][l["event"]])
    stake = CTX["stake"]
    fair_pay = stake / math.prod(l["fair"] for l in legs)
    new = {"kind": "own", "tier": "Your combo", "legs": legs, "fair": fair_pay,
           "min": fair_pay * CFG["accept_pct"] / 100, "kalshi": stake / math.prod(l["p"] for l in legs)}
    CTX["combos"].append(new)
    k = len(CTX["combos"])
    hist = load_json(HISTORY, {"builds": []})
    b = next((x for x in hist["builds"] if x["id"] == CTX["build_id"]), None)
    if b is not None:
        b["combos"].append({"kind": "own", "tier": "Your combo", "fair": round(fair_pay, 2), "min": round(new["min"], 2),
                            "legs": [{"ticker": l["ticker"], "pick": l["pick"], "dog": l["fair"] < 0.5} for l in legs]})
        save_json(HISTORY, hist)
    return k, None


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
    other = next(x for x in CTX["all_games"][leg["event"]] if x["ticker"] != ticker and not x.get("tie"))
    if not pickable(other) and not other.get("live"):
        return False, (f"{e(other['pick'])} is only {other['fair']:.0%} to win, below the "
                       f"{sport_rule(other['ticker'], 'min_pick', 0):.0%} floor for this sport.")
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
            " Tap Flip again to undo. New price shows whether Kalshi's offer is good.</div>")
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
    if not CTX or (not i and action not in ("batch", "custom")):
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
                auto = len(parts) > 4 and parts[4] == "auto"     # prices only: the cap applies when you Accept
                spent = 0 if auto else week_spend()
                if not auto and spent + total > CFG["budget"] + 0.01:
                    say(f"<span class='verdict no'>Those add up to {money(total)}, which would take this "
                        f"{slate_word()} to {money(spent + total)}, over your {money(CFG['budget'])} cap. "
                        "Untick some or lower the amounts.</span>", 0)
                    for k, _ in wanted:
                        say("", k)
                    return
                say(f"<span class='muted'>Getting Kalshi's price for {'all ' if auto else ''}{len(wanted)} combos… "
                    "(up to a minute)</span>", 0)

                def one(item):
                    k, amt = item
                    try:
                        o = get_offer(k, amt, check_cap=False)
                        if auto and CFG.get("size_auto") and o.get("pct"):
                            want = stake_for(o["pct"])
                            if want and abs(want - amt) > 0.01:
                                say(f"<span class='muted'>{o['pct']:.0%} of fair: getting the price for "
                                    f"{money(want)}…</span>", k)
                                o2 = get_offer(k, want, check_cap=False)
                                if "error" not in o2:
                                    o = o2
                            webview.evaluate_javascript("setStake(%d, %s)" % (k, json.dumps(o["stake"] if want else amt)))
                        say(offer_html(k, o), k)
                        return "error" not in o
                    except Exception as err:
                        say(f"<span class='verdict no'>{html.escape(str(err)[:160])}</span>", k)
                        return False
                with ThreadPoolExecutor(max_workers=4) as pool:
                    got = sum(pool.map(one, wanted))
                say(f"<span class='muted'>{got} of {len(wanted)} prices in · offers last a minute or two</span>", 0)
            elif action == "custom":
                k, note = add_own_combo([t for t in (parts[3] if len(parts) > 3 else "").split(",") if t])
                if not k:
                    webview.evaluate_javascript("myMsg(%s)" % json.dumps(f"<span class='verdict no'>{note}</span>"))
                    return
                rerender(focus=k)
                with open(LATEST, encoding="utf-8") as f:
                    swap_page(webview, inject_state(f.read(), quiet=True))
                if can_trade():
                    say("<span class='muted'>Asking Kalshi for a price… (up to 20 seconds). Nothing is bought until "
                        "you tap Accept.</span>", k)
                    say(offer_html(k, get_offer(k)), k)
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
    pct = f"{o['pct']:.0%} of fair" if o.get("pct") else ""
    verdict = (f"<span class='verdict ok'>{pct or 'Above your cut-off'}</span>" if o["ok"] else
               f"<span class='verdict no'>{pct + ' · ' if pct else ''}under your {CFG['accept_pct']}%</span>")
    ev = (f"<div class='muted' style='font-size:13px;margin-top:2px'>Expected "
          f"{signed_money(o['stake'] * (o['pct'] - 1))} per {money(o['stake'])} bet</div>" if o.get("pct") else "")
    accept = (f"<button class='btn go' onclick='act(\"accept\",{i})'>Accept · {money(o['stake'])}</button>"
              f"<button class='btn' onclick='act(\"decline\",{i})'>Skip</button>" if o["ok"] else
              f"<button class='btn' onclick='act(\"decline\",{i})'>Skip</button>"
              f"<button class='btn quiet' onclick='act(\"accept\",{i})'>Accept anyway</button>")
    return (f"<div class='row' style='align-items:center'><span>Kalshi pays <b>{money(o['pays'])}</b></span>{verdict}</div>"
            f"{ev}<div class='quote'>{accept}</div>")


# ================================================================ settings screen (a page in the same window)
SETTINGS_JS = r"""
var SL = %s;
function label(k){ var s=document.getElementById(k), d=SL[k]; if(!s) return;
  var v=+s.value, txt = d.names ? d.names[v] : d.unit==='$' ? '$'+v : v+(d.unit||'');
  document.getElementById('v-'+k).textContent = txt; budget(); }
function val(k){ var el=document.getElementById(k); return el ? +el.value : 0; }
function budget(){ var n=val('full_count')+val('safer_count')+val('middle_count')+val('moonshot_count');
  var st=val('stake'), cap=val('budget'), b=document.getElementById('budgetline'); if(!b) return;
  b.textContent = n+' combo'+(n===1?'':'s')+' × $'+st+' = $'+(n*st)+(n*st>cap ? ' · over your $'+cap+' cap' : ' · cap $'+cap);
  b.className = n*st>cap ? 'neg' : ''; }
function txtval(k){ var el=document.getElementById(k); return el ? el.value : ''; }
function collect(){ var out={};
  Object.keys(SL).forEach(function(k){ var el=document.getElementById(k); if(el) out[k]=+el.value; });
  document.querySelectorAll('input.sw').forEach(function(el){ out[el.id]=el.checked; });
  if(document.getElementById('odds_key')) out.odds_key=txtval('odds_key').trim();
  if(document.getElementById('kalshi_key_id')) out.kalshi_key_id=txtval('kalshi_key_id').trim();
  if(document.getElementById('watcher_code')) out.watcher_code=txtval('watcher_code').trim();
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

    def slider(key, title, lo, hi, step=1, unit="", names=None):
        sliders[key] = {"unit": unit, "names": names}
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
        top.append(f"<div class='game' style='padding:14px 16px;box-shadow:inset 0 0 0 1.5px "
                   f"{'var(--good)' if good else 'var(--bad)'}'>"
                   f"<b class='{'pos' if good else ''}'>{html.escape(notice)}</b></div>")
    latest = RUN_OPTS.get("latest")
    if latest and version_tuple(latest) > version_tuple(VERSION):
        top.append(f"<button class='btn go big' onclick=\"go('update')\">Update to version {latest}</button>")
    else:
        top.append("<button class='btn big' onclick=\"go('update')\">Check for updates</button>")
    if CFG.get("kalshi_key_id") or os.path.exists(KEYFILE):
        top.append("<button class='btn big' onclick=\"go('check')\">Check Kalshi connection</button>")
        top.append("<button class='btn big' onclick=\"go('catalog')\">What can go in combos?</button>")

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
    if not CFG.get("kalshi_key_id") and not os.path.exists(KEYFILE):
        mode = "setup"                            # first run: a short welcome instead of every setting
        if not CFG.get("tour_pending"):
            CFG["tour_pending"] = True            # the quick tour follows once Kalshi is connected
            save_json(SAVED, CFG)
    APP["smode"] = mode
    APP["where"] = mode
    sec = {
        "money": section("Money", slider("stake", "Per combo", 1, 20, unit="$") +
                         slider("budget", "Mix cap" if is_mix() else "Daily cap" if by_day() else "Weekend cap", 10, 200, 10, "$") +
                         slider("accept_pct", "Fair-price cut-off", 50, 100, 5, "% of fair") +
                         switch("size_auto", "Bet more when the price is good ($3 to $10)"),
                         "Kalshi's prices are marked below your cut-off when they pay less than this share of the fair payout."),
        "mix": "<details class='game disc' id='mix'><summary><span><b>Combo mix</b><span class='muted'>How many of each type</span></span></summary>"
               + ("" if not LG().get("full") else
                  section("Full slate (every game)", slider("full_count", "Combos", 0, 10) +
                          slider("upsets_min", "Fewest underdogs", 0, 8) + slider("upsets_max", "Most underdogs", 0, 8)))
               + "".join(section(t.capitalize(), slider(f"{t}_count", "Combos", 0, 10) +
                                 slider(f"{t}_min", "Fewest games", 2, top_) + slider(f"{t}_max", "Most games", 2, top_))
                         for t, top_ in [("safer", 8), ("middle", 12), ("moonshot", 16)]) + "</details>",
        "days": section("Games from", slider("mix_window", "Window", 0, 2, 1, "", names=MIX_WINDOWS)
                        + switch("next_day", "Same day means tomorrow"),
                        f"{len(all_games)} game{'' if len(all_games) == 1 else 's'} across the NFL, NBA and NHL in this "
                        "window. Combos mix them; Kalshi decides which games it allows together.") if is_mix() else
                section("Day", switch("next_day", "Use tomorrow's games instead of today's"),
                        f"{len(all_games)} game{'' if len(all_games) == 1 else 's'} on Kalshi for "
                        f"{'tomorrow' if CFG.get('next_day') else 'today'}.") if by_day() else
                section("Days", "".join(switch(k, f"{d} <span class='muted'>· {counts.get(d, 0)} game{'' if counts.get(d, 0) == 1 else 's'}</span>")
                                        for k, d in [("thursday", "Thursday"), ("saturday", "Saturday"), ("monday", "Monday")]),
                        "Sunday is always in."),
        "picks": section("Your picks", ("".join(picks) if len(picks) <= 6 else
                                        f"<details id='pk' class='disc'><summary><span><b>{len(picks)} games</b>"
                                        f"<span class='muted'>Tap to lock a team or skip a game</span></span></summary>"
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
                        + slider("ride", "Let it ride", 0, len(RIDE) - 1, 1, "",
                                 names=[n for n, _ in RIDE])
                        + switch("auto_sell", "Auto cash-out at my Let it ride level")
                        + slider("auto_cap", "Auto cash-outs a day, at most", 1, 10, 1, "")
                        + switch("auto_hedge", "Hedge instead when that locks in more")
                        + switch("prefer_hedge", "Prefer hedging, even at up to 5% less")
                        + slider("hedge_cap", "Most to spend on one hedge", 25, 500, 25, "$")
                        + "<div class='row'><span class='muted'>Notifications from your Mac (bundled, at most one "
                          "every 30 min; quiet 10 PM-7 AM except urgent)</span></div>"
                        + switch("notify_value", "Combos quoting at a fair price")
                        + switch("notify_price", "A better price on a combo")
                        + switch("notify_cash", "Cash-outs and hedges")
                        + switch("notify_news", "Big line moves and news")
                        + ((switch("tp_follow", "Move auto-sell prices as games are won or lost")
                            + switch("tp_ladder", "Auto-sell in thirds (a ladder of prices)")
                            + switch("tp_auto", "Auto-sell all my live combos (every league)")) if AUTOSELL else ""),
                        ("Bankroll: the bigger a cash-out offer is next to this, the more the planner favours "
                         "taking the sure money. Let it ride sets when the planner tells you to cash out: it plays "
                         "out the games still to come in order and, at each step, weighs cashing out then (at the "
                         "discount Kalshi buyers really pay, learned from your own offers) against waiting another "
                         "game. Cautious acts on your real bankroll, Steady 2×, Balanced 4×, Bold 10×, Ride it out "
                         "only near full value. Auto cash-out sells by itself when the card says Cash out: a pick "
                         "has already won and Kalshi's offer beats waiting another game at your level. It works "
                         "while the planner is open, or all the time if your Pi watcher is running (Kalshi buys "
                         "combos back only through live offers), and tells you each time. It stops after the daily "
                         "limit and never sells for less than you paid unless a game is turning against you. When a combo is "
                         "down to its last game and buying the other team locks in more than the cash-out offer, it "
                         "hedges instead (a purchase, up to your hedge limit; above it, it cashes out). "
                         "Otherwise nothing sells unless you confirm."
                         + (" Auto-sell puts a standing sell order on Kalshi that fills only if a buyer pays that "
                            "much." if AUTOSELL else ""))),
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
        "watcher": section("Pi watcher",
                           f"<input class='txt' id='watcher_code' placeholder='Paste the pairing code from the Pi' "
                           f"autocapitalize='off' autocorrect='off' spellcheck='false' value='{e(CFG.get('watcher_code', ''))}'>"
                           + "<button class='btn' style='margin-top:8px' onclick=\"go('save')\">Save</button>"
                           + (f"<div style='margin-top:8px'>{watcher_line()}</div>" if CFG.get("watcher_code") else ""),
                           "A Raspberry Pi at home that runs all the time: it sends alerts (through the ntfy app) "
                           "with your phone locked and, if you turn on Auto cash-out, does that too, by the same "
                           "rules (while it's running, only the Pi auto-sells, so nothing sells twice). Saving here "
                           "sends your Let it ride level and Auto cash-out switch to it, signed so only your phone "
                           "can change them. Its own Kalshi key needs read + write access to sell."),
        "home": section("Home Screen", "<button class='btn' onclick=\"go('homescreen')\">Add to Home Screen…</button>"
                        f"<div class='muted' style='font-size:12px;margin-top:8px;word-break:break-all'>Shortcut link: "
                        f"{e(launch_url())}</div>",
                        "Opens the planner with one tap from your Home Screen, without the Pythonista editor."),
    }
    vline = (f"<div class='muted' style='text-align:center;font-size:13px;margin:14px 0 30px'>Version {VERSION} · "
             + ("up to date" if latest and version_tuple(latest) <= version_tuple(VERSION) else
                "update available" if latest else "couldn't check for updates") + "</div>")
    if mode == "setup":
        def step(n, title, body, note):
            return (f"<div class='card' style='padding:16px'><div class='tier'>Step {n}</div>"
                    f"<div style='font-size:19px;font-weight:750;margin:2px 0 8px'>{title}</div>{body}"
                    f"<div class='muted' style='font-size:13px;margin-top:10px'>{note}</div></div>")
        link = lambda url, text: (f"<a class='btn' style='display:flex;align-items:center;justify-content:center;"
                                  f"text-decoration:none;margin:0 0 10px' href='combo://open/{quote(url, safe='')}'>{text}</a>")
        body = "".join([
            "<header><h1>Welcome</h1><div class='sub'>Two minutes of setup, then you're building combos.</div></header><section>",
            "".join(x for x in top if "class='game'" in x),
            step(1, "Connect Kalshi",
                 link(KALSHI_WEB + "/account/profile", "Open Kalshi API keys ↗")
                 + "<input class='txt' id='kalshi_key_id' placeholder='Key ID' autocapitalize='off' autocorrect='off' spellcheck='false'>"
                 + "<textarea class='txt' id='pem' rows='4' style='margin-top:8px' autocapitalize='off' autocorrect='off' "
                   "spellcheck='false' placeholder='Paste the whole private key (BEGIN … END)'></textarea>"
                 + "<button class='btn go big' style='margin-top:10px' onclick=\"go('check')\">Save &amp; connect</button>",
                 "In Kalshi: Account → API keys → Create. Choose read + write so the planner can place and cash out "
                 "combos, but only when you tap to confirm. Kalshi shows the private key once: copy all of it. "
                 "Both stay on this phone only."),
            step(2, "Sportsbook odds <span class='muted' style='font-size:14px;font-weight:600'>optional</span>",
                 link("https://the-odds-api.com/#get-access", "Get a free odds key ↗")
                 + f"<input class='txt' id='odds_key' placeholder='Odds key' autocapitalize='off' autocorrect='off' "
                   f"spellcheck='false' value='{e(CFG['odds_key'])}'>",
                 "Lets the planner compare Kalshi's prices with the sportsbooks to find value. The free plan is plenty."),
            step(3, "Put it on your Home Screen <span class='muted' style='font-size:14px;font-weight:600'>optional</span>",
                 "<button class='btn' onclick=\"go('homescreen')\">Add to Home Screen…</button>",
                 "Opens the planner with one tap, without the Pythonista editor. You can do this later in Settings."),
            "</section>"])
    elif mode == "build":
        upd = (f"<div class='note'>Update available: see the Settings tab.</div>"
               if latest and version_tuple(latest) > version_tuple(VERSION) else "")
        notice_html = [x for x in top if "class='game'" in x]
        body = "".join([
            f"<header><h1>Build</h1>{sport_seg('form')}<div class='sub'><span id='budgetline'></span></div>"
            + (lambda w: f"<div class='muted' style='font-size:13px;margin-top:4px'>⏰ Your combos have priced best {w[2]} "
               f"the games (+{w[3]:.0%} of fair).</div>" if w else "")(best_buy_window())
            + "</header><section>",
            upd, "".join(notice_html),
            ("" if CFG.get("built_once") else
             "<div class='tip'><b>New here?</b> The settings below are already set to sensible defaults. Tap "
             "<b>Build combos</b> at the bottom to see suggestions. Nothing is placed until you choose to.</div>"),
            sec["days"], sec["money"], sec["mix"], sec["picks"],
            "<button class='btn go big' style='margin:18px 0 8px' onclick=\"go('build')\">Build combos</button>",
            "</section>"])
    else:
        # urgent things (a notice, an update waiting) stay on top; routine checks live at the bottom
        urgent = [x for x in top if "class='game'" in x or "Update to version" in x]
        routine = [x.replace("class='btn big'", "class='btn big'") for x in top
                   if x not in urgent and "go('lg-" not in x]
        body = "".join([
            "<header><h1>Settings</h1></header><section>",
            ("<div class='stack'>" + "".join(urgent) + "</div>") if urgent else "",
            sec["look"], sec["cash"], sec["kalshi"], sec["odds"],
            "<details class='lostbox' id='moreset'><summary>More settings · game order, overlap, mid-day, Pi watcher</summary>",
            sec["order"], sec["midday"], sec["overlap"], sec["watcher"], "</details>",
            sec["home"],
            "<button class='btn go big' style='margin:22px 0 4px' onclick=\"go('save')\">Save settings</button>",
            "<h2>About</h2><div class='stack'>" + "".join(routine)
            + "<a class='btn big' style='display:flex;align-items:center;justify-content:center;text-decoration:none' "
              "href='combo://nav/tour'>Show the quick tour</a></div>",
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
            before = {k: CFG.get(k) for k in WATCHER_SYNCED}
            for k, v in vals.items():
                if k in CFG:
                    CFG[k] = type(CFG[k])(v) if isinstance(CFG[k], (int, bool)) and not isinstance(v, dict) else v
            save_cfg(cleared)
            if choice != "save" and before != {k: CFG.get(k) for k in WATCHER_SYNCED}:
                import threading               # left Settings another way: the Pi still hears of it
                threading.Thread(target=send_watcher_settings, daemon=True).start()
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



# ================================================================ share-sheet check and widget
def shared_ticker(text):
    """The combo's market ticker from a Kalshi share link (its marketTicker), or from any text."""
    m = re.search(r"marketTicker=(KXMVE[A-Z0-9]*-[A-Z0-9]+-[A-Z0-9]+)", text or "", re.I) or \
        re.search(r"\b(KXMVE[A-Z0-9]*-[A-Z0-9]+-[A-Z0-9]+)\b", text or "", re.I)
    return m.group(1).upper() if m else None


def check_combo(ticker, stake=None):
    """Price a combo you built in the Kalshi app before buying: each pick's chance from its own
    Kalshi market, the fair payout, and Kalshi's real quote for your stake. Nothing is bought."""
    import time
    stake = float(stake or CFG["stake"])
    cache = load_json(LEGS_CACHE, {})
    legs = combo_legs(ticker, cache)
    save_json(LEGS_CACHE, cache)
    if not legs:
        return {"error": "Kalshi didn't return this combo's picks. Check the link and try again."}
    picks, chances, asks = [], [], []
    for l in legs:
        try:
            r = requests.get(f"{KALSHI}/markets/{l['ticker']}", timeout=15)
            m = r.json().get("market", {}) if r.ok else {}
        except (requests.RequestException, ValueError):
            m = {}
        p, ask = live_price(m), price(m)
        if p is None:
            return {"error": f"Couldn't get a price for {l['ticker']}."}
        name = m.get("yes_sub_title") or m.get("title") or l["ticker"]
        if l.get("side", "yes") == "no":
            p, ask, name = 1 - p, (1 - live_bid(m)) if live_bid(m) is not None else None, "Not: " + name
        if m.get("result") in ("yes", "no"):
            won = (m["result"] == "yes") == (l.get("side", "yes") == "yes")
            p, ask = (1.0, 1.0) if won else (0.0, 0.0)
        picks.append((name, p))
        chances.append(p)
        asks.append(ask or p)
    fair = math.prod(chances)
    if fair <= 0:
        return {"error": "A pick in this combo has already lost."}
    out = {"ticker": ticker, "picks": picks, "stake": stake, "fair_pays": stake / fair, "chance": fair}
    if can_trade():
        try:
            clear_my_rfqs(ticker)
            rfq = kalshi_send("POST", "/communications/rfqs",
                              {"market_ticker": ticker, "target_cost_dollars": f"{stake:.2f}",
                               "rest_remainder": False, "replace_existing": False})["id"]
            best, start = None, time.time()
            while time.time() - start < 20:
                time.sleep(1.5)
                qs = kalshi_send("GET", "/communications/quotes",
                                 params={"rfq_id": rfq, "rfq_user_filter": "self"}).get("quotes", [])
                for q in qs:
                    if q.get("status") == "open" and q.get("no_bid_dollars"):
                        y = 1 - float(q["no_bid_dollars"])
                        if 0 < y < 1 and (best is None or y < best):
                            best = y
                if best and time.time() - start > 5:
                    break
            kalshi_send("DELETE", f"/communications/rfqs/{rfq}")
            if best:
                out["pays"] = stake / best
                note_buy_ratio(len(legs), out["pays"] / (stake / math.prod(asks)))
        except (RuntimeError, PermissionError, requests.RequestException, KeyError) as err:
            out["quote_error"] = str(err)[:140]
    if out.get("pays"):
        out["pct"] = out["pays"] / out["fair_pays"]
        out["ev"] = stake * (out["pct"] - 1)
    return out


def check_html(c):
    """The share-sheet answer, as a small page."""
    e = html.escape
    head = (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><style>{CSS}</style></head><body>")
    if "error" in c:
        return themed(head + f"<header><h1>Combo check</h1></header><section><div class='empty'>{e(c['error'])}"
                      "</div></section></body></html>")
    if c.get("pct"):
        ok = c["pct"] >= CFG["accept_pct"] / 100
        verdict = (f"<span class='verdict {'ok' if ok else 'no'}'>{c['pct']:.0%} of fair · "
                   f"{'at or above' if ok else 'below'} your {CFG['accept_pct']}% cut-off</span>")
        top = (f"<div class='row'><b>Kalshi pays {money(c['pays'])}</b><b class='{'pos' if c['ev'] >= 0 else 'neg'}'>"
               f"{signed_money(c['ev'])}</b></div><div class='muted' style='font-size:13px'>expected per "
               f"{money(c['stake'])} bet · fair payout {money(c['fair_pays'])}</div><div style='margin-top:8px'>{verdict}</div>")
    else:
        why = c.get("quote_error") or ("Connect your Kalshi account in the planner's Settings to get Kalshi's quote."
                                       if not can_trade() else "No quote came in. Try again in a minute.")
        top = (f"<div class='row'><b>Fair payout {money(c['fair_pays'])}</b></div><div class='muted' "
               f"style='font-size:13px'>for {money(c['stake'])}. {e(why)}</div>")
    rows = "".join(f"<div class='row' style='padding:6px 0;border-top:1px solid var(--line)'><span>{e(n)}</span>"
                   f"<span class='muted'>{p:.0%}</span></div>" for n, p in c["picks"])
    return themed(head + f"<header><h1>Combo check</h1><div class='sub'>{len(c['picks'])} picks · "
                  f"{c['chance']:.1%} chance</div></header><section><div class='game'>{top}</div>"
                  f"<h2>Picks</h2><div class='game'>{rows}</div><div class='muted' style='font-size:12px;"
                  "margin:10px 4px'>Fair uses each pick's own Kalshi price. Nothing was bought.</div>"
                  "</section></body></html>")


HELPER_CHECK = r"""# Combo check: share a combo from the Kalshi app to this script (Pythonista's share sheet)
# and it shows Kalshi's quote next to the fair payout. Nothing is bought.
# Written by the planner; it updates this file itself.
import os, importlib.util, ui
try:
    import appex, clipboard
except ImportError:
    appex = clipboard = None
DOCS = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("combo_engine_check", os.path.join(DOCS, "combo_planner_engine.py"))
E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.set_league("nfl")
text = ""
if appex and appex.is_running_extension():
    text = appex.get_url() or appex.get_text() or " ".join(appex.get_urls() or [])
elif clipboard:
    text = clipboard.get() or ""
v = ui.WebView(name="Combo check")
v.load_html(E.themed("<html><body style='font:17px -apple-system;padding:24px'>Asking Kalshi for a quote… (up to 20 seconds)</body></html>"))
v.present("sheet")
t = E.shared_ticker(text)
v.load_html(E.check_html(E.check_combo(t) if t else {"error": "Share a combo from the Kalshi app (Share, then Run Pythonista Script, then Combo check), or copy its link and run this script."}))
"""

HELPER_WIDGET = r"""# Combo widget: your combos at a glance (Pythonista > Settings > Today Widget > pick this script).
# Reads what your Pi publishes, so it stays light. Written by the planner; it updates this file itself.
import os, json, time, base64, hmac, hashlib
import ui, requests
try:
    import appex
except ImportError:
    appex = None
DOCS = os.path.dirname(os.path.abspath(__file__))
NTFY = "https://ntfy.sh"


def load(name):
    try:
        with open(os.path.join(DOCS, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def unseal(secret, blob):
    try:
        data = base64.urlsafe_b64decode(blob.encode())
        nonce, mac, ct = data[:16], data[16:48], data[48:]
        if not hmac.compare_digest(mac, hmac.new(secret.encode(), nonce + ct, hashlib.sha256).digest()):
            return None
        key = hashlib.sha256((secret + "|seal").encode()).digest()
        stream = b"".join(hashlib.sha256(key + nonce + i.to_bytes(4, "big")).digest() for i in range(len(ct) // 32 + 1))
        return json.loads(bytes(a ^ b for a, b in zip(ct, stream)))
    except (ValueError, TypeError):
        return None


def latest(topic, since):
    try:
        r = requests.get(f"{NTFY}/{topic}/json", params={"poll": "1", "since": since}, timeout=8)
        lines = [json.loads(x) for x in r.text.splitlines() if x.strip()] if r.ok else []
        return lines[-1]["message"] if lines else None
    except Exception:
        return None


def money(x):
    return ("+" if x >= 0 else "-") + "$" + (f"{abs(x):,.2f}" if abs(x) < 100 else f"{abs(x):,.0f}")


code = (load("combo_keys.json").get("watcher_code") or load("combo_settings.json").get("watcher_code") or "").strip()
lines = []
if not code:
    lines = ["Pair your Pi watcher in the planner's", "Settings to see your combos here."]
else:
    conf = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode())
    hb = json.loads(latest(conf["topic"] + "-hb", "10m") or "{}")
    rep = unseal(conf["secret"], latest(conf["topic"] + "-report", "24h") or "") or {}
    if hb:
        age = int((time.time() - hb.get("at", 0)) / 60)
        state = "Pi ✓" if age < 3 else f"Pi quiet {age} min"
        lines.append(f"{state} · {hb.get('live', 0)} riding · {hb.get('playing', 0)} playing now")
        if hb.get("cash"):
            lines.append("💰 Cash out: " + ", ".join(hb["cash"][:3]))
        elif hb.get("next"):
            lines.append("Next game " + time.strftime("%a %-I:%M %p", time.localtime(hb["next"])))
        else:
            lines.append("Nothing needs you")
        if hb.get("paused"):
            lines.append("⏸ Auto cash-out paused")
    else:
        lines.append("No word from the Pi in 10+ minutes")
    st = rep.get("stats") or {}
    w = st.get("week") or [0, 0, 0]
    if w[0]:
        lines.append(f"7 days: {money(w[2] - w[1])} on ${w[1]:,.0f}")
v = ui.View(frame=(0, 0, 320, 24 + 22 * len(lines)))
for i, t in enumerate(lines):
    lab = ui.Label(frame=(12, 10 + 22 * i, 300, 22), text=t, font=("<system-bold>" if i == 0 else "<system>", 15))
    lab.flex = "W"
    v.add_subview(lab)
b = ui.Button(frame=v.bounds, flex="WH")
b.action = lambda s: __import__("webbrowser").open("pythonista3://nfl_combo_planner?action=run")
v.add_subview(b)
if appex and appex.is_running_extension():
    appex.set_widget_view(v)
else:
    v.present("sheet")
"""

HELPERS = {"combo_check.py": HELPER_CHECK, "combo_widget.py": HELPER_WIDGET}


def write_helpers():
    """Keep the share-sheet and widget scripts next to the planner, current with this version."""
    for name, src in HELPERS.items():
        path = os.path.join(HERE, name)
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == src:
                    continue
        except OSError:
            pass
        try:
            with open(path + ".new", "w", encoding="utf-8") as f:
                f.write(src)
            os.replace(path + ".new", path)
        except OSError:
            pass


# ================================================================ main
RUN_OPTS = {}


def this_week(sunday):
    """Has this week already been set? 'account' (combos on Kalshi), 'planner'
    (combos ticked Placed in the planner), or None."""
    if can_trade():
        loading("Checking your Kalshi account…")
        acct, _, _ = fetch_account()
        if acct and any(on_live(a, sunday.isoformat()) for a in acct):
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
    if in_pythonista():
        write_helpers()
    loading(f"Loading {'the ' + LG()['name'].lower() if by_day() else 'this week'}'s games from Kalshi…")
    RUN_OPTS["latest"] = latest_version()
    all_games, days, sunday = week_games(fetch_markets())
    CFG["picks"] = {e: v for e, v in CFG["picks"].items() if e in all_games}  # drop old weeks
    schedule_buy_nudge(all_games)
    import_key_file()
    start_autosell_keeper()
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
        sent = send_watcher_settings()
        RUN_OPTS["notice"] = "Saved." + (" Sent to the Pi watcher." if sent else "") + (
            "" if CFG.get("odds_key") else " (No sportsbook key: chances use Kalshi's prices.)")
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
    if choice == "catalog":
        loading("Asking Kalshi which events it allows in combos…")
        return present(combos_catalog_html())
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
    if not CFG.get("built_once"):
        CFG["built_once"] = True
        save_cfg()

    notes = []
    loading("Getting sportsbook odds…")
    book, note = fetch_book_odds(CFG["odds_key"])
    notes.append(note)
    matched, news = attach_fair(all_games, book)
    remember_pregame(all_games)
    if book and matched < len(all_games):
        notes.append(f"{len(all_games) - matched} game{'s' * ((len(all_games) - matched) != 1)} had no sportsbook match and use Kalshi's prices.")

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
        elif book and sport_rule(e, "require_line", False) and not any(x.get("src") for x in all_games[e]) \
                and CFG["picks"].get(e) is None:
            skipped[e] = ("Left out: no sportsbook line for this game, so there's no way to tell whether "
                          "Kalshi's price is fair. Lock a team to include it anyway.")
        elif CFG["skip_news"] and news.get(e, 0) >= NEWS_GAP and on[days[e]] \
                and CFG["picks"].get(e) is None:
            skipped[e] = (f"Left out: Kalshi and the sportsbooks disagree by {news[e]:.0%}, "
                          "probably breaking news. Lock a team to include it anyway.")
    if any("disagree" in v for v in skipped.values()):
        n = sum("disagree" in v for v in skipped.values())
        notes.append(f"Left out {n} game{'s' * ((n) != 1)} with likely breaking news. See the Games tab.")
    live_in = [e for e in live if e not in skipped and on[days[e]]]
    live_out = [e for e in live if e in skipped and on[days[e]]]
    if live:
        notes.append(f"Mid-day build: {len(live_in)} game{'s' * ((len(live_in)) != 1)} in progress included at Kalshi's live prices"
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
            why.append(f"{len(live_out)} game{'s' * ((len(live_out)) != 1)} in progress were left out as bad bets: nearly decided, "
                       f"prices jumping too much, or no team with at least a {CFG['live_min']}% live chance.")
        if off:
            why.append(f"{len(off)} game{'s' * ((len(off)) != 1)} are on days you have switched off ({', '.join(offdays)}).")
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
                       + (f"Kalshi may not offer {LG()['name']} combos, or not on these games. "
                          "Try tomorrow's games, or switch league with the buttons at the top." if by_day() else
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
                "build_id": build_id, "stake": CFG["stake"], "offers": {}, "autoq": True})
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
        r = requests.get(UPDATE_URL + "/version.txt", params={"t": int(time.time())}, timeout=6,
                         headers={"Cache-Control": "no-cache"})   # the query skips GitHub's 5-minute cache
        if r.ok and re.fullmatch(r"[0-9.]+", r.text.strip()):
            return r.text.strip()
    except requests.RequestException:
        pass
    return None


def install_update():
    """Download the newest version, check it, keep a backup, swap it in.
    Returns (ok, message). Your settings, keys and history are separate files and stay put."""
    try:
        r = requests.get(UPDATE_URL + "/nfl_combo_planner.py", params={"t": int(time.time())}, timeout=30,
                         headers={"Cache-Control": "no-cache"})
        if not getattr(r, "ok", False):
            return False, "Couldn't download the update. Check your connection and try again."
        src = r.content.decode("utf-8", errors="strict")
        raw = r.content
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
    try:
        approve_pi_update(found.group(1), raw)
    except Exception:
        pass
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


def take_over_open_window():
    """Running the planner again (Run, or the home-screen icon) while it's already open used to
    start a second copy in a second window on top of the first, both refreshing. Now the new copy
    takes over the open window and the old copy stands down, the same way an update does."""
    import builtins
    old = getattr(builtins, "_combo_planner_app", None)
    builtins._combo_planner_app = APP
    if not in_pythonista() or old is None or old is APP or old.get("closed") or old.get("web") is None:
        return
    try:
        if not old["win"].on_screen:
            return
    except Exception:
        return
    keep = dict(RUN_OPTS)
    try:
        adopt_window(old, None)
    except Exception:
        return
    for k in ("goto", "smode", "notice"):      # a plain relaunch opens where it normally would
        RUN_OPTS.pop(k, None)
        if k in keep:
            RUN_OPTS[k] = keep[k]


def run():
    """main(), but any failure shows a readable page instead of a stuck spinner."""
    take_over_open_window()
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


# ================================================================ shadow auto-trading (paper)
# The Mac runs the full-auto strategy with no money: it asks Kalshi for real combo quotes, "buys"
# only when the quote pays at least your shadow threshold (default: more than fair, i.e. a profit
# expected), and settles each paper bet when the games finish. The record shows whether a real
# full-auto budget would have made money before any is risked.
SHADOW = os.path.join(HERE, "combo_shadow.json")
SHADOW_DEF = {"start": 300.0, "min_pct": 100, "per_day": 30.0, "max_open": 15, "quotes_per_day": 12,
              "per_pass": 2}


def shadow_state():
    st = load_json(SHADOW, {})
    for k, v in SHADOW_DEF.items():
        st.setdefault(k, v)
    st.setdefault("bank", st["start"])
    st.setdefault("bets", [])
    st.setdefault("quotes", [])
    return st


def shadow_settle(st):
    """Settle paper bets whose games are decided. Returns how many changed."""
    open_bets = [b for b in st["bets"] if b["status"] == "open"]
    if not open_bets:
        return 0
    res = fetch_results({l["ticker"] for b in open_bets for l in b["legs"]})
    changed = 0
    for b in open_bets:
        rs = [res.get(l["ticker"]) for l in b["legs"]]
        if "no" in rs:
            b.update(status="lost", payout=0.0, done=time.time())
        elif all(r == "yes" for r in rs):
            b.update(status="won", payout=b["pays"], done=time.time())
            st["bank"] += b["pays"]
        else:
            continue
        changed += 1
    return changed


def shadow_pass(book_snap, log=print, alert=None):
    """One round for the league on screen: settle, then quote the best couple of combos and paper-buy
    any that pay at least the threshold. Returns a list of things that happened."""
    st = shadow_state()
    did = [f"settled {n}" for n in [shadow_settle(st)] if n]
    today = dt.date.today().isoformat()
    q_today = sum(1 for q in st["quotes"] if q["day"] == today)
    spent_today = sum(b["stake"] for b in st["bets"] if b["day"] == today)
    if q_today >= st["quotes_per_day"] or sum(b["status"] == "open" for b in st["bets"]) >= st["max_open"]:
        save_json(SHADOW, st)
        return did
    attach_fair_book = load_book_state(book_snap)
    games_held = {frozenset(l["ticker"] for l in b["legs"]) for b in st["bets"]}
    cands = shadow_candidates_with(attach_fair_book)
    CTX.clear()
    CTX.update(combos=cands, stake=CFG["stake"], offers={})
    asked = 0
    for i, c in enumerate(cands, 1):
        if asked >= st["per_pass"] or q_today + asked >= st["quotes_per_day"]:
            break
        if frozenset(l["ticker"] for l in c["legs"]) in games_held:
            continue
        asked += 1
        try:
            r = get_offer(i, check_cap=False)
        except Exception as err:                  # a quote that fails is just skipped
            log("shadow quote failed:", type(err).__name__, err)
            continue
        o = CTX["offers"].pop(i, None)
        if o:
            try:
                kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
            except Exception:
                pass
        if r.get("error") or not r.get("pct"):
            continue
        pct = r["pct"]
        key = "|".join(sorted(l["ticker"] for l in c["legs"]))
        before = st.setdefault("seen", {}).get(key)
        st["seen"][key] = round(pct, 4)
        if alert and pct * 100 >= CFG["accept_pct"]:
            picks = ", ".join(l["pick"] for l in c["legs"])
            if before is None:
                alert(f"💡 A {len(c['legs'])}-pick {LG()['name']} combo is quoting at {pct:.0%} of fair: {picks}. "
                      "Build it from the Games list to get your own price.", "value")
            elif pct - before >= 0.05:
                alert(f"📈 Better price: {picks} went from {before:.0%} to {pct:.0%} of fair.", "price")
        st["quotes"].append({"day": today, "pct": round(pct, 4), "legs": len(c["legs"]), "league": LEAGUE["code"]})
        stake = 10 if pct >= 1.10 else 8 if pct >= 1.05 else 5
        if pct * 100 < st["min_pct"] or spent_today + stake > st["per_day"] or stake > st["bank"]:
            did.append(f"quoted {len(c['legs'])}-pick at {pct:.0%} of fair: passed")
            continue
        pays = r["pays"] * stake / r["stake"]
        st["bank"] -= stake
        spent_today += stake
        st["bets"].append({"id": f"S{len(st['bets']) + 1}", "day": today, "at": time.time(), "league": LEAGUE["code"],
                           "legs": [{"ticker": l["ticker"], "pick": l["pick"], "fair": round(l["fair"], 4),
                                     "p": round(l["p"], 4)} for l in c["legs"]],
                           "stake": stake, "pays": round(pays, 2), "pct": round(pct, 4), "status": "open"})
        did.append(f"paper-bought {len(c['legs'])}-pick at {pct:.0%} of fair: {money(stake)} to win {money(pays)}")
    st["quotes"] = st["quotes"][-500:]
    if len(st.get("seen", {})) > 400:
        st["seen"] = dict(list(st["seen"].items())[-300:])
    save_json(SHADOW, st)
    return did


def shadow_candidates_with(book):
    games, days, slate = week_games(fetch_markets())
    attach_fair(games, book)
    if not games:
        return []
    combos, _ = build_combos(games, {}, random.Random(int(time.time() // 3600)))
    out = []
    for c in combos:
        if not c.get("fair") or not c.get("kalshi") or any(started(l) for l in c["legs"]):
            continue
        if any(l.get("src") is None for l in c["legs"]):
            continue                              # only picks with a sportsbook line to judge them by
        kicks = [_kick_ts(l) for l in c["legs"]]
        if None in kicks or min(kicks) - time.time() > SHADOW_WINDOW:
            continue                              # quote close to game time, when combos price best
        out.append(((est_offer(c)[1] or 0.8 * c["kalshi"] / c["fair"]), c))
    out.sort(key=lambda x: -x[0])
    good = []
    for _, c in out:
        if len(good) >= 6:
            break
        if not thin_legs(c["legs"]):              # thin order books make Kalshi's price unreliable
            good.append(c)
    return good


SHADOW_WINDOW = 8 * 3600


def _kick_ts(leg):
    try:
        return dt.datetime.fromisoformat(str(KICKOFF.get(leg.get("event") or "")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def shadow_summary(st=None):
    st = st or shadow_state()
    done = [b for b in st["bets"] if b["status"] != "open"]
    staked = sum(b["stake"] for b in done)
    back = sum(b.get("payout", 0) for b in done)
    qs = [q["pct"] for q in st["quotes"]]
    return {"start": st["start"], "bank": round(st["bank"], 2), "open": sum(b["status"] == "open" for b in st["bets"]),
            "open_staked": sum(b["stake"] for b in st["bets"] if b["status"] == "open"),
            "n": len(done), "won": sum(b["status"] == "won" for b in done), "staked": staked, "back": round(back, 2),
            "quotes": len(qs), "best": max(qs) if qs else None,
            "median": statistics.median(qs) if qs else None, "near": sum(q >= 0.95 for q in qs),
            "min_pct": st["min_pct"], "recent": st["bets"][-8:]}


def shadow_text(sm):
    if not sm["quotes"]:
        return "🧪 Shadow auto: no quotes yet."
    pl = sm["back"] - sm["staked"]
    return (f"🧪 Shadow auto (no real money): {sm['n']} settled, {signed_money(pl)} on {money(sm['staked'])}"
            f" · {sm['open']} open · bank {money(sm['bank'] + sm['open_staked'])} of {money(sm['start'])}."
            f" Kalshi quotes so far: median {sm['median']:.0%} of fair, best {sm['best']:.0%}"
            f" ({sm['quotes']} asked; it buys at {sm['min_pct']}%+).")


def shadow_html(sm):
    """A card for Results > Record."""
    e = html.escape
    if not sm:
        return ""
    rows = "".join(
        f"<div class='row'><span>{e(' + '.join(l['pick'] for l in b['legs']))}</span>"
        f"<span class='nums'>{money(b['stake'])} → {money(b['pays'])} · "
        f"{ {'open': 'open', 'won': '✅ won', 'lost': '❌ lost'}[b['status']] }</span></div>"
        for b in reversed(sm.get("recent") or []))
    return ("<section><h2><span>🧪 Shadow auto-trading</span></h2><div class='game'>"
            f"<div class='row'><span>{e(shadow_text(sm))}</span></div>{rows}"
            "<div class='row'><span class='muted'>Your Mac runs the full-auto strategy with real Kalshi quotes "
            "but no money. It only paper-buys when a quote pays more than fair. Go live only once this shows a "
            "profit over 50+ bets.</span></div></div></section>")


# ================================================================ order books (Kalshi)
BOOK_DEPTH = {}


def book_depth(ticker, max_age=60):
    """Kalshi's order book for one pick: {'bid', 'ask', 'spread', 'ask_size' (contracts at the best
    ask), 'thin'}. Thin = wide spread or little size, so the price isn't reliable. None if unknown."""
    now = time.time()
    got = BOOK_DEPTH.get(ticker)
    if got and now - got[0] < max_age:
        return got[1]
    try:
        r = requests.get(f"{KALSHI}/markets/{ticker}/orderbook", timeout=10)
        ob = ((r.json() or {}).get("orderbook") or {}) if r.ok else {}
    except (requests.RequestException, ValueError):
        return None

    def levels(side):
        rows = ob.get(f"{side}_dollars") or [[x[0] / 100, x[1]] for x in (ob.get(side) or [])]
        out = []
        for row in rows:
            try:
                out.append((float(row[0]), float(row[1])))
            except (TypeError, ValueError, IndexError):
                pass
        return sorted(out)
    yes, no = levels("yes"), levels("no")
    if not yes or not no:
        info = {"bid": yes[-1][0] if yes else None, "ask": 1 - no[-1][0] if no else None,
                "spread": None, "ask_size": no[-1][1] if no else 0, "thin": True}
    else:
        bid, ask = yes[-1][0], 1 - no[-1][0]
        info = {"bid": bid, "ask": ask, "spread": round(ask - bid, 4), "ask_size": no[-1][1],
                "thin": ask - bid > 0.04 or no[-1][1] < 100}
    BOOK_DEPTH[ticker] = (now, info)
    if len(BOOK_DEPTH) > 3000:
        for k in sorted(BOOK_DEPTH, key=lambda k: BOOK_DEPTH[k][0])[:1000]:
            BOOK_DEPTH.pop(k, None)
    return info


def thin_legs(legs):
    """Picks in a combo whose Kalshi price comes from a thin order book (names), checked live."""
    out = []
    for l in legs:
        d = book_depth(l["ticker"])
        if d and d["thin"]:
            out.append(l["pick"])
    return out


# ================================================================ which odds source is most accurate
ACCURACY = os.path.join(HERE, "combo_accuracy.json")
SOURCES = ("pinnacle", "odds service", "sportsbook", "polymarket", "kalshi", "blend")
ACC_CACHE = {}


def accuracy_state():
    st = load_json(ACCURACY, {})
    st.setdefault("open", {})
    st.setdefault("done", [])
    return st


def accuracy_record(games, snap, window=1200):
    """For games starting within `window` seconds: remember each source's chance for one team
    (the latest seen before kickoff counts). Call often before games."""
    st = accuracy_state()
    now = time.time()
    parts = snap.get("parts") or {}
    n = 0
    for e, sides in games.items():
        if len(sides) != 2 or any(x.get("tie") for x in sides):
            continue                                  # two-way games only (draws muddy the scoring)
        try:
            kt = dt.datetime.fromisoformat(str(KICKOFF.get(e)).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if not (now < kt < now + window):
            continue
        a = sides[0]
        if not a.get("book_name"):
            continue
        tot = sum(x["p"] for x in sides)
        row = {"team": a["book_name"], "ticker": a["ticker"], "kick": kt, "league": ticker_sport(a["ticker"]),
               "kalshi": round(a["p"] / tot, 4), "blend": round(a["fair"], 4)}
        for src, p in (parts.get(a["book_name"]) or {}).items():
            row[src] = round(p, 4)
        st["open"][e] = row
        n += 1
    if n:
        save_json(ACCURACY, st)
    return n


def accuracy_resolve():
    """Score recorded games that have finished (from Kalshi's settled results)."""
    st = accuracy_state()
    due = {e: r for e, r in st["open"].items() if time.time() > r["kick"] + 2 * 3600}
    if not due:
        return 0
    res = fetch_results({r["ticker"] for r in due.values()})
    n = 0
    for e, r in due.items():
        out = res.get(r["ticker"])
        if out in ("yes", "no"):
            st["done"].append(dict(r, won=1 if out == "yes" else 0))
            del st["open"][e]
            n += 1
        elif time.time() > r["kick"] + 4 * 86400:
            del st["open"][e]                         # never settled (postponed?): drop it
    st["done"] = st["done"][-3000:]
    save_json(ACCURACY, st)
    ACC_CACHE.clear()
    return n


def accuracy_summary():
    """Per source: games scored, Brier score (lower is better), and the gain over Kalshi's own
    pre-game price on the same games (positive = more accurate than Kalshi)."""
    done = accuracy_state()["done"]
    out = {}
    for src in SOURCES:
        rows = [r for r in done if r.get(src) is not None]
        if not rows:
            continue
        brier = sum((r[src] - r["won"]) ** 2 for r in rows) / len(rows)
        both = [r for r in rows if r.get("kalshi") is not None]
        vs = None
        if both and src != "kalshi":
            vs = (sum((r["kalshi"] - r["won"]) ** 2 for r in both) - sum((r[src] - r["won"]) ** 2 for r in both)) / len(both)
        out[src] = {"n": len(rows), "brier": round(brier, 4), "vs_kalshi": round(vs, 4) if vs is not None else None}
    return out


def source_weights():
    """(sportsbook weight, Polymarket weight) for the free blend: even until 150 games of each are
    scored, then by measured accuracy (inverse Brier score)."""
    try:
        if "sum" not in ACC_CACHE or time.time() - ACC_CACHE.get("at", 0) > 3600:
            ACC_CACHE.update(sum=accuracy_summary(), at=time.time())
        sm = ACC_CACHE["sum"]
    except Exception:
        return 1.0, 1.0
    b, p = sm.get("sportsbook"), sm.get("polymarket")
    if not b or not p or min(b["n"], p["n"]) < 150:
        return 1.0, 1.0
    wb, wp = 1 / max(b["brier"], 0.05), 1 / max(p["brier"], 0.05)
    return 2 * wb / (wb + wp), 2 * wp / (wb + wp)


def accuracy_text(sm):
    if not sm:
        return "Nothing scored yet: the Mac records every source's price at kickoff and scores it when the game ends."
    names = {"pinnacle": "Pinnacle", "odds service": "Odds service", "sportsbook": "ESPN's sportsbook",
             "polymarket": "Polymarket", "kalshi": "Kalshi", "blend": "Planner's fair price"}
    parts = []
    for src, v in sorted(sm.items(), key=lambda kv: kv[1]["brier"]):
        vs = v.get("vs_kalshi")
        parts.append(f"{names.get(src, src)} {v['brier']:.3f} ({v['n']} games"
                     + (f", {'more' if vs > 0 else 'less'} accurate than Kalshi" if vs else "") + ")")
    return "Brier score, lower is better: " + "; ".join(parts) + "."


def _as_auto(fn):
    """Automatic cash-outs/hedges you turned on don't stop to ask about the backup key."""
    def run(*a, **k):
        AUTO.on = True
        try:
            return fn(*a, **k)
        finally:
            AUTO.on = False
    run.__name__, run.__doc__ = fn.__name__, fn.__doc__
    return run


auto_sell_now = _as_auto(auto_sell_now)
autosell_pass = _as_auto(autosell_pass)


if __name__ == "__main__":
    launch()
