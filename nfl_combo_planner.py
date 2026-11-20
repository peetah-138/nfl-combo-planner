#!/usr/bin/env python3
"""
nfl_combo_planner.py - plan Kalshi NFL combos for a weekend slate.
Read-only: uses Kalshi's public market data (and, optionally, sportsbook odds
from the-odds-api.com). It never places a bet.

Pythonista on iPhone: tap Run, set the sliders and switches, tap Build.
Everything is remembered. No need to edit anything in this file.
"""
import csv, datetime as dt, html, itertools, json, math, os, random, re, statistics, sys, threading, time
from collections import defaultdict
from urllib.parse import quote, unquote
import requests

SEED = None  # leave as is
VERSION = "2026.11.18.118"
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
    "take_profit": 0,     # auto cash-out: sell once Kalshi's offer reaches this % of the payout (0 = off)
    "tp_v2": False,       # (set once: the old 75% take-profit default switched off in favor of smart selling)
    "lock_trail": True,   # auto cash-out: after a big run-up, sell if the offer falls 20% from its high (still a profit)
    "stop_loss": False,   # manual override: auto cash-out may sell below what you paid when a game turns against you
                          # (the app also learns a loss cut per league, see smart_tune; this switch is separate)
    "smart_sell": True,   # auto cash-out: weighs the offer against the risk of holding, by sport (on top of take profit)
    "panel_budget": 40,   # the daily panel: most to spend on one day's panel
    "panel_live": True,   # the daily panel may include games already under way, priced live (Pete opted in)
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
    "killer_mode": "watch",  # Mac buys killer deals by itself: "off", "watch" (only records), "on"
    "maker_mode": "watch",   # Mac keeps standing buy orders under fair: "off", "watch" (only records), "on"
    "hub_ui": True,       # with the Mac reachable, open Combo Hub's screens inside this app
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
DAY_ORDER = ["Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Monday", "Today", "Tomorrow"]
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
    # AHL: the NHL's top minor league. Hockey shapes (short combos, a one-goal game swings), its own tuning;
    # a sportsbook line is required; ESPN has no AHL scoreboard, so live scores come from the league's own feed.
    "ahl": {"name": "AHL", "short": "AHL", "icon": "🏒", "series": "KXAHLGAME", "odds": "icehockey_ahl",
            "espn": None, "espn_q": {}, "slate": "day", "game_hours": 2.75, "periods": 3, "full": False,
            "teams": None, "require_line": True,
            "settings": "combo_settings_ahl.json", "latest": "combos_latest_ahl.html",
            "defaults": {"budget": 25, "full_count": 0, "mix_v3": True, "upsets_min": 1, "upsets_max": 2,
                         "safer_count": 2, "safer_min": 2, "safer_max": 2, "middle_count": 2, "middle_min": 3,
                         "middle_max": 3, "moonshot_count": 1, "moonshot_min": 4, "moonshot_max": 5}},
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
SHARED_KEYS = ("kalshi_key_id", "odds_key", "bankroll", "auto_cash", "cash_every", "ride", "tp_follow", "tp_auto", "tp_ladder", "watcher_code", "auto_sell", "auto_cap", "auto_hedge", "hedge_cap", "prefer_hedge", "size_auto", "notify_value", "notify_price", "notify_cash", "notify_news", "killer_mode", "maker_mode", "hub_ui", "refresh_secs", "take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "panel_live", "tp_v2")


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
    return {"Sunday": True, "Wednesday": CFG["thursday"], "Thursday": CFG["thursday"], "Friday": CFG["thursday"],
            "Saturday": CFG["saturday"], "Monday": CFG["monday"], "Today": True, "Tomorrow": True}


def day_tag(d):
    return "" if d in ("Today", "Tomorrow") else d[:3]
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
try:                                                     # Pete's day boundaries, daylight saving included
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:                                        # no time-zone data (some iOS builds): standard time
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
    if not CFG.get("tp_v2"):                      # smart selling replaces the fixed take-profit (Pete's call):
        if CFG.get("take_profit") == 75:          # the old default goes to Off; a level he picks himself stays
            CFG["take_profit"] = 0
        CFG["tp_v2"] = True
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
    """Write all at once (temp file, then swap), so another copy reading it never sees half a file."""
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        try:
            os.remove(tmp)
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


def week_games(markets, loose=False, weeks=1):
    """This NFL week's games (Wed-Mon around the coming Sunday), or for daily leagues today's
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
        day_of = {sunday + dt.timedelta(days=d): n for d, n in zip(range(-4, 2), DAY_ORDER)}
        if today.weekday() == 0:                 # Monday: tonight's game still belongs to the
            day_of.setdefault(today, "Monday")   # week that just ended, so keep it in view
        for w in range(1, weeks):                # longer plays: the following week(s) too
            for d, n in list(day_of.items()):
                day_of.setdefault(d + dt.timedelta(days=7 * w), n)
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


def devig(implied):
    """A sportsbook's implied chances (they add up to more than 100%) -> fair chances. Power method:
    finds k with sum(p^k) = 1, which takes more of the book's cut off long shots than favourites,
    matching how books actually shade lines (the favourite-longshot bias). Plain scaling as a fallback."""
    ps = [p for p in implied if p and p > 0]
    if len(ps) != len(implied) or not ps:
        return implied
    tot = sum(ps)
    if not 1.0 < tot < 1.25:
        return [p / tot for p in ps]
    lo, hi = 1.0, 3.0
    for _ in range(50):
        k = (lo + hi) / 2
        if sum(p ** k for p in ps) > 1:
            lo = k
        else:
            hi = k
    out = [p ** ((lo + hi) / 2) for p in ps]
    t2 = sum(out)
    return [p / t2 for p in out]


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
            fv = devig([h, a] + ([d] if d else []))
            return fv[0], fv[1], (fv[2] if d else None), (o.get("provider") or {}).get("name") or "ESPN"
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
    fetched = time.time()                         # when this line was read: a game already under way has a live line
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(fetched))
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
                fair_all = devig(inv)
                for o, p in zip(outs, fair_all):
                    if o.get("name", "").lower() == "draw":
                        continue                  # teams only; the draw is 1 minus the two
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
                "day": espn_day(ev.get("commence_time")), "opp": away if team == home else home,
                "at": fetched, "inplay": bool(ev.get("commence_time")) and ev["commence_time"] <= now_iso})
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
        for i, (s, n) in enumerate(zip(sides, names)):
            s["book_name"] = n if src else None
            g = bg[i] if src and BOOK_GAMES and all(bg) else None   # a line read after the start is a live line
            s["line_at"], s["line_live"] = (g.get("at"), bool(g.get("inplay"))) if g else (None, False)
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


WINNER_SERIES = ("KXAHLGAME", "KXNFLGAME", "KXNCAAMBGAME", "KXNBAGAME", "KXNHLGAME", "KXNCAAFGAME", "KXNCAAWBGAME",
                 "KXEUROLEAGUEGAME", "KXUFCFIGHT", "KXATPMATCH") + tuple(['KXEPLGAME', 'KXLALIGAGAME', 'KXSERIEAGAME', 'KXBUNDESLIGAGAME', 'KXLIGUE1GAME', 'KXMLSGAME', 'KXLIGAMXGAME'])


def winners_only(legs):
    return all((l["ticker"] or "").startswith(WINNER_SERIES) for l in legs)


def week_of(ticker):
    d = game_date({"event_ticker": ticker})
    if not d:
        return None
    if (ticker or "").upper().startswith(("KXNCAAMB", "KXNBA", "KXNHL", "KXAHL", "KXNCAAWB", "KXEUROLEAGUE", "KXATP")):
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


ACCT_POS = {"at": 0, "items": []}      # every position from the last account read (singles and spreads too)


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
        ACCT_POS.update(at=time.time(), items=positions)
        bal = account_get(key, key_id, "/portfolio/balance")
    except (ValueError, PermissionError) as err:
        return None, None, str(err)
    except (requests.RequestException, OSError) as err:
        code = getattr(getattr(err, "response", None), "status_code", None)
        why = "Kalshi asked us to slow down" if code == 429 else f"Kalshi said {code}" if code else type(err).__name__
        return None, None, f"Couldn't reach your Kalshi account just now ({why}). Showing what's saved."

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
            "<div class='side'>"
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
            + "<span class='muted' style='font-weight:400'> · see all</span></span></summary>" + decision_html(c["legs"]) + "<ol>")
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
                   "planner or your watcher is watching before games start.</div>")
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
            + ("<div class='muted' style='font-size:13px;margin-top:4px'>Your cash-outs: "
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
        body.append(edge_html(pi["stats"], f"From your {wname()}, which records every kickoff price · updated "
                              + dt.datetime.fromtimestamp(pi["stats"]["at"]).strftime("%-I:%M %p")))
    else:
        body.append(edge_html(edge_stats(acct), "From this phone: kickoff prices are recorded only while the "
                              "planner is open before games, so the watcher's report is more complete."))
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
 old.forEach(function(c){if(out.indexOf(c)<0&&c.id!=='toast'&&String(c.id||'').indexOf('cw')!==0&&c.parentNode===a)a.removeChild(c);});
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
            if kind == "tap":                         # a light tap for ordinary buttons
                g = ObjCClass("UIImpactFeedbackGenerator").alloc().initWithStyle_(0)
                g.prepare()
                g.impactOccurred()
                return
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
        if url.startswith("combo://hubweb"):
            import threading
            webview.evaluate_javascript("toast('Opening Combo Hub…')")
            threading.Thread(target=open_hub_web, args=(webview,), daemon=True).start()
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
        notify(f"🖥 Your {wname()} watcher stopped checking in. This phone is handling alerts and auto cash-out "
               f"while the planner is open. Check the {wname()}'s power and network.")
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


# ---------------------------------------------------------------- the stop-loss switch, guarded (issue #27)
# The manual "sell at a loss" switch (off by default) only lifts auto cash-out's "never below what you paid" guard
# once ALL of these hold for a pick in the combo: its game is really under way on a fresh score feed (no feed or a
# stale one: never), late enough in the game, not at halftime or a break, the pick has fallen a long way from its
# chance before the game (and is now under 50%), and that has held on 3+ checks in a row over at least 3 minutes.
# How late and how big a fall are learned league by league (smart_tune); they start conservative and only a
# league's own record can loosen them below the start.
SL_DEFAULT = {"prog": 0.50, "drop": 0.20}      # at least half the game played; at least 20 points under its pregame chance
SL_BOUNDS = {"prog": (0.35, 0.90), "drop": (0.10, 0.45)}
SL_STEP = 0.05
SL_MIN_N, SL_MIN_GAIN = 50, 0.02               # combos with recorded game prices before a league's own settings move
SL_CHECKS, SL_SPAN, SL_GAP = 3, 180, 300       # 3+ checks in a row, spanning 3+ minutes, none more than 5 minutes apart
SL_FEED_AGE = 150                              # a score older than this (seconds) is stale: no loss sale


def stoploss_params(tickers):
    """How late in the game, and how big a fall from the pregame chance, the stop-loss switch needs for this bet:
    its league's own learned settings once it has enough results, else its sport's, else everyone's, else the
    conservative start. Borrowed settings can only make it stricter, never looser than the start."""
    d = smart_table()
    k = bet_key(tickers)
    sport = ticker_sport(next(iter(tickers), "") or "") if k != "mix" else None
    for key in (k, sport, "all"):
        e = d.get(key) if key else None
        if e and e.get("sl_n", 0) >= SL_MIN_N and e.get("sl_prog") is not None:
            out = {"prog": float(e["sl_prog"]), "drop": float(e.get("sl_drop", SL_DEFAULT["drop"])), "key": key}
            if key != k:
                out.update(prog=max(out["prog"], SL_DEFAULT["prog"]), drop=max(out["drop"], SL_DEFAULT["drop"]))
            return out
    return dict(SL_DEFAULT, key=None)


def score_age(code, now=None):
    """Seconds since this league's scores were last fetched successfully (a failed fetch keeps the old copy)."""
    now = now or time.time()
    at = (SCORES_BY.get(code) or {}).get("at", 0)
    if code == LEAGUE["code"]:
        at = max(at, SCORES.get("at", 0))
    return now - at if at else 1e9


def at_break(sc):
    """Halftime, an intermission or the end of a period (the book thins and prices wander)."""
    det = str(sc.get("detail") or "")
    return bool(sc.get("brk")) or det == "Half" or det.startswith("End") or \
        bool(re.search(r"\b0:00$", det)) or bool(re.search(r"\b(Q|P|H)\d+ 0\.0$", det))


def game_played(sc):
    """Share of the game played (0..1) from the score feed's period and clock, or None when it can't say."""
    if not sc or sc.get("state") != "in" or sc.get("frac") is None:
        return None
    return round(1 - float(sc["frac"]), 3)


def fresh_live_score(ticker, side, now=None):
    """This pick's game on a fresh score feed, while it's in play: (score, '') or (None, why not). Shared by every
    guard that acts on a live game (the stop-loss switch, the learned loss cut, auto-hedge)."""
    sc = leg_score({"ticker": ticker, "side": side})   # never Kalshi's live data (display only)
    if not sc:
        return None, "no score feed"
    if score_age(ticker_sport(ticker) or "", now) > SL_FEED_AGE:
        return None, "score feed stale"
    if sc.get("state") != "in":
        return None, "game not under way"
    return sc, ""


def stop_loss_leg(ticker, side, pre, now_ch, pr, now=None):
    """Whether one pick passes every stop-loss guard right now: (True, '') or (False, why not)."""
    sc, why = fresh_live_score(ticker, side, now)
    if not sc:
        return False, why
    if pre is None or now_ch is None:
        return False, "no pregame chance"
    if at_break(sc):
        return False, "halftime or a break"
    played = game_played(sc)
    if played is None or played < pr["prog"]:
        return False, "too early in the game"
    if now_ch >= 0.5 or pre - now_ch < pr["drop"]:
        return False, "not far enough below its pregame chance"
    return True, ""


def _sl_confirm(key, hit, why, now):
    """The 'held on SL_CHECKS checks in a row spanning SL_SPAN seconds, none more than SL_GAP apart' part of the
    loss guards, counted under `key` (one count per bet and per kind of loss sale). Any miss starts it again."""
    streak = MINE.setdefault("sl_streak", {})
    seen = streak.get(key) or []
    if not hit:
        streak.pop(key, None)
        return False, why
    if seen and now - seen[-1] > SL_GAP:
        seen = []
    seen = (seen + [now])[-20:]
    streak[key] = seen
    if len(seen) < SL_CHECKS or now - seen[0] < SL_SPAN:
        return False, "waiting to confirm the drop"
    return True, ""


def stop_loss_check(t, h, now=None, also=True, key=None):
    """The guard for selling a combo at a loss (the stop-loss switch, and the learned loss cut), called once per
    auto cash-out check: (ready, why not). Every pick already playing must have a fresh feed; one of them must pass
    every guard; `also` (the caller's own trigger, e.g. 'the combo is under the learned cut-off') must hold too; and
    all that must have held on SL_CHECKS checks in a row spanning SL_SPAN seconds (counted under `key`, default
    the combo). Any miss starts the count again."""
    now = now or time.time()
    need = [(side, tk) for (side, tk), _ in h.get("need") or []]
    pr = stoploss_params([tk for _, tk in need])
    hit, why = False, "no pick playing"
    for side, tk in need:
        pre = (h.get("pre_of") or {}).get(tk)
        ch = (h.get("ch_of") or {}).get(tk)
        ok, w = stop_loss_leg(tk, side, pre, ch, pr, now)
        if w in ("no score feed", "score feed stale"):
            try:
                st = leg_start({"ticker": tk, "side": side}, {})
            except Exception:
                st = None
            if st is None or st.timestamp() <= now:
                hit, why = False, w                     # a game on (or maybe on) with no fresh score: never
                break
        if ok:
            hit = True
        elif not hit:
            why = w
    if hit and not also:
        hit, why = False, "not under the cut-off"
    return _sl_confirm(key or t, hit, why, now)


def single_pre(x):
    """A single bet's chance before its game: the last one seen before it started (kept while the app runs), else,
    for a game-winner, the saved pregame chance. None when unknown, and then a loss cut never fires."""
    v = (MINE.get("pre_single") or {}).get(x.get("t"))
    if v is None and x.get("kind") == "win":
        p = load_json(PREGAME, {}).get(x.get("t"))
        if p is not None:
            v = p if (x.get("side") or "yes") == "yes" else 1 - p
    return v


def cut_loss_single_check(x, loss, now=None):
    """The learned loss cut's guard for a single bet, spread or total, called once per auto cash-out check: the same
    guards as the stop-loss switch (late in the game by the league's learned share, a fresh score, not at a break, at
    least the league's learned fall below the pregame chance, under 50%) plus 'under the cut-off', all held on 3+
    checks over 3+ minutes. Returns (ready, why not)."""
    now = now or time.time()
    leg = _score_leg(x["t"], x.get("kind") or "win", x.get("side") or "yes", x.get("sport") or "")
    q = x.get("chance")
    ok, why = stop_loss_leg(leg["ticker"], leg["side"], single_pre(x), q, stoploss_params([x["t"]]), now)
    if ok and not (loss and q is not None and q <= loss):
        ok, why = False, "not under the cut-off"
    return _sl_confirm("cut:" + x["t"], ok, why, now)


def note_cut_held(t, label, why, guard, hedge=False):
    """A learned loss cut (or, with hedge=True, an auto-hedge) that the guards held back: logged once per bet and
    reason (for Results › Selling)."""
    if len(MINE.setdefault("cut_told", {})) > 500:
        MINE["cut_told"].clear()
    told = MINE["cut_told"].setdefault(("hedge:" if hedge else "") + t, set())
    if not guard or guard in told:
        return
    told.add(guard)
    log_decision(dict({"combo": label, "ticker": t, "why": why, "result": "held", "guard": guard},
                      **({"hedge": True} if hedge else {})))


# ---------------------------------------------------------------- auto-hedge, guarded (issue #27)
# Auto-hedge (with Auto cash-out on) buys the other side of a combo's last game instead of an already-chosen sale.
# Before it buys, all of these must hold: the last game is in play on a fresh score (not missing or stale), not at
# halftime or a break, the hedge locks in at least what the combo cost, and all that held on 3+ checks in a row over
# 3+ minutes (the same count as the loss guards). Then the order book is read again and the sums are redone on that
# price. While it's confirming, the sale waits; if any other guard fails, it cashes out as if auto-hedge were off.
HEDGE_GAP = 0.06                                   # the widest bid/ask gap on the hedge side it will buy into


def hedge_guard(t, h, hg, now=None):
    """The auto-hedge guards for combo `t` with hedge `hg` (from hedge_for), called once per check where the hedge
    beats the cash-out: (ready, why not). Shares the loss guards' fresh-score and confirmation helpers."""
    now = now or time.time()
    need = h.get("need") or []
    hit, why = False, "not down to one pick"
    if len(need) == 1:
        (side, tk), _ = need[0]
        sc, why = fresh_live_score(tk, side, now)
        hit = sc is not None
        if hit and at_break(sc):
            hit, why = False, "halftime or a break"
        if hit and hg["locked"] < h["cost"]:
            hit, why = False, "wouldn't lock in what you paid"
    ready, why = _sl_confirm("hedge:" + t, hit, why, now)
    return ready, ("waiting to confirm" if why == "waiting to confirm the drop" else why)


def hedge_fresh(t, h, whole):
    """Re-read the hedge side's order book right before buying and redo the sums on that price: (hedge, '') when it
    still beats the cash-out, fits the cap and locks in at least the combo's cost, else (None, why not)."""
    hg = hedge_for(t)
    bk = book_depth(hg["ticker"], max_age=0) if hg and hg.get("n") else None
    if not bk or not bk.get("ask"):
        return None, "no fresh price for the hedge"
    if bk.get("spread") is None or bk["spread"] > HEDGE_GAP + 1e-9:
        return None, "hedge side's order book too thin"
    hg = hedge_for(t, price=bk["ask"])
    if not hg or not hg.get("n"):
        return None, "no fresh price for the hedge"
    if hg["cost"] > float(CFG.get("hedge_cap", 100)):
        return None, "over the hedge cap at the fresh price"
    if not hedge_beats(hg, whole):
        return None, "no longer beats the cash-out at the fresh price"
    if hg["locked"] < h["cost"]:
        return None, "wouldn't lock in what you paid at the fresh price"
    return hg, ""


def hedge_beats(hg, whole):
    """Whether hedging locks in enough compared with the whole cash-out offer `whole`."""
    if CFG.get("prefer_hedge", True):
        return hg["locked"] >= whole * 0.95
    return hg["locked"] >= whole + 0.5


def hedge_unsure(t):
    """A hedge on this combo whose outcome is unknown: marked 'check', never retried, and auto cash-out leaves the
    combo alone until you look."""
    return bool((load_json(HEDGES, {}).get(t) or {}).get("check"))


def swing_lambda(h):
    """How much the risk of holding counts, from the picks still to play: swingier sports (a one-goal hockey
    lead) count more; a game that's mostly played counts less (time left, square-rooted: half the game left
    is ~70% of the swing); between games of a slate combo, with a pick already won, a checkpoint counts more."""
    vols = []
    for (side, tk), _ in h.get("need") or []:
        sw = SWING.get(ticker_sport(tk) or "", 1.0)
        sc = leg_score({"ticker": tk, "side": side}) or {}
        if sc.get("state") == "in" and sc.get("frac") is not None:
            sw *= math.sqrt(max(sc["frac"], 0.02))
        vols.append(sw)
    lam = 0.35 * (sum(vols) / len(vols) if vols else 1.0)
    live = any(lv for _, lv, _ in h.get("legs_left") or [])
    checkpoint = not live and h.get("won_some") and not h.get("progressed")
    return (lam * 1.3, "checkpoint") if checkpoint else (lam, "")


GAME_SD = {"nhl": 2.4, "ahl": 2.5, "soccer": 1.9, "mls": 1.9, "epl": 1.9}      # final-margin spread (goals) for low scorers
SCORE_UNIT = {"nhl": (1, "goal"), "ahl": (1, "goal"), "soccer": (1, "goal"), "mls": (1, "goal"), "epl": (1, "goal"), "nfl": (7, "touchdown"),
              "ncaaf": (7, "touchdown"), "nba": (6, "6-0 run"), "ncaamb": (6, "6-0 run"), "ncaawb": (6, "6-0 run")}


def what_if(ticker, chance, side="yes"):
    """How this pick's chance would move on the next score either way: {'unit', 'up', 'down'} or None.
    The current price already says how strong the lead is; a score shifts the margin by one unit against
    the spread of what's left (full-game spread x square root of the time left)."""
    code = ticker_sport(ticker) or ""
    if code not in SCORE_UNIT or chance is None or not 0.005 < chance < 0.995:
        return None
    sc = leg_score({"ticker": ticker, "side": side}) or {}
    if sc.get("state") != "in" or sc.get("frac") is None:
        return None
    g, unit = SCORE_UNIT[code]
    sd = (GAME_SD.get(code) or MARGIN_SD.get(code) or 12.0) * math.sqrt(max(sc["frac"], 0.02))
    nd = statistics.NormalDist()
    z = nd.inv_cdf(chance)
    return {"unit": unit, "up": round(nd.cdf(z + g / sd), 4), "down": round(nd.cdf(z - g / sd), 4)}


def recap(day=None):
    """Yesterday in one card: the panel's bets, combos that finished, and the streak of days up."""
    day = day or (dt.datetime.now(PACIFIC) - dt.timedelta(days=1)).date().isoformat()
    out = {"day": day, "bets": [], "pl": 0.0, "won": 0, "lost": 0}
    p = {"items": day_items(day)}
    for c in p["items"]:
        if c.get("result"):
            out["bets"].append({"what": bet_text(c), "kind": c["kind"],
                                "pl": c["pl"], "chance": c["chance"]})
    if STORE["db"]:
        start = dt.datetime.fromisoformat(day).replace(tzinfo=PACIFIC).timestamp()
        mine = {c.get("market") for c in (p or {}).get("items", []) if c.get("market")}
        for r in store_rows("select combo, cost, pays, back, status, legs from bets where settled >= ? and settled < ?",
                            (start, start + 86400)):
            if r["combo"] in mine:
                continue                               # a panel combo: already counted above
            got = r["back"] if r["status"] == "cashed" else r["pays"] if r["status"] == "won" else 0
            out["bets"].append({"what": f"Combo ({len(json.loads(r['legs'] or '[]'))} picks)", "kind": "combo",
                                "pl": round((got or 0) - r["cost"], 2), "status": r["status"]})
    out["pl"] = round(sum(b["pl"] for b in out["bets"]), 2)
    out["won"] = sum(1 for b in out["bets"] if b["pl"] > 0)
    out["lost"] = sum(1 for b in out["bets"] if b["pl"] <= 0)
    if out["bets"]:
        out["best"] = max(out["bets"], key=lambda b: b["pl"])
        out["worst"] = min(out["bets"], key=lambda b: b["pl"])
        sure = [b for b in out["bets"] if b.get("chance") and b["chance"] >= 0.7 and b["pl"] < 0]
        long_ = [b for b in out["bets"] if b.get("chance") and b["chance"] < 0.45 and b["pl"] > 0]
        out["note"] = ("A likely one missed: " + sure[0]["what"] + ". That happens about a third of the time at 70%."
                       if sure else "A long shot came in: " + long_[0]["what"] + "." if long_ else "")
    streak, d = 0, dt.date.fromisoformat(day)
    for _ in range(30):                                # days up in a row, ending yesterday
        q = day_items(d.isoformat())
        pl = sum(c.get("pl") or 0 for c in q if c.get("result"))
        if not q or pl <= 0:
            break
        streak += 1
        d -= dt.timedelta(days=1)
    out["streak"] = streak
    return out


TP_MIN_GAIN = 1.25       # take profit only with at least 25% over what you paid
TRAIL_ARM, TRAIL_DROP = 0.60, 0.20   # lock in: armed once the offer reached 60% of the payout (and 1.5x cost)


def take_profit_reason(t, h, cut_ok=False):
    """Whether Pete's profit rules say sell this combo now: "take profit" when the offer reaches his
    take-profit % of the payout, or "lock in" when, after a big run-up, it has fallen 20% from its
    high but is still a clear profit. A learned "cut loss" also needs `cut_ok`: the loss guards held
    (stop_loss_check under "cut:<ticker>", run once per check by auto_sell_now); without it, never. Tracked on a steady estimate (live chance x payout x Kalshi's
    usual discount) so a one-off quote can't fake a high or a drop; the real offer is checked before
    any sale. Returns (reason, the least whole-combo offer to accept) or (None, 0)."""
    if not h or h.get("left", 1) <= 0 or not h.get("pays"):
        return None, 0.0
    live = any(lv for _, lv, _ in h.get("legs_left") or [])
    est = kalshi_discount(live) * h["p"] * h["pays"]
    o = MINE["cash"].get(t) or {}
    real = o["offer"] / max(o.get("frac", 1.0), 0.01) if o.get("offer") and o.get("rfq") not in (None, "estimate") \
        and time.time() - o.get("at", 0) <= offer_life() else 0.0
    peak = MINE.setdefault("peak", {})
    peak[t] = max(peak.get(t, 0.0), est)
    tp = float(CFG.get("take_profit") or 0) / 100
    floor = max(tp * h["pays"], TP_MIN_GAIN * h["cost"])
    hits = []
    if tp and max(est / 0.9, real) >= floor:
        hits.append(("take profit", floor))
    pr = smart_params([tk for (_, tk), _ in h.get("need") or []])
    rl = ride_lam()
    if CFG.get("smart_sell", True) and rl is not None:  # nimble: lock in when that beats the risk of holding
        q, P = h["p"], h["pays"]
        lam, why_note = swing_lambda(h)
        lam *= pr["lam"] * rl
        hold_risky = q * P - lam * P * math.sqrt(max(q * (1 - q), 0))
        floor2 = max(hold_risky, pr["floor"] * h["cost"])
        if q >= 0.5 and max(est / 0.95, real) >= floor2:
            hits.append(("checkpoint" if why_note else "smart", floor2))
        if pr["loss"] and live and h["p"] <= pr["loss"] and cut_ok:  # learned for this league, and every loss guard held
            hits.append(("cut loss", 0.02 * h["cost"]))
    if hits:
        return min(hits, key=lambda x: x[1])
    if CFG.get("lock_trail", True) and peak[t] >= max(TRAIL_ARM * h["pays"], 1.5 * h["cost"]) \
            and est <= (1 - TRAIL_DROP) * peak[t] and max(est, real) >= 1.1 * h["cost"]:
        return "lock in", 1.1 * h["cost"]
    return None, 0.0


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
        cands = [(t, f, "plan") for t, f in sorted(plan["acts"].items(), key=lambda x: -x[1]) if f]
        asked = MINE.setdefault("tp_asked", {})
        cands = [c for c in cands if not hands_off(c[0])]
        sl_ready = {}                                     # the stop-loss switch: only once every guard holds
        if CFG.get("stop_loss"):
            for t, h in list(MINE["hold"].items()):
                sl_ready[t] = stop_loss_check(t, h)[0]
        cut_ready = {}                                    # the learned loss cut: the same guards, counted apart
        if CFG.get("smart_sell", True) and ride_lam() is not None:
            for t, h in list(MINE["hold"].items()):
                loss = smart_params([tk for (_, tk), _ in h.get("need") or []])["loss"]
                if not loss:
                    continue
                trig = any(lv for _, lv, _ in h.get("legs_left") or []) and h["p"] <= loss
                cut_ready[t], gw = stop_loss_check(t, h, also=trig, key="cut:" + t)
                if trig and not cut_ready[t]:
                    note_cut_held(t, h.get("label", t), "cut loss", gw)
        for t, h in list(MINE["hold"].items()):          # Pete's profit rules, on every live combo
            if any(c[0] == t for c in cands) or hands_off(t):
                continue
            why, floor = take_profit_reason(t, h, cut_ready.get(t, False))
            if why and time.time() - asked.get(t, 0) >= 90:
                asked[t] = time.time()
                cands.append((t, 1.0, why))
        for t, f, why in cands:
            h = MINE["hold"].get(t)
            if hedge_unsure(t):
                continue                                  # a hedge with an unknown outcome: hands off until checked
            o = fresh_offer(t) if why == "plan" else (MINE["cash"].get(t) or {"offer": 0.01, "frac": 1.0, "rfq": "estimate"}) if h else None
            if not (f and h and o) or t in MINE.get("selling", set()):
                continue
            if why == "plan":
                if not h.get("won_some"):
                    continue
                thr = wait_threshold(t)
            else:
                thr = take_profit_reason(t, h, cut_ready.get(t, False))[1]
                if not thr:
                    continue
            if why == "plan" and o["offer"] / max(o.get("frac", 1.0), 0.01) < thr:
                continue
            if why != "plan" and o.get("rfq") not in (None, "estimate") and time.time() - o.get("at", 0) <= offer_life() \
                    and o["offer"] / max(o.get("frac", 1.0), 0.01) < CASH_SLIP * thr:
                continue                                  # a real offer just came in below the line
            if why != "plan" and (o.get("rfq") in (None, "estimate") or time.time() - o.get("at", 0) > offer_life()):
                o = dict(o, rfq="estimate")
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
            rec = {"combo": h["label"], "ticker": t, "offer": round(o["offer"], 2), "cut_off": round(thr, 2), "why": why,
                   "chance": round(h["p"], 4), "cost": round(h["cost"], 2), "pays": h["pays"],
                   "picks_left": [round(c, 3) for c, _, _ in h.get("legs_left") or []]}
            if sold_today() >= int(CFG.get("auto_cap", 5)):
                log_decision(dict(rec, result="skipped", why="daily cap reached"))
                if MINE.get("cap_told") != dt.date.today().isoformat():
                    MINE["cap_told"] = dt.date.today().isoformat()
                    out.append(f"🤖 Auto cash-out reached today's cap of {CFG.get('auto_cap', 5)} sales. "
                               f"{h['label']} qualifies too: open the planner to cash it out yourself.")
                continue
            below = o["offer"] < h["cost"] * o.get("frac", 1.0)
            if below and why != "cut loss" and not (CFG.get("stop_loss") and sl_ready.get(t)):
                log_decision(dict(rec, result="skipped", why="below what you paid"))
                continue
            if below and why != "cut loss":
                rec["stop_loss"] = True
            hg = hedge_for(t) if CFG.get("auto_hedge") else None
            whole = o["offer"] / max(o.get("frac", 1.0), 0.01)
            better = hedge_beats(hg, whole) if hg and hg.get("n") else False
            if better:
                if hg["cost"] > float(CFG.get("hedge_cap", 100)):
                    rec["hedge_skipped"] = f"hedge would cost {money(hg['cost'])}, over the {money(CFG.get('hedge_cap', 100))} cap"
                    better = False
            if better:
                ready, gw = hedge_guard(t, h, hg)
                if ready:
                    hg, gw = hedge_fresh(t, h, whole)
                    ready = hg is not None
                if not ready:
                    if gw == "waiting to confirm":
                        continue                # the sale waits while the hedge is confirmed (3+ checks, 3+ minutes)
                    note_cut_held(t, h["label"], why, gw, hedge=True)
                    rec["hedge_skipped"] = "held back by the guards: " + gw
                else:
                    if t in MINE["cash"]:
                        drop_cash(t)            # not selling: release the cash-out request
                    msg = place_hedge(t, hg=hg, auto=True)
                    ok = msg.startswith("✅")
                    unsure = msg.startswith("⚠️")
                    log_decision(dict(rec, result="hedged" if ok else "hedge check" if unsure else "hedge failed",
                                      hedge_cost=round(hg["cost"], 2), locked=round(hg["locked"], 2), note=msg[:140]))
                    if ok:
                        vs = ("more than" if hg["locked"] > whole + 0.5 else "about the same as")
                        out.append(f"🤖 Auto-hedge (Let it ride: {ride_level()[0]}): locks in {vs} the "
                                   f"{money(whole)} cash-out, without the buyer's cut. " + msg)
                        continue
                    if unsure:
                        out.append("🤖 Auto-hedge: " + msg)
                        continue                # never retried, and no sale on top of a hedge that may have filled
            msg = accept_cash(t)
            log_decision(dict(rec, result="sold" if msg.startswith("✅") else "failed", note=msg[:140]))
            lead = {"take profit": f"🤖 Take profit: the offer reached {CFG.get('take_profit')}% of the payout. ",
                    "lock in": "🤖 Locked in a profit: the offer fell 20% from its high. ",
                    "smart": "🤖 Took the profit: locking it in now beats the risk of holding. ",
                    "checkpoint": "🤖 Checkpoint: the early games came through, so it took the profit before the next ones. ",
                    "cut loss": "🤖 Cut a loss: in this league, selling a bet this far behind has done better than holding. "}.get(
                why, "🤖 Auto cash-out (Let it ride: " + ride_level()[0] + "). ")
            if rec.get("stop_loss"):
                lead = ("🤖 Stop-loss (your switch): late in the game a pick fell well below its pregame chance "
                        "and stayed there, so it sold for less than you paid. ")
            out.append(lead + msg)
            if msg.startswith("✅"):
                MINE.get("peak", {}).pop(t, None)
        try:
            out += smart_sell_singles()
        except Exception as err:
            print("smart sell (singles):", type(err).__name__, err)
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


def day_money(mine):
    """What actually finished today: money back from combos that won or were cashed today, what they cost,
    and the profit. "Today" is when the combo finished (the Mac's record of it, else its last game's date),
    not when it was bought, so a combo cashed yesterday with games tomorrow doesn't count today."""
    today = dt.datetime.now(PACIFIC).date()
    when = {}
    if STORE.get("db"):
        for r in store_rows("select combo, settled from bets where settled is not null"):
            try:
                when[r["combo"]] = dt.datetime.fromtimestamp(float(r["settled"]), PACIFIC).date()
            except (TypeError, ValueError, OSError):
                pass
    back = cost = 0.0
    won = cashed = lost = 0
    for a in mine:
        st = a["status"]
        if st not in ("won", "lost", "cashed"):
            continue
        d = when.get(a["ticker"])
        if d is None:
            try:
                d = dt.date.fromisoformat(a.get("week") or "")
            except ValueError:
                continue
            if st == "cashed" and d > today:
                continue                       # sold early, day unknown: don't guess it was today
        if d != today:
            continue
        got = a["back"] if st == "cashed" else a["pays"] if st == "won" else 0.0
        back += got
        cost += a["cost"]
        won += st == "won"
        cashed += st == "cashed"
        lost += st == "lost"
    return {"back": round(back, 2), "cost": round(cost, 2), "pl": round(back - cost, 2),
            "won": won, "cashed": cashed, "lost": lost}


# ---- bets you placed on Kalshi yourself vs. ones the app bought ----
APP_SEEN = {"at": 0, "set": set()}
HELD_FILE = os.path.join(HERE, "held_events.json")


def _app_table():
    store_x("create table if not exists app_bets(ticker text primary key, ts real, how text)")


def mark_app(ticker, how="app"):
    """Remember that the app (panel, Build, standing orders, killer deals, hedges) bought this market."""
    if not (STORE["db"] and ticker):
        return
    try:
        _app_table()
        store_x("insert or ignore into app_bets values(?,?,?)", (ticker, time.time(), how))
        APP_SEEN["at"] = 0
    except Exception as err:
        print("mark_app:", type(err).__name__, err)


def note_app_order(method, path, body):
    """Called for every signed Kalshi request: buys (and combo price requests) are the app's."""
    if method != "POST" or not isinstance(body, dict):
        return
    if path == "/portfolio/orders" and body.get("action", "buy") == "buy":
        mark_app(body.get("ticker"), "order")
    elif path == "/portfolio/events/orders" and body.get("side", "bid") == "bid":
        mark_app(body.get("ticker"), "order")
    elif path == "/communications/rfqs":
        mark_app(body.get("market_ticker"), "combo")


def app_bets():
    """Markets the app bought (None where there's no history store, e.g. the phone)."""
    if not STORE["db"]:
        return None
    if time.time() - APP_SEEN["at"] > 20:
        try:
            _app_table()
            APP_SEEN.update(at=time.time(), set={r["ticker"] for r in store_rows("select ticker from app_bets")})
        except Exception:
            return None
    return APP_SEEN["set"]


def seed_origins(held):
    """The first time: everything already held was bought before this tracking existed, so it counts as the app's."""
    got = app_bets()
    if got is None or "__seeded__" in got:
        return
    for t in list(held) + ["__seeded__"]:
        mark_app(t, "before")


def is_own(t):
    """True for a bet you placed on Kalshi yourself (not through the app)."""
    got = app_bets()
    return bool(got) and "__seeded__" in got and bool(t) and t not in got


SELF_SELL = os.path.join(HERE, "combo_selfsell.json")


def self_sell_set():
    """Bets you've switched to "I'll sell it" on Live: smart sell leaves those alone."""
    return set(load_json(SELF_SELL, {}))


def set_self_sell(t, mine):
    """mine=True: you'll sell this one yourself. False: smart sell watches it (the default for every bet)."""
    d = load_json(SELF_SELL, {})
    if mine:
        d[t] = time.time()
    else:
        d.pop(t, None)
    save_json(SELF_SELL, d)


def hands_off(t):
    """Smart sell (and hedging and take-profit orders) skip a bet you've set to "I'll sell it"."""
    return bool(t) and t in self_sell_set()


def single_sell_reason(x, bid, ask, track=True, cut_ok=False):
    """Smart sell for a single bet, spread or total: the same rules as combos, on Kalshi's order book. A learned
    "cut loss" also needs `cut_ok` (cut_loss_single_check: every loss guard held); without it, never.
    Returns (reason, the least it may sell the whole position for, after fees) or (None, floor shown on Live)."""
    n, cost, q = x.get("n") or 0, x.get("cost") or 0, x.get("chance")
    if not n or bid is None or bid <= 0 or q is None or x.get("state") not in ("live", "pre"):
        return None, 0.0
    net = n * (bid - single_fee(bid))
    t = x["t"]
    peak = MINE.setdefault("peak", {})
    if track:
        peak[t] = max(peak.get(t, 0.0), net)
    hits = []
    tp = float(CFG.get("take_profit") or 0) / 100
    if tp:
        f = max(tp * n, TP_MIN_GAIN * cost)
        if net >= f:
            hits.append(("take profit", f))
    floor2 = 0.0
    pr = smart_params([t])
    rl = ride_lam()
    if CFG.get("smart_sell", True) and rl is not None:
        leg = _score_leg(t, x.get("kind") or "win", x.get("side") or "yes", x.get("sport") or "")
        lam, _ = swing_lambda({"need": [((leg["side"], leg["ticker"]), "")], "legs_left": [(q, x.get("state") == "live", 0)]})
        lam *= pr["lam"] * rl
        floor2 = max(q * n - lam * n * math.sqrt(max(q * (1 - q), 0)), pr["floor"] * cost)
        if q >= 0.5 and net >= floor2:
            hits.append(("smart", floor2))
        if pr["loss"] and x.get("state") == "live" and q <= pr["loss"] and net > 0 and cut_ok:
            hits.append(("cut loss", 0.0))
    if hits:
        return min(hits, key=lambda h: h[1])
    pk = peak.get(t, 0.0)
    if CFG.get("lock_trail", True) and pk >= max(TRAIL_ARM * n, 1.5 * cost) and net <= (1 - TRAIL_DROP) * pk \
            and net >= 1.1 * cost:
        return "lock in", 1.1 * cost
    return None, floor2


SINGLE_RESTING = {"at": 0, "t": set()}


def resting_single_sells():
    """Singles with a sell order already waiting on Kalshi (a sell-early favorite's exit, or one you placed)."""
    if time.time() - SINGLE_RESTING["at"] > 60:
        try:
            data = kalshi_send("GET", "/portfolio/orders", params={"status": "resting", "limit": 200}) or {}
            SINGLE_RESTING.update(at=time.time(), t={o.get("ticker") for o in data.get("orders", [])
                                                      if o.get("action") == "sell" and not is_combo(o.get("ticker"))})
        except Exception:
            return None
    return SINGLE_RESTING["t"]


def sell_single_now(t, side, n, price):
    """Sell n contracts of a single bet at `price` or better, now or not at all. Returns (sold, error)."""
    import uuid
    body = {"ticker": t, "action": "sell", "side": side, "type": "limit", "count": int(n),
            f"{side}_price": max(1, int(math.floor(price * 100 + 1e-6))), "time_in_force": "immediate_or_cancel",
            "reduce_only": True, "client_order_id": str(uuid.uuid4())}
    if body["count"] < 1:
        return 0, "under one contract"
    try:
        o = (kalshi_send("POST", "/portfolio/orders", body) or {}).get("order") or {}
    except PermissionError:
        return 0, "Kalshi refused. The key needs write (trading) access."
    except RuntimeError as err:
        return 0, f"Kalshi didn't take the order: {err}"
    filled = float(o.get("fill_count_fp") or o.get("fill_count") or
                   (body["count"] - float(o.get("remaining_count") or 0) if o.get("status") == "executed" else 0))
    ACCT_CACHE["at"] = 0
    SINGLES["at"] = 0
    ACCT_POS["at"] = 0
    return filled, None


def smart_sell_singles():
    """Auto cash-out for single bets, spreads and totals (yours or the app's): sells into Kalshi's order book when
    smart sell, take profit or lock-in says so. Skips ones set to "I'll sell it", ones with a sell order already
    waiting, and thin markets where the bid is far below the ask. Returns the messages to send."""
    out = []
    if time.time() - SINGLES["at"] > 180:
        return out                                   # Live hasn't refreshed lately: don't act on old prices
    resting = None
    for x in list(SINGLES["items"]):
        if hands_off(x["t"]) or x.get("state") not in ("live", "pre"):
            continue
        m = SINGLES["mk"].get(x["t"]) or {}
        side = x["side"]
        bid = dollars(m, f"{side}_bid")
        ask = dollars(m, f"{side}_ask")
        cut_ok = False                                # the learned loss cut: only once every loss guard held
        loss = smart_params([x["t"]])["loss"] if CFG.get("smart_sell", True) and ride_lam() is not None else None
        if loss:
            cut_ok, gw = cut_loss_single_check(x, loss)
            if not cut_ok and x.get("state") == "live" and x.get("chance") is not None and x["chance"] <= loss:
                note_cut_held(x["t"], x.get("label", x["t"]), "cut loss", gw)
        why, floor = single_sell_reason(x, bid, ask, cut_ok=cut_ok)
        if not why:
            continue
        if ask and bid and ask - bid > LIVE_SPREAD:
            continue                                  # too thin to sell at a fair price right now
        if resting is None:
            resting = resting_single_sells()
            if resting is None:
                return out
        if x["t"] in resting:
            continue
        rec = {"combo": x["label"], "ticker": x["t"], "offer": round(x["n"] * bid, 2), "cut_off": round(floor, 2),
               "why": why, "chance": x["chance"], "cost": x["cost"], "pays": x["n"], "kind": x["kind"]}
        if sold_today() >= int(CFG.get("auto_cap", 5)):
            log_decision(dict(rec, result="skipped", why="daily cap reached"))
            continue
        sold, err = sell_single_now(x["t"], side, x["n"], bid)
        log_decision(dict(rec, result="sold" if sold else "failed", note=(err or f"{sold:g} sold")[:140]))
        if sold:
            MINE.get("peak", {}).pop(x["t"], None)
            got = sold * (bid - single_fee(bid))
            lead = {"take profit": "🤖 Take profit", "lock in": "🤖 Locked in a profit",
                    "smart": "🤖 Smart sell", "cut loss": "🤖 Cut a loss"}.get(why, "🤖 Smart sell")
            out.append(f"{lead}: sold {x['label']} for about {money(got)} (paid {money(x['cost'])}).")
    return out


def game_event(ev):
    return re.sub(r"(SPREAD|TOTAL)-", "GAME-", ev or "")


def note_held(events):
    events = sorted(e for e in events if e)
    old = load_json(HELD_FILE, {})
    if old.get("events") != events or time.time() - old.get("at", 0) > 300:
        save_json(HELD_FILE, {"at": time.time(), "events": events})


def account_events(max_age=1800):
    """Games you bet on Kalshi yourself (not through the app), so the panel doesn't double up on them."""
    d = load_json(HELD_FILE, {})
    return set(d.get("events") or []) if time.time() - d.get("at", 0) < max_age else set()


SINGLES = {"at": 0, "items": [], "mk": {}}


def _bet_kind(t):
    u = (t or "").upper()
    return "spread" if "SPREAD-" in u else "total" if "TOTAL-" in u else "win" if "GAME-" in u else "other"


def _score_leg(t, kind, side, code):
    """A stand-in game pick for a single/spread/total so leg_score can find its game."""
    head, ev, tail = (t.split("-", 2) + ["", ""])[:3]
    head = re.sub(r"(SPREAD|TOTAL)$", "GAME", head)
    if kind == "spread":
        tail = re.sub(r"\d+$", "", tail)
    if kind == "total":
        teams = sport_teams(code)
        for n in (2, 3, 4):
            if ev[-n:] in teams:
                return {"ticker": f"{head}-{ev}-{ev[-n:]}", "side": "yes"}
        return {"ticker": f"{head}-{ev}-{ev[-3:]}", "side": "yes"}
    return {"ticker": f"{head}-{ev}-{tail}", "side": side}


def _line_num(text):
    m = re.search(r"(?:over|by)\s+([\d.]+)", text or "", re.I)
    return float(m.group(1)) if m else None


def _single_how(kind, side, line, sc):
    """Where a spread, total or single stands right now, in words."""
    if not sc or sc.get("me") is None or sc.get("opp") is None:
        return ""
    me, opp = float(sc["me"]), float(sc["opp"])
    if kind == "spread" and line is not None:
        margin = me - opp                       # sc is from the side this bet needs (leg_score flips for "no")
        need = line if side == "yes" else -line
        good = margin > need
        return f"{'Covering' if good else 'Not covering'} now · {'+' if margin >= 0 else ''}{margin:g}, needs {'more than ' + format(line, 'g') if side == 'yes' else 'to lose by under ' + format(line, 'g') if line else 'to win'}"
    if kind == "total" and line is not None:
        tot = me + opp
        good = tot > line if side == "yes" else tot < line
        return f"{'On track' if good else 'Not on track'} · {tot:g} so far, line {line:g}"
    if kind == "win":
        return "Winning now" if me > opp else "Losing now" if me < opp else "Tied"
    return ""


def open_singles(max_age=30):
    """Every open single bet, spread and total in your Kalshi account, with live scores, for the Live page."""
    if time.time() - SINGLES["at"] < max_age:
        return SINGLES["items"]
    pos = ACCT_POS["items"] if time.time() - ACCT_POS["at"] < 300 else None
    if pos is None:
        key_id = CFG.get("kalshi_key_id", "").strip()
        if not key_id or not os.path.exists(KEYFILE):
            return []
        with open(KEYFILE, encoding="utf-8") as f:
            key = load_private_key(f.read())
        pos = all_positions(key, key_id)
        ACCT_POS.update(at=time.time(), items=pos)
    held = []
    for p in pos:
        t = p.get("ticker") or p.get("market_ticker")
        n = float(p.get("position_fp") or p.get("position") or 0)
        if t and not is_combo(t) and abs(n) > 0.005:
            held.append((t, n, p))
    mk = {}
    for i in range(0, len(held), 50):
        chunk = [t for t, _, _ in held[i:i + 50]]
        try:
            r = requests.get(f"{KALSHI}/markets", params={"tickers": ",".join(chunk)}, timeout=15)
            r.raise_for_status()
            mk.update({m.get("ticker"): m for m in r.json().get("markets", [])})
        except (requests.RequestException, ValueError):
            mk.update({t: SINGLES["mk"][t] for t in chunk if t in SINGLES["mk"]})
    try:                                             # display only: scores for tennis, EuroLeague, UFC
        kalshi_live_kick(klive_events([{"ticker": t, "event": game_event((mk.get(t) or {}).get("event_ticker") or "")}
                                          for t, _, _ in held if not (mk.get(t) or {}).get("result")]))
    except Exception as err:
        print("kalshi live data:", type(err).__name__, err)
    out = []
    for t, n, p in held:
        m = mk.get(t) or {}
        side = "yes" if n > 0 else "no"
        n = abs(n)
        kind = _bet_kind(t)
        code = ticker_sport(t) or "other"
        yes_sub = (m.get("yes_sub_title") or "").strip()
        label = yes_sub if side == "yes" else ((m.get("no_sub_title") or "").strip() or ("Not: " + yes_sub if yes_sub else ""))
        if kind == "win" and side == "yes" and yes_sub and "win" not in yes_sub.lower():
            label = f"{yes_sub} to win"
        bid = dollars(m, "yes_bid") if side == "yes" else dollars(m, "no_bid")
        lp = live_price(m) if m else None
        chance = (lp if side == "yes" else 1 - lp) if lp is not None else (bid or None)
        cost = dollars(p, "market_exposure") or dollars(p, "total_traded")
        res = m.get("result") if m.get("result") in ("yes", "no") else None
        status = (m.get("status") or "").lower()
        sc = None
        try:
            if code in SPORTS and (SPORTS[code].get("espn") or SPORTS[code].get("feed")):
                fetch_scores(code=code)
            sc = leg_score(_score_leg(t, kind, side, code))
        except Exception:
            sc = None
        live = bool(sc) and str(sc.get("state") or "") in ("in", "live")
        state = "done" if res else "over" if status in ("closed", "settled", "finalized", "determined") else \
            "live" if live else "pre"
        rs = None                                   # started, nothing settled it, no live score: say so honestly
        ksc = None                                  # tennis, EuroLeague, UFC: Kalshi's live data, shown only
        if not sc and code in KLIVE_SPORTS:         # (state, and so smart sell, stay exactly as before)
            try:
                ksc = kalshi_score({"ticker": t, "side": side})
            except Exception:
                ksc = None
        if state == "pre":
            ks_detail = (ksc or {}).get("detail", "") if ksc and (ksc.get("me") is None or ksc["state"] == "post") else ""
            rs = safe_run_status(code, start_dt(game_event(m.get("event_ticker") or "")),
                            score_state=(sc or ksc or {}).get("state"), detail=ks_detail)
        dsc = sc or (ksc if ksc and ksc.get("me") is not None and ksc["state"] != "pre" else None)   # the score to show
        team = re.sub(r"\s+(wins by|to win).*$", "", label or "", flags=re.I).strip() or (sc or {}).get("abbr") or t
        out.append({"t": t, "ticker": t, "name": team if kind != "total" else (label or t),
                    "opp": (sc or {}).get("opp_abbr") or "", "live": chance if state == "live" else None,
                    "sc": {k: dsc.get(k) for k in ("me", "opp", "abbr", "opp_abbr", "detail")} if dsc else None,
                    "on": bool(ksc and not sc and ksc["state"] == "in"),       # display: Kalshi's data says it's playing
                    "src": "kalshi" if ksc and not sc else "",
                    "kind": kind, "sport": code, "side": side, "label": label or m.get("title") or t,
                    "game": (m.get("title") or "").strip(), "event": m.get("event_ticker") or "",
                    "n": round(n, 2), "cost": round(cost, 2), "pays": round(n, 2),
                    "worth": round(n * bid, 2) if bid is not None else None,
                    "chance": round(chance, 4) if chance is not None else None, "state": state, "res": res,
                    "score": re.sub(r"<[^>]+>", "", score_line(sc)) if sc and state != "pre" else
                    re.sub(r"<[^>]+>", "", score_line(dsc)) if dsc and dsc["state"] in ("in", "post") else "",
                    "starts": start_label(game_event(m.get("event_ticker") or "")) if state == "pre" and not rs else "",
                    "note": (rs or {}).get("text", ""), "phase": (rs or {}).get("phase", ""),
                    "short": (rs or {}).get("short", ""),
                    "how": _single_how(kind, side, _line_num(yes_sub), sc) if state in ("live", "over") else
                    _single_how(kind, side, _line_num(yes_sub), dsc)       # tennis lines count games, not the sets shown
                    if dsc and not sc and dsc["state"] in ("in", "post") and (code != "tennis" or kind == "win") else "",
                    "url": game_url(_score_leg(t, "win", "yes", code)["ticker"])
                    if _score_leg(t, "win", "yes", code)["ticker"].startswith(tuple(GAME_SLUG)) else ""})
    pre = MINE.setdefault("pre_single", {})          # each single's last chance before its game (loss-cut guard)
    for x in out:
        if x["state"] == "pre" and x.get("chance") is not None:
            pre[x["t"]] = x["chance"]
    for t in [t for t in pre if t not in {x["t"] for x in out}]:
        pre.pop(t, None)
    mine = self_sell_set()
    for x in out:
        x["self"] = x["t"] in mine
        m = mk.get(x["t"]) or {}
        try:
            why, fl = single_sell_reason(x, dollars(m, f"{x['side']}_bid"), None, track=False)
            x["sell_at"] = round(fl, 2) if fl and (x.get("chance") or 0) >= 0.5 else None
        except Exception:
            x["sell_at"] = None
    out.sort(key=lambda x: (x["state"] != "live", x["state"] == "done", x["starts"] or "~"))   # order kept: smart sell walks it
    SINGLES.update(at=time.time(), items=out, mk=mk)
    return out


def live_view(mine, views, plan, chance_one, balance):
    """Everything Combo Hub's Live screen shows, as plain data."""
    import time
    acts = (plan or {}).get("acts") or {}
    for v in views:
        t = v["t"]
        h = MINE["hold"].get(t)
        if not h:
            continue
        o = MINE["cash"].get(t) or {}
        real = fresh_offer(t) if o.get("rfq") != "estimate" else None
        v["hold_value"] = round(h["hold"], 2)
        v["won_some"] = bool(h.get("won_some"))
        v["offer"] = round(o["offer"] / max(o.get("frac", 1.0), 0.01), 2) if o.get("offer") else None
        if v["offer"] is None:                    # no offer asked for yet: what Kalshi usually pays for this
            try:
                v["offer"] = round(kalshi_discount(v["live"]) * v["p"] * v["pays"], 2)
            except Exception:
                pass
        v["offer_real"] = bool(real)
        v["fair_value"] = round(h["p"] * h["pays"], 2)          # what it's worth at the market's own chances
        v["overpay"] = round(v["offer"] / v["fair_value"], 3) if real and v["offer"] and v["fair_value"] > 0 else None
        v["offer_age"] = round(time.time() - o.get("at", 0)) if o.get("at") else None
        f = acts.get(t) or 0
        v["verdict"] = "sell" if f == 1 else "half" if f == 0.5 else "hold"
        try:                                       # the reasoning, in numbers and one sentence
            W = max(CFG["bankroll"], 1) + MINE.get("locked", 0)
            v["hold_ce"] = round(single_value(h["p"], h["pays"], W), 2)
            v["why"] = re.sub(r"<[^>]+>", "", plan_words(t, f, {"offer": v["offer"] or 0, "frac": 1.0}, h, W)) \
                if v["offer"] else ""
        except Exception:
            v["hold_ce"], v["why"] = None, ""
        try:
            v["threshold"] = round(wait_threshold(t), 2) if h.get("won_some") else None
        except Exception:
            v["threshold"] = None
        try:                                       # the cash-out moment: Pete's profit rules say now
            why, floor = take_profit_reason(t, h)
            v["moment"] = {"why": why, "at": round(floor, 2)} if why and (v.get("offer") or 0) >= 0.97 * floor else None
        except Exception:
            v["moment"] = None
        try:
            hg = hedge_for(t)
            v["hedge"] = {k: hg.get(k) for k in ("name", "cost", "locked", "price", "done")} if hg else None
        except Exception:
            v["hedge"] = None
    alive = [v for v in views if v["group"] in ("pending", "won")]
    need = {}
    for v in views:
        if v["group"] != "pending":
            continue
        for lg in v["legs"]:
            if lg["res"]:
                continue
            k = (lg["ticker"], lg["side"])
            x = need.setdefault(k, {"name": lg["name"], "opp": lg["opp"], "sport": lg["sport"], "combos": 0, "pays": 0.0,
                                    "ticker": lg["ticker"],
                                    "state": lg["state"], "score": lg["score"], "sc": lg["sc"], "starts": lg["starts"],
                                    "phase": lg.get("phase", ""), "note": lg.get("note", ""), "short": lg.get("short", ""),
                                    "chance": lg["live"] if lg["live"] is not None else lg["chance"]})
            x["combos"] += 1
            x["pays"] += v["pays"]
    games = sorted(need.values(), key=lambda x: (x["state"] != "live", -x["combos"]))
    try:
        singles = open_singles()
    except Exception as err:
        print("singles on Live:", type(err).__name__, err)
        singles = []
    try:
        seed_origins([v["t"] for v in views if v["group"] == "pending"] + [x["t"] for x in singles])
        mine_sell = self_sell_set()
        for v in views:
            v["own"] = v["group"] == "pending" and is_own(v["t"])
            v["self"] = v["t"] in mine_sell
        for x in singles:
            x["own"] = is_own(x["t"])
            x["self"] = x["t"] in mine_sell
        note_held({game_event(l.get("event") or "") for a in mine if a.get("status") == "pending" and is_own(a["ticker"])
                   for l in a["legs"]} | {game_event(x["event"]) for x in singles if x["own"]})
    except Exception as err:
        print("bet origins:", type(err).__name__, err)
    week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    settled = [a for a in (MINE.get("acct") or mine) if a["status"] in ("won", "lost", "cashed") and (a.get("week") or "") >= week_ago]
    week_pl = sum((a["back"] if a["status"] == "cashed" else a["pays"] if a["status"] == "won" else 0) - a["cost"]
                  for a in settled)
    today = day_money(MINE.get("acct") or mine)
    return {"at": time.time(), "balance": balance, "combos": views, "today": today, "singles": singles,
            "auto_sell": bool(CFG.get("auto_sell")),
            "riding": sum(1 for v in views if v["group"] == "pending"),
            "staked": round(sum(v["cost"] for v in views if v["group"] == "pending"), 2),
            "chance_one": chance_one, "best": max((v["pays"] for v in alive), default=0),
            "cash_now": round(sum(v.get("offer") or 0 for v in views if v["group"] == "pending"), 2),
            "hold_value": round(sum(h["hold"] for h in MINE["hold"].values()), 2),
            "locked": MINE.get("locked", 0), "week_pl": round(week_pl, 2), "games": games[:30],
            "risk": max(games, key=lambda x: (x["combos"], x["pays"])) if games else None,
            "todo": [v["t"] for v in views if v.get("verdict") in ("sell", "half") and v.get("offer_real")]}


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
                continue        # nothing earned yet (no pick won, no big in-game gain): hold for the upside
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
        who = f"your {wname()}" if in_pythonista() and watcher_alive() else "it"
        out.append(f"<div class='muted' style='font-size:13px;margin-top:6px'>🤖 Auto cash-out is on: {who} "
                   + (f"sells by itself if Kalshi offers about {money(thr)} or more." if h.get("won_some") and thr
                      else "waits until a pick in this combo has won.") + "</div>")
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


def hedge_for(ticker, price=None):
    """For a combo down to its last pick: buying the other side of that game so you collect about
    the same whichever team wins. {ticker, name, price, n, cost, locked, done} or None. `price` (a fresh
    ask from the order book) replaces the last board price."""
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
    q = (price if price is not None else buy.get("p")) if buy else None
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


def hedge_unknown(err):
    """Whether a failed hedge order may still have gone through (no answer, a lost connection, a Kalshi server
    error): then it is marked 'check' and never retried."""
    if isinstance(err, PermissionError):
        return False
    if isinstance(err, RuntimeError):
        if "Tap again within" in str(err):
            return False                                  # the backup-key prompt: nothing was sent
        m = re.search(r"\((\d{3})\)\s*$", str(err))
        return "may or may not" in str(err) or not m or m.group(1).startswith("5")
    return True


def place_hedge(ticker, hg=None, auto=False):
    """Buy the other side of the last pick's game, at today's price or not at all (fills now or
    cancels). Runs after you confirm, or from guarded auto-hedge with `hg` priced on a fresh order book.
    An order whose outcome is unknown is marked 'check' (never retried) and the message starts with ⚠️.
    Returns a message."""
    import uuid
    h = MINE["hold"].get(ticker) or {}
    hg = hg or hedge_for(ticker)
    if not hg or not hg.get("n"):
        return "Nothing to hedge on this combo now."

    def unsure(err):
        d = load_json(HEDGES, {})
        d[ticker] = dict(d.get(ticker) or {}, check=int(time.time()), check_ticker=hg["ticker"], name=hg["name"])
        save_json(HEDGES, d)
        ACCT_CACHE["at"] = 0
        return (f"⚠️ The hedge on {h.get('label', 'the combo')} ({hg['name']}) may or may not have gone through "
                f"({type(err).__name__}). Check Kalshi. It won't be tried again"
                + (", and auto cash-out leaves this combo alone." if auto else "."))
    body = {"ticker": hg["ticker"], "side": "bid", "count": f"{hg['n']:.2f}", "price": f"{hg['price']:.4f}",
            "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": str(uuid.uuid4())}
    try:
        r = kalshi_send("POST", "/portfolio/events/orders", body) or {}
        filled = float(r.get("fill_count") or 0)
    except PermissionError:
        return "Kalshi refused. Your API key needs write (trading) access to hedge."
    except Exception as err:
        if not (isinstance(err, RuntimeError) and "(404)" in str(err)):
            return unsure(err) if hedge_unknown(err) else f"Kalshi didn't take the hedge: {err}"
        legacy = {"ticker": hg["ticker"], "action": "buy", "side": "yes", "type": "limit",
                  "count": int(hg["n"]), "yes_price": int(round(hg["price"] * 100)),
                  "time_in_force": "immediate_or_cancel", "client_order_id": str(uuid.uuid4())}
        try:
            o = (kalshi_send("POST", "/portfolio/orders", legacy) or {}).get("order") or {}
        except PermissionError:
            return "Kalshi refused. Your API key needs write (trading) access to hedge."
        except Exception as err2:
            return unsure(err2) if hedge_unknown(err2) else f"Kalshi didn't take the hedge: {err2}"
        filled = float(o.get("fill_count_fp") or o.get("fill_count") or
                       (legacy["count"] - float(o.get("remaining_count") or 0) if o.get("status") == "executed" else 0))
    ACCT_CACHE["at"] = 0
    if filled <= 0:
        return f"No one was selling {hg['name']} at {hg['price'] * 100:.0f}¢ just now. Nothing was bought."
    d = load_json(HEDGES, {})
    d[ticker] = dict(d.get(ticker) or {}, n=round(hg["done"] + filled, 2), ticker=hg["ticker"], name=hg["name"])
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
    "ahl": {"icon": "🏒", "name": "AHL", "espn": None, "feed": "ahl", "q": {}, "periods": 3, "day": True, "hours": 2.75},
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
                ("nhl", "KXNHL"), ("ahl", "KXAHL"), ("nfl", "KXNFL"), ("euroleague", "KXEUROLEAGUE"), ("ufc", "KXUFC"),
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
    if not sp or not (sp.get("espn") or sp.get("feed")) or time.time() - got["at"] < max_age:
        return got["by"]
    if sp.get("feed"):
        return _fetch_feed_scores(code, sp, got)
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
                info = {"frac": _frac_left(code, st, n_per, state),
                        "me": int(float(me.get("score") or 0)), "opp": int(float(opp.get("score") or 0)),
                        "abbr": tm.get("abbreviation", ""),
                        "opp_abbr": (opp.get("team") or {}).get("abbreviation", ""),
                        "opp_name": (opp.get("team") or {}).get("displayName", ""),
                        "state": state, "detail": detail, "start": ev.get("date") or "",
                        "ball": str(sit.get("possession", "")) == str(me.get("id") or tm.get("id")),
                        "redzone": bool(sit.get("isRedZone")), "sport": code,
                        "game": ev.get("id"), "day": espn_day(ev.get("date")),
                        "wp": _wp(prob, me.get("homeAway")) if state == "in" else None,
                        "brk": state == "in" and any(x in typ.get("name", "") for x in ("HALFTIME", "END_PERIOD", "END_OF_PERIOD"))}
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


# The AHL's own public score feed (the JSON its website's score widgets read, run by HockeyTech): ESPN has no
# AHL scoreboard. Free, no login. The client key below is the public one baked into theahl.com's pages, not a
# secret; the AHL_FEED_KEY environment variable replaces it if the league ever rotates it.
AHL_FEED_URL = "https://lscluster.hockeytech.com/feed/index.php"
AHL_FEED_KEY = os.environ.get("AHL_FEED_KEY") or "ccb91f29d6744675"
AHL_ALIAS = {"CLT": ("CHA",)}      # Kalshi's tickers spell a few teams differently from the league's feed
try:
    from zoneinfo import ZoneInfo as _ZI
    FEED_TZ = _ZI("America/Toronto")                 # the feed's own clock (Eastern, daylight saving included)
except Exception:                                    # no time-zone data (some iOS builds)
    FEED_TZ = None


def _feed_start(g):
    """(UTC start as ISO text, US-Eastern game date) of one feed game. The feed's 'Ord' is the start in Eastern
    time and is the reliable one (its ISO text has a wrong offset for some western arenas), so it wins when
    time-zone data exists; otherwise the ISO text is used."""
    day = None
    try:
        day = dt.date.fromisoformat(str(g.get("Ord") or g.get("Date") or "")[:10])
        if FEED_TZ:
            t = dt.datetime.strptime(str(g["Ord"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=FEED_TZ)
            return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), day
    except (KeyError, ValueError, TypeError):
        pass
    try:
        t = dt.datetime.fromisoformat(str(g.get("GameDateISO8601") or ""))
        return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), day or (t - dt.timedelta(hours=5)).date()
    except ValueError:
        return "", day


def _feed_state(g):
    """'pre' / 'in' / 'post' from the feed's game status (1 not started, 2 in progress, 3 and 4 final)."""
    stt = str(g.get("GameStatus") or "")
    if stt in ("3", "4") or str(g.get("GameStatusString") or "").lower().startswith("final"):
        return "post"
    return "in" if stt == "2" else "pre"


def _fetch_feed_scores(code, sp, got):
    """Live scores for a league whose games ESPN doesn't carry, in the shape fetch_scores builds from ESPN: the
    same cache, and the same last-good-copy fallback when the feed can't be reached or sends something odd."""
    import time
    n_per = sp["periods"]
    try:
        r = requests.get(AHL_FEED_URL, params={
            "feed": "modulekit", "view": "scorebar", "numberofdaysback": 1, "numberofdaysahead": 3,
            "key": AHL_FEED_KEY, "client_code": sp["feed"], "fmt": "json", "lang": "en"}, timeout=8)
        games = r.json()["SiteKit"]["Scorebar"] if r.ok else None
        if not isinstance(games, list):
            return got["by"]                                 # keep the last good copy, never cache a blank
        by = {}
        for g in games:
            state = _feed_state(g)
            try:
                per = int(g.get("Period") or 0)
            except ValueError:
                per = 0
            clock = str(g.get("GameClock") or "").lstrip("0")
            clock = ("0" + clock) if clock.startswith(":") else (clock or "0:00")
            if state == "post":
                detail = str(g.get("GameStatusStringLong") or "").strip()
                if not detail.startswith("Final"):
                    detail = "Final"
            elif state == "in":
                if str(g.get("PeriodNameShort") or "").upper() == "SO":
                    detail = "SO"
                elif str(g.get("Intermission") or "0") == "1":
                    detail = f"End P{per}" if per <= n_per else "End OT"
                else:
                    detail = f"{'OT' if per > n_per else 'P' + str(per)} {clock}"
            else:
                detail = str(g.get("GameStatusStringLong") or g.get("GameStatusString") or "")
            start, day = _feed_start(g)
            st = {"period": per, "displayClock": clock}
            sides = []
            for pre in ("Home", "Visitor"):
                nm = g.get(pre + "LongName") or f"{g.get(pre + 'City', '')} {g.get(pre + 'Nickname', '')}".strip()
                sides.append((nm, g.get(pre + "Code") or "", int(float(g.get(pre + "Goals") or 0)), pre))
            for i, (name, abbr, goals, pre) in enumerate(sides):
                oname, oabbr, ogoals, _ = sides[1 - i]
                if not name:
                    continue
                info = {"frac": _frac_left(code, st, n_per, state), "me": goals, "opp": ogoals,
                        "abbr": abbr, "opp_abbr": oabbr, "opp_name": oname, "state": state, "detail": detail,
                        "start": start, "ball": False, "redzone": False, "sport": code,
                        "game": g.get("ID"), "day": day, "wp": None,
                        "brk": state == "in" and str(g.get("Intermission") or "0") == "1"}
                keys = {name, norm_team(name), norm_team(g.get(pre + "City") or ""),
                        norm_team(g.get(pre + "Nickname") or ""), "@" + abbr.upper()}
                keys |= {"@" + x for x in AHL_ALIAS.get(abbr.upper(), ())}
                for alt in keys - {"", "@"}:
                    by.setdefault(alt, []).append(info)
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
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


PERIOD_MIN = {"nfl": 15, "ncaaf": 15, "nba": 12, "wnba": 10, "ncaamb": 20, "ncaawb": 10, "nhl": 20, "ahl": 20,
              "soccer": 45, "mls": 45, "epl": 45}


def _frac_left(code, st, n_per, state):
    """Share of regulation still to play (0..1), from ESPN's period and clock. None when not live."""
    if state == "pre":
        return 1.0
    if state != "in":
        return 0.0
    per = st.get("period") or 1
    if per > n_per:
        return 0.04                                    # overtime: one score decides it
    L = PERIOD_MIN.get(code, 15)
    raw = str(st.get("displayClock") or "0:00").strip()
    if code in ("soccer", "mls", "epl"):               # soccer clocks count up: "67'" or "45'+2'"
        m = re.match(r"(\d+)", raw)
        played = int(m.group(1)) if m else 45 * (per - 0.5)
        return round(min(max((n_per * L - played) / (n_per * L), 0.0), 1.0), 3)
    try:
        if ":" in raw:                                 # "7:42"
            mm, _, ss = raw.partition(":")
            clock = int(mm) + float(ss or 0) / 60
        else:                                          # under a minute: "45.2" seconds
            clock = float(raw) / 60
    except ValueError:
        clock = L / 2
    return round(min(max(((n_per - per) * L + min(clock, L)) / (n_per * L), 0.0), 1.0), 3)


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
    else:                                      # a game outside the sport on screen (tennis in an NBA view)
        t = start_dt(l.get("event") or (l["ticker"] or "").rsplit("-", 1)[0])
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


# Hours after the start when we stop calling a game "on" if nothing says it is: sports with no live score source
# (tennis, UFC, EuroLeague, AHL) otherwise look live for ever. Sport-typical lengths, a little generous.
DONE_HOURS = {"nfl": 4.25, "nba": 3.25, "nhl": 3.5, "ahl": 3.5, "ncaamb": 2.75, "ncaawb": 2.75, "ncaaf": 4.5,
              "euroleague": 2.75, "ufc": 3.0, "soccer": 2.75, "tennis": 4.0}


def ago_text(secs):
    """'25 min', '3h 10m', '5h', '2 days' for how long ago something began."""
    m = max(int(secs // 60), 0)
    if m < 60:
        return f"{max(m, 1)} min"
    if m < 24 * 60:
        h, r = divmod(m, 60)
        return f"{h}h {r}m" if r >= 10 else f"{h}h"
    d = m // (24 * 60)
    return f"{d} day{'s' if d != 1 else ''}"


def run_status(sport, started_at, now=None, score_state=None, detail=""):
    """Honest status for a game that has started but that Kalshi hasn't settled.
    None if it hasn't started. Otherwise {"phase": "on" | "waiting" | "probably_over" | "over", "text": ...}:
    "on" while a score says so or while it is within a sport-typical length; "waiting" when the score source says
    it hasn't begun yet although its scheduled time has passed (tennis matches often run late); "probably_over"
    after a sport-typical length when there is no score to say otherwise (the pick stays open until Kalshi settles
    it); "over" when the score source says it finished. `detail` is what the score source says, for sports whose
    feed has no points to show (a UFC fight's round). Display only: nothing that buys or sells reads this."""
    if not started_at:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    secs = (now - started_at).total_seconds()
    if secs < 0:
        return None
    word = {"tennis": "Match", "ufc": "Fight"}.get(sport, "Game")
    if score_state == "in":
        return {"phase": "on", "text": detail or "", "short": detail or ""}
    if score_state == "post":
        return {"phase": "over", "text": f"{word} over · {detail + ' · ' if detail else ''}waiting on Kalshi to settle",
                "short": f"{word} over"}
    if score_state == "pre":
        return {"phase": "waiting", "text": f"Not started yet · was due {ago_text(secs)} ago", "short": "Not started yet"}
    ago = ago_text(secs)
    if secs / 3600.0 < DONE_HOURS.get(sport, 3.5):
        return {"phase": "on", "text": f"Started {ago} ago · no live score", "short": f"Started {ago} ago"}
    return {"phase": "probably_over", "text": f"Probably finished · started {ago} ago, waiting on Kalshi",
            "short": "Probably over"}


# ---------------------------------------------------------------- Kalshi's own live game data (display only)
# ESPN has nothing for tennis, EuroLeague or UFC. Kalshi's public API has the live score block its own app shows
# (no key, no account: /milestones maps a game's event ticker to its "milestone", /live_data/batch returns up to
# 100 milestones' scores in one call). It is used ONLY to show scores: leg_score, fetch_scores and SCORES_BY (which
# smart sell, auto cash-out, early results and the started-game rules read) never see it. Light by design: one
# milestone lookup per game (kept for hours), one batch call per refresh for every game under way, the last good
# copy kept when Kalshi is slow or says 429, and a growing pause after failures.
KLIVE_SPORTS = ("tennis", "euroleague", "ufc")
KLIVE = {"ms": {}, "live": {}, "cool": 0.0, "fails": 0}       # event -> milestone; milestone id -> {"at", "d"}
KLIVE_MS_TTL, KLIVE_MS_MISS, KLIVE_NEW_MAX = 6 * 3600, 900, 8   # keep a mapping 6h, a "none found" 15 min; 8 lookups a refresh
KLIVE_HDR = {"Accept": "application/json"}                       # public reads, sent straight to Kalshi (no key)


def _klive_fail(r=None):
    """Kalshi said no (429/5xx) or couldn't be reached: pause 15s, 30s, 60s ... up to 10 min (or its Retry-After)."""
    import time
    KLIVE["fails"] += 1
    wait = min(600, 15 * 2 ** (KLIVE["fails"] - 1))
    try:
        wait = max(wait, min(900, float((getattr(r, "headers", None) or {}).get("Retry-After"))))
    except (TypeError, ValueError):
        pass
    KLIVE["cool"] = time.time() + wait


def _klive_sides(m):
    """(first id, second id) of a milestone, in the order its title and Kalshi's event code name them:
    tennis and UFC list the first competitor first; team games read 'Away at Home'."""
    d = m.get("details") or {}
    if d.get("first_competitor_id"):
        return d.get("first_competitor_id"), d.get("second_competitor_id")
    if d.get("first_fighter_id"):
        return d.get("first_fighter_id"), d.get("second_fighter_id")
    if " at " in (m.get("title") or "") or d.get("away_team_id"):
        return d.get("away_team_id"), d.get("home_team_id")
    return None, None


def kalshi_milestone(event, now=None):
    """Kalshi's milestone for one game's event ticker (cached), or None. Never retried within the miss window."""
    import time
    now = now or time.time()
    got = KLIVE["ms"].get(event)
    if got and now - got["at"] < (KLIVE_MS_TTL if got.get("id") else KLIVE_MS_MISS):
        return got if got.get("id") else None
    if now < KLIVE["cool"]:
        return got if got and got.get("id") else None
    try:
        r = requests.get(f"{KALSHI}/milestones", params={"related_event_ticker": event, "limit": 10},
                         headers=KLIVE_HDR, timeout=6)
        if r.status_code == 429 or r.status_code >= 500:
            _klive_fail(r)
            return got if got and got.get("id") else None
        ms = (r.json().get("milestones") or []) if r.ok else []
    except (requests.RequestException, ValueError, AttributeError):
        _klive_fail()
        return got if got and got.get("id") else None
    KLIVE["fails"] = 0
    pick = next((m for m in ms if event in (m.get("primary_event_tickers") or [])), None) or \
        next((m for m in ms if event in (m.get("related_event_tickers") or [])), None)
    if not pick or not pick.get("id"):
        KLIVE["ms"][event] = {"at": now, "id": None}
        return None
    first, second = _klive_sides(pick)
    KLIVE["ms"][event] = {"at": now, "id": pick["id"], "type": pick.get("type") or "", "title": pick.get("title") or "",
                          "first": first, "second": second, "start": pick.get("start_date") or "",
                          "rounds": (pick.get("details") or {}).get("fight_length") or (pick.get("details") or {}).get("best_of")}
    return KLIVE["ms"][event]


def kalshi_live_refresh(events, max_age=None):
    """Bring Kalshi's live data up to date for these games' event tickers (only sports ESPN lacks). One batch call
    for all of them; at most KLIVE_NEW_MAX new milestone lookups per call. Quietly keeps the last good copy."""
    import time
    now = time.time()
    max_age = max(SCORES_MAX_AGE if max_age is None else max_age, 5)
    evs = sorted({e for e in events if e and ticker_sport(e) in KLIVE_SPORTS})
    if not evs or now < KLIVE["cool"]:
        return 0
    ids, new = [], 0
    for e in evs:
        known = KLIVE["ms"].get(e)
        if not known:
            if new >= KLIVE_NEW_MAX:
                continue
            new += 1
        m = kalshi_milestone(e, now)
        if m and m.get("id"):
            ids.append(m["id"])
        if now < KLIVE["cool"]:
            break
    stale = sorted({i for i in ids if now - (KLIVE["live"].get(i) or {}).get("at", 0) >= max_age})
    for k in range(0, len(stale), 100):
        try:
            r = requests.get(f"{KALSHI}/live_data/batch", params={"milestone_ids": stale[k:k + 100]},
                             headers=KLIVE_HDR, timeout=6)
            if r.status_code == 429 or r.status_code >= 500:
                _klive_fail(r)
                break
            rows = r.json().get("live_datas") if r.ok else None
            if not isinstance(rows, list):
                continue                                    # odd answer: keep the last good copy
        except (requests.RequestException, ValueError, AttributeError):
            _klive_fail()
            break
        KLIVE["fails"] = 0
        seen = set()
        for x in rows:
            if isinstance(x, dict) and x.get("milestone_id") and isinstance(x.get("details"), dict):
                KLIVE["live"][x["milestone_id"]] = {"at": time.time(), "d": x["details"], "type": x.get("type") or ""}
                seen.add(x["milestone_id"])
        for i in set(stale[k:k + 100]) - seen:          # no live block yet (not begun): note it, ask again next time
            if not (KLIVE["live"].get(i) or {}).get("d"):
                KLIVE["live"][i] = {"at": time.time(), "d": None, "type": ""}
    klive_prune(now)
    return len(stale)


def klive_prune(now=None):
    """Forget old live-score lookups so the caches don't grow for the life of the process: a game's milestone after
    twice its keep time (a "none found" after twice its miss window), a live block after an hour (nothing older
    than 15 minutes is ever shown)."""
    import time
    now = now or time.time()
    for e, v in list(KLIVE["ms"].items()):
        if now - (v.get("at") or 0) > 2 * (KLIVE_MS_TTL if v.get("id") else KLIVE_MS_MISS):
            KLIVE["ms"].pop(e, None)
    for i, v in list(KLIVE["live"].items()):
        if now - (v.get("at") or 0) > KLIVE_LIVE_KEEP:
            KLIVE["live"].pop(i, None)


KLIVE_LIVE_KEEP = 3600            # seconds a live block is kept
KLIVE_BUDGET = 1.5                # most seconds a page build (and so the watcher's loop) waits for these scores
KLIVE_JOB = {"t": None, "lock": threading.Lock()}
KLIVE_LOGGED = set()


def klive_log_once(what, key, err):
    """Note a bad live-score field once per game (not every loop)."""
    k = (what, str(key), type(err).__name__)
    if k in KLIVE_LOGGED:
        return
    if len(KLIVE_LOGGED) > 500:
        KLIVE_LOGGED.clear()
    KLIVE_LOGGED.add(k)
    print(f"live score skipped ({what} {key}):", type(err).__name__, err)


def kalshi_live_kick(events, budget=None):
    """Refresh Kalshi's live data (display only) in a background thread and wait at most `budget` seconds for it,
    so a slow Kalshi never holds up the watcher's loop (auto cash-out, smart sell) or a Live rebuild. Pages show
    the last good copy until it lands. One refresh runs at a time. True if it finished within the budget."""
    evs = {e for e in events if e}
    if not evs:
        return True
    with KLIVE_JOB["lock"]:
        th = KLIVE_JOB["t"]
        if th is None or not th.is_alive():
            def run():
                try:
                    kalshi_live_refresh(evs)
                except Exception as err:
                    print("kalshi live data:", type(err).__name__, err)
            th = threading.Thread(target=run, daemon=True, name="klive")
            KLIVE_JOB["t"] = th
            th.start()
    th.join(KLIVE_BUDGET if budget is None else budget)
    return not th.is_alive()


def safe_run_status(*a, **k):
    """run_status for display, never raising into the page build (and so the trading loop)."""
    try:
        return run_status(*a, **k)
    except Exception as err:
        klive_log_once("status", a[0] if a else "", err)
        return None


def _kclock(t):
    """'07:42' -> '7:42', '00:45' -> '0:45'."""
    t = str(t or "").strip()
    m = re.match(r"^(\d+):(\d{2})", t)
    return f"{int(m.group(1))}:{m.group(2)}" if m else t


def _kstate(d):
    w = str(d.get("widget_status") or "").lower()
    st = str(d.get("status") or "").lower()
    if w == "finished" or st in ("closed", "finished", "ended", "complete", "completed") or \
            str(d.get("match_status") or "").lower() in ("ended", "postgame", "finished") or d.get("winner"):
        return "post"
    return "in" if w == "live" or st in ("started", "inprogress", "in_progress", "live") else "pre"


def _ktennis(d, mine_first, n_sets):
    """(sets me, sets them, detail) for a tennis match from my side."""
    a, b = ("competitor1", "competitor2") if mine_first else ("competitor2", "competitor1")
    me_id = d.get(a + "_id")
    ra, rb = d.get(a + "_round_scores") or [], d.get(b + "_round_scores") or []
    sets = [(int(x.get("score") or 0), int(y.get("score") or 0)) for x, y in zip(ra, rb)]
    if _kstate(d) == "post":
        return int(d.get(a + "_overall_score") or 0), int(d.get(b + "_overall_score") or 0), \
            " ".join(f"{x}–{y}" for x, y in sets) or "Final"
    if not sets:
        return int(d.get(a + "_overall_score") or 0), int(d.get(b + "_overall_score") or 0), ""
    gm, go = sets[-1]
    pa, pb = d.get(a + "_current_round_score"), d.get(b + "_current_round_score")
    adv = d.get("advantage") or ""
    pts = ""
    if adv:
        pts = "AD–40" if adv == me_id else "40–AD"
    elif pa or pb:
        pts = f"{pa or 0}–{pb or 0}"
    text = f"Set {len(sets)}{' of ' + str(n_sets) if n_sets else ''} · {gm}–{go}" + (f" · {pts}" if pts else "")
    if d.get("server") and d.get("server") == me_id:
        text += " · serving"
    return int(d.get(a + "_overall_score") or 0), int(d.get(b + "_overall_score") or 0), text


def _khoops(d, mine_first):
    me, opp = (d.get("away_points"), d.get("home_points")) if mine_first else (d.get("home_points"), d.get("away_points"))
    per = int(d.get("period") or 0)
    phase = str(d.get("match_status") or d.get("genius_phase") or "")
    state = _kstate(d)
    if state == "post":
        detail = "Final" + (" OT" if per > 4 else "")
    elif state == "pre":
        detail = ""
    elif "half" in phase.lower():
        detail = "Half"
    elif phase.startswith("Before") and per:
        detail = f"End Q{per}" if per <= 4 else "End OT"
    else:
        detail = f"{'OT' if per > 4 else 'Q' + str(per or 1)} {_kclock(d.get('period_remaining_time'))}".strip()
    return int(me or 0), int(opp or 0), detail


def _kfight(d, rounds):
    """What a UFC fight's feed says. The in-fight fields are unverified (no fight was live when this was built), so
    only the round is read, and the clock only if a field for it turns up; never a made-up clock."""
    state = _kstate(d)
    if state == "post":
        how = str(d.get("method_of_victory") or "").strip()
        r, t = d.get("final_round") or d.get("current_round"), str(d.get("final_round_time_left") or "").strip()
        return " · ".join(x for x in (how, f"R{r}" + (f" {t}" if t and t not in ("0:00", "00:00") else "") if r else "") if x)
    if state == "in":
        r = d.get("current_round")
        clock = next((_kclock(d[k]) for k in ("current_round_time_left", "round_time_left", "time_left", "clock")
                      if d.get(k)), "")
        return (f"Round {r}{' of ' + str(rounds) if rounds else ''}" if r else "In progress") + \
            (f" · {clock} left" if clock else " · no clock")
    return ""


def kalshi_score(l, max_age=900):
    """_kalshi_score, but a bad field in Kalshi's feed means "no score" for that game only (logged once), never an
    error that could stop the page build and the auto cash-out that follows it."""
    try:
        return _kalshi_score(l, max_age)
    except Exception as err:
        klive_log_once("kalshi", (l or {}).get("ticker") if isinstance(l, dict) else l, err)
        return None


def _kalshi_score(l, max_age=900):
    """The score of the game this pick is on, from Kalshi's live data, shaped like leg_score's (from the side the pick
    needs), or None. Only for sports ESPN lacks; None when the data is missing, older than `max_age` seconds, or the
    pick can't be matched to a side for sure. Points are None for a fight (no score to show, only its round)."""
    import time
    t = l.get("ticker") or ""
    code = ticker_sport(t)
    if code not in KLIVE_SPORTS or "-" not in t:
        return None
    ev, suffix = t.rsplit("-", 1)
    m = KLIVE["ms"].get(ev)
    if not m or not m.get("id"):
        return None
    got = KLIVE["live"].get(m["id"])
    if not got or not got.get("d") or time.time() - got["at"] > max_age:
        return None
    d = got["d"]
    mt = re.search(r"-\d{2}[A-Z]{3}\d{2}(?:\d{4})?([A-Z0-9]+)$", ev)
    tail = mt.group(1) if mt else ""
    side_of_tail = None
    for team in dict.fromkeys((suffix.upper(), re.sub(r"\d+$", "", suffix.upper()))):   # a spread's "RMA5" -> "RMA"
        if not team or team.isdigit() or not tail:
            continue
        if tail.startswith(team) and not tail.endswith(team):
            side_of_tail = (True, team, tail[len(team):])
        elif tail.endswith(team) and not tail.startswith(team):
            side_of_tail = (False, team, tail[:-len(team)])
        if side_of_tail:
            break
    if "TOTAL" in ev.upper() or (not side_of_tail and re.sub(r"[\d.]+", "", suffix) == ""):
        first, mine_code, opp_code = True, tail[:len(tail) // 2], tail[len(tail) // 2:]   # a total: no side, read from the first
    elif side_of_tail:
        first, mine_code, opp_code = side_of_tail
    else:
        return None                                                  # can't tell which side: say nothing
    if l.get("side", "yes") == "no" and "TOTAL" not in ev.upper():
        first, mine_code, opp_code = not first, opp_code, mine_code
    state = _kstate(d)
    kind = (got.get("type") or m.get("type") or "")
    me = opp = None
    if kind.startswith("tennis"):
        mine_id = m["first"] if first else m["second"]
        mine_first = d.get("competitor1_id") == mine_id if d.get("competitor1_id") and mine_id else first
        me, opp, detail = _ktennis(d, mine_first, m.get("rounds"))
    elif kind.startswith("basketball"):
        me, opp, detail = _khoops(d, first)
    elif kind.startswith("mma"):
        detail = _kfight(d, m.get("rounds"))
    else:
        return None
    win = d.get("winner") or ""
    mine_id = m["first"] if first else m["second"]
    return {"me": me, "opp": opp, "abbr": mine_code, "opp_abbr": opp_code, "opp_name": "", "state": state,
            "detail": detail, "start": m.get("start") or "", "ball": False, "redzone": False, "sport": code,
            "game": m["id"], "day": ticker_day(t), "wp": None, "frac": None, "src": "kalshi",
            "won": (win == mine_id) if (state == "post" and win and mine_id) else None,
            "delayed": bool(d.get("live_data_delayed")), "age": round(time.time() - got["at"])}


def klive_events(legs, side_of=None, soon=15 * 60):
    """Event tickers of these picks worth asking Kalshi's live data about: sports ESPN lacks, games that have
    started or start within `soon` seconds (or whose start is unknown)."""
    now = dt.datetime.now(dt.timezone.utc)
    out = set()
    for l in legs:
        t = l.get("ticker") or ""
        if ticker_sport(t) not in KLIVE_SPORTS or "-" not in t:
            continue
        try:
            st = leg_start(l, side_of or {})
        except Exception:
            st = None
        if st is None or (st - now).total_seconds() < soon:
            out.add(t.rsplit("-", 1)[0])
    return out


def display_score(l, points=True, pre=False):
    """The score to SHOW for a pick: the usual source (ESPN / the AHL feed) first, then Kalshi's live data for the
    sports ESPN lacks. Display only: anything that buys, sells or decides a result calls leg_score instead.
    With points=True a record with no points (a UFC fight) is left out; with pre=False so is a Kalshi record for a
    game that hasn't begun (it has nothing to show but that). Never raises: a bad field means no score for that game."""
    try:
        sc = leg_score(l)
        if sc:
            return sc
        sc = kalshi_score(l)
        return sc if sc and (not points or sc.get("me") is not None) and (pre or sc.get("state") != "pre") else None
    except Exception as err:
        klive_log_once("display", (l or {}).get("ticker") if isinstance(l, dict) else l, err)
        return None


def kalshi_live_on():
    """Is any game in Kalshi's live data (the display-only copy) under way right now?"""
    import time
    now = time.time()
    return any(now - v["at"] < 300 and v.get("d") and _kstate(v["d"]) == "in" for v in list(KLIVE["live"].values()))


def when_label(t):
    """'Started 25 min ago', 'Tonight 7:10 PM', 'Tue 4:00 PM', 'Nov 29' for a start time."""
    if not t:
        return ""
    t = t.astimezone()
    now = dt.datetime.now().astimezone()
    if t <= now:
        return "Started " + ago_text((now - t).total_seconds()) + " ago"
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
        if a["status"] != "pending" or MINE.get("busy") or t in MINE.get("selling", set()) or hands_off(t):
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
                  "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news",
                  "killer_mode", "maker_mode", "accept_pct", "size_min", "size_max", "budget", "include_live", "live_min",
                  "take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "panel_live")
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
HUB_GET_HOSTS = (KALSHI + "/", "https://site.api.espn.com/", "https://lscluster.hockeytech.com/")
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
    """The planner's `requests`: public Kalshi, ESPN and AHL-feed reads come from the Mac when it's up."""
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


def open_hub_web(webview=None):
    """Open the Mac's web view in Safari, already signed in (a one-time link from the Mac). If the
    Mac hasn't updated yet, opens the plain page (it asks for the passcode)."""
    def say(msg):
        try:
            if webview is not None:
                webview.evaluate_javascript("toast(%s);setTimeout(function(){toast('')},4000)" % json.dumps(msg))
        except Exception:
            pass
    c = hub_conf()
    if not c:
        return say("Pair your Mac first (Settings > Watcher).")
    got = hub_call("weblink", timeout=8)
    if got is None:
        return say("Couldn't reach your Mac. Is Tailscale on?")
    url = (got.get("base") or c["hub"]).rstrip("/") + (got.get("path") or "/")   # https when the Mac has it
    try:
        import webbrowser
        webbrowser.open("safari-" + url if in_pythonista() else url)
    except Exception:
        open_outside(url)
    if not got.get("path"):
        say("Your Mac is still updating, so it may ask for the passcode this time.")


def open_hub_inside():
    """With the Mac reachable, show Combo Hub (same screens as the browser, always current) in this
    app's window. False if it can't, so the phone's own screens open instead."""
    if not CFG.get("hub_ui", True) or not hub_conf():
        return False
    loading("Connecting to your Mac…")
    got = hub_call("weblink", timeout=5)
    if not got or not got.get("path"):
        return False
    c = hub_conf()
    base = (got.get("base") or c["hub"]).rstrip("/")
    web = _web()
    if web is None:
        return False
    web.delegate = HubKeeper(base)
    APP.update(page="hub", where="hub", screen=None)
    web.load_url(base + got["path"])
    return True


@safe_delegate
class HubKeeper:
    """Combo Hub inside the app: its own pages stay here, links to games open in Safari, and
    'Phone screens' in its menu switches back to this app's own screens."""
    def __init__(self, base):
        self.base = base

    def webview_should_start_load(self, webview, url, nav_type):
        if url.startswith("combo://haptic/"):
            haptic({"success": "success", "error": "error", "warning": "warning"}.get(url.rsplit("/", 1)[-1], "tap"))
            return False
        if url.startswith("combo://phone"):
            RUN_OPTS["phone_ui"] = True
            import threading
            threading.Thread(target=run, daemon=True).start()
            return False
        if url.startswith(("http://", "https://")) and not url.startswith(self.base) and nav_type == "link_clicked":
            open_outside(url)
            return False
        return not url.startswith("combo://")

    def webview_did_finish_load(self, webview):
        try:
            webview.evaluate_javascript("window.__inapp&&window.__inapp()")
        except Exception:
            pass


def hub_line():
    """One line for Live/Settings about the Mac hub, or ''."""
    if not hub_conf():
        return ""
    if hub_up():
        ms = f" · {HUB['ms']:.0f} ms" if HUB.get("ms") else ""
        return (f"<div class='wline'>💻 Mac hub connected{ms}. Live data and trades go through your Mac. "
                "<a href='combo://hubweb' style='color:var(--accent);font-weight:600;text-decoration:none'>"
                "Open Combo Hub ↗</a></div>")
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


def send_watcher_settings(with_cfg=True):
    """Send your Let it ride / Auto cash-out settings (and Kalshi's learned discount) to the Pi,
    signed so only your phone can change them. The Pi is listening, so it takes effect within
    seconds. Never sends keys. with_cfg=False (after an update) sends only the update approval,
    so the phone's copy of the settings doesn't overwrite what you changed on the Mac."""
    import hmac, hashlib, time
    c = watcher_conf()
    if not c:
        return False
    body = json.dumps({"at": int(time.time()), "cfg": {k: CFG.get(k) for k in WATCHER_SYNCED} if with_cfg else {},
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
        send_watcher_settings(with_cfg=False)


def refresh_pi_approval():
    """At each launch: re-approve this exact version for the Mac/Pi. Fixes an approval made while
    GitHub's file cache still served the previous watcher (the Mac then refuses the mismatch)."""
    import hashlib
    try:
        with open(ENGINE if os.path.exists(ENGINE) else SCRIPT_PATH, "rb") as f:
            mine = f.read()
        if f'VERSION = "{VERSION}"'.encode() not in mine:
            return                                  # not the file that's running: approve nothing
        ok = load_json(PI_APPROVE, {})
        w = requests.get(UPDATE_URL + "/watcher/combo_watcher.py", params={"t": int(time.time())}, timeout=20,
                         headers={"Cache-Control": "no-cache"})
        w_sha = hashlib.sha256(w.content).hexdigest() if w.ok else ""
        e_sha = hashlib.sha256(mine).hexdigest()
        if w_sha and (ok.get("version") != VERSION or ok.get("watcher") != w_sha or ok.get("engine") != e_sha):
            save_json(PI_APPROVE, {"version": VERSION, "engine": e_sha, "watcher": w_sha})
            send_watcher_settings(with_cfg=False)
    except (OSError, requests.RequestException):
        pass


def wname():
    """What's watching: 'Mac' (it says so in its heartbeat, or the phone is paired with the Mac hub) or 'Pi'."""
    try:
        hb = watcher_status()
    except Exception:
        hb = None
    if (hb or {}).get("host"):
        return hb["host"]
    return "Mac" if hub_conf() else "Pi"


def watcher_line():
    """One line for Live: is the Pi watching?"""
    if not watcher_conf():
        return ""
    if hub_conf():
        return hub_line() + _watcher_line()
    return _watcher_line()


def _watcher_line():
    import time
    hb = watcher_status()
    if hb and time.time() - hb.get("at", 0) < 180 and hb.get("err"):
        return (f"<div class='wline bad'>🖥 {wname()} watcher is running but its checks are failing: "
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
    return (f"<div class='wline bad'>🖥 {wname()} watcher hasn't checked in for 3+ minutes." + last +
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
        import traceback
        traceback.print_exc()                       # the Mac's log keeps the details
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


PROGRESS_MULT = 1.75    # games under way and the chance up 75%+ on the price you paid counts as earned


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
    all_games = MINE["all_games"]
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
    MINE["acct"] = acct                            # the full list, for today's and the week's totals
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
    try:                                       # tennis, EuroLeague, UFC: Kalshi's live data, for display only
        kalshi_live_kick(klive_events([l for a in mine if a["status"] == "pending" for l in a["legs"]
                                          if not results.get(l["ticker"])], side_of))
    except Exception as err:
        print("kalshi live data:", type(err).__name__, err)

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
    views = []                                  # the same numbers as data, for Combo Hub's own screens
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
            ll = legs_left_of(a["legs"], inf, side_of)
            paid = a["cost"] / a["pays"] if a["pays"] else 1.0
            # "Earned" = a pick has won, or (for games played at the same time, where nothing is won
            # until the end) the games are on and the combo's chance is well above what you paid.
            progressed = any(lv for _, lv, _ in ll) and p >= PROGRESS_MULT * paid
            pre_of = {}                                  # each pick's chance before its game (stop-loss guard)
            for l, (_, _, _, r) in zip(a["legs"], inf):
                t0 = l["ticker"]
                if l.get("side", "yes") == "no":
                    s0 = side_of.get(t0)
                    o0 = other_side(all_games[s0["event"]], s0) if s0 else None
                    t0 = o0["ticker"] if o0 else None
                if not r and t0 and pregame.get(t0):
                    pre_of[l["ticker"]] = pregame[t0]
            MINE["hold"][a["ticker"]] = {"label": f"Combo {i}", "p": p, "pays": a["pays"], "cost": a["cost"],
                                         "hold": p * a["pays"], "left": left, "rough": a["ticker"] in rough,
                                         "won_some": any(r == "yes" for *_, r in inf) or progressed,
                                         "progressed": progressed and not any(r == "yes" for *_, r in inf),
                                         "need": [((l.get("side", "yes"), l["ticker"]), nm)
                                                  for l, (nm, _, _, r) in zip(a["legs"], inf) if not r],
                                         "worth": left <= 3 and p * a["pays"] >= 2 * a["cost"],
                                         "legs_left": ll, "pre_of": pre_of,
                                         "ch_of": {l["ticker"]: ch for l, (_, _, ch, r) in zip(a["legs"], inf) if not r}}
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
            value = ""
        rows = []
        vlegs = []
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
            sline = score_line(display_score(l)) if not res else ""
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
            _st = pick_state(l, side_of) if not res else None
            _lp = (MARKET_INFO.get(l["ticker"]) or {}).get("live") if _st == "live" else None
            if _lp is not None and l.get("side", "yes") == "no":
                _lp = 1 - _lp
            _sc = display_score(l, points=False, pre=True) if not res else None   # display only (Kalshi's data for tennis etc.)
            _ks = bool(_sc and _sc.get("src") == "kalshi")
            try:                                       # display only: a bad field never stops the build
                _rs = (safe_run_status(ticker_sport(l["ticker"]), leg_start(l, side_of), score_state=(_sc or {}).get("state"),
                                       detail=_sc.get("detail") or "" if _ks and (_sc.get("me") is None or _sc.get("state") == "post") else "")
                       if _st == "live" else None)
            except Exception as err:
                klive_log_once("status", l.get("ticker"), err)
                _rs = None
            if _ks and (_sc.get("me") is None or _sc["state"] == "pre"):   # a fight (its round is in the note) or not begun
                _sc = None
            vlegs.append({"ticker": l["ticker"], "name": name, "opp": opp, "chance": ch, "live": _lp, "res": res,
                          "state": _st, "phase": (_rs or {}).get("phase", ""), "note": (_rs or {}).get("text", ""),
                          "short": (_rs or {}).get("short", ""), "score": re.sub(r"<[^>]+>", "", score_line(_sc)) if _sc else "",
                          "sc": {k: _sc.get(k) for k in ("me", "opp", "abbr", "opp_abbr", "detail")} if _sc else None,
                          "src": "kalshi" if _ks else "",
                          "starts": start_label(l.get("event") or "") if not res else "",
                          "sport": ticker_sport(l["ticker"]) or "other", "side": l.get("side", "yes"),
                          "url": game_url(l["ticker"]) if (l["ticker"] or "").startswith(tuple(GAME_SLUG)) else ""})
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
        # games on with no score for longer than a game takes: say so, don't claim "Live now" for ever
        gone_live = any_live and all(v["phase"] in ("probably_over", "over") for v in vlegs
                                     if v["state"] == "live" and not v["res"])
        # a score source says the "started" games haven't begun (a tennis match running late): don't say "Live now"
        late = any_live and not gone_live and all(v["phase"] in ("waiting", "probably_over", "over") for v in vlegs
                                                  if v["state"] == "live" and not v["res"])
        when = (("Probably finished" if gone_live else "Not started yet" if late else "Live now") if any_live
                else when_label(nxt)) if group == "pending" else ""
        dots = "".join({"yes": "<i class='d w'></i>", "no": "<i class='d l'></i>"}.get(r, "<i class='d o'></i>")
                       for _, (_, _, _, r) in legs_sorted)
        sort_t = 0 if any_live and not gone_live else (nxt.timestamp() if nxt else 9e12)
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
        live_sc = next((display_score(l) for l, (_, _, _, r) in legs_sorted if not r and pick_state(l, side_of) == "live"
                        and display_score(l)), None)
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
        kind = ("playing" if any_live and not gone_live else "quiet") if group == "pending" else group
        views.append({"t": a["ticker"], "i": i, "label": f"Combo {i}", "group": group, "kind": kind,
                      "sports": sports, "p": p, "pays": a["pays"], "cost": a["cost"], "back": a.get("back", 0),
                      "full": a.get("full_pays") or 0, "when": when, "live": any_live and not gone_live, "sort": sort_t,
                      "preview": preview, "legs": vlegs, "week": a.get("week")})
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
    try:
        MINE["view"] = live_view(mine, views, plan, hits_any / trials, balance)
    except Exception as err:                      # the data copy must never break the page
        MINE["view"] = {"error": f"{type(err).__name__}: {err}"}
    cards = [(g, re.sub(r"@@CASH:([^@]+)@@", lambda m: cash_block(m.group(1), plan), c)) for g, c in cards]
    act_on = {t for t, f in ((plan or {}).get("acts") or {}).items() if f} | {t for t in MINE["hold"] if fresh_offer(t)}
    cards = [(g, re.sub(r"@@OPEN:([^@]+)@@", lambda m: " open" if html.unescape(m.group(1)) in act_on else "", c))
             for g, c in cards]
    alive = [a for a in mine if snap.get(a["ticker"], {}).get("status") in ("pending", "won")]
    best = max((a["pays"] for a in alive), default=0)      # lost combos can't pay out
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
            sc_l = display_score(l)                  # the game strip is display only
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
    body = [head, "<header><h1>Live</h1><div class='sub'>"
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
    note_app_order(method, path, body)
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


def edge_stake(pct, lo=3, hi=10, chance=None):
    """Bet size from the edge (the Kelly rule). pct = Kalshi's payout as a share of fair. The edge is
    pulled 30% toward zero first, since our fair chances aren't perfect, then Kelly's fraction of your
    bankroll is used, inside your $lo-$hi limits. At or below fair: the least."""
    q = min(max(chance or 0.25, 0.005), 0.95)       # the combo's chance of hitting
    adj = 1 + (pct - 1) * 0.7
    if adj <= 1:
        return lo
    b = adj / q - 1                                  # net odds at that price
    f = (adj - 1) / b if b > 0 else 0                # Kelly: edge over odds
    return int(max(lo, min(hi, round(CFG.get("bankroll", 500) * f))))


def stake_for(pct, legs=None):
    """How much to bet on a combo, from Kalshi's price as a share of fair: nothing under your
    cut-off, the least just above it, the most when it's above fair. With the picks given, less
    when you already need one of them in combos carrying a big share of what's riding."""
    cut = CFG["accept_pct"] / 100
    if pct < cut:
        return 0
    lo, hi = CFG.get("size_min", 3), CFG.get("size_max", 10)
    v = edge_stake(pct, lo, hi, math.prod(l["fair"] for l in legs) if legs and all(l.get("fair") for l in legs) else None)
    if legs:
        f, _ = exposure_factor(legs)
        v = max(lo, round(v * f))
    return v


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
    try:
        store_quote(c, stake, pays, pct)
    except Exception:
        pass
    CTX["offers"][i] = {"rfq": rfq, "quote": q["id"], "pays": pays, "market": market,
                        "price": yes_price, "stake": stake, "p": CTX["stake"] / c["fair"] if c.get("fair") else None}
    return {"pays": pays, "price": yes_price, "min": minimum, "ok": pays >= minimum, "stake": stake, "pct": pct}


def accept_offer(i, skip_cap=False):
    """Step 4: accept. 'no' is correct: it hits the seller's NO bid, which buys you YES. skip_cap: the daily
    panel, whose own budget was checked when you approved it."""
    import time
    o = CTX["offers"].get(i)
    if not o:
        return {"error": "That offer expired. Tap New price for a fresh one."}
    spent = 0 if skip_cap else week_spend()
    if not skip_cap and spent + o["stake"] > CFG["budget"] + 0.01:
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
        b = next((x for x in hist["builds"] if x["id"] == CTX.get("build_id")), None)
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
    b = next((x for x in hist["builds"] if x["id"] == CTX.get("build_id")), None)
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
    b = next((x for x in hist["builds"] if x["id"] == CTX.get("build_id")), None)
    if b is not None:
        b["combos"].append({"kind": "own", "tier": "Your combo", "fair": round(fair_pay, 2), "min": round(new["min"], 2),
                            "legs": [{"ticker": l["ticker"], "pick": l["pick"], "dog": l["fair"] < 0.5} for l in legs]})
        save_json(HISTORY, hist)
    return k, None


def save_combo(i, new):
    """Write a changed combo back to the saved history (and clear its Placed/offer)."""
    hist = load_json(HISTORY, {"builds": []})
    b = next((x for x in hist["builds"] if x["id"] == CTX.get("build_id")), None)
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
                            want = stake_for(o["pct"], CTX["combos"][k - 1]["legs"])
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
                                        for k, d in [("thursday", "Wed & Thu" if any(x == "Wednesday" for x in days.values()) else "Thursday"),
                                                     ("saturday", "Saturday"), ("monday", "Monday")]),
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
                        + switch("auto_hedge", "Hedge instead when that locks in more (only on a fresh live "
                                 "score, never at a break, at least what you paid, held 3+ min, fresh price)")
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
                         "while the planner is open, or all the time if your watcher (Mac or Pi) is running (Kalshi buys "
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
        "watcher": section("Watcher (Mac or Pi)",
                           f"<input class='txt' id='watcher_code' placeholder='Paste the pairing code from your Mac or Pi' "
                           f"autocapitalize='off' autocorrect='off' spellcheck='false' value='{e(CFG.get('watcher_code', ''))}'>"
                           + "<button class='btn' style='margin-top:8px' onclick=\"go('save')\">Save</button>"
                           + (f"<div style='margin-top:8px'>{watcher_line()}</div>" if CFG.get("watcher_code") else "")
                           + (switch("hub_ui", "Open Combo Hub's screens when the Mac is reachable") if CFG.get("watcher_code") else ""),
                           "Your Mac (or a Raspberry Pi) at home, running all the time: it sends alerts (through the ntfy app) "
                           "with your phone locked and, if you turn on Auto cash-out, does that too, by the same "
                           "rules (while it's running, only the watcher auto-sells, so nothing sells twice). Saving here "
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
        upd = ("<div class='note'>Update available: see the Settings tab.</div>"
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
            "<details class='lostbox' id='moreset'><summary>More settings · game order, overlap, mid-day, watcher</summary>",
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
    lines = ["Pair your watcher in the planner's", "Settings to see your combos here."]
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
        lines.append("No word from your watcher in 10+ minutes")
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
    if in_pythonista() and not RUN_OPTS.pop("phone_ui", False) and not RUN_OPTS.get("goto") and open_hub_inside():
        return                                    # Combo Hub from the Mac, inside this app
    loading(f"Loading {'the ' + LG()['name'].lower() if by_day() else 'this week'}'s games from Kalshi…")
    RUN_OPTS["latest"] = latest_version()
    all_games, days, sunday = week_games(fetch_markets())
    CFG["picks"] = {e: v for e, v in CFG["picks"].items() if e in all_games}  # drop old weeks
    schedule_buy_nudge(all_games)
    if in_pythonista() and watcher_conf():
        threading.Thread(target=refresh_pi_approval, daemon=True).start()
    import_key_file()
    start_autosell_keeper()
    counts = defaultdict(int)
    for d in days.values():
        counts["Thursday" if d in ("Friday", "Wednesday") else d] += 1

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
        RUN_OPTS["notice"] = "Saved." + (f" Sent to your {wname()}." if sent else "") + (
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
SHADOW_DEF = {"start": 300.0, "min_pct": 100, "per_day": 30.0, "max_open": 15, "quotes_per_day": 60,
              "per_pass": 3, "v": 2}


def shadow_state():
    st = load_json(SHADOW, {})
    if st and st.get("v", 1) < 2:                # more looks per day now that good ones become buy ideas
        st.update(quotes_per_day=SHADOW_DEF["quotes_per_day"], per_pass=SHADOW_DEF["per_pass"], v=2)
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
    if q_today >= st["quotes_per_day"]:          # (a full paper portfolio still looks for buy ideas)
        save_json(SHADOW, st)
        return did
    attach_fair_book = load_book_state(book_snap)
    games_held = {frozenset(l["ticker"] for l in b["legs"]) for b in st["bets"]}
    cands = shadow_candidates_with(attach_fair_book)
    ck = lambda c: "|".join(sorted(l["ticker"] for l in c["legs"]))
    due = {k for k, t in (st.get("reask") or {}).items() if t <= time.time()}
    cands.sort(key=lambda c: ck(c) not in due)   # a near miss from last time gets asked again first
    st["reask"] = {k: t for k, t in (st.get("reask") or {}).items() if k not in due and time.time() - t < 3600}
    CTX.clear()
    CTX.update(combos=cands, stake=CFG["stake"], offers={}, source="shadow")
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
        if (not r.get("error") and r.get("pct") and r["pct"] >= KILLER["combo_pct"] and not c.get("same_game")
                and len(c["legs"]) <= KILLER["combo_legs"] and CFG.get("killer_mode", "watch") != "off"):
            ok, why_not = killer_check(c["legs"], book_snap)
            if ok:                                         # a killer combo: take this quote while it's live
                killer_act("combo", c["legs"], r["stake"], r["pays"], r["pct"],
                           lambda: _killer_combo(i), alert, log)
            else:
                log("near-killer combo held back:", "; ".join(why_not))
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
        cut = CFG["accept_pct"] / 100
        if cut - 0.03 <= pct < cut and key not in st.setdefault("reasked", []):
            st["reask"][key] = time.time() + 300     # just under the cut-off: a fresh price in a few minutes
            st["reasked"] = (st["reasked"] + [key])[-200:]
        before = st.setdefault("seen", {}).get(key)
        st["seen"][key] = round(pct, 4)
        if pct * 100 >= CFG["accept_pct"] and (before is None or pct - before >= 0.05) and not c.get("same_game"):
            sid = store_suggestion(c, r, pct)            # a buy idea: Live shows it, one tap gets your price
            picks = " + ".join(l["pick"] for l in c["legs"])
            url = f"/app#s={sid}" if sid else "/app"
            pays_txt = f"{money(r['stake'])} pays about {money(r['pays'])}"
            inplay = " Includes a game in progress, so the price moves fast." if any(started(l) for l in c["legs"]) else ""
            if alert and before is None:
                _alert(alert, f"💡 Buy idea: {picks} ({LG()['name']}) is priced at {pct:.0%} of fair. "
                              f"{pays_txt}. Tap to get your price.{inplay}", "value", url)
            elif alert:
                _alert(alert, f"📈 Better price: {picks} went from {before:.0%} to {pct:.0%} of fair. {pays_txt}.",
                       "price", url)
        st["quotes"].append({"day": today, "pct": round(pct, 4), "legs": len(c["legs"]), "league": LEAGUE["code"]})
        stake = 10 if pct >= 1.10 else 8 if pct >= 1.05 else 5
        if pct * 100 < st["min_pct"] or spent_today + stake > st["per_day"] or stake > st["bank"] or \
                sum(b["status"] == "open" for b in st["bets"]) >= st["max_open"]:
            did.append(f"quoted {len(c['legs'])}-pick at {pct:.0%} of fair: passed")
            continue
        pays = r["pays"] * stake / r["stake"]
        st["bank"] -= stake
        spent_today += stake
        st["bets"].append({"id": f"S{len(st['bets']) + 1}", "day": today, "at": time.time(), "league": LEAGUE["code"],
                           "same_game": bool(c.get("same_game")),
                           "legs": [{"ticker": l["ticker"], "pick": l["pick"], "fair": round(l["fair"], 4),
                                     "p": round(l["p"], 4)} for l in c["legs"]],
                           "stake": stake, "pays": round(pays, 2), "pct": round(pct, 4), "status": "open"})
        did.append(f"paper-bought {len(c['legs'])}-pick at {pct:.0%} of fair: {money(stake)} to win {money(pays)}")
    st["quotes"] = st["quotes"][-500:]
    if len(st.get("seen", {})) > 400:
        st["seen"] = dict(list(st["seen"].items())[-300:])
    save_json(SHADOW, st)
    return did


def maker_ratio(n, hours=None):
    """What Kalshi's combo makers typically pay vs its own single-game prices, for n picks (learned)."""
    m = QMODEL["m"]
    if (m is None or time.time() - QMODEL["at"] > 600) and STORE["db"]:
        QMODEL.update(m=quote_model(), at=time.time())
        m = QMODEL["m"]
    if m:
        e = m["eff"]
        return math.exp(m["mu"] + e.get(f"n:{_nbucket(n)}", 0) + e.get(f"h:{_hbucket(hours)}", 0))
    r = est_quote_ratio(n)
    return r or max(0.6, 0.97 - 0.035 * n)          # before anything is learned: a cautious guess


def value_combos(games, stake=None, k=8, min_fair=0.25, max_legs=5, live_ok=()):
    """Combos built for price, not for chance: picks where Kalshi's own price is cheapest against the
    sharp books' fair chance, combined so those gaps multiply. Scores every combination of the best
    picks with the learned maker discount and keeps the ones most likely to be priced over fair."""
    import itertools
    stake = stake or CFG["stake"]
    best = {}
    for e, sides in games.items():
        for x in sides:
            if x.get("tie") or not x.get("fair") or not x.get("p") or x["fair"] < min_fair:
                continue
            if started(x) and e not in live_ok:
                continue
            if x.get("src") is None and not x.get("live"):
                continue                               # no outside line: nothing to compare Kalshi against
            edge = x["fair"] / x["p"]
            if e not in best or edge > best[e][0]:
                best[e] = (edge, x)
    pool = sorted(best.values(), key=lambda t: -t[0])[:14]
    scored = []
    for n in range(2, max_legs + 1):
        top = pool[:14 if n <= 3 else 11 if n == 4 else 9]
        for combo in itertools.combinations(top, n):
            legs = [x for _, x in combo]
            mult = math.prod(ed for ed, _ in combo)    # Kalshi payout vs fair payout, before the maker's cut
            hrs = _hours_to(legs)
            pct = mult * maker_ratio(n, hrs)
            chance = math.prod(l["fair"] for l in legs)
            if chance < 0.01:
                continue
            scored.append((pct, chance, legs))
    scored.sort(key=lambda t: -t[0])
    out, used = [], {}
    for pct, chance, legs in scored:
        if len(out) >= k:
            break
        if any(used.get(l["ticker"], 0) >= 2 for l in legs):
            continue                                   # spread it out: no pick in more than 2 value combos
        for l in legs:
            used[l["ticker"]] = used.get(l["ticker"], 0) + 1
        fair_pay = stake / chance
        out.append({"kind": "value", "tier": "Value", "legs": legs, "fair": fair_pay,
                    "kalshi": stake / math.prod(l["p"] for l in legs), "min": fair_pay * CFG["accept_pct"] / 100,
                    "value_pct": round(pct, 4)})
    return out


# ---- single-game ideas: no combo maker, just Kalshi's price plus its fee
SINGLE_MIN_EDGE = 0.025           # at least 2.5 cents a contract better than fair, after the fee


def single_fee(p):
    return FEE_RATE * p * (1 - p)


def opp_of(games, x):
    return next((y["pick"] for y in games.get(x.get("event"), []) if y["ticker"] != x["ticker"] and not y.get("tie")), "")


def single_candidates(games, live_ok=(), min_fair=0.2):
    """Teams whose Kalshi price (the ask) is clearly below the sharp books' fair chance, after the fee."""
    out = []
    for e, sides in games.items():
        for x in sides:
            if x.get("tie") or not x.get("fair") or not x.get("p") or x["fair"] < min_fair or x["p"] >= 0.97:
                continue
            if started(x) and e not in live_ok:
                continue
            if x.get("src") is None and not x.get("live"):
                continue
            edge = x["fair"] - x["p"] - single_fee(x["p"])
            if edge >= SINGLE_MIN_EDGE and edge / x["p"] >= 0.04:
                out.append(dict(x, edge=round(edge, 4)))
    return sorted(out, key=lambda x: -x["edge"] / x["p"])


INJ = {}


def league_injuries(code, max_age=1800):
    """ESPN's injury report for a league: {team name (lower): [(player, position, status, iso date, note)]}.
    Cached half an hour. Empty when ESPN has no report for the sport."""
    path = (SPORTS.get(code) or LEAGUES.get(code) or {}).get("espn")
    if not path:
        return {}
    got = INJ.get(code)
    if got and time.time() - got[0] < max_age:
        return got[1]
    out = {}
    try:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/injuries", timeout=12)
        data = r.json() if r.ok else {}
        for team in data.get("injuries") or []:
            name = ((team.get("team") or {}).get("displayName") or team.get("displayName") or "").lower()
            rows = []
            for it in team.get("injuries") or []:
                ath = it.get("athlete") or {}
                rows.append((ath.get("displayName") or "", (ath.get("position") or {}).get("abbreviation") or "",
                             it.get("status") or (it.get("type") or {}).get("description") or "",
                             it.get("date") or "", (it.get("shortComment") or "")[:140]))
            if name:
                out[name] = rows
    except (requests.RequestException, ValueError, AttributeError):
        out = {}
    INJ[code] = (time.time(), out)
    return out


def injury_note(code, *teams, hours=48):
    """The injuries worth knowing for these teams: Out or Doubtful, newest first (short text), and
    whether any is fresh (reported in the last 3 hours, when prices may still be catching up)."""
    rep_ = league_injuries(code)
    lines, fresh = [], False
    now = dt.datetime.now(dt.timezone.utc)
    for t in teams:
        tl = (t or "").lower()
        rows = rep_.get(tl) or next((v for k, v in rep_.items() if tl and (tl in k or k.split()[-1] == tl.split()[-1])), [])
        for name, pos, status, when, note in rows:
            st = status.lower()
            if not any(w in st for w in ("out", "doubtful", "injured reserve", "suspension")):
                continue
            try:
                age = (now - dt.datetime.fromisoformat(when.replace("Z", "+00:00"))).total_seconds() / 3600
            except ValueError:
                age = 99
            if age > hours and "out" not in st:
                continue
            fresh = fresh or age < 3
            lines.append((age, f"{t.split()[-1] if t else ''}: {name} ({pos}) {status}"))
    lines.sort()
    return [x for _, x in lines[:4]], fresh


CTXNOTE = {}


def _espn_board(code, day, max_age=1800):
    path = (SPORTS.get(code) or LEAGUES.get(code) or {}).get("espn")
    if not path:
        return []
    k = (code, day)
    got = CTXNOTE.get(k)
    if got and time.time() - got[0] < max_age:
        return got[1]
    try:
        q = dict((LEAGUES.get(code) or {}).get("espn_q") or {}, dates=day)
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard", params=q, timeout=12)
        evs = (r.json() if r.ok else {}).get("events") or []
    except (requests.RequestException, ValueError):
        evs = []
    CTXNOTE[k] = (time.time(), evs)
    return evs


def game_context(code, *teams):
    """Short context for a card: back-to-backs (NBA, NHL) and outdoor weather (football), from ESPN."""
    out = []
    names = [t.lower() for t in teams if t]
    if not names:
        return out
    today = dt.date.today()
    try:
        if code in ("nba", "nhl", "ncaamb", "ncaawb"):
            played = set()
            for ev in _espn_board(code, (today - dt.timedelta(days=1)).strftime("%Y%m%d"), max_age=6 * 3600):
                for c in ((ev.get("competitions") or [{}])[0].get("competitors") or []):
                    played.add(((c.get("team") or {}).get("displayName") or "").lower())
            out += [f"{t.split()[-1].title()} played yesterday (back-to-back)" for t in names if t in played]
        if code in ("nfl", "ncaaf"):
            for ev in _espn_board(code, today.strftime("%Y%m%d")):
                comp = (ev.get("competitions") or [{}])[0]
                teams_in = {((c.get("team") or {}).get("displayName") or "").lower() for c in comp.get("competitors") or []}
                if not teams_in & set(names) or (comp.get("venue") or {}).get("indoor"):
                    continue
                w = ev.get("weather") or comp.get("weather") or {}
                if w:
                    out.append(f"Outdoors: {w.get('temperature', '')}°F, {w.get('displayValue', '')}")
    except Exception:
        pass
    return out[:3]


# ---- killer deals: bought by the Mac on its own, only when every check passes (see KILLER)
KILLER = {"single_edge": 0.08, "single_rel": 0.15, "combo_pct": 1.15, "combo_legs": 4, "per_buy": 10.0,
          "per_day": 2, "day_dollars": 20.0, "agree": 0.02, "steady_mins": 30, "news_hours": 3}


def killer_today():
    start = time.mktime(dt.date.today().timetuple())
    rows = store_rows("select stake from killer where mode='on' and status='bought' and ts >= ?", (start,))
    return len(rows), sum(r["stake"] for r in rows)


def sources_agree(snap, pick, fair):
    """At least two odds sources within 2 points of each other and of the fair chance we use."""
    parts = (snap or {}).get("parts") or {}
    p = parts.get(pick)
    if p is None:
        last = (pick or "").split()[-1:]
        p = next((v for k, v in parts.items() if last and k.split()[-1:] == last), None)
    vals = [v for v in (p or {}).values() if isinstance(v, (int, float))]
    close = [v for v in vals if abs(v - fair) <= KILLER["agree"]]
    return len(close) >= 2, len(vals)


def steady(ticker, fair, mins=None):
    """Seen at about this fair chance for the last half hour (not a flash or a line still moving)."""
    mins = mins or KILLER["steady_mins"]
    rows = store_rows("select ts, fair from fairs where ticker=? and ts > ? order by ts",
                      (ticker, time.time() - mins * 60 * 1.5))
    if not rows or time.time() - rows[0]["ts"] < mins * 60 * 0.66:
        return False                                  # not watched long enough yet
    return max(abs(r["fair"] - fair) for r in rows) <= KILLER["agree"]


def killer_check(legs, snap, live_ok=()):
    """(ok, reasons-not) for picks a killer deal would rest on."""
    why = []
    for l in legs:
        if started(l):
            why.append(f"{l['pick']}: game in progress")
            continue
        ok, n = sources_agree(snap, l["pick"], l["fair"])
        if not ok:
            why.append(f"{l['pick']}: needs two odds sources agreeing ({n} found)")
        if not steady(l["ticker"], l["fair"]):
            why.append(f"{l['pick']}: line not steady for {KILLER['steady_mins']} minutes yet")
        d = book_depth(l["ticker"])
        if not d or d.get("thin"):
            why.append(f"{l['pick']}: thin order book")
    try:
        _, fresh = injury_note(LEAGUE["code"], *[l["pick"] for l in legs], hours=KILLER["news_hours"])
        if fresh:
            why.append("fresh injury news")
    except Exception:
        pass
    return not why, why


def killer_act(kind, legs, stake, pays, pct, buy, alert=None, log=print):
    """Record a killer deal; in 'on' mode (and inside the caps) buy it with `buy()`. Returns a line."""
    mode = CFG.get("killer_mode", "watch")
    if mode == "off":
        return None
    picks = " + ".join(l["pick"] for l in legs)
    key = json.dumps(sorted(l["ticker"] for l in legs))
    if store_rows("select 1 from killer where legs=? and ts > ?", (key, time.time() - 6 * 3600)):
        return None                                   # one per deal
    status, why = "watched", ""
    if mode == "on":
        n, dollars = killer_today()
        spent = week_spend() if can_trade() else 0
        if n >= KILLER["per_day"] or dollars + stake > KILLER["day_dollars"] + 0.01:
            status, why = "skipped", "daily killer-deal cap reached"
        elif spent + stake > CFG["budget"] + 0.01:
            status, why = "skipped", "over your spending cap"
        else:
            ok, msg = buy()
            status, why = ("bought", msg) if ok else ("failed", msg)
    store_x("insert into killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why) values(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), kind, key, picks, mode, status, stake, pays, round(pct, 4), why))
    if alert:
        if status == "bought":
            _alert(alert, f"🔥 Auto-bought a killer deal: {picks} for {money(stake)} to win {money(pays)} "
                          f"({pct:.0%} of fair). {why}", "cash", "/app")
        elif status == "watched":
            _alert(alert, f"🔥 Killer deal (watch mode, nothing bought): {picks} at {pct:.0%} of fair, "
                          f"{money(stake)} to win {money(pays)}. Tap to buy it yourself.", "value", "/app")
    log(f"killer deal {status}: {picks} at {pct:.0%} {why}")
    return status


def killer_resolve():
    """Settle killer-deal records (watched ones too) so Results can show how they did."""
    rows = store_rows("select rowid, legs from killer where outcome is null and ts < ?", (time.time() - 2 * 3600,))
    if not rows:
        return 0
    res = fetch_results({t for r in rows for t in json.loads(r["legs"])})
    n = 0
    for r in rows:
        rs = [res.get(t) for t in json.loads(r["legs"])]
        out = "lost" if "no" in rs else "won" if all(x == "yes" for x in rs) else None
        if out:
            store_x("update killer set outcome=? where rowid=?", (out, r["rowid"]))
            n += 1
    return n


def killer_summary():
    rows = store_rows("select * from killer order by ts desc limit 60")
    done = [r for r in rows if r["outcome"] and r["status"] in ("watched", "bought")]
    pl = sum((r["pays"] if r["outcome"] == "won" else 0) - r["stake"] for r in done)
    return {"mode": CFG.get("killer_mode", "watch"), "rows": rows[:12], "settled": len(done), "pl": round(pl, 2),
            "staked": round(sum(r["stake"] for r in done), 2), "rules": KILLER}


# ---- spreads and totals: priced from the sportsbook line with a score model
# Winning margin and total points are close to normal around the line for football and basketball
# (spreads of NFL games miss by about 13.5 points on average, the classic result); hockey and soccer
# goals are Poisson. The line itself comes free from ESPN's sportsbook data.
MARGIN_SD = {"nfl": 13.5, "ncaaf": 16.0, "nba": 12.0, "ncaamb": 10.5, "ncaawb": 11.0, "euroleague": 11.0}
TOTAL_SD = {"nfl": 10.0, "ncaaf": 14.0, "nba": 17.0, "ncaamb": 14.0, "ncaawb": 13.0, "euroleague": 14.0}
LINE_MIN_EDGE = 0.04             # model prices need a wider margin than straight win prices


def _phi(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def _poisson_cdf(k, lam):
    if k < 0:
        return 0.0
    term = tot = math.exp(-lam)
    for i in range(1, int(k) + 1):
        term *= lam / i
        tot += term
    return min(1.0, tot)


def line_markets(code):
    """Kalshi's spread and total markets for a league, if it lists them: [market dicts with 'kind']."""
    base = re.match(r"(KX[A-Z]+?)(GAME|MATCH|FIGHT)$", (LEAGUES.get(code, {}).get("series") or "").split(",")[0] or "")
    if not base:
        return []
    out = []
    for kind in ("SPREAD", "TOTAL"):
        try:
            for m in fetch_series(base.group(1) + kind):
                words = " ".join(str(m.get(k) or "") for k in ("title", "subtitle", "yes_sub_title", "rules_primary")).lower()
                if re.search(r"\bbetween\b|\bexactly\b|\d+\s*(to|-)\s*\d+ (points|goals|runs)", words):
                    continue                           # a range (loses if it goes too high): the model prices only "over X"
                out.append(dict(m, kind=kind.lower()))
        except (requests.RequestException, ValueError):
            pass
    return out


def espn_lines(code):
    """{frozenset(team names lower): {'home', 'away', 'spread_home', 'total', 'start'}} from ESPN today and tomorrow."""
    out = {}
    for day in (dt.date.today(), dt.date.today() + dt.timedelta(days=1)):
        for ev in _espn_board(code, day.strftime("%Y%m%d")):
            comp = (ev.get("competitions") or [{}])[0]
            teams = {c.get("homeAway"): (c.get("team") or {}) for c in comp.get("competitors") or []}
            odds = (comp.get("odds") or [{}])[0] if comp.get("odds") else {}
            if not teams.get("home") or not odds:
                continue
            home, away = teams["home"], teams["away"]
            spread = odds.get("spread")
            det = odds.get("details") or ""
            hit = re.match(r"([A-Z]{2,5})\s+([+-]?\d+(?:\.\d+)?)", det)
            if hit:                                   # "KC -3.5": the favourite and its line
                line = float(hit.group(2))
                spread = line if hit.group(1) == home.get("abbreviation") else -line
            try:
                spread = float(spread) if spread is not None else None
                total = float(odds.get("overUnder")) if odds.get("overUnder") is not None else None
            except (TypeError, ValueError):
                continue
            out[frozenset({(home.get("displayName") or "").lower(), (away.get("displayName") or "").lower()})] = {
                "home": home.get("displayName") or "", "away": away.get("displayName") or "",
                "home_abbr": home.get("abbreviation") or "", "away_abbr": away.get("abbreviation") or "",
                "spread_home": spread, "total": total, "start": ev.get("date")}
    return out


def line_fair(code, kind, line, team_is_home, g):
    """Model chance for 'team wins by more than line' (spread) or 'total over line' (total)."""
    if kind == "spread":
        if g.get("spread_home") is None:
            return None
        mu = -g["spread_home"] if team_is_home else g["spread_home"]      # expected winning margin
        if code in MARGIN_SD:
            return _phi((mu - line) / MARGIN_SD[code])
        if code in ("nhl", "ahl", "soccer") and g.get("total"):
            lam_t = g["total"]
            lh = max(0.2, (lam_t + mu) / 2)
            la = max(0.2, lam_t - lh)
            # Skellam by summation: P(team goals - other goals > line)
            p = 0.0
            for a in range(0, 15):
                pa = math.exp(-la) * la ** a / math.factorial(a)
                need = math.floor(a + line) + 1             # home goals needed
                p += pa * (1 - _poisson_cdf(need - 1, lh))
            return p                                    # lh is this team's goals (mu is its margin)
        return None
    if g.get("total") is None:
        return None
    if code in TOTAL_SD:
        return _phi((g["total"] - line) / TOTAL_SD[code])
    if code in ("nhl", "ahl", "soccer"):
        return 1 - _poisson_cdf(math.floor(line), g["total"])
    return None


def line_candidates(code, everything=False):
    """Spread and total markets where Kalshi's price is clearly below the model's fair chance
    (everything=True: all markets near the sportsbook line, for the Build board)."""
    mk, lines = line_markets(code), espn_lines(code)
    if not mk or not lines:
        return []
    out = []
    for m in mk:
        p = price(m)
        if not p or p >= 0.95 or p <= 0.05:
            continue
        sub = (m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or "")
        strike = m.get("floor_strike")
        # the game: its two team codes must make up the event code exactly (last words like "Bears" or
        # "Eagles" are shared by many college teams, so names alone can't be trusted)
        tail = re.sub(r"^\d{2}[A-Z]{3}\d{2}", "", (m.get("event_ticker") or "").rsplit("-", 1)[-1])
        g = next((gg for gg in lines.values() if gg["home_abbr"] and gg["away_abbr"] and
                  tail in (gg["away_abbr"] + gg["home_abbr"], gg["home_abbr"] + gg["away_abbr"])), None)
        if not g:
            continue
        try:
            line = float(strike) if strike is not None else float(re.findall(r"(\d+(?:\.\d+)?)", sub)[-1])
        except (ValueError, IndexError):
            continue
        if m["kind"] == "spread":
            hn, an = g["home"].lower(), g["away"].lower()
            sl = sub.lower()
            in_h = hn in sl or any(w in sl for w in hn.split()[:-1] if len(w) > 3)
            in_a = an in sl or any(w in sl for w in an.split()[:-1] if len(w) > 3)
            if in_h == in_a:                            # can't tell which team this market is about: skip it
                tkt = m["ticker"].rsplit("-", 1)[-1].upper()
                if tkt.startswith(g["home_abbr"].upper()) != tkt.startswith(g["away_abbr"].upper()):
                    in_h = tkt.startswith(g["home_abbr"].upper())
                else:
                    continue
            team_is_home = in_h
            team = g["home"] if team_is_home else g["away"]
            sd = MARGIN_SD.get(code, 2.0)
            mu = -g["spread_home"] if (g["spread_home"] is not None and team_is_home) else (g["spread_home"] or 0)
            if abs(line - mu) > sd * 0.8:
                continue                                # far from the line: the model's tails are less reliable
            fair = line_fair(code, "spread", line, team_is_home, g)
            label = f"{team} win by {line:g}+" if line > 0 else f"{team} lose by under {abs(line):g}"
        else:
            sd = TOTAL_SD.get(code, 1.5)
            if g["total"] is None or abs(line - g["total"]) > sd * 0.8:
                continue
            fair = line_fair(code, "total", line, True, g)
            label = f"Over {line:g} ({g['away'].split()[-1]} at {g['home'].split()[-1]})"
        if fair is None:
            continue
        if abs(fair - p) > 0.15:                        # the market disagrees wildly: our match or model is wrong
            continue
        edge = fair - p - single_fee(p)
        if everything or (edge >= LINE_MIN_EDGE and edge / p >= 0.06):
            out.append({"ticker": m["ticker"], "event": m.get("event_ticker"), "pick": label, "fair": round(fair, 4),
                        "p": p, "edge": round(edge, 4), "kind": m["kind"], "line": line, "src": "model",
                        "book_line": g["spread_home"] if m["kind"] == "spread" else g["total"],
                        "start": g.get("start"), "game": f"{team_short(code, g['away'])} at {team_short(code, g['home'])}"})
    return sorted(out, key=lambda x: -x["edge"] / x["p"])


# ---- same-game combos (a team to win + the game's total): tested on paper first
SAME_GAME_RHO = {"nfl": 0.05, "ncaaf": 0.05, "nba": 0.03, "ncaamb": 0.03}   # margin-total link (small)
PROBE = {}


def combo_probe(code):
    """Does Kalshi let spread/total markets into combos with the game winner? Checked once a day:
    {'total': bool, 'spread': bool, 'at'}."""
    got = PROBE.get(code)
    if got and time.time() - got["at"] < 86400:
        return got
    out = {"total": False, "spread": False, "at": time.time()}
    mk = line_markets(code)
    for kind in ("total", "spread"):
        m = next((x for x in mk if x["kind"] == kind and x.get("event_ticker")), None)
        if not m:
            continue
        try:
            r = requests.get(f"{KALSHI}/multivariate_event_collections", timeout=20,
                             params={"associated_event_ticker": m["event_ticker"], "status": "open", "limit": 50})
            cols = r.json().get("multivariate_contracts", []) if r.ok else []
        except (requests.RequestException, ValueError):
            cols = []
        game_ev = re.sub(r"(SPREAD|TOTAL)-", "GAME-", m["event_ticker"])
        for c in cols:
            inside = {a.get("ticker") for a in c.get("associated_events", [])} or set(c.get("associated_event_tickers") or [])
            if m["event_ticker"] in inside and game_ev in inside:
                out[kind] = True
                break
    PROBE[code] = out
    if STORE["db"]:
        store_x("insert into events values(?,?,?,?)", (time.time(), "probe", code, json.dumps(out)))
    return out


def joint_win_over(mu, sd_m, tot, sd_t, line, rho, over=True, n=20000):
    """Chance the team wins AND the total goes over (or under) `line`, with margin and total
    linked by rho. Monte Carlo with a fixed seed, so the same inputs give the same answer."""
    rnd = random.Random(7)
    hit = 0
    for _ in range(n):
        z1 = rnd.gauss(0, 1)
        z2 = rho * z1 + math.sqrt(1 - rho * rho) * rnd.gauss(0, 1)
        if mu + sd_m * z1 > 0 and ((tot + sd_t * z2 > line) == over):
            hit += 1
    return hit / n


def same_game_combos(code, games, stake=None, k=2):
    """Winner + total combos from the same game, priced jointly (not by multiplying), for the paper test."""
    if code not in SAME_GAME_RHO or not combo_probe(code).get("total"):
        return []
    stake = stake or CFG["stake"]
    lines, mk = espn_lines(code), [m for m in line_markets(code) if m["kind"] == "total"]
    out = []
    for e, sides in games.items():
        for x in sides:
            if x.get("tie") or not x.get("p") or started(x):
                continue
            g = next((gg for teams, gg in lines.items() if (x.get("pick") or "").lower() in teams), None)
            if not g or g.get("spread_home") is None or g.get("total") is None:
                continue
            home = (x["pick"] or "").lower() == g["home"].lower()
            mu = -g["spread_home"] if home else g["spread_home"]
            tm = next((m for m in mk if g["home_abbr"] in m.get("event_ticker", "") and g["away_abbr"] in m.get("event_ticker", "")
                       and abs(float(m.get("floor_strike") or 0) - g["total"]) <= 1.5 and price(m)), None)
            if not tm:
                continue
            line = float(tm["floor_strike"])
            joint = joint_win_over(mu, MARGIN_SD[code], g["total"], TOTAL_SD[code], line, SAME_GAME_RHO[code])
            tp = price(tm)
            leg2 = {"ticker": tm["ticker"], "event": tm["event_ticker"], "pick": f"Over {line:g}", "p": tp,
                    "fair": _phi((g["total"] - line) / TOTAL_SD[code]), "src": "model"}
            legs = [x, leg2]
            out.append({"kind": "same_game", "tier": "Same game", "legs": legs, "fair": stake / joint,
                        "kalshi": stake / (x["p"] * tp), "min": stake / joint * CFG["accept_pct"] / 100,
                        "same_game": True, "value_pct": round(joint / (x["p"] * tp), 4)})
    out.sort(key=lambda c: -c["value_pct"])
    return out[:k]


def line_pass(code, alert=None, log=print):
    """Spread and total ideas for one league (single bets: no combo maker). Model-priced, so never
    killer deals; shown with the line they're priced from."""
    if not STORE["db"]:
        return []
    did, now = [], time.time()
    for x in line_candidates(code)[:3]:
        try:
            if dt.datetime.fromisoformat(str(x["start"]).replace("Z", "+00:00")).timestamp() < now + 300:
                continue                                # pre-game only: the model knows nothing about the score
        except ValueError:
            continue
        d = book_depth(x["ticker"])
        if d and d["thin"]:
            continue
        prev = store_rows("select pct, ts from suggestions where legs=? and n=1 order by ts desc limit 1",
                          (json.dumps([x["ticker"]]),))
        pct = x["fair"] / (x["p"] + single_fee(x["p"]))
        if prev and now - prev[0]["ts"] < 7200 and pct - prev[0]["pct"] < 0.03:
            continue
        stake = edge_stake(1 + (pct - 1) * 0.7, CFG.get("size_min", 3), CFG.get("size_max", 10), x["fair"])
        n = max(1, int(stake / (x["p"] + single_fee(x["p"]))))
        sid = store_suggestion({"legs": [dict(x, event=x["event"] or "")], "fair": stake / x["fair"]},
                               {"pays": float(n), "stake": round(n * (x["p"] + single_fee(x["p"])), 2)}, pct)
        store_x("update suggestions set note=? where id=?",
                (f"Priced from the sportsbook {'spread' if x['kind'] == 'spread' else 'total'} of "
                 f"{x['book_line']:+g}".replace("+", "" if x["kind"] == "total" else "+") + " with a score model", sid))
        if alert:
            _alert(alert, f"📐 {x['pick']} at {x['p'] * 100:.0f}¢ on Kalshi; the score model puts it at {x['fair']:.0%} "
                          f"from the sportsbook line. About {x['edge'] * 100:.1f}¢ a contract in your favour.", "value",
                   f"/app#s={sid}" if sid else "/app")
        did.append(f"line idea {x['pick']} {x['p']:.2f} vs {x['fair']:.2f}")
    return did


# ---- standing orders: buy orders resting a few cents under fair, managed by the Mac
MAKER = {"discount": 0.03, "per_order": 10.0, "max_orders": 6, "max_dollars": 40.0, "min_fair": 0.2,
         "max_fair": 0.85, "cancel_mins": 20, "reprice": 0.01, "horizon_hours": 30}


def maker_fee(p):
    return 0.25 * FEE_RATE * p * (1 - p)             # resting orders pay much less than taking; assume a quarter


def maker_open(mode=None):
    q = "select rowid, * from maker where status in ('posted', 'watching')"
    return store_rows(q + (" and mode=?" if mode else ""), (mode,) if mode else ())


def maker_cancel(row, why, log=print):
    if row["mode"] == "on" and row.get("order_id"):
        try:
            kalshi_send("DELETE", f"/portfolio/orders/{row['order_id']}")
        except Exception as err:
            log("standing order cancel failed:", err)
    store_x("update maker set status=?, why=?, updated=? where rowid=?",    # a part-filled order keeps its fill
            ("filled" if (row.get("filled") or 0) > 0 else "cancelled", why, time.time(), row["rowid"]))


def maker_cancel_all(why="paused", log=print):
    for row in maker_open():
        maker_cancel(row, why, log)


def _maker_post(ticker, n, price, expire_ts):
    import uuid
    body = {"ticker": ticker, "action": "buy", "side": "yes", "type": "limit", "count": int(n),
            "yes_price": int(round(price * 100)), "client_order_id": str(uuid.uuid4()),
            "expiration_ts": int(expire_ts)}                # Kalshi drops it by itself before the game
    o = (kalshi_send("POST", "/portfolio/orders", body) or {}).get("order") or {}
    return o.get("order_id") or o.get("id")


def _maker_status(order_id):
    o = (kalshi_send("GET", f"/portfolio/orders/{order_id}") or {}).get("order") or {}
    filled = float(o.get("fill_count_fp") or o.get("fill_count") or 0)
    return (o.get("status") or "").lower(), filled


def maker_pass(games, book_snap, alert=None, log=print):
    """Keep standing buy orders a few cents under fair for the league on screen: post, re-price when the
    fair chance moves, cancel near game time or on news, and record fills. Watch mode only simulates."""
    mode = CFG.get("maker_mode", "watch")
    now, did = time.time(), []
    sides = {x["ticker"]: x for sd in games.values() for x in sd}
    for row in maker_open():                           # switched modes: what the old mode left out there goes
        if (row["mode"] == "on") != (mode == "on") or mode == "off":
            maker_cancel(row, f"switched to {mode}", log)
    # 1) look after what's already out there (this league's)
    for row in maker_open():
        x = sides.get(row["ticker"])
        if x is None:
            continue
        kick = row.get("kick") or 0
        fair_now = x.get("fair") or row["fair"]
        try:
            _, fresh = injury_note(LEAGUE["code"], x["pick"], opp_of(games, x), hours=3)
        except Exception:
            fresh = False
        if row["mode"] == "on":
            try:
                st, filled = _maker_status(row["order_id"])
            except Exception:
                st, filled = "", 0
            if filled > (row.get("filled") or 0):
                store_x("update maker set filled=?, updated=? where rowid=?", (filled, now, row["rowid"]))
                if alert:
                    _alert(alert, f"✅ Standing order filled: {filled:g} {x['pick']} at {row['price'] * 100:.0f}¢ "
                                  f"(fair {fair_now:.0%}). Auto standing order.", "cash", "/app")
                did.append(f"filled {x['pick']}")
            if st in ("executed", "canceled", "cancelled", "expired"):
                store_x("update maker set status=?, updated=? where rowid=?",
                        ("filled" if (filled or 0) > 0 else "cancelled", now, row["rowid"]))
                continue
        else:                                          # watch: filled if Kalshi's ask came down to our price
            ask = x.get("p")
            if ask is not None and ask <= row["price"] + 1e-9:
                store_x("update maker set status='filled', filled=n, updated=? where rowid=?", (now, row["rowid"]))
                did.append(f"would have filled {x['pick']} at {row['price']:.2f}")
                continue
        if kick and kick - now < MAKER["cancel_mins"] * 60:
            maker_cancel(row, "game about to start", log)
        elif fresh:
            maker_cancel(row, "injury news", log)
        elif abs(fair_now - row["fair"]) >= MAKER["reprice"]:
            maker_cancel(row, f"fair moved {row['fair']:.0%} → {fair_now:.0%}", log)   # re-posted below
    if mode == "off":
        return did
    # 2) post new ones, within the limits
    live = maker_open(mode="on" if mode == "on" else "watch")
    held = {r["ticker"] for r in live}
    recent = store_rows("select ticker from maker where status='filled' and ts > ?", (now - 86400,))
    held_events = {sides[r["ticker"]]["event"] for r in live + recent if r["ticker"] in sides}   # one per game
    committed = sum(r["price"] * r["n"] for r in live)
    spent = week_spend() if (mode == "on" and can_trade()) else 0
    cands = []
    for x in sides.values():
        if x.get("tie") or x.get("src") is None or started(x) or not x.get("fair") or not x.get("p"):
            continue
        if not MAKER["min_fair"] <= x["fair"] <= MAKER["max_fair"] or x["ticker"] in held or x["event"] in held_events:
            continue
        kick = _kick_ts(x)
        if not kick or kick - now < (MAKER["cancel_mins"] + 10) * 60 or kick - now > MAKER["horizon_hours"] * 3600:
            continue
        price = math.floor((x["fair"] - MAKER["discount"] - maker_fee(x["fair"])) * 100) / 100
        if price <= 0.02 or price >= x["p"]:
            continue                                   # at or above the ask: that's a buy idea, not a resting order
        ok, _ = sources_agree(book_snap, x["pick"], x["fair"])
        if not ok:
            continue                                   # one source isn't enough to leave an order sitting
        cands.append((kick, x, price))
    cands.sort(key=lambda t: t[0])
    for kick, x, price in cands:
        if len(live) >= MAKER["max_orders"] or x["event"] in held_events:
            continue
        n = max(1, int(min(MAKER["per_order"], CFG.get("size_max", 10)) / price))
        cost = n * price
        if committed + cost > MAKER["max_dollars"] or (mode == "on" and spent + committed + cost > CFG["budget"] + 0.01):
            break
        oid, status = None, "watching"
        if mode == "on":
            try:
                oid = _maker_post(x["ticker"], n, price, kick - MAKER["cancel_mins"] * 60)
                status = "posted"
            except Exception as err:
                log("standing order not posted:", err)
                continue
        store_x("insert into maker(ts, ticker, pick, mode, price, n, fair, status, order_id, filled, updated, kick) "
                "values(?,?,?,?,?,?,?,?,?,?,?,?)", (now, x["ticker"], x["pick"], mode, price, n, x["fair"], status, oid, 0,
                                                    now, kick))
        live.append({"ticker": x["ticker"], "price": price, "n": n})
        held_events.add(x["event"])
        committed += cost
        did.append(f"{'posted' if mode == 'on' else 'watching'} {x['pick']} {n} at {price:.2f} (fair {x['fair']:.2f})")
    return did


def maker_resolve():
    rows = store_rows("select rowid, ticker from maker where status='filled' and outcome is null and updated < ?",
                      (time.time() - 3600,))
    if not rows:
        return 0
    res = fetch_results({r["ticker"] for r in rows})
    for r in rows:
        if res.get(r["ticker"]) in ("yes", "no"):
            store_x("update maker set outcome=? where rowid=?", ("won" if res[r["ticker"]] == "yes" else "lost", r["rowid"]))
    return len(rows)


def maker_summary():
    rows = store_rows("select * from maker order by ts desc limit 80")
    done = [r for r in rows if r["status"] == "filled" and r["outcome"]]
    pl = sum(((1 - r["price"]) if r["outcome"] == "won" else -r["price"]) * (r["filled"] or r["n"]) for r in done)
    return {"mode": CFG.get("maker_mode", "watch"), "open": [r for r in rows if r["status"] in ("posted", "watching")][:8],
            "recent": rows[:10], "settled": len(done), "pl": round(pl, 2),
            "filled": sum(1 for r in rows if r["status"] == "filled"), "rules": MAKER}


def single_pass(book_snap, alert=None, log=print):
    """Look for single-game value in the league on screen; each one becomes a buy idea (no quotes needed)."""
    if not STORE["db"]:
        return []
    book = load_book_state(book_snap)
    games, _, _ = week_games(fetch_markets())
    attach_fair(games, book)
    live_ok = set()
    if CFG.get("include_live", True):
        bf = {e: [x["fair"] for x in sd] for e, sd in games.items() if sd[0].get("src")}
        skipped, live = screen_live(games, bf)
        live_ok = set(live) - set(skipped)
    did, now = [], time.time()
    try:
        did += maker_pass(games, book_snap, alert, log)
    except Exception as err:
        log("standing orders:", type(err).__name__, err)
    for x in single_candidates(games, live_ok)[:8]:              # remember fair chances for the steadiness check
        store_x("insert into fairs values(?,?,?,?)", (now, x["ticker"], x["fair"], x["p"]))
    for x in single_candidates(games, live_ok)[:4]:
        told = False
        d = book_depth(x["ticker"])
        if d and d["thin"]:
            continue                                  # a thin book: the price isn't real
        try:
            inj, fresh = injury_note(LEAGUE["code"], x["pick"], x.get("opp") or opp_of(games, x))
        except Exception:
            inj, fresh = [], False
        if fresh and x["edge"] >= 0.06:
            log(f"single {x['pick']} skipped: fresh injury news and a big gap, prices may be catching up")
            continue                                  # a gap that big right after news is usually the news
        prev = store_rows("select pct, ts from suggestions where legs=? and n=1 order by ts desc limit 1",
                          (json.dumps([x["ticker"]]),))
        pct = x["fair"] / (x["p"] + single_fee(x["p"]))
        if prev and now - prev[0]["ts"] < 7200 and pct - prev[0]["pct"] < 0.03:
            continue                                  # already offered, and not meaningfully better
        stake = edge_stake(pct, CFG.get("size_min", 3), CFG.get("size_max", 10), x["fair"])
        n = max(1, int(stake / (x["p"] + single_fee(x["p"]))))
        if x["edge"] >= KILLER["single_edge"] and x["edge"] / x["p"] >= KILLER["single_rel"] and \
                CFG.get("killer_mode", "watch") != "off":
            ok, why_not = killer_check([x], book_snap)
            if ok:
                d = book_depth(x["ticker"], max_age=0) or {}
                ask = d.get("ask") or x["p"]
                kn = max(1, int(min(stake, KILLER["per_buy"]) / (ask + single_fee(ask))))
                if (d.get("ask_size") or 0) >= kn and fair_ok(x, ask):
                    st = killer_act("single", [x], round(kn * (ask + single_fee(ask)), 2), float(kn),
                                    x["fair"] / (ask + single_fee(ask)),
                                    lambda: _killer_single(x["ticker"], kn, ask), alert, log)
                    if st == "bought":
                        continue                       # bought, and its own alert already went out
                    told = st == "watched"
            else:
                log(f"near-killer {x['pick']} held back: {'; '.join(why_not)}")
        c = {"legs": [x], "fair": stake / x["fair"]}
        sid = store_suggestion(c, {"pays": float(n), "stake": round(n * (x["p"] + single_fee(x["p"])), 2)}, pct)
        live = " (game in progress)" if started(x) else ""
        extra = game_context(LEAGUE["code"], x["pick"], x.get("opp") or opp_of(games, x))
        if inj or extra:
            store_x("update suggestions set note=? where id=?", (" · ".join(inj + extra), sid))
        msg = (f"🎯 Single: {x['pick']}{live} at {x['p'] * 100:.0f}¢ on Kalshi; the sharp books say "
               f"{x['fair']:.0%}. About {x['edge'] * 100:.1f}¢ a contract in your favour after the fee."
               + (f" Injuries: {'; '.join(inj[:2])}." if inj else ""))
        if alert and not told:
            _alert(alert, msg, "value", f"/app#s={sid}" if sid else "/app")
        did.append(f"single idea {x['pick']} {x['p']:.2f} vs {x['fair']:.2f}")
    return did


def fair_ok(x, ask):
    return x["fair"] - ask - single_fee(ask) >= KILLER["single_edge"] * 0.9


def _killer_single(ticker, n, price):
    filled, err = buy_single(ticker, n, price)
    if err:
        return False, err
    if filled <= 0:
        return False, "nobody was selling at that price any more"
    return True, f"Bought {filled:g} at {price * 100:.0f}¢."


def buy_single(ticker, n, price):
    """Buy n YES contracts at `price` or better, now or not at all (fills now or cancels). After your tap."""
    import uuid
    body = {"ticker": ticker, "action": "buy", "side": "yes", "type": "limit", "count": int(n),
            "yes_price": int(round(price * 100)), "time_in_force": "immediate_or_cancel",
            "client_order_id": str(uuid.uuid4())}
    try:
        o = (kalshi_send("POST", "/portfolio/orders", body) or {}).get("order") or {}
    except PermissionError:
        return 0, "Kalshi refused. The key needs write (trading) access."
    except RuntimeError as err:
        return 0, f"Kalshi didn't take the order: {err}"
    filled = float(o.get("fill_count_fp") or o.get("fill_count") or
                   (body["count"] - float(o.get("remaining_count") or 0) if o.get("status") == "executed" else 0))
    ACCT_CACHE["at"] = 0
    return filled, None


def _alert(alert, msg, kind, url):
    try:
        alert(msg, kind, url)
    except TypeError:                                 # an older alert function: no link
        alert(msg, kind)


def store_suggestion(c, r, pct):
    """Remember a combo Kalshi just priced at or above your cut-off, so Live can offer it. Returns its id."""
    if not STORE["db"]:
        return None
    now = time.time()
    live = any(started(l) for l in c["legs"])
    kicks = [x for x in (_kick_ts(l) for l in c["legs"]) if x and x > now]   # the next game still to start
    sid = f"{int(now)}{random.randint(100, 999)}"
    store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) "
            "values(?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, now, LEAGUE["code"], json.dumps([l["ticker"] for l in c["legs"]]),
             " + ".join(l["pick"] for l in c["legs"]), len(c["legs"]), round(pct, 4), round(r["pays"], 2),
             r["stake"], round(c.get("fair") or 0, 2), min(kicks) if kicks else None, int(live)))
    if len(c["legs"]) == 1 and c["legs"][0].get("fair"):
        store_x("update suggestions set pfair=? where id=?", (c["legs"][0]["fair"], sid))
    try:                                              # who's out, for the card (from ESPN's injury report)
        picks = [l["pick"] for l in c["legs"]]
        inj, _ = injury_note(LEAGUE["code"], *picks)
        extra = game_context(LEAGUE["code"], *picks)
        if inj or extra:
            store_x("update suggestions set note=? where id=?", (" · ".join(inj + extra), sid))
    except Exception:
        pass
    return sid


def live_suggestions(max_age=3600, limit=6):
    """Buy ideas still worth a look: recent, games not started yet, best price first, one per set of picks."""
    now = time.time()
    rows = store_rows("select * from suggestions where ts > ? and (kick is null or kick > ?) "
                      "and (coalesce(live, 0) = 0 or ts > ?) order by pct desc",
                      (now - max_age, now + 300, now - 600))      # in-progress ideas go stale in 10 minutes
    seen, out = set(), []
    for r in rows:
        if r["legs"] in seen:
            continue
        seen.add(r["legs"])
        out.append(dict(r, legs=json.loads(r["legs"]), sport=LEAGUES.get(r["lg"], {}).get("short", r["lg"])))
    return out[:limit]


def _killer_combo(i):
    if i not in CTX["offers"]:
        return False, "the quote expired"
    r = accept_offer(i)
    if r.get("error"):
        return False, r["error"]
    return True, "Bought at Kalshi's quote."


def shadow_candidates_with(book):
    games, days, slate = week_games(fetch_markets())
    attach_fair(games, book)
    if not games:
        return []
    live_ok = set()
    if CFG.get("include_live", True):              # games under way, with the same safety screens as Build
        bf = {e: [x["fair"] for x in sides] for e, sides in games.items() if sides[0].get("src")}
        skipped, live = screen_live(games, bf)
        games = {e: sd for e, sd in games.items() if e not in skipped}
        live_ok = set(live) - set(skipped)
    games = {e: sd for e, sd in games.items() if e in live_ok or not any(started(x) for x in sd)}
    if not games:
        return []
    combos, _ = build_combos(games, {}, random.Random(int(time.time() // 600)))
    try:
        combos = value_combos(games, live_ok=live_ok) + combos   # built for price first, then the usual mix
    except Exception as err:
        console_note(f"value search: {type(err).__name__}: {err}")
    try:
        combos = same_game_combos(LEAGUE["code"], games) + combos   # paper test of same-game pricing
    except Exception as err:
        console_note(f"same-game search: {type(err).__name__}: {err}")
    out, seen_keys = [], set()
    floor = CFG.get("live_min", 25) / 100
    for c in combos:
        if not c.get("fair") or not c.get("kalshi"):
            continue
        ck = frozenset(l["ticker"] for l in c["legs"])
        if ck in seen_keys:
            continue
        seen_keys.add(ck)
        if any(started(l) and (l["event"] not in live_ok or (l.get("fair") or 0) < floor) for l in c["legs"]):
            continue                              # a game under way that failed the checks, or a long shot now
        if any(l.get("src") is None and not l.get("live") for l in c["legs"]):
            continue                              # only picks with a sportsbook line (or a checked live price)
        kicks = [_kick_ts(l) for l in c["legs"]]
        if None in kicks or min(kicks) - time.time() > SHADOW_WINDOW:
            continue                              # quote close to game time, when combos price best
        pred = None
        try:
            pred = predict_quote(c)
        except Exception:
            pass
        if pred and pred["n"] >= 40 and pred["p_clear"] <= 0.05:
            continue                              # learned: Kalshi won't price this near fair; save the quote
        out.append(((pred["pct"] if pred else None) or est_offer(c)[1] or 0.8 * c["kalshi"] / c["fair"], c))
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
    ev = leg.get("event") or ""
    if ev not in KICKOFF:
        ev = re.sub(r"(SPREAD|TOTAL)-", "GAME-", ev)        # a spread/total: its game's kickoff
    try:
        return dt.datetime.fromisoformat(str(KICKOFF.get(ev)).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ================================================================ the daily panel
# Up to ~10 bets a day across sports and bet types, chosen together for the best chance that the whole
# panel ends up ahead (Pete's goal), not the biggest possible profit. Rules:
#  - every bet is priced at or better than its real chance (fair = the sharp books, margin removed),
#    after Kalshi's fee; combos must be predicted to clear the (self-adjusting) cut-off
#  - no hidden overlap: at most 2 bets ride on any one game, never both sides of one game
#  - each sport on its own rhythm: NBA/NHL/college by the day, the NFL week as one slate
#  - sell-early favorites: bought at fair or better with an exit price the Mac sells at by itself
#  - NFL slate combos spread over the day's time slots, with the usual number of upsets built in
# Pete approves a panel once; the Mac then buys each bet right away (Pete's decision: waiting until shortly before
# the game gave up the price he approved), after checking the price again, swapping in a similar bet if one no
# longer qualifies. A paper copy runs the panel fully
# automatically alongside, which is the record that decides when it can be handed $300.
PANEL = {"size": 10, "per_game": 2, "longer_max": 2, "pool_age": 45 * 60,
         "fresh_age": 12 * 60, "min_edge": 0.02, "line_edge": 0.06, "line_share": 0.3, "budget": 40.0, "max_bet_share": 0.05, "skim": 0.5}
PANEL_POOL = {}            # code -> (time, [candidates])
PANEL_GAMES = {}           # code -> games coming up (for showing only the sports that have any)
NEXT_KICK = {}             # code -> the next start time (checked every few minutes when it's close)
LIVE_NOW = {}              # code -> True while it has a game under way priced live for the panel (checked often)
LIVE_WHY = {}              # code -> {game: why a game under way was left out}
BUY_WAIT = {}              # code -> when an approved bet last waited for fresher prices (looked at again soon)
REBUILD_FLAG = os.path.join(HERE, "panel_rebuild.flag")
BUY_FLAG = os.path.join(HERE, "panel_buy.flag")      # left by Approve / Add: the Mac's buying pass runs within seconds


def sports_near(within=2 * 3600):
    """Sports with a game starting in the next two hours, or a game under way priced live for the panel: checked
    every few minutes, not every ten (live prices go stale fast)."""
    now = time.time()
    near = [c for c, k in NEXT_KICK.items() if (k and now < k <= now + within) or LIVE_NOW.get(c)] + \
        [c for c, on in LIVE_NOW.items() if on and c not in NEXT_KICK]
    return near + [c for c, t in BUY_WAIT.items() if now - t < 15 * 60 and c not in near]   # approved, waiting on a fresh price


def rebuild_asked():
    """Combo Hub asked for a fresh panel now (a tap of 'Build a fresh panel'); clears the request."""
    try:
        os.remove(REBUILD_FLAG)
        return True
    except OSError:
        return False


REBUILD_STATE = os.path.join(HERE, "combo_rebuild.json")   # how far a requested rebuild has got (the page shows it)


def rebuild_pending():
    """A fresh panel was asked for and the Mac hasn't started on it yet (the flag is still there)."""
    return os.path.exists(REBUILD_FLAG)


def ask_rebuild():
    """Ask the Mac for a fresh panel now: its rebuild thread sees this within a few seconds."""
    try:
        open(REBUILD_FLAG, "w").close()
        return True
    except OSError:
        return False


def ask_buy():
    """Approve / Add just scheduled bets: wake the Mac's buying pass now instead of at its next minute."""
    try:
        open(BUY_FLAG, "w").close()
        return True
    except OSError:
        return False


def buy_asked():
    """The watcher's panel_loop: was a buying pass asked for? Clears the request (a later tap leaves a new one)."""
    try:
        os.remove(BUY_FLAG)
        return True
    except OSError:
        return False


def _rebuild_note(**kw):
    save_json(REBUILD_STATE, dict(kw, upd=time.time()))


def rebuild_status(now=None):
    """What the Build page shows about a requested rebuild: asked (waiting for the Mac to start), running
    (which sport, how many of how many), or done (how many bets it found, or why none). None when nothing to say."""
    now = now or time.time()
    s = load_json(REBUILD_STATE, None) or {}
    if s.get("state") == "running" and now - (s.get("upd") or 0) < 300:
        return s
    try:
        asked = os.path.getmtime(REBUILD_FLAG)
    except OSError:
        asked = None
    if asked:
        return {"state": "asked", "at": asked, "wait": round(now - asked)}
    if s.get("state") == "done" and now - (s.get("upd") or 0) < 6 * 3600 and _panel_day(s["upd"]) == _panel_day(now):
        return s
    return None


def panel_rebuild(collect, codes, lock=None, log=print):
    """'Build a fresh panel' was tapped: look at every sport now (not at the next 10-minute round), then put the
    panel together the usual way (panel_pass: the same choices and rules; drafts only, never buys).
    collect(code) gathers one sport's candidates; lock guards the shared engine between steps. Notes progress
    for the page as it goes and returns the panel_pass messages."""
    import contextlib
    lock = lock or contextlib.nullcontext()
    rebuild_asked()                                    # clear the request; a new tap during the run asks again
    codes, t0 = list(codes), time.time()
    for i, code in enumerate(codes):
        _rebuild_note(state="running", at=t0, sport=code, i=i, n=len(codes))
        try:
            with lock:
                collect(code)
        except Exception as err:
            log(f"rebuild {code} skipped:", type(err).__name__, err)
    _rebuild_note(state="running", at=t0, sport="", i=len(codes), n=len(codes), step="choosing")
    with lock:
        out = panel_pass(log=log)
        real = panel_get("real")
        games = sum(PANEL_GAMES.get(c) or 0 for c in codes)
        left = float(CFG.get("panel_budget", PANEL["budget"])) - spent_earlier_today()
    if real and real.get("status") == "draft":
        found, kind = len(real.get("items") or []), "panel"
    elif real and real.get("status") == "approved":
        x = panel_extras(real)
        found, kind = len((x or {}).get("items") or []), "extra"
    else:
        found, kind = 0, "panel"
    why = ""
    if not found:
        if not games:
            why = "No games left today to bet on."
        elif left < 2:
            why = "Today's panel budget is already used."
        else:
            why = (f"Checked {games} upcoming game{'s' if games != 1 else ''}: none is priced better than its real "
                   f"chance right now (Kalshi is in line with the sportsbooks).")
    _rebuild_note(state="done", at=t0, took=round(time.time() - t0, 1), found=found, kind=kind, games=games, why=why,
                  n=len(codes))
    log(f"panel rebuild: {found} bet{'s' if found != 1 else ''} in {time.time() - t0:.0f}s")
    return out
CUTOFF_FILE = os.path.join(HERE, "combo_cutoffs.json")
SIZING_FILE = os.path.join(HERE, "combo_sizing.json")
SWING = {"nhl": 1.25, "ahl": 1.3, "soccer": 1.25, "mls": 1.25, "epl": 1.25, "nfl": 1.0, "ncaaf": 0.95, "nba": 0.8,
         "ncaamb": 0.9, "ncaawb": 0.9, "wnba": 0.85, "mlb": 1.05, "tennis": 1.0}   # how fast a lead can vanish


def _local_day_end(now=None):
    """4 a.m. Pacific tomorrow: today's panel covers games starting before then."""
    t = dt.datetime.now(PACIFIC) if now is None else dt.datetime.fromtimestamp(now, PACIFIC)
    end = (t + dt.timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
    if t.hour < 4:
        end -= dt.timedelta(days=1)
    return end.timestamp()


def _nfl_week_end(now=None):
    """Tuesday 4 a.m. Pacific after this NFL week's Monday game."""
    t = dt.datetime.now(PACIFIC) if now is None else dt.datetime.fromtimestamp(now, PACIFIC)
    days = (1 - t.weekday()) % 7 or 7
    return (t + dt.timedelta(days=days)).replace(hour=4, minute=0, second=0, microsecond=0).timestamp()


# ---- the self-adjusting combo cut-off, per league and size: a league short on data uses its sport's level
# (exactly what it used before leagues had their own), and a sport with no record yet borrows everyone's, but
# only upward: a borrowed level is never under the 95% start (only a group's own record can take it toward 85%).
CUT_MIN_N = 30            # quotes a league (or everyone together) needs before its own cut-off is used
CUT_START = 95.0          # where every group starts; the floor for a level borrowed from everyone's


def _cut_key(code, n):
    return f"{code}:{'2' if n <= 2 else '3-4' if n <= 4 else '5-7' if n <= 7 else '8+'}"


def _tickers_of(legs):
    out = []
    for x in legs or ():
        t = x.get("ticker") if isinstance(x, dict) else x[0] if isinstance(x, (list, tuple)) and x else x
        out.append(t if isinstance(t, str) else "")
    return out


def _combo_league(code, legs):
    """The league a combo's cut-off is learned in when it's narrower than its sport (each soccer league),
    else None (a league that is its own sport, or a combo across leagues)."""
    tks = [t for t in _tickers_of(legs) if t]
    k = bet_key(tks) if tks else None
    return k if k and k not in ("mix", "other", code) and ticker_sport(tks[0]) == code else None


def _cut_own(e):
    """A league's (or everyone's) own cut-off counts once it has solid data, or once it has moved."""
    return bool(e) and (e.get("n", 0) >= CUT_MIN_N or bool(e.get("why")))


def _cut_level(d, code, n, legs=None):
    """(level in %, the group it came from): the league's own once it has enough quotes, else the sport's
    (unchanged from before), else everyone's once that has enough, else the 95% start."""
    lg = _combo_league(code, legs)
    if lg:
        e = d.get(_cut_key(lg, n))
        if _cut_own(e):
            return float(e.get("level", 95)), _cut_key(lg, n)
    e = d.get(_cut_key(code, n))
    if e and (not e.get("borrowed") or _cut_own(e)):
        return float(e.get("level", 95)), _cut_key(code, n)
    e = d.get(_cut_key("all", n))
    if _cut_own(e):                                # everyone's mixes every sport: borrowed only upward
        return max(float(e.get("level", 95)), CUT_START), _cut_key("all", n)
    return CUT_START, None


def combo_cutoff(code, n, legs=None):
    """The share of fair a combo must be priced at for the panel. Starts at 95%; never below 85%.
    legs (tickers or leg dicts) lets a league with its own record (e.g. the Premier League) use its own level."""
    return _cut_level(load_json(CUTOFF_FILE, {}), code, n, legs)[0] / 100


def adjust_cutoffs(force=False):
    """Once a week: move each group's cut-off a step from its own evidence. Up if combos bought just above
    the bar have been returning well under what they cost; down (never below 85%) if the ones it would have
    skipped, just under the bar, are returning more than they cost. Needs 30+ settled quotes in a band.
    Groups: everyone together, each sport (as always), and each league inside a sport (soccer's). A group
    new to the file starts from the level it was borrowing, so its first step is from there. A sport still
    borrowing (never at or under 95%) is saved marked "borrowed" until it has 30+ quotes of its own, so a
    borrowed level is never kept as if the sport had learned it."""
    d = load_json(CUTOFF_FILE, {})
    if not force and time.time() - d.get("_at", 0) < 7 * 86400:
        return []
    if not STORE["db"]:
        return []
    rows = store_rows("select sport, n, pct, pays, stake, legs, outcome, ts from quotes where pct is not null and ts > ?",
                      (time.time() - 60 * 86400,))
    trip = exit_factor()
    groups = defaultdict(list)
    kind = {}                                          # key -> (0 everyone | 1 sport | 2 league, sport, n)
    for r in rows:
        legs = json.loads(r["legs"] or "[]")
        cl = close_prices([x[0] for x in legs])
        r = dict(r)
        if legs and len(cl) == len(legs) and all(x[1] for x in legs):
            # the faster signal: what the combo was worth at game time (Kalshi's own prices then), after the trip
            r["val"] = r["pays"] / r["stake"] * math.prod(cl[x[0]] for x in legs) * trip
        elif r["outcome"] in ("won", "lost"):
            r["val"] = (r["pays"] / r["stake"] if r["outcome"] == "won" else 0) * trip
        else:
            continue
        n = r["n"] or 2
        sps = (r["sport"] or "").split(",")
        for sp in sps:
            groups[_cut_key(sp, n)].append(r)
            kind[_cut_key(sp, n)] = (1, sp, n)
            lg = _combo_league(sp, legs) if len(sps) == 1 else None
            if lg:
                groups[_cut_key(lg, n)].append(r)
                kind[_cut_key(lg, n)] = (2, sp, n)
        groups[_cut_key("all", n)].append(r)
        kind[_cut_key("all", n)] = (0, "all", n)
    moved = []
    for key in sorted(groups, key=lambda k: kind[k][0]):     # everyone, then sports, then leagues (they borrow up)
        rs = groups[key]
        e = d.get(key)
        g, sp, n = kind[key]
        borrowing = g == 1 and (not e or (e.get("borrowed") and not _cut_own(e)))
        if g == 1 and not borrowing:
            cur = float(e.get("level", 95))            # a sport already in the file: exactly as before
        elif g == 1 or (g == 2 and not _cut_own(e)):
            cur = _cut_level(d, sp, n)[0]              # new sport / thin league: the level it was borrowing
        else:
            cur = float((e or {}).get("level", 95))
        L = cur / 100
        above = [r["val"] for r in rs if L <= r["pct"] < L + 0.05]
        below = [r["val"] for r in rs if L - 0.05 <= r["pct"] < L]
        avg = lambda xs: sum(xs) / len(xs)
        new, why = cur, ""
        if len(above) >= 25 and avg(above) < 0.97:
            step = 3 if len(above) >= 40 and avg(above) < 0.85 else 2
            new, why = min(cur + step, 110), f"raised: combos just over the bar were worth {avg(above):.0%} of their cost by game time"
        elif len(below) >= 25 and avg(below) >= 1.0 and cur > 85:
            step = 3 if len(below) >= 40 and avg(below) >= 1.05 else 2
            new, why = max(cur - step, 85), f"lowered: combos it skipped just under the bar were worth {avg(below):.0%} of their cost by game time"
        if new != cur:
            d[key] = {"level": new, "why": why, "at": int(time.time()), "n": len(rs)}
            moved.append(f"{key} {cur:.0f}% → {new:.0f}% ({why})")
        elif g == 2 and not _cut_own(e):
            d[key] = {"level": cur, "why": "", "n": len(rs)}   # still on its sport's level (or now its own, from there)
        elif borrowing:                                # still on a borrowed level (95%+); its own from there at 30+
            d[key] = {"level": cur, "why": "", "n": len(rs), **({"borrowed": True} if len(rs) < CUT_MIN_N else {})}
        else:
            d.setdefault(key, {"level": cur, "why": "", "n": len(rs)})["n"] = len(rs)
    d["_at"] = time.time()
    save_json(CUTOFF_FILE, d)
    return moved


def cutoff_summary():
    """The cut-offs for Settings: every sport's, and a league's or everyone's once it has its own."""
    d = load_json(CUTOFF_FILE, {})
    return [{"group": k, **{a: b for a, b in v.items() if a != "borrowed"}} for k, v in sorted(d.items())
            if not k.startswith("_") and (k.split(":")[0] in SPORTS or _cut_own(v))]



# ---- sizing that grows (slowly) with the bankroll, shrinks fast, and sets half of each month's profit aside
def month_profit(month):
    """Realized profit in a month ("YYYY-MM", Pacific): combos settled or cashed that month (from your Kalshi
    record) plus the panel's single bets. Deposits and withdrawals don't count, unlike a balance change."""
    if not STORE["db"]:
        return 0.0
    y, m = map(int, month.split("-"))
    start = dt.datetime(y, m, 1, tzinfo=PACIFIC).timestamp()
    end = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=PACIFIC).timestamp()
    pl = 0.0
    for r in store_rows("select cost, pays, back, status from bets where settled >= ? and settled < ?", (start, end)):
        got = r["back"] if r["status"] == "cashed" else r["pays"] if r["status"] == "won" else 0
        pl += (got or 0) - (r["cost"] or 0)
    _panel_table()
    for r in store_rows("select body from panel where (mode='real' or mode like 'real#%') and day like ?", (month + "%",)):
        pl += sum(c.get("pl") or 0 for c in json.loads(r["body"]).get("items", [])
                  if c.get("result") and c["kind"] != "combo")    # panel combos are already in your Kalshi record
    return round(pl, 2)


def sizing_base(balance=None):
    """The bankroll the panel sizes from: what's in Kalshi minus the profit set aside (until you say you've
    moved it out), and when it has grown, only 10% more a week than last time (losses count right away)."""
    s = load_json(SIZING_FILE, {})
    if balance is None:
        balance = fetch_account(max_age=600, every_league=True)[1]
    bal = float(balance) if balance is not None else float(CFG.get("bankroll", 300))
    now = time.time()
    month = dt.datetime.now(PACIFIC).strftime("%Y-%m")
    if s.get("month") != month:                       # new month: set aside half of last month's profit
        if s.get("month"):
            prof = month_profit(s["month"])
            if prof > 0:
                s["reserved"] = round(s.get("reserved", 0) + PANEL["skim"] * prof, 2)
                s["skim_note"] = f"Set aside {money(PANEL['skim'] * prof)}, half of {s['month']}'s {money(prof)} profit."
        s["month"] = month
    reserved = min(s.get("reserved", 0), bal)
    avail = max(bal - reserved, 0)
    prev = s.get("base") or avail
    weeks = max((now - s.get("base_at", now)) / (7 * 86400), 0)
    base = min(avail, prev * (1.10 ** weeks)) if avail > prev else avail
    if now - s.get("base_at", 0) > 86400 or avail < prev:
        s.update(base=round(base, 2), base_at=now)
    save_json(SIZING_FILE, s)
    return base, s


def skim_moved():
    """Pete moved the set-aside profit out of Kalshi: stop subtracting it (it's no longer in the balance)."""
    s = load_json(SIZING_FILE, {})
    amt = s.get("reserved", 0)
    s["reserved"] = 0
    s["moved"] = round(s.get("moved", 0) + amt, 2)
    save_json(SIZING_FILE, s)
    return amt


def _size(c, base):
    """Dollars for one panel bet: a quarter of Kelly on a shrunk edge, inside $2..5% of the bankroll, using
    what the bet really pays (a sell-early favorite wins only its exit gain, not $1)."""
    hi = max(2.0, PANEL["max_bet_share"] * base)
    q = c["chance"]
    if c["kind"] == "early":
        p = c["price"]
        b = (c["exit"] - p - single_fee(p) - single_fee(c["exit"])) / (p + single_fee(p))
    elif c["kind"] == "combo":
        b = c["pct"] * c["fair_mult"] - 1
    else:
        p = c["price"]
        b = (1 - p - single_fee(p)) / (p + single_fee(p))
    if b <= 0 or not 0 < q < 1:
        return 2.0
    edge = q * b - (1 - q)                              # expected profit per dollar
    if edge <= 0:
        return 2.0
    f = 0.7 * edge / b                                  # Kelly on an edge shrunk 30%
    return round(min(hi, max(2.0, 0.25 * f * base)), 2)


# ---- candidates
PRO_SHORT = ("nfl", "nba", "nhl", "ahl")        # pro teams read fine by last word ("Flyers"); college and the rest keep full names


MULTI_NICK = ("Maple Leafs", "Red Wings", "Blue Jackets", "Golden Knights", "Silver Knights", "Trail Blazers", "Wolf Pack",
              "Hockey Club", "Black Hawks", "Blue Devils")      # nicknames of two words: 'Leafs' or 'Club' alone would mislead


def team_short(code, name):
    """A team the way the panel names it: 'Flyers' for pro leagues, the full name elsewhere ('Temple Owls')."""
    name = str(name or "").strip()
    if code not in PRO_SHORT or not name:
        return name
    return next((n for n in MULTI_NICK if name.endswith(n)), name.split()[-1])


def stamp_games(code, games):
    """Give every side of every game a plain-English matchup ('Flyers vs Bruins', the pick named first), so each
    panel bet and each leg of a combo says which game it is on. Computed from the sides already in hand: no
    lookups, and nothing about prices or choices changes."""
    for sides in games.values():
        two = [x for x in sides if not x.get("tie")]
        if len(two) != 2:
            continue
        for x, y in ((two[0], two[1]), (two[1], two[0])):
            x["me"] = team_short(code, x.get("pick"))
            x["vs"] = team_short(code, y.get("pick"))
            x["game"] = f"{x['me']} vs {x['vs']}"


def league_tag(code, ticker=""):
    """The league's short name; a soccer bet says which league ('Premier League'), not just 'Soccer'."""
    if code == "soccer" and ticker:
        k = league_key(ticker)
        if k in LEAGUE_NAME:
            return LEAGUE_NAME[k]
    return str((LEAGUES.get(code) or SPORTS.get(code) or {}).get("short") or (SPORTS.get(code) or {}).get("name") or "")


def leg_text(l, kind="combo"):
    """One panel leg in plain English: 'Over 7.5 (Flyers at Bruins)', 'Flyers to beat Bruins'."""
    pick = str(l.get("pick") or "")
    if kind == "line":
        base = re.sub(r" \(.*\)$", "", pick)
        return f"{base} ({l['game']})" if l.get("game") else pick
    if l.get("vs"):
        return f"{l.get('me') or pick} to beat {l['vs']}"
    return pick


def bet_text(c):
    """A panel bet named with its game, for notifications and logs."""
    return " + ".join(leg_text(l, c.get("kind")) for l in c.get("legs") or [])


def _cand(kind, code, legs, chance, ret, why, **extra):
    kicks = [k for k in (_kick_ts(l) for l in legs) if k]
    if not kicks:
        for l in legs:
            try:
                kicks.append(dt.datetime.fromisoformat(str(l.get("start")).replace("Z", "+00:00")).timestamp())
            except ValueError:
                pass
    live = [l for l in legs if l.get("live")]          # picks priced live, on games already under way
    pre = [k for k in (_kick_ts(l) for l in legs if not l.get("live")) if k]
    out = dict({"id": kind + ":" + "+".join(sorted(l["ticker"] for l in legs)), "kind": kind, "code": code,
                "icon": (LEAGUES.get(code) or SPORTS.get(code) or {}).get("icon", ""),
                "legs": [{k: l.get(k) for k in ("ticker", "event", "pick", "p", "fair", "game", "vs", "me")} for l in legs],
                "league": league_tag(code, legs[0]["ticker"] if legs else ""),
                "chance": round(chance, 4), "ret": round(ret, 4), "why": why,
                "kick": min(kicks) if kicks else None, "last": max(kicks) if kicks else None}, **extra)
    if len(legs) == 1 and not out.get("game"):
        out["game"] = legs[0].get("game") or ""          # the one game a single, spread or total is on
    if live:
        out["live"] = True
        out["kick_pre"] = min(pre) if pre else None
        for nl, l in zip(out["legs"], legs):
            if l.get("live"):
                nl.update(live=True, pre=l.get("pre"), how=l.get("live_how"))
    return out


def sell_early_candidates(games):
    """Favorites (65-88%) priced at or under fair after the fee, with an exit price above it. Since a fair
    price moves like a fair coin, the chance it touches the exit before the game ends is about fair/exit."""
    out = []
    for e, sides in games.items():
        for x in sides:
            if x.get("tie") or not x.get("fair") or not x.get("p") or started(x) or x.get("src") is None:
                continue
            if not 0.65 <= x["fair"] <= 0.88:
                continue
            fee = single_fee(x["p"])
            if x["p"] + fee > x["fair"]:
                continue
            exit_ = round(min(0.97, x["p"] + max(0.06, (1 - x["p"]) * 0.45)), 2)
            touch = min(0.99, x["fair"] / exit_) * 0.95     # less for the spread and for the order having to fill
            gain = exit_ - x["p"] - fee - single_fee(exit_)
            ev = touch * gain - (1 - touch) * (x["p"] + fee)
            out.append(dict(x, exit=exit_, touch=round(touch, 4), ev=ev / x["p"]))
    return sorted(out, key=lambda x: -x["touch"])


def slate_combos(games, code, k=3):
    """NFL-style slate combos: games from more than one time slot (so early wins create a sell point), with
    as many underdogs as a slate usually produces (the sum of each game's upset chance), picking the
    underdogs Kalshi prices cheapest against fair."""
    pre = {e: [s for s in sd if not s.get("tie")] for e, sd in games.items()
           if not any(started(s) for s in sd) and all(s.get("fair") and s.get("p") and s.get("src") for s in sd if not s.get("tie"))}
    pre = {e: sd for e, sd in pre.items() if len(sd) == 2}
    if len(pre) < 4:
        return []
    kick = {e: _kick_ts(sd[0]) or 0 for e, sd in pre.items()}
    slots = sorted({round(t / 5400) for t in kick.values()})
    if len(slots) < 2:
        return []
    out = []
    evs = sorted(pre, key=lambda e: kick[e])
    for n in (5, 6, 8):
        if n > len(evs):
            continue
        # spread across slots: walk the slots round-robin, taking the games with the best-priced side first
        by_slot = defaultdict(list)
        for e in evs:
            by_slot[round(kick[e] / 5400)].append(e)
        for s in by_slot:
            by_slot[s].sort(key=lambda e: -max(x["fair"] / x["p"] for x in pre[e]))
        chosen, i = [], 0
        while len(chosen) < n and any(by_slot.values()):
            s = slots[i % len(slots)]
            if by_slot.get(s):
                chosen.append(by_slot[s].pop(0))
            i += 1
        favs = {e: max(pre[e], key=lambda x: x["fair"]) for e in chosen}
        dogs = {e: min(pre[e], key=lambda x: x["fair"]) for e in chosen}
        exp_up = sum(d["fair"] for d in dogs.values())
        fw = favorite_win_rate(code)                   # favorites win less (or more) often than the books say?
        if fw:
            exp_up *= (1 - fw[0]) / max(1 - fw[1], 0.05)
        upsets = round(exp_up)
        flip = sorted((e for e in chosen if dogs[e]["fair"] >= 0.3), key=lambda e: -dogs[e]["fair"] / dogs[e]["p"])[:upsets]
        legs = [dogs[e] if e in flip else favs[e] for e in chosen]
        chance = math.prod(l["fair"] for l in legs)
        base = math.prod(l["fair"] / l["p"] for l in legs)
        c = {"legs": legs, "fair": 1 / chance, "kalshi": 1 / math.prod(l["p"] for l in legs)}
        pq = predict_quote(c)
        pct = pq["pct"] if pq else base * maker_ratio(len(legs), _hours_to(legs))
        out.append((pct, chance, legs, len(flip)))
    out.sort(key=lambda t: -t[0])
    return out[:k]


def _close_table():
    store_x("create table if not exists closes(ticker text primary key, sport text, event text, fair real, "
            "price real, kick real, ts real, outcome text)")


def record_closes(games, code):
    """Every pre-game side's latest fair chance and Kalshi price. The last one before kickoff is the
    game-time (closing) price: what the panel's buys are judged against, and with the result, what the
    chances are checked against."""
    if not STORE["db"]:
        return
    _close_table()
    now = time.time()
    for e, sides in games.items():
        for x in sides:
            if x.get("tie") or not x.get("fair") or not x.get("p") or started(x) or x.get("src") is None:
                continue
            store_x("insert or replace into closes values(?,?,?,?,?,?,?,coalesce((select outcome from closes where ticker=?),null))",
                    (x["ticker"], code, e, x["fair"], x["p"], _kick_ts(x), now, x["ticker"]))


def resolve_closes(limit=150):
    """Fill in results for finished games (in the history loop), for the pre-game lines and the live chances."""
    if not STORE["db"]:
        return 0
    _close_table()
    try:
        resolve_live_fairs(limit)
    except Exception:
        pass
    rows = store_rows("select ticker from closes where outcome is null and kick < ? limit ?", (time.time() - 4 * 3600, limit))
    if not rows:
        return 0
    res = fetch_results([r["ticker"] for r in rows])
    n = 0
    for r in rows:
        v = res.get(r["ticker"])
        if v in ("yes", "no"):
            store_x("update closes set outcome=? where ticker=?", (v, r["ticker"]))
            n += 1
    return n


def close_prices(tickers):
    """{ticker: last Kalshi price before its game started} for games that have started."""
    if not STORE["db"] or not tickers:
        return {}
    _close_table()
    q = ",".join("?" * len(tickers))
    rows = store_rows(f"select ticker, price, kick from closes where ticker in ({q})", tuple(tickers))
    return {r["ticker"]: r["price"] for r in rows if r["kick"] and r["kick"] < time.time() and r["price"]}


def exit_factor():
    """The whole trip: share of a combo's value kept on average, given how often combos get cashed out
    early (at Kalshi's usual discount) instead of held to the end."""
    if not STORE["db"]:
        return 1.0
    rows = store_rows("select status from bets where status in ('won','lost','cashed') and settled > ?",
                      (time.time() - 60 * 86400,))
    if len(rows) < 10:
        return 1.0
    f = sum(r["status"] == "cashed" for r in rows) / len(rows)
    return 1 - f * (1 - kalshi_discount(False))


CALIB = {"at": 0, "m": {}}
CALIB_LIVE = {"at": 0, "m": {}}


def calibration(table="closes"):
    """For each sport and chance band: how often teams the books gave that chance actually won, from your own
    record of games. {sport: [(lo, hi, mean fair, win rate, n)]}, plus each league inside a sport (each soccer
    league, by its own key) and everyone's record together ("all"). Refreshed hourly. table="live_fairs": the
    same for chances worked out during games (the live model), which learn on their own."""
    cache = CALIB_LIVE if table == "live_fairs" else CALIB
    if time.time() - cache["at"] < 3600 or not STORE["db"]:
        return cache["m"]
    _close_table()
    _live_fair_table()
    rows = store_rows(f"select ticker, sport, fair, outcome from {'live_fairs' if table == 'live_fairs' else 'closes'} "
                      "where outcome in ('yes','no')")
    by = defaultdict(list)
    for r in rows:
        x = (r["fair"], r["outcome"] == "yes")
        by[r["sport"]].append(x)
        by["all"].append(x)
        lg = league_key(r["ticker"])
        if lg not in ("other", "mix", r["sport"]) and ticker_sport(r["ticker"]) == r["sport"]:
            by[lg].append(x)
    out = {}
    for sp, xs in by.items():
        bands = []
        for lo in (0.0, 0.3, 0.45, 0.55, 0.7, 0.85):
            hi = {0.0: 0.3, 0.3: 0.45, 0.45: 0.55, 0.55: 0.7, 0.7: 0.85, 0.85: 1.01}[lo]
            b = [(f, w) for f, w in xs if lo <= f < hi]
            if b:
                bands.append((lo, hi, sum(f for f, _ in b) / len(b), sum(w for _, w in b) / len(b), len(b)))
        out[sp] = bands
    cache.update(at=time.time(), m=out)
    return out


def calib_fair(code, fair, ticker=None, table="closes"):
    """The books' chance, nudged toward what actually happened in your record for this band, borrowing
    everyone -> sport -> league. Each level starts from the nudge above it and moves toward its own record by
    n/(n+300) of the gap (n = its games in the band; 300 games = halfway): every other sport's record from the
    books' chance (everyone's minus this sport's own games, so none count twice), the sport from that nudge,
    and a league inside the sport (ticker given, e.g. the Premier League) from its sport's. So a level with no
    games of its own gets exactly the one above, and a sport alone in a band is exactly what it was before."""
    m = calibration(table)

    def band(key):
        return next(((mf, wr, n) for lo, hi, mf, wr, n in m.get(key, []) if lo <= fair < hi), None)
    a, s = band("all"), band(code)
    if a and s:                                    # everyone else's: everyone's band minus this sport's games
        k = a[2] - s[2]
        a = ((a[0] * a[2] - s[0] * s[2]) / k, (a[1] * a[2] - s[1] * s[2]) / k, k) if k > 0 else None
    lg = league_key(ticker) if ticker else None
    bl = band(lg) if lg and lg not in ("other", "mix", code, "all") and ticker_sport(ticker) == code else None
    adj, hit = 0.0, False
    for b in (a, s, bl):
        if b:
            adj += b[2] / (b[2] + 300) * ((b[1] - b[0]) - adj)
            hit = True
    if not hit:
        return fair
    return min(max(fair + adj, 0.01), 0.99)


def favorite_win_rate(code):
    """How often favorites have actually won in your record for this sport (None under 60 games)."""
    _close_table()
    rows = store_rows("select fair, outcome from closes where sport=? and outcome in ('yes','no') and fair > 0.5", (code,)) \
        if STORE["db"] else []
    if len(rows) < 60:
        return None
    return sum(r["outcome"] == "yes" for r in rows) / len(rows), sum(r["fair"] for r in rows) / len(rows), len(rows)


# ---- games already under way (Pete's call: the panel judges a game by its chance of a profit, not by whether
# it has started). A game in progress gets a real, current fair chance or it stays out:
#  1. a live sportsbook line (the odds service's line, fetched after the start and no older than LIVE_LINE_AGE), or
#  2. the live model: the score and the clock (ESPN, or the AHL's own feed) on top of the last line before the
#     game (what the books thought of the two teams), then calibrated by this league's own record of live chances.
# Either way it needs a fresh score (LIVE_SCORE_AGE), the game still in play (never a finished one), a fresh Kalshi
# price with a tight buy/sell gap, and Kalshi's price within LIVE_DISAGREE of it (a wider gap is far more often
# something the score doesn't show, like an injury or a power play, than a real bargain). The pre-game fair price
# is never used for a game under way. Sports without a score feed we trust stay out and say so.
LIVE_SCORE_AGE = 120     # seconds: an older score (or none) = the game is not eligible
LIVE_LINE_AGE = 180      # seconds: a live sportsbook line older than this isn't used
LIVE_POOL_AGE = 6 * 60   # seconds: a live-priced panel bet older than this is re-checked before it's offered or bought
LIVE_MODEL = {"nfl": ("pts", 13.5), "ncaaf": ("pts", 16.0), "nba": ("pts", 12.0), "ncaamb": ("pts", 10.5),
              "ncaawb": ("pts", 11.0), "nhl": ("goals", 6.0), "ahl": ("goals", 6.2), "soccer": ("goals3", 2.7)}
LIVE_EXCLUDED = {"euroleague": "EuroLeague", "ufc": "UFC", "tennis": "tennis"}   # no score feed we trust to price on
LIVE_EXCLUDED_WHY = ("EuroLeague, UFC and tennis games stay out once they've started: their only live scores are "
                     "Kalshi's display data, with no clock to price on, so there's no fresh score we trust.")


def live_panel_on():
    """The Settings switch 'Include games already under way' (on unless Pete turned it off). Read from the shared
    settings file too, so the Mac's engines and the web app agree without waiting for a reload."""
    v = load_json(MAIN_SAVED, {}).get("panel_live") if os.path.exists(MAIN_SAVED) else None
    return bool(CFG.get("panel_live", True) if v is None else v)


def _live_fair_table():
    store_x("create table if not exists live_fairs(ticker text, ts real, sport text, fair real, how text, outcome text)")


def note_live_fair(ticker, sport, fair, how, now=None):
    """Keep one live chance per pick per half hour, so its league's live record can calibrate the model."""
    if not STORE["db"]:
        return
    now = now or time.time()
    _live_fair_table()
    if store_rows("select 1 from live_fairs where ticker=? and ts > ?", (ticker, now - 1800)):
        return
    store_x("insert into live_fairs(ticker, ts, sport, fair, how, outcome) values(?,?,?,?,?,null)",
            (ticker, now, sport, round(fair, 4), how))


def resolve_live_fairs(limit=150):
    _live_fair_table()
    rows = store_rows("select distinct ticker from live_fairs where outcome is null and ts < ? limit ?",
                      (time.time() - 3600, limit))
    res = fetch_results([r["ticker"] for r in rows]) if rows else {}
    for r in rows:
        if res.get(r["ticker"]) in ("yes", "no"):
            store_x("update live_fairs set outcome=? where ticker=?", (res[r["ticker"]], r["ticker"]))


def pregame_fair(ticker):
    """The last sportsbook chance recorded before this pick's game started (its closing line), or None."""
    if not STORE["db"]:
        return None
    _close_table()
    rows = store_rows("select fair, kick from closes where ticker=?", (ticker,))
    return rows[0]["fair"] if rows and rows[0]["fair"] and rows[0]["kick"] and rows[0]["kick"] <= time.time() + 300 else None


def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k) if k >= 0 else 0.0


def _goal_chances(lead, la, lb):
    """(P this team ends ahead, P level) with the rest of the game's goals Poisson: la for it, lb for the other."""
    win = tie = 0.0
    for b in range(0, 16):
        pb = _pois(b, lb)
        win += pb * (1 - _poisson_cdf(b - lead, la))
        tie += pb * _pois(b - lead, la)
    return win, tie


def live_model_chance(sport, pre, lead, frac, wp=None):
    """This team's chance to win from here: `pre` its chance before the game (the closing line), `lead` its score
    lead now, `frac` the share of regulation left. Points sports: the final margin is normal around the lead plus
    the pre-game edge still to come. Hockey and soccer: the goals still to come are Poisson, split so the pre-game
    chance comes out right; hockey ties go to overtime. ESPN's own football win chance, when it has one, is averaged in."""
    kind, k = LIVE_MODEL[sport]
    pre = min(max(pre, 0.02), 0.98)
    f = min(max(frac, 0.005), 1.0)
    if kind == "pts":
        mu = k * statistics.NormalDist().inv_cdf(pre)
        out = _phi((lead + mu * f) / (k * math.sqrt(f)))
        if wp is not None:
            out = (out + wp) / 2
        return out

    def whole(sh, fr, ld):
        w, t = _goal_chances(ld, k * sh * fr, k * (1 - sh) * fr)
        return w + (t * (0.5 + 0.5 * (sh - 0.5)) if kind == "goals" else 0)
    lo, hi = 0.02, 0.98                                 # this team's share of the goals, from its pre-game chance
    for _ in range(40):
        mid = (lo + hi) / 2
        if whole(mid, 1.0, 0) < pre:
            lo = mid
        else:
            hi = mid
    return whole((lo + hi) / 2, f, lead)


def live_side_fair(x, now=None, refresh=True):
    """A current fair chance for one side of a game under way: (chance, how, None) or (None, None, why not).
    Never the pre-game price: a fresh live sportsbook line, or the live model on a fresh score."""
    now = now or time.time()
    sport = ticker_sport(x.get("ticker")) or ""
    if sport in LIVE_EXCLUDED or sport not in LIVE_MODEL:
        return None, None, f"no live score feed we trust for {LIVE_EXCLUDED.get(sport, sport or 'this sport')}"
    if refresh:
        try:
            fetch_scores(max_age=min(30, LIVE_SCORE_AGE // 3), code=sport)
        except Exception:
            pass
    if score_age(sport, now) > LIVE_SCORE_AGE:
        return None, None, "no fresh live score"
    sc = leg_score({"ticker": x["ticker"], "side": "yes"})
    if not sc:
        return None, None, "no live score for this game"
    if sc.get("state") == "post":
        return None, None, "the game is over"
    if sc.get("state") != "in" or sc.get("frac") is None:
        return None, None, "the score feed doesn't show it in play"
    if x.get("line_live") and x.get("src") and now - (x.get("line_at") or 0) <= LIVE_LINE_AGE and x.get("fair"):
        return float(x["fair"]), "live sportsbook line", None
    pre = x.get("pre") or pregame_fair(x["ticker"])
    if not pre:
        return None, None, "no pre-game line to start from"
    raw = live_model_chance(sport, calib_fair(sport, pre, x["ticker"]), sc["me"] - sc["opp"], sc["frac"], sc.get("wp"))
    return calib_fair(sport, raw, x["ticker"], table="live_fairs"), "live model", None


def panel_live_games(games, now=None):
    """The games under way that can go in the panel, priced live: ({game: sides}, {game: why not}). Each side
    gets fair (current), edge, live=True, pre (its closing line) and live_how; anything short of the bar is left out."""
    now = now or time.time()
    ok, why = {}, {}
    for e, sides in games.items():
        if not any(started(x) for x in sides):
            continue
        two = [x for x in sides if not x.get("tie")]
        if any(x.get("p") is None or x.get("bid") is None for x in two):
            why[e] = "no live buyers or sellers on Kalshi"
            continue
        gap = max(x["p"] - x["bid"] for x in two)
        if gap > LIVE_SPREAD:
            why[e] = f"the live price is jumpy ({gap * 100:.0f}¢ between buy and sell)"
            continue
        got, bad = [], None
        for x in two:
            x["pre"] = pregame_fair(x["ticker"])
            f, how, w = live_side_fair(x, now)
            if f is None:
                bad = w
                break
            got.append((x, f, how))
        if bad:
            why[e] = bad
            continue
        if len(got) == 2 and len(two) == len(sides):    # two-way: the two chances add up to 100%
            t = got[0][1] + got[1][1]
            got = [(x, f / t, how) for x, f, how in got]
        if max(f for _, f, _ in got) >= LIVE_DECIDED:
            why[e] = "nearly decided"
            continue
        mids = {x["ticker"]: (x["p"] + x["bid"]) / 2 for x in two}
        if any(abs(f - mids[x["ticker"]]) >= LIVE_DISAGREE for x, f, _ in got):
            why[e] = "Kalshi's live price and the live chance disagree too much (something the score doesn't show)"
            continue
        for x, f, how in got:
            x.update(fair=round(f, 4), edge=round(f - x["p"], 4), live=True, live_how=how, src=x.get("src") or how)
            try:
                note_live_fair(x["ticker"], ticker_sport(x["ticker"]), f, how, now)
            except Exception:
                pass
        ok[e] = sides
    return ok, why


def live_recheck(legs, now=None):
    """Right before buying: every leg on a game under way is priced again on a fresh score. Returns (legs with
    fresh chances, None) or (None, why not)."""
    out = []
    for l in legs:
        if not l.get("live"):
            out.append(l)
            continue
        f, how, w = live_side_fair(dict(l, line_live=False), now)
        if f is None:
            return None, w
        if f >= LIVE_DECIDED or f < 0.05:
            return None, "the game is nearly decided"
        out.append(dict(l, fair=round(f, 4), live_how=how))
    return out, None


def _start_ok(c, now, margin):
    """May this panel bet still be shown, approved or bought? A bet on games not started yet: only while its
    first game is `margin` seconds or more away. A bet priced live on a game under way: while that's switched on
    (and any other games in it are still `margin` away)."""
    if c.get("live"):
        if not live_panel_on():
            return False
        k = c.get("kick_pre")
        return k is None or k >= now + margin
    return (c.get("kick") or 0) >= now + margin


def panel_collect(book_snap, code, log=print):
    """Gather this league's panel candidates. Called for each league by the Mac. Games not started yet use the
    sportsbooks' chances; games already under way (when switched on) only with a fresh live chance
    (panel_live_games), never the pre-game one."""
    book = load_book_state(book_snap)
    games, _, _ = week_games(fetch_markets())
    attach_fair(games, book)
    every = games
    games = {e: sd for e, sd in every.items() if not any(started(x) for x in sd)}
    live, LIVE_WHY[code] = ({}, {})
    if live_panel_on():
        try:
            live, LIVE_WHY[code] = panel_live_games(every)
        except Exception as err:
            log(f"live games {code}:", type(err).__name__, err)
    LIVE_NOW[code] = bool(live)
    PANEL_GAMES[code] = len(games) + len(live)
    kicks = [k for sd in games.values() for k in [_kick_ts(sd[0])] if k and k > time.time()]
    NEXT_KICK[code] = min(kicks) if kicks else None
    try:
        record_closes(games, code)
    except Exception as err:
        log("closing prices:", type(err).__name__, err)
    pre_games = games
    games = dict(pre_games, **live)
    stamp_games(code, games)                           # each side names its game (display only)
    for sd in pre_games.values():                      # the books' chances, corrected by your own record
        two = [x for x in sd if x.get("fair") and not x.get("tie")]
        for x in two:
            x["fair_book"] = x["fair"]
            x["fair"] = calib_fair(code, x["fair"], x.get("ticker"))
        if len(two) == 2:                              # both sides still add up to what the books gave them
            k = sum(x["fair_book"] for x in two) / max(sum(x["fair"] for x in two), 1e-6)
            for x in two:
                x["fair"] = round(x["fair"] * k, 4)
    cands = []
    for x in single_candidates(games, live_ok=set(live)):
        cands.append(_cand("single", code, [x], x["fair"], x["edge"] / (x["p"] + single_fee(x["p"])),
                           (f"Game under way: Kalshi charges {x['p'] * 100:.0f}¢ for a {x['fair']:.0%} chance now "
                            f"({x.get('live_how')}, on a fresh score)." if x.get("live") else
                            f"Kalshi charges {x['p'] * 100:.0f}¢ for a {x['fair']:.0%} chance."), price=x["p"],
                           opp=opp_of(games, x)))
    for x in sell_early_candidates(games):
        if any(c["id"] == "single:" + x["ticker"] for c in cands):
            continue
        cands.append(_cand("early", code, [x], x["touch"], x["ev"],
                           f"Bought at fair or better; the Mac sells at {x['exit'] * 100:.0f}¢, which it reaches about "
                           f"{x['touch']:.0%} of the time.", price=x["p"], exit=x["exit"], opp=opp_of(games, x)))
    try:
        for x in line_candidates(code):
            if x["edge"] >= LINE_MIN_EDGE:
                cands.append(_cand("line", code, [dict(x, start=x.get("start"))], x["fair"], x["edge"] / x["p"],
                                   "From the sportsbook line and how often games land past it.", price=x["p"],
                                   game=x.get("game"), line_kind=x.get("kind")))
    except Exception as err:
        log(f"panel lines {code}:", type(err).__name__, err)
    for c in value_combos(games, k=6, live_ok=set(live)):
        n = len(c["legs"])
        pq = predict_quote(c)
        pct = pq["pct"] if pq else c.get("value_pct")
        if pct and pct >= combo_cutoff(code, n, c["legs"]):
            cands.append(_cand("combo", code, c["legs"], math.prod(l["fair"] for l in c["legs"]), pct - 1,
                               "Every pick is priced under its real chance, so the combo should pay more than it's worth.",
                               pct=round(pct, 4), fair_mult=round(1 / math.prod(l["fair"] for l in c["legs"]), 3)))
    if code == "nfl":
        for pct, chance, legs, ups in slate_combos(pre_games, code):
            if pct >= combo_cutoff(code, len(legs), legs):
                cands.append(_cand("combo", code, legs, chance, pct - 1,
                                   f"Spread across the day's time slots with {ups} upset{'s' if ups != 1 else ''} built in "
                                   f"(a Sunday usually has that many), so early wins give a chance to cash out.",
                                   pct=round(pct, 4), fair_mult=round(1 / chance, 3), slate=True))
    if code == "nfl":                                  # longer plays: this week and next, two checkpoints
        try:
            far, _, _ = week_games(fetch_markets(), weeks=2)
            attach_fair(far, book)
            far = {e: sd for e, sd in far.items() if not any(started(x) for x in sd)}
            stamp_games(code, far)
            weeks = {e: week_of(e) for e in far}
            if len(set(weeks.values())) >= 2:
                for c in value_combos(far, k=8, max_legs=4):
                    wk = {weeks[l["event"]] for l in c["legs"]}
                    pq = predict_quote(c)
                    pct = pq["pct"] if pq else c.get("value_pct")
                    if len(wk) >= 2 and pct and pct >= combo_cutoff(code, len(c["legs"]), c["legs"]) + 0.05:
                        cands.append(_cand("combo", code, c["legs"], math.prod(l["fair"] for l in c["legs"]), pct - 1,
                                           "Two NFL weekends: the first is a checkpoint to cash out early.",
                                           pct=round(pct, 4), fair_mult=round(1 / math.prod(l["fair"] for l in c["legs"]), 3),
                                           weeks=2))
        except Exception as err:
            log("two-week NFL:", type(err).__name__, err)
    PANEL_POOL[code] = (time.time(), cands)
    return cands


# ---- choosing the panel
def _events_of(c):
    return [re.sub(r"(SPREAD|TOTAL)-", "GAME-", l.get("event") or "") for l in c["legs"]]


def _sim_panel(items, n=3000, seed=7):
    """Monte Carlo of the panel's total profit. One draw per game, so bets on the same game move together and
    the two teams in a game can never both win (a single on one team and a combo with the other are exclusive).
    Spreads and totals get their own draw."""
    rng = random.Random(seed)
    sides = defaultdict(list)                          # game -> tickers of its sides that appear, fixed order
    for c in items:
        for l in c["legs"]:
            if l["ticker"] not in sides[l.get("event") or l["ticker"]]:
                sides[l.get("event") or l["ticker"]].append(l["ticker"])

    def wins(l, u):
        e = l.get("event") or l["ticker"]
        first = sides[e][0] == l["ticker"]             # first side wins on low draws, any other on high draws
        return u[e] < l["fair"] if first else u[e] > 1 - l["fair"]
    totals = []
    for _ in range(n):
        u = {e: rng.random() for e in sides}
        tot = 0.0
        for c in items:
            s = c["stake"]
            if c["kind"] == "combo":
                won = all(wins(l, u) for l in c["legs"])
                tot += s * (c["pct"] * c["fair_mult"] - 1) if won else -s
            elif c["kind"] == "early":
                l = c["legs"][0]
                touched = wins(l, u) or rng.random() < max(c["chance"] - l["fair"], 0) / max(1 - l["fair"], 1e-6)
                p = c["price"]
                n_ = s / (p + single_fee(p))
                tot += n_ * (c["exit"] - p - single_fee(p) - single_fee(c["exit"])) if touched else -s
            else:
                p = c["price"]
                n_ = s / (p + single_fee(p))
                tot += n_ * 1.0 - s if wins(c["legs"][0], u) else -s
        totals.append(tot)
    return totals


def choose_panel(cands, budget, base, size=None):
    """Greedy: keep adding the bet that most raises the chance the panel finishes ahead (expected profit
    breaks ties), inside the overlap rules and the budget."""
    size = size or PANEL["size"]
    picked, spent, per_game = [], 0.0, defaultdict(int)
    solo = set()                                       # games that already carry a single, spread or total
    pool = [dict(c, stake=_size(c, base)) for c in cands if _qualifies(c)]
    while len(picked) < size and pool:
        best = None
        for c in pool:
            evs = _events_of(c)
            if any(per_game[e] >= PANEL["per_game"] for e in evs):
                continue
            if c["kind"] != "combo" and evs[0] in solo:
                continue                                       # one straight bet per game: no team + over overlap
            if c["kind"] == "line" and sum(1 for x in picked if x["kind"] == "line") >= max(2, int(size * PANEL["line_share"])):
                continue                                       # spreads and totals: at most about a third of the panel
            if spent + c["stake"] > budget + 0.01:
                continue
            tot = _sim_panel(picked + [c], n=1500)
            pr = sum(1 for t in tot if t > 0) / len(tot)
            ev = sum(tot) / len(tot)
            score = pr + 0.05 * ev / max(budget, 1) + c.get("prio", 0)
            if best is None or score > best[0]:
                best = (score, c, pr, ev)
        if not best:
            break
        _, c, pr, ev = best
        picked.append(c)
        spent += c["stake"]
        pool = [x for x in pool if x["id"] != c["id"]]
        for e in _events_of(c):
            per_game[e] += 1
            if c["kind"] != "combo":
                solo.add(e)
    # every prefix of that order is a candidate panel. Pete's goal: the best chance the day ends up ahead,
    # with the money secondary. The chance is lumpy (one or two heavy favorites can look "safest" while
    # making almost nothing), so: find the best chance any prefix reaches, keep every prefix within 5 points
    # of it, and of those take the one that expects to make the most. That uses the budget on good bets
    # while giving up almost none of the chance of finishing ahead.
    floor_n = min(len(picked), 3)
    stats = {}
    for k in range(floor_n, len(picked) + 1):
        tot = _sim_panel(picked[:k], n=2000)
        stats[k] = (sum(1 for t in tot if t > 0) / len(tot), sum(tot) / len(tot))
    if stats:
        top = max(v[0] for v in stats.values())
        ok_k = [k for k, v in stats.items() if v[0] >= top - 0.05]
        picked = picked[:max(ok_k, key=lambda k: stats[k][1])]
    spent = sum(c["stake"] for c in picked)
    tot = _sim_panel(picked) if picked else [0]
    return picked, {"p_ahead": round(sum(1 for t in tot if t > 0) / len(tot), 3), "ev": round(sum(tot) / len(tot), 2),
                    "stake": round(spent, 2), "worst": round(min(tot), 2), "best": round(max(tot), 2)}


def sport_pay_index():
    """How close to fair Kalshi pays on combos in each sport, relative to all sports (from your quotes); also
    each league inside a sport (each soccer league, by its own key) once it has 10+ quotes of its own."""
    if not STORE["db"]:
        return {}
    rows = store_rows("select sport, pct, legs from quotes where pct is not null and ts > ?", (time.time() - 45 * 86400,))
    by, lgs = defaultdict(list), defaultdict(list)
    for r in rows:
        by[r["sport"] or ""].append(r["pct"])
        sp = r["sport"] or ""
        if sp and "," not in sp:
            try:
                lg = _combo_league(sp, json.loads(r["legs"] or "[]"))
            except ValueError:
                lg = None
            if lg:
                lgs[lg].append(r["pct"])
    allv = [p for v in by.values() for p in v]
    if len(allv) < 20:
        return {}
    mid = statistics.median(allv)
    out = {k: round(statistics.median(v) / mid, 3) for k, v in by.items() if len(v) >= 10 and "," not in k}
    out.update({k: round(statistics.median(v) / mid, 3) for k, v in lgs.items() if len(v) >= 10 and k not in out})
    return out


def pay_index_of(idx, code, legs=None):
    """A combo's pay index: its league's own once it has enough quotes, else its sport's, else neutral (1.0)."""
    lg = _combo_league(code, legs)
    return idx[lg] if lg and lg in idx else idx.get(code, 1.0)


def build_panel(codes=None, budget=None, now=None, exclude=()):
    """Today's panel (and a couple of longer plays) from the latest candidates of each league. exclude: games
    to leave out (already bet on). budget given explicitly is used as-is (what's left for extras)."""
    now = now or time.time()
    budget = float(budget) if budget is not None else float(CFG.get("panel_budget", PANEL["budget"])) - spent_earlier_today(now)
    base, _ = sizing_base()
    day_end, nfl_end = _local_day_end(now), _nfl_week_end(now)
    idx = sport_pay_index()
    today, longer = [], []
    for code, (at, cands) in PANEL_POOL.items():
        if now - at > PANEL["pool_age"] or (codes and code not in codes):
            continue
        for c in cands:
            if not c.get("kick") or not _start_ok(c, now, 20 * 60):
                continue
            if c.get("live") and now - at > LIVE_POOL_AGE:
                continue                                   # a live price this old is no longer a price
            c = dict(c)
            if c["kind"] == "combo":                       # lean toward the sports that pay closest to fair (tie-break only)
                c["prio"] = max(-0.01, min(0.01, 0.1 * (pay_index_of(idx, code, c["legs"]) - 1.0)))
            end = nfl_end if code == "nfl" else day_end
            if c["last"] <= end:
                today.append(c)
            elif c["kind"] == "combo" and (c["last"] <= now + 3 * 86400 or c.get("weeks")) and c["ret"] >= 0.10:
                longer.append(c)
    held = {e for c in day_items(_panel_day(now)) if c.get("state") in ("bought", "buying", "check") for e in _events_of(c)}
    held |= set(exclude) | account_events()
    today = [c for c in today if not held & set(_events_of(c))]     # games an earlier panel today already bet on
    games_today = len({e for c in today for e in _events_of(c)})
    size = min(14, max(6, 4 + games_today // 3))       # heavy hockey/NBA nights get a bigger panel
    nfl_day = any(c["code"] == "nfl" and c["kick"] <= day_end for c in today)
    for c in today:
        c["prio"] = c.get("prio", 0.0) + (0.03 if (nfl_day and c["code"] == "nfl") else 0.0)
    picked, stats = choose_panel(today, budget, base, size=size)
    pool = defaultdict(int)
    for c in today:
        if _qualifies(c):
            pool[c["kind"]] += 1
    stats["pool"] = dict(pool)
    used = {e for c in picked for e in _events_of(c)}
    longer = [dict(c, stake=_size(c, base)) for c in
              sorted(longer, key=lambda c: -c["ret"]) if not used & set(_events_of(c))][:PANEL["longer_max"]]
    return {"at": now, "items": sorted(picked, key=lambda c: c["kick"] or 0), "longer": longer, "stats": stats,
            "budget": budget, "base": round(base, 2), "codes": codes or sorted(PANEL_POOL), "games": dict(PANEL_GAMES)}


# ---- storage, approval and the Mac's buying (right after approval)


def _panel_day(now=None):
    t = dt.datetime.now(PACIFIC) if now is None else dt.datetime.fromtimestamp(now, PACIFIC)
    return (t - dt.timedelta(hours=4)).date().isoformat()


def _panel_table():
    db = STORE["db"]
    if db and not STORE.get("panel_ok"):
        with _SLOCK:
            db.execute("create table if not exists panel(day text, mode text, ts real, status text, body text, "
                       "primary key(day, mode))")
        STORE["panel_ok"] = True


def panel_tx(day, mode, fn):
    """Read-change-write one panel row inside a SQLite write lock, so the phone's Approve/Cancel and the
    Mac's buying can never overwrite each other (they run in different processes). fn(panel or None,
    status) returns (new panel, new status) to save, or None to leave it. Errors are raised, never
    swallowed: money state must not be lost quietly. Returns what fn returned."""
    db = STORE["db"]
    if not db:
        raise RuntimeError("history file not open")
    _panel_table()
    with _SLOCK:
        db.execute("begin immediate")
        try:
            row = db.execute("select status, body from panel where day=? and mode=?", (day, mode)).fetchone()
            p = json.loads(row["body"]) if row else None
            got = fn(p, row["status"] if row else None)
            if got:
                body, status = got
                body = {k: v for k, v in body.items() if k != "status"}
                db.execute("insert or replace into panel values(?,?,?,?,?)",
                           (day, mode, body.get("at", time.time()), status, json.dumps(body)))
            db.execute("commit")
            return got
        except BaseException:
            db.execute("rollback")
            raise


def panel_save_draft(p, mode="real"):
    """Keep the latest draft for today (replaced every round until it's approved)."""
    if not STORE["db"]:
        return
    panel_tx(_panel_day(p["at"]), mode, lambda cur, st: None if st not in (None, "draft") else (p, "draft"))


def panel_get(mode="real", day=None):
    if not STORE["db"]:
        return None
    _panel_table()
    rows = store_rows("select * from panel where day=? and mode=?", (day or _panel_day(), mode))
    if not rows:
        return None
    p = json.loads(rows[0]["body"])
    p["status"] = rows[0]["status"]
    return p


def _item(p, cid):
    return next((c for c in (p or {}).get("items", []) if c["id"] == cid), None)


def panel_approve(ids=None, view="all", at=None):
    """Pete's tap: the Mac buys these panel bets (all by default) right away, each after a fresh price check. A one-sport
    panel (view = its code) becomes today's panel when approved. `at` is the version he was looking at;
    if the panel has been rebuilt since, nothing is approved and he's asked to look again. After a Cancel,
    approving again schedules the bets that weren't bought."""
    src = panel_get("real" if view in ("all", "", None) else f"view:{view}")
    if not src:
        return False, "There's no panel yet. Give it a few minutes."
    if at and abs(float(at) - src["at"]) > 1:
        return False, "The panel was just updated with new prices. Take another look, then approve."
    msg = {}

    def fn(cur, st):
        if st == "approved":
            msg["no"] = "Today's panel is already approved."
            return None
        if st == "cancelled" and view in ("all", "", None):
            p = cur                                     # re-approve after a cancel: same panel
        else:
            p = {k: v for k, v in src.items() if k != "status"}
        for c in p["items"]:
            if c.get("state") in ("bought", "buying", "check", "swapped", "skipped", "failed"):
                continue
            if (ids is None or c["id"] in ids) and not _start_ok(c, time.time(), 5 * 60):
                c["state"], c["note"] = "skipped", ("games under way are switched off in Settings" if c.get("live") else
                                                    "its game had already started when you approved")
                msg["late"] = msg.get("late", 0) + 1
                continue
            c["state"] = "scheduled" if (ids is None or c["id"] in ids) else "left out"
        msg["n"] = sum(1 for c in p["items"] if c.get("state") == "scheduled")
        if not msg["n"] and msg.get("late"):
            return None                                  # nothing left to buy: don't approve a dead panel
        return p, "approved"
    panel_tx(_panel_day(src["at"]), "real", fn)
    if msg.get("no"):
        return False, msg["no"]
    n = msg["n"]
    if n:
        ask_buy()
    if not n and msg.get("late"):
        prune_drafts()
        ask_rebuild()
        return False, ("Those games have already started, so nothing was approved or bought. The Mac is looking "
                       "at today's remaining games now; you can watch it here, and a fresh panel appears when it's ready.")
    return True, (f"Approved {n} bet{'s' if n != 1 else ''}. The Mac buys {'them' if n != 1 else 'it'} now, "
                  f"checking each price again first (not while Pause is on).")


# A panel bet in one of these states is riding, being bought, or was turned down by Kalshi at buy time today: it's
# never added or offered again the same day, so a second Add tap (or two at once) can't buy it twice and a bet Kalshi
# wouldn't sell isn't retried on every tap. A bet skipped or swapped out before any order (or left out at approval)
# may come back as a "New since you approved" extra if it's good again.
PANEL_LIVE = ("scheduled", "buying", "bought", "check")
PANEL_TRIED = PANEL_LIVE + ("failed",)


def _extras_filter(items, real):
    """Extras without any bet today's panel has tried (PANEL_TRIED) and without games a live panel bet is on."""
    its = (real or {}).get("items", [])
    taken = {c["id"] for c in its if c.get("state") in PANEL_TRIED}
    used = {e for c in its if c.get("state") in PANEL_LIVE for e in _events_of(c)}
    return [c for c in items if c["id"] not in taken and not (used & set(_events_of(c)))]


def panel_extras(real=None):
    """The New-since-you-approved extras as shown (see _extras_filter). None when there's no extras row."""
    x = panel_get("extra")
    if not x:
        return None
    real = real if real is not None else panel_get("real")
    return dict(x, items=_extras_filter(x.get("items", []), real))


def panel_add(ids, view):
    """Add bets from one sport's panel (or the new-since-you-approved extras) to today's already-approved panel,
    inside the day's panel budget, skipping any game today's panel already has a bet on. They're bought right away.
    Safe to repeat: a bet already in today's panel (anything but skipped/left out) is never added again, the check
    and the add happen in one locked step (panel_tx), and added extras leave the extras card at once."""
    src = panel_get("extra" if view == "extra" else f"view:{view}")
    if not src:
        return False, "Those picks are gone. Pull to refresh."
    ids = set(ids or [])
    msg = {}

    def fn(cur, st):
        if st != "approved" or not cur:
            msg["no"] = "Today's panel isn't approved, so approve this one instead."
            return None
        active = [c for c in cur["items"] if c.get("state") in ("scheduled", "buying", "bought", "check")]
        used = {e for c in active for e in _events_of(c)}
        room = float(cur.get("budget") or CFG.get("panel_budget", PANEL["budget"])) - sum(c["stake"] for c in active)
        added, skipped = [], []
        for c in src["items"]:
            old = _item(cur, c["id"])
            if c["id"] not in ids or (old and old.get("state") in PANEL_TRIED):
                continue
            if not _start_ok(c, time.time(), 5 * 60):
                skipped.append(c["legs"][0]["pick"])
                continue
            if used & set(_events_of(c)):
                skipped.append(c["legs"][0]["pick"])
                continue
            if c["stake"] > room + 0.01:
                skipped.append(c["legs"][0]["pick"])
                continue
            room -= c["stake"]
            used |= set(_events_of(c))
            if old:                                       # it was skipped/swapped earlier: this replaces that entry
                cur["items"] = [i for i in cur["items"] if i["id"] != c["id"]]
            cur["items"].append(dict({k: v for k, v in c.items() if k != "buy_at"}, state="scheduled"))
            added.append(c["legs"][0]["pick"])
        msg["added"], msg["skipped"] = added, skipped
        msg["in"] = {c["id"] for c in cur["items"] if c["id"] in ids and c.get("state") in PANEL_TRIED}
        msg["dupe"] = sum(1 for c in cur["items"] if c["id"] in ids and c.get("state") in PANEL_LIVE) - len(added)
        msg["failed"] = [c["legs"][0]["pick"] for c in cur["items"] if c["id"] in ids and c.get("state") == "failed"]
        return (cur, st) if added else None
    panel_tx(_panel_day(), "real", fn)
    if msg.get("no"):
        return False, msg["no"]
    gone = msg.get("in") or set()
    if view == "extra" and gone:                            # in today's panel (this tap or an earlier one): off the card

        def drop(cur, st):
            if not cur or st != "draft":
                return None
            keep = [c for c in cur.get("items", []) if c["id"] not in gone]
            return None if len(keep) == len(cur.get("items", [])) else (dict(cur, items=keep), st)
        try:
            panel_tx(_panel_day(), "extra", drop)
        except Exception as err:                            # display only: api_panel filters them out anyway
            print("panel: couldn't tidy the extras card:", type(err).__name__, err)
    a, k = msg.get("added", []), msg.get("skipped", [])
    f = msg.get("failed") or []
    nf = (f" {len(f)} couldn't be bought earlier today (Kalshi had no good price), so "
          f"{'they aren' if len(f) != 1 else 'it isn'}'t tried again today.") if f else ""
    if not a:
        if msg.get("dupe") and not k and not f:
            return True, "Already in today's panel. Nothing more to do."
        if f and not k:
            return False, "Nothing added." + nf
        return False, "Nothing added: " + ("those games already have a bet, or it's over today's panel budget." if k else "nothing selected.")
    ask_buy()
    return True, (f"Added {len(a)} to today's panel. The Mac is buying {'them' if len(a) != 1 else 'it'} now." + (f" Left out {len(k)}: already a bet on that game, or over the budget." if k else "") + nf)


def day_items(day, prefix="real"):
    """Every panel bet of a day, including panels that were restarted (kept as 'real#1', 'real#2'...)."""
    if not STORE["db"]:
        return []
    _panel_table()
    rows = store_rows("select body from panel where day=? and (mode=? or mode like ?)", (day, prefix, prefix + "#%"))
    return [c for r in rows for c in json.loads(r["body"]).get("items", [])]


def spent_earlier_today(now=None):
    """Money already used today by panels that were stopped and restarted."""
    if not STORE["db"]:
        return 0.0
    _panel_table()
    rows = store_rows("select body from panel where day=? and mode like 'real#%'", (_panel_day(now),))
    return round(sum(c["stake"] for r in rows for c in json.loads(r["body"]).get("items", [])
                     if c.get("state") in ("bought", "buying", "check")), 2)


def panel_restart():
    """After a Stop: put today's stopped panel aside (its bought bets stay on the record) so the Mac builds a
    fresh panel from today's remaining games right away (rebuild_loop), with whatever budget is left."""
    day = _panel_day()
    _panel_table()
    n = len(store_rows("select 1 from panel where day=? and mode like 'real#%'", (day,))) + 1

    def fn(cur, st):
        if st != "cancelled":
            return None
        db = STORE["db"]                                # inside panel_tx's transaction: one atomic move
        db.execute("insert or replace into panel values(?,?,?,?,?)", (day, f"real#{n}", cur.get("at", time.time()), "closed",
                                                                     json.dumps({k: v for k, v in cur.items() if k != "status"})))
        db.execute("delete from panel where day=? and mode='real'", (day,))
        return None
    if not store_rows("select 1 from panel where day=? and mode='real' and status='cancelled'", (day,)):
        return False, "Today's panel isn't stopped."
    panel_tx(day, "real", fn)
    left = float(CFG.get("panel_budget", PANEL["budget"])) - spent_earlier_today()
    ask_rebuild()                                     # the Mac starts on it within a few seconds
    return True, (f"Building a fresh panel from today's remaining games, with {money(max(left, 0))} of today's budget left. "
                  f"You can watch it here; it appears on its own, ready to approve.")


def panel_look_now():
    """The Build page's 'Look now' (no panel yet, or the last look found nothing): ask the Mac to look at every
    sport right away instead of at its next round. Only drafts come of it; nothing is approved or bought."""
    real = panel_get("real")
    if real and real.get("status") in ("approved", "cancelled"):
        return False, "Today's panel is already decided. Use the buttons on it instead."
    if not ask_rebuild():
        return False, "Couldn't ask the Mac. Try again."
    return True, "The Mac is looking at every sport now."


def panel_cancel():
    def fn(cur, st):
        if not cur:
            return None
        for c in cur["items"]:
            if c.get("state") == "scheduled":
                c["state"] = "cancelled"
        return cur, "cancelled"
    if not panel_tx(_panel_day(), "real", fn):
        return False, "No panel today."
    return True, "Stopped. Nothing else from today's panel will be bought. Approve again to restart it."


def _fresh(c):
    """The same bet in the newest candidates, or None if it no longer qualifies; 'wait' when the candidates
    are too old to judge (right after a restart, or a slow round)."""
    at, cands = PANEL_POOL.get(c["code"], (0, []))
    if time.time() - at > (LIVE_POOL_AGE if c.get("live") else PANEL["fresh_age"]):
        return "wait"
    return next((x for x in cands if x["id"] == c["id"] and _qualifies(x)), None)


def _qualifies(x):
    """The panel's bar for one bet: combos at or over their cut-off; sell-early favorites at fair or better;
    singles, spreads and totals at least 2% better than fair."""
    if x["kind"] == "combo":
        return x.get("pct", 0) >= combo_cutoff(x["code"], len(x["legs"]), x["legs"])
    if x["kind"] == "early":
        return x["ret"] >= 0
    if x["kind"] == "line":                            # priced by our own score model, not the sharp books:
        l = x["legs"][0]                               # its errors look like edges, so it needs a bigger one
        return (l.get("fair") or 0) - (l.get("p") or 1) >= PANEL["line_edge"]
    return x["ret"] >= PANEL["min_edge"]


def _replacement(c, p):
    """A similar bet: same kind of risk (chance within 12 points), starting within 2 hours, no overlap."""
    used = {e for x in p["items"] if x.get("state") in ("scheduled", "buying", "bought", "paper", "check")
            for e in _events_of(x)}
    best = None
    for code, (at, cands) in PANEL_POOL.items():
        if time.time() - at > PANEL["fresh_age"]:
            continue
        for x in cands:
            if not _qualifies(x) or not x.get("kick") or not _start_ok(x, time.time(), 15 * 60):
                continue
            if x.get("live") and time.time() - at > LIVE_POOL_AGE:
                continue
            if abs(x["chance"] - c["chance"]) > 0.12 or abs((x["kick"] or 0) - (c["kick"] or 0)) > 2 * 3600:
                continue
            if used & set(_events_of(x)) or any(y["id"] == x["id"] for y in p["items"]):
                continue
            if best is None or x["ret"] > best["ret"]:
                best = x
    return best


def _with_ctx(fn):
    """Run fn with a private copy of the planner's build context, so a panel buy never shares (or wipes)
    what the phone's or the shadow's builds are doing, and history lookups have nothing to trip on."""
    saved = dict(CTX)
    try:
        CTX.clear()
        CTX.update({"offers": {}, "build_id": None, "combos": [], "games": {}, "all_games": {}})
        return fn()
    finally:
        CTX.clear()
        CTX.update(saved)


def _panel_combo(c, cutoff):
    legs = [dict(x) for x in c["legs"]]
    CTX["stake"] = c["stake"]
    CTX["combos"] = [{"kind": "panel", "tier": "Panel", "legs": legs, "fair": c["stake"] * c["fair_mult"],
                      "min": c["stake"] * c["fair_mult"] * cutoff,
                      "kalshi": c["stake"] / math.prod(x["p"] for x in legs)}]


def _buy_panel_bet(c):
    """Place one panel bet for real. Returns (ok, note, details): ok False = nothing was bought (never retried),
    None (an exception from the order itself) = unknown, so it's marked "check". A bet on a game under way is
    priced again on a fresh score first, and anything the checks or Kalshi turn down before an order is a skip."""
    if c.get("live"):
        legs, why = live_recheck(c["legs"])
        if legs is None:
            return False, f"its game is under way and {why}", {}
        c = dict(c, legs=legs, fair_mult=round(1 / math.prod(x["fair"] for x in legs), 3))
    l = c["legs"][0]
    if c["kind"] in ("single", "early", "line"):
        book = book_depth(l["ticker"], max_age=5) or {}
        ask = book.get("ask")
        if not ask:
            return False, "no price on Kalshi right now", {}
        if c.get("live") and (book.get("bid") is None or round(ask - book["bid"], 4) > LIVE_SPREAD):
            return False, "its game is under way and the live price is too jumpy to buy", {}
        edge_needed = 0.0 if c["kind"] == "early" else PANEL["min_edge"] * ask
        if ask + single_fee(ask) + edge_needed > l["fair"] + 1e-9:
            return False, f"the price moved to {ask * 100:.0f}¢, no longer good enough against its {l['fair']:.0%} chance", {}
        n = int(c["stake"] // (ask + single_fee(ask)))
        if n < 1:
            return False, "the stake is under one contract", {}
        filled, err = buy_single(l["ticker"], n, ask)
        if err or filled <= 0:
            return False, err or "nobody was selling at that price", {}
        d = {"filled": filled, "price": ask, "paid": ask, "bought_at": int(time.time())}
        if c["kind"] == "early":
            e = post_sell(l["ticker"], filled, c["exit"])
            d["exit_order"] = "placed" if not e else f"failed: {e}"
        return True, f"bought {filled:g} at {ask * 100:.0f}¢", d
    cut = combo_cutoff(c["code"], len(c["legs"]), c["legs"])

    def go():
        _panel_combo(c, cut)
        try:                                             # nothing is bought until accept_offer: a refusal here is a skip
            q = get_offer(1, c["stake"], check_cap=False)
        except (RuntimeError, PermissionError, requests.RequestException) as err:
            return False, f"Kalshi wouldn't price it ({str(err)[:120]})", {}
        if q.get("error"):
            return False, q["error"], {}
        if not q.get("ok"):
            o = CTX["offers"].pop(1, None)
            if o:
                try:
                    kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
                except Exception:
                    pass
            return False, f"Kalshi offered {q['pct']:.0%} of fair, under the {cut:.0%} cut-off", {}
        market = (CTX["offers"].get(1) or {}).get("market")
        r = accept_offer(1, skip_cap=True)               # the panel's own budget was checked when it was built
        if r.get("error"):
            return False, r["error"], {"market": market}
        return True, f"bought for {money(c['stake'])}, pays {money(q['pays'])} ({q['pct']:.0%} of fair)", \
            {"pays": round(q["pays"], 2), "pct": round(q["pct"], 4), "market": market, "bought_at": int(time.time())}
    return _with_ctx(go)


def _quote_only(c):
    """A real Kalshi price for a paper combo, without buying: (pays, share of fair) or (None, None)."""
    def go():
        _panel_combo(c, 0)
        CTX["source"] = "paper panel"
        q = get_offer(1, c["stake"], check_cap=False)
        o = CTX["offers"].pop(1, None)
        if o:
            try:
                kalshi_send("DELETE", f"/communications/rfqs/{o['rfq']}")
            except Exception:
                pass
        return (None, None) if q.get("error") else (q["pays"], q.get("pct"))
    return _with_ctx(go)


def exit_filled(ticker, price, since, n):
    """Whether a sell-early exit order sold: sells of this pick at or above the exit price, made after the
    panel bought it, adding up to (nearly) the contracts bought. Sales you make yourself before then don't count."""
    try:
        fills = (kalshi_send("GET", "/portfolio/fills", params={"ticker": ticker, "limit": 100}) or {}).get("fills") or []
    except Exception:
        return False
    sold = 0.0
    for f in fills:
        px = f.get("yes_price_dollars") or (f.get("yes_price") or 0) / 100
        try:
            ts = dt.datetime.fromisoformat(str(f.get("created_time")).replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = 0
        if f.get("action") == "sell" and float(px or 0) >= price - 0.005 and ts >= since - 60:
            sold += float(f.get("count_fp") or f.get("count") or 0)
    return sold >= 0.99 * n


def _set_items(day, mode, changes):
    """Apply {item id: {field: value}} to the stored panel atomically."""
    def fn(cur, st):
        if not cur:
            return None
        for cid, ch in changes.items():
            c = _item(cur, cid)
            if c is not None:
                c.update(ch)
            elif ch.get("_new"):
                cur["items"].append({k: v for k, v in ch.items() if k != "_new"})
        return cur, st
    return panel_tx(day, mode, fn)


def panel_exec(alert=None, log=print, paused=False, may_trade=True):
    """On the Mac every minute, and within seconds of an Approve/Add (ask_buy): buy every approved panel bet still
    waiting (rechecked first, swapped if needed), and run the paper panel the same way without money. There's no
    waiting for a time before the game (Pete's decision); only the price checks and the start rules decide. Each real buy is marked "buying" (and saved) before
    the order goes out, so a crash can never lead to buying it twice; a buy whose outcome is unknown is
    marked "check" and you're told, never retried."""
    out = []
    now = time.time()
    day = _panel_day()
    sk = load_json(SIZING_FILE, {})
    if sk.get("skim_note") and sk.get("skim_told") != sk.get("month"):
        sk["skim_told"] = sk.get("month")
        save_json(SIZING_FILE, sk)
        out.append(f"💰 {sk['skim_note']} The app no longer bets with it; move it out of Kalshi, then tap "
                   f"\"I moved it\" in Settings › Money. Set aside so far: {money(sk.get('reserved', 0))}.")
    for mode in ("real", "paper"):
        p = panel_get(mode)
        if not p or p["status"] not in ("approved", "paper"):
            continue
        for c in list(p["items"]):
            if c.get("state") == "buying" and now - c.get("buy_started", now) > 300:
                _set_items(day, mode, {c["id"]: {"state": "check", "note": "the Mac stopped mid-purchase; check Kalshi"}})
                out.append(f"⚠️ Panel: not sure whether {bet_text(c)} was bought (the Mac restarted mid-purchase). "
                           f"Check Kalshi; it won't be bought again.")
                continue
            if c.get("state") != "scheduled":
                continue
            if (c.get("buy_at") or 0) > now:
                continue                                  # approved before buying-at-once (#51): keeps the time it was approved under
            picks = bet_text(c)
            if not _start_ok(c, now, 5 * 60):
                f0 = _fresh(c) if live_panel_on() and not c.get("live") else None
                if isinstance(f0, dict) and f0.get("live") and _start_ok(f0, now, 5 * 60):
                    c = dict(c, live=True, kick_pre=f0.get("kick_pre"))   # under way now, and still good priced live
                    _set_items(day, mode, {c["id"]: {"live": True, "kick_pre": f0.get("kick_pre")}})
                else:
                    _set_items(day, mode, {c["id"]: {"state": "skipped", "note": (
                        "games under way are switched off in Settings" if c.get("live") else
                        "its game was about to start before the price could be checked")}})
                    if mode == "real":
                        out.append(f"⏭️ Panel: skipped {picks}: " + ("games under way are switched off." if c.get("live")
                                                                     else "its game starts too soon to buy safely."))
                    continue
            if mode == "real" and (paused or not may_trade):
                hold = "paused" if paused else "no key"   # the card says why it isn't bought yet
                if c.get("hold") != hold:
                    _set_items(day, mode, {c["id"]: {"hold": hold}})
                continue
            f = _fresh(c)
            if f == "wait":                               # candidates too old: try again shortly, and have the Mac
                if mode == "real":                        # look at that sport again soon (sports_near)
                    BUY_WAIT[c["code"]] = now
                    if c.get("hold") != "price":
                        _set_items(day, mode, {c["id"]: {"hold": "price"}})
                continue
            if f is None:
                alt = _replacement(c, p)
                if alt:
                    alt = dict(alt, stake=c["stake"], state="scheduled", swapped_for=picks)
                    _set_items(day, mode, {c["id"]: {"state": "swapped"}, alt["id"]: dict(alt, _new=True)})
                    ask_buy()                             # buy the swapped-in bet on a pass right after this one
                    if mode == "real":
                        out.append(f"🔁 Panel: swapped {picks} for {bet_text(alt)}: "
                                   f"its price no longer beat its chance.")
                else:
                    _set_items(day, mode, {c["id"]: {"state": "skipped",
                                                     "note": "no longer priced well enough, and nothing similar qualified"}})
                    if mode == "real":
                        out.append(f"⏭️ Panel: skipped {picks}: its price moved and nothing similar qualified.")
                continue
            upd = {k: f[k] for k in ("legs", "chance", "ret", "price", "pct", "exit", "fair_mult", "live", "kick_pre") if k in f}
            if mode == "paper":
                upd.update(state="paper", paid=f.get("price"), bought_at=int(now))
                if c["kind"] == "combo" and may_trade:      # a real price, so the paper record is honest
                    try:
                        pays, pct = _quote_only(dict(c, **upd))
                    except Exception:
                        pays, pct = None, None
                    if pays and pct is not None:
                        if pct < combo_cutoff(c["code"], len(c["legs"]), c["legs"]):
                            upd.update(state="skipped", note=f"Kalshi offered {pct:.0%} of fair, under the cut-off")
                        else:
                            upd.update(pays=round(pays, 2), pct=round(pct, 4))
                _set_items(day, mode, {c["id"]: upd})
                continue
            # real money: claim it first (saved), then buy, then record
            claimed = {}

            def claim(cur, st):
                it = _item(cur, c["id"])
                if st != "approved" or not it or it.get("state") != "scheduled":
                    return None                           # cancelled or already taken in the meantime
                it.update(upd, state="buying", buy_started=time.time())
                it.pop("hold", None)
                claimed["ok"] = True
                return cur, st
            panel_tx(day, mode, claim)
            if not claimed:
                continue
            try:
                ok, note, d = _buy_panel_bet(dict(c, **upd))
            except Exception as err:
                ok, note, d = None, f"{type(err).__name__}: {err}", {}
            state = "bought" if ok else ("skipped" if c.get("live") else "failed") if ok is False else "check"
            try:
                _set_items(day, mode, {c["id"]: dict(d, state=state, note=note, at=int(time.time()))})
            except Exception as err:                       # leave it "buying": never re-bought; flagged after 5 min
                log("panel: couldn't save a purchase result:", type(err).__name__, err)
            out.append(("✅ Panel bought: " if ok else "⚠️ Panel couldn't buy " if ok is False else
                        "⚠️ Panel: check Kalshi for ") + f"{picks}: {note}.")
    return out


def panel_settle():
    """Record results for panel bets (real and paper) once their games are decided."""
    if not STORE["db"]:
        return []
    _panel_table()
    since = (dt.datetime.now(PACIFIC).date() - dt.timedelta(days=10)).isoformat()
    for mode in ("real", "paper", "lab"):
        for r in store_rows("select * from panel where (mode=? or mode like ?) and day >= ?", (mode, mode + "#%", since)):
            p = json.loads(r["body"])
            changes = {}
            for c in p["items"]:
                ch = {}
                if c.get("state") in ("bought", "paper") and c.get("clv") is None and (c.get("kick") or 9e12) < time.time() \
                        and not c.get("live"):                 # bought during the game: the closing price came before it
                    cl = close_prices([l["ticker"] for l in c["legs"]])
                    if len(cl) == len(c["legs"]) and all(l.get("p") for l in c["legs"]):
                        ch["clv"] = round(math.prod(cl[l["ticker"]] for l in c["legs"]) /
                                          math.prod(l["p"] for l in c["legs"]) - 1, 4)
                if c.get("state") not in ("bought", "paper") or c.get("result"):
                    if ch:
                        changes[c["id"]] = ch
                    continue
                touched = c.get("touched")
                if c["kind"] == "early" and not touched:
                    if mode == "real":                     # real: only a filled exit order counts
                        touched = c.get("exit_order") == "placed" and can_trade() and \
                            exit_filled(c["legs"][0]["ticker"], c["exit"], c.get("bought_at") or c.get("at") or 0,
                                        c.get("filled") or 0)
                    else:                                  # paper: the bid reaching the exit, less a margin for fills
                        b = book_depth(c["legs"][0]["ticker"]) or {}
                        touched = (b.get("bid") or 0) >= c["exit"] + 0.01
                    if touched:
                        ch["touched"] = True
                res = fetch_results([l["ticker"] for l in c["legs"]])
                if all(res.get(l["ticker"]) in ("yes", "no") for l in c["legs"]):
                    won = all(res[l["ticker"]] == "yes" for l in c["legs"])
                    s = c["stake"]
                    p_ = c.get("paid") or c.get("price") or 0.5
                    if c["kind"] == "combo":
                        pays = c.get("pays") or s * c.get("pct", 1) * c.get("fair_mult", 1)
                        pl = pays - s if won else -s
                    elif c["kind"] == "early" and touched:
                        n = s / (p_ + single_fee(p_))
                        pl = n * (c["exit"] - p_ - single_fee(p_) - single_fee(c["exit"]))
                    else:
                        n = s / (p_ + single_fee(p_))
                        pl = n - s if won else -s
                    ch.update(result="won" if pl > 0 else "lost", pl=round(pl, 2))
                    try:                                   # what smart sell would have done, from its game prices
                        sim = sim_exit(c)
                    except Exception:
                        sim = None
                    if sim:
                        ch.update(sim_pl=sim[0], sim_why=sim[1])
                if ch:
                    changes[c["id"]] = ch
            if changes:
                _set_items(r["day"], r["mode"], changes)
    return []


def panel_record():
    """The paper panel's record (the gate for handing it $300) and the real panel's."""
    out = {}
    _panel_table()
    for mode in ("real", "paper"):
        rows = store_rows("select body from panel where mode=? or mode like ?", (mode, mode + "#%")) if STORE["db"] else []
        bodies = [json.loads(r["body"]) for r in rows]
        bets = [c for b in bodies for c in b.get("items", []) if c.get("result")]
        days = defaultdict(float)
        for b in bodies:
            for c in b.get("items", []):
                if c.get("result"):
                    days[_panel_day(b["at"])] += c["pl"]
        clv = [c["clv"] for b in bodies for c in b.get("items", []) if c.get("clv") is not None]
        out[mode] = {"clv": round(sum(clv) / len(clv), 4) if clv else None, "clv_n": len(clv),
                     "bets": len(bets), "won": sum(1 for c in bets if c["result"] == "won"),
                     "pl": round(sum(c["pl"] for c in bets), 2), "staked": round(sum(c["stake"] for c in bets), 2),
                     "days": len(days), "days_up": sum(1 for v in days.values() if v > 0)}
    pp = out["paper"]
    pp["ready"] = (pp["bets"] >= 50 and pp["pl"] > 0 and pp["days_up"] >= 0.55 * max(pp["days"], 1)
                   and (pp["clv"] is None or pp["clv"] >= 0))
    return out


# ---------------------------------------------------------------- the combo lab and the analytics
# Pete: "make the paper buy combos at different levels so we can learn more." Every day the lab paper-buys
# a few combos in each price band (how much Kalshi pays vs. fair), from real Kalshi quotes, with no money.
# During games the Mac records each paper and panel bet's prices, so afterwards it can estimate what smart
# sell would have done, not only what riding to the end did.
LAB_BANDS = [(0.80, 0.85, "80–85%"), (0.85, 0.90, "85–90%"), (0.90, 0.95, "90–95%"), (0.95, 1.00, "95–100%"),
             (1.00, 9.99, "100%+")]
ALL_BANDS = [(0.0, 0.70, "under 70%"), (0.70, 0.80, "70–80%")] + LAB_BANDS
LAB = {"per_band": 3, "stake": 5.0, "fresh": 1800}


def _band(pct, bands=LAB_BANDS):
    for lo, hi, name in bands:
        if pct is not None and lo <= pct < hi:
            return name
    return None


def _pick_label(t):
    return PICK_NAME.get(t) or (MARKET_INFO.get(t) or {}).get("name") or \
        sport_teams(ticker_sport(t) or "").get(t.rsplit("-", 1)[-1]) or t.rsplit("-", 1)[-1]


def lab_pass(now=None):
    """Paper-buy today's lab combos: up to 3 per price band, from Kalshi quotes of the last half hour whose
    games start in 20+ minutes, never the same combo twice. Returns how many were added."""
    if not STORE["db"]:
        return 0
    now = now or time.time()
    rows = store_rows("select rowid as id, ts, sport, n, legs, stake, pays, fair, pct, hours from quotes "
                      "where ts > ? and pct is not null and hours is not null and stake > 0", (now - LAB["fresh"],))
    if not rows:
        return 0
    got = {}

    def fn(cur, st):
        p = cur or {"at": now, "items": [], "budget": 0, "lab": True}
        have = {c["id"] for c in p["items"]}
        count = defaultdict(int)
        for c in p["items"]:
            count[c["band"]] += 1
        seen = {tuple(sorted(l["ticker"] for l in c["legs"])) for c in p["items"]}
        added = 0
        for r in sorted(rows, key=lambda r: -r["ts"]):
            b = _band(r["pct"])
            kick = r["ts"] + (r["hours"] or 0) * 3600
            legs = json.loads(r["legs"] or "[]")
            key = tuple(sorted(x[0] for x in legs))
            iid = f"lab:{r['id']}"
            if not b or not legs or kick < now + 20 * 60 or iid in have or key in seen or count[b] >= LAB["per_band"]:
                continue
            k = LAB["stake"] / r["stake"]
            p["items"].append({"id": iid, "kind": "combo", "band": b, "code": (r["sport"] or "other").split(",")[0],
                               "sports": r["sport"], "stake": LAB["stake"], "pays": round(r["pays"] * k, 2),
                               "pct": round(r["pct"], 4), "chance": round(r["stake"] / r["fair"], 4) if r["fair"] else None,
                               "legs": [{"ticker": x[0], "p": x[1], "fair": x[2], "pick": _pick_label(x[0])} for x in legs],
                               "kick": kick, "state": "paper", "quote": r["id"], "at": now})
            count[b] += 1
            seen.add(key)
            added += 1
        got["n"] = added
        return (p, "paper") if added else None
    panel_tx(_panel_day(now), "lab", fn)
    return got.get("n", 0)


def lab_ticks(now=None):
    """Record the in-game prices of every open paper, lab and panel bet (one batched Kalshi call), so the
    analytics can replay what smart sell would have done. Returns how many prices were saved."""
    if not STORE["db"]:
        return 0
    now = now or time.time()
    _panel_table()
    since = (dt.datetime.now(PACIFIC).date() - dt.timedelta(days=2)).isoformat()
    want = set()
    for r in store_rows("select body from panel where day >= ? and (mode in ('lab','paper','real') or mode like 'real#%')",
                        (since,)):
        for c in json.loads(r["body"]).get("items", []):
            if c.get("state") in ("paper", "bought") and not c.get("result") and now - 8 * 3600 < (c.get("kick") or 9e12) < now + 300:
                want |= {l["ticker"] for l in c["legs"]}
    want = sorted(want)
    saved = 0
    if now - LAB.get("pruned", 0) > 86400:          # keep the game-price record to 45 days
        LAB["pruned"] = now
        store_x("delete from ticks where state='sim' and ts < ?", (now - 45 * 86400,))
    for i in range(0, len(want), 50):
        try:
            r = requests.get(f"{KALSHI}/markets", params={"tickers": ",".join(want[i:i + 50])}, timeout=15)
            r.raise_for_status()
            for m in r.json().get("markets", []):
                lp = 1.0 if m.get("result") == "yes" else 0.0 if m.get("result") == "no" else live_price(m)
                if lp is not None:
                    store_x("insert into ticks values(?,?,?,?,?)", (now, m.get("ticker"), lp, "sim", (m.get("status") or "")[:12]))
                    saved += 1
        except (requests.RequestException, ValueError):
            continue
    return saved


# (sim_exit lives with the self-tuning smart sell below)


ANALYTICS = {"at": 0, "v": None}


def _roi(pl, staked):
    return round(pl / staked, 4) if staked else None


def analytics(max_age=600):
    """Everything the Mac has learned, by price level, bet type, sport and exit. Cached 10 minutes."""
    if ANALYTICS["v"] is not None and time.time() - ANALYTICS["at"] < max_age:
        return ANALYTICS["v"]
    if not STORE["db"]:
        return {}
    now = time.time()
    out = {"at": now}
    # 1. combos by price level: every combo Kalshi quoted in the last 90 days, as if bought at that quote
    levels = {name: {"band": name, "n": 0, "hits": 0, "exp": 0.0, "staked": 0.0, "ride": 0.0, "gt_n": 0, "gt": 0.0}
              for _, _, name in ALL_BANDS}
    for r in store_rows("select legs, stake, pays, fair, pct, outcome from quotes where pct is not null and ts > ? "
                        "and outcome in ('won','lost')", (now - 90 * 86400,)):
        b = _band(r["pct"], ALL_BANDS)
        if not b or not r["stake"]:
            continue
        L = levels[b]
        L["n"] += 1
        L["hits"] += r["outcome"] == "won"
        L["exp"] += (r["stake"] / r["fair"]) if r["fair"] else 0
        L["staked"] += r["stake"]
        L["ride"] += (r["pays"] if r["outcome"] == "won" else 0) - r["stake"]
        legs = json.loads(r["legs"] or "[]")
        cl = close_prices([x[0] for x in legs])
        if legs and len(cl) == len(legs) and all(x[1] for x in legs):
            L["gt_n"] += 1
            L["gt"] += r["pays"] * math.prod(cl[x[0]] for x in legs) - r["stake"]
    _panel_table()
    bodies = [(r["mode"], json.loads(r["body"])) for r in
              store_rows("select mode, body from panel where mode in ('real','paper','lab') or mode like 'real#%'")]
    items = [(m.split("#")[0], c) for m, b in bodies for c in b.get("items", []) if c.get("result")]
    lab = defaultdict(lambda: {"n": 0, "won": 0, "staked": 0.0, "pl": 0.0, "sim": 0.0})
    for m, c in items:
        if m == "lab":
            x = lab[c.get("band")]
            x["n"] += 1
            x["won"] += c["result"] == "won"
            x["staked"] += c["stake"]
            x["pl"] += c["pl"]
            x["sim"] += c["sim_pl"] if c.get("sim_pl") is not None else c["pl"]
    rows = []
    for _, _, name in ALL_BANDS:
        L, x = levels[name], lab.get(name)
        if not L["n"] and not x:
            continue
        rows.append({"band": name, "n": L["n"], "hit": round(L["hits"] / L["n"], 3) if L["n"] else None,
                     "exp": round(L["exp"] / L["n"], 3) if L["n"] else None, "ride": _roi(L["ride"], L["staked"]),
                     "gt": _roi(L["gt"], L["staked"] * L["gt_n"] / L["n"]) if L["gt_n"] else None, "gt_n": L["gt_n"],
                     "lab_n": x["n"] if x else 0, "lab_ride": _roi(x["pl"], x["staked"]) if x else None,
                     "lab_smart": _roi(x["sim"], x["staked"]) if x else None})
    out["levels"] = rows
    # 2. bet types and 3. sports: the real panel, the paper panel and the lab
    names = {"single": "Single games", "early": "Sell-early favorites", "line": "Spreads & totals", "combo": "Combos"}

    def roll(key, its=None):
        g = defaultdict(lambda: {"n": 0, "won": 0, "staked": 0.0, "pl": 0.0, "clv": [], "sim": 0.0, "sim_n": 0})
        for m, c in (items if its is None else its):
            k = (m if m != "lab" else "paper", key(c))
            x = g[k]
            x["n"] += 1
            x["won"] += c["result"] == "won"
            x["staked"] += c["stake"]
            x["pl"] += c["pl"]
            if c.get("clv") is not None:
                x["clv"].append(c["clv"])
            if c.get("sim_pl") is not None:
                x["sim_n"] += 1
            x["sim"] += c["sim_pl"] if c.get("sim_pl") is not None else c["pl"]
        return [{"mode": m, "what": w, "n": x["n"], "won": x["won"], "pl": round(x["pl"], 2), "roi": _roi(x["pl"], x["staked"]),
                 "clv": round(sum(x["clv"]) / len(x["clv"]), 4) if x["clv"] else None,
                 "smart": _roi(x["sim"], x["staked"]), "sim_n": x["sim_n"]}
                for (m, w), x in sorted(g.items(), key=lambda kv: (kv[0][0] != "real", -kv[1]["n"]))]
    out["types"] = roll(lambda c: names.get(c["kind"], c["kind"]))
    out["sports"] = roll(lambda c: (SPORTS.get(c.get("code") or "", {}).get("name") or (c.get("code") or "other").upper()))
    # bets bought on games already under way, as their own group by league, so their record is judged on its own
    out["live"] = roll(lambda c: league_label(bet_key([l["ticker"] for l in c["legs"]])),
                       [(m, c) for m, c in items if c.get("live")])
    out["live_excluded"] = LIVE_EXCLUDED_WHY
    # 4. exits: your real combos (Kalshi record) ridden vs cashed, and what automatic selling did
    ex = defaultdict(lambda: {"n": 0, "cost": 0.0, "back": 0.0})
    for r in store_rows("select cost, pays, back, status from bets where status in ('won','lost','cashed') and settled > ?",
                        (now - 90 * 86400,)):
        k = "Cashed out early" if r["status"] == "cashed" else "Rode to the end"
        e = ex[k]
        e["n"] += 1
        e["cost"] += r["cost"] or 0
        e["back"] += (r["back"] if r["status"] == "cashed" else r["pays"] if r["status"] == "won" else 0) or 0
    out["exits"] = [{"what": k, "n": e["n"], "pl": round(e["back"] - e["cost"], 2), "roi": _roi(e["back"] - e["cost"], e["cost"])}
                    for k, e in ex.items()]
    auto, held, hheld = defaultdict(int), defaultdict(int), defaultdict(int)
    try:
        cut = time.time() - 30 * 86400
        with open(SELL_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict) or d.get("at", 0) < cut:
                    continue
                if d.get("result") in ("sold", "hedged"):
                    auto[d.get("why") or d.get("result")] += 1
                elif d.get("result") == "held" and d.get("guard"):
                    (hheld if d.get("hedge") else held)[d["guard"]] += 1   # a loss cut or auto-hedge held back, and why
    except OSError:
        pass
    out["auto"] = dict(auto)
    out["cut_held"] = dict(held)
    out["hedge_held"] = dict(hheld)
    real = [c for m, c in items if m == "real"]
    out["notes"] = _analytics_notes(rows, out["types"], len(real))
    try:
        out["tuning"] = smart_summary()
    except Exception:
        out["tuning"] = []
    ANALYTICS.update(at=now, v=out)
    return out


def _analytics_notes(levels, types, n_real):
    """A few plain sentences: what the numbers say so far, and how sure they are."""
    notes = []
    big = [r for r in levels if r["n"] >= 30 and r["ride"] is not None]
    if big:
        best = max(big, key=lambda r: r["ride"])
        notes.append(f"Combos priced {best['band']} of fair have done best so far: {best['ride']:+.0%} riding to the end "
                     f"over {best['n']} quotes.")
    thin = [r["band"] for r in levels if 0 < r["n"] < 30]
    if thin:
        notes.append("Not enough results yet for " + ", ".join(thin) + " (30+ each before reading much into them).")
    for t in types:
        if t["mode"] == "paper" and t["n"] >= 20 and t["smart"] is not None and t["roi"] is not None \
                and abs(t["smart"] - t["roi"]) >= 0.05:
            better = "smart sell" if t["smart"] > t["roi"] else "riding to the end"
            notes.append(f"{t['what']} (paper): {better} has done better ({t['smart']:+.0%} vs {t['roi']:+.0%}).")
    if not n_real:
        notes.append("No real panel bets have settled yet.")
    return notes


# ---------------------------------------------------------------- smart sell that tunes itself, league by league
# Pete: no hard "never/always" lines; every rule starts somewhere sensible and the data moves it, league by
# league (college basketball isn't the NBA). Once a week the Mac replays settled bets on their recorded game
# prices with slightly different settings and keeps whatever has really done better, in small steps, only
# with enough results. Leagues short on data borrow their sport's settings, then everyone's.
SMART_FILE = os.path.join(HERE, "combo_smart.json")
SMART_DEFAULT = {"floor": 1.5, "lam": 1.0, "loss": None}
SMART_BOUNDS = {"floor": (1.2, 2.0), "lam": (0.5, 2.0), "loss": (0.10, 0.30)}
SMART_MIN_N, SMART_MIN_GAIN = 30, 0.02
SOCCER_LEAGUE = {"KXEPL": "epl", "KXLALIGA": "laliga", "KXSERIEA": "seriea", "KXBUNDESLIGA": "bundesliga",
                 "KXLIGUE1": "ligue1", "KXMLS": "mls", "KXLIGAMX": "ligamx"}
LEAGUE_NAME = {"epl": "Premier League", "laliga": "La Liga", "seriea": "Serie A", "bundesliga": "Bundesliga",
               "ligue1": "Ligue 1", "mls": "MLS", "ligamx": "Liga MX", "mix": "Mixed", "all": "Everything"}
SMART_CACHE = {"at": 0, "d": {}}
RIDE_LAM = {0: 1.4, 1: 1.2, 2: 1.0, 3: 0.75}          # Let it ride: Cautious sells sooner, Bold holds longer


def league_key(t):
    u = (t or "").upper()
    for pre, k in SOCCER_LEAGUE.items():
        if u.startswith(pre):
            return k
    return ticker_sport(t) or "other"


def bet_key(tickers):
    ks = {league_key(t) for t in tickers if t}
    return ks.pop() if len(ks) == 1 else "mix"


def league_label(k):
    return LEAGUE_NAME.get(k) or (SPORTS.get(k) or {}).get("name") or k.upper()


def smart_table():
    if time.time() - SMART_CACHE["at"] > 60:
        SMART_CACHE.update(at=time.time(), d=load_json(SMART_FILE, {}))
    return SMART_CACHE["d"]


def smart_params(tickers):
    """The smart-sell settings for a bet: its league's own once it has enough results, else its sport's,
    else everyone's, else the starting point (1.5x floor, standard risk, no selling at a loss). The learned loss
    cut is never borrowed (borrowing may only make selling at a loss stricter): only a league's own record turns
    it on."""
    d = smart_table()
    k = bet_key(tickers)
    sport = ticker_sport(next(iter(tickers), "") or "") if k not in ("mix",) else None
    for key in (k, sport, "all"):
        e = d.get(key) if key else None
        if e and e.get("n", 0) >= SMART_MIN_N:
            out = {**SMART_DEFAULT, **{x: e.get(x, SMART_DEFAULT[x]) for x in SMART_DEFAULT}, "key": key}
            if key != k:
                out["loss"] = None
            return out
    return dict(SMART_DEFAULT, key=None)


def ride_lam():
    """How the Let it ride setting scales smart sell (None: Ride it out turns smart sell off)."""
    i = min(max(int(CFG.get("ride", 2)), 0), len(RIDE) - 1)
    return RIDE_LAM.get(i)


def _paths(c):
    """A bet's recorded game prices as [(time, {ticker: chance})], oldest first (any source of ticks)."""
    tks = [l["ticker"] for l in c["legs"]]
    q_ = ",".join("?" * len(tks))
    since = (c.get("bought_at") or c.get("at") or c.get("kick") or 0) if c.get("live") else (c.get("kick") or 0) - 300
    rows = store_rows(f"select ts, ticker, chance from ticks where ticker in ({q_}) and ts >= ? and chance is not null "
                      f"order by ts", (*tks, since))
    cur = {l["ticker"]: (l.get("p") or 0.5) for l in c["legs"]}
    out, by = [], defaultdict(list)
    for r in rows:
        by[round(r["ts"])].append(r)
    for ts in sorted(by):
        for r in by[ts]:
            cur[r["ticker"]] = r["chance"]
        out.append((ts, dict(cur)))
    return out


def _replay(c, path, fl=1.5, lm=1.0, loss=None, trail=True, cut_at=None):
    """Replays smart sell on a bet's path with the given settings. Returns (profit, why) when it would have
    sold, else None (it rides to the end). A loss cut happens only at the times in `cut_at` (when the live loss
    guards would have held: _cut_guard_ts); with none given, never."""
    stake = c["stake"]
    if c["kind"] == "combo":
        P = c.get("pays") or 0
    else:
        p0 = c.get("paid") or c.get("price") or c["legs"][0].get("p") or 0.5
        P = stake / (p0 + single_fee(p0))
    if not P or len(path) < 3:
        return None
    tks = [l["ticker"] for l in c["legs"]]
    peak = 0.0
    for ts, cur in path:
        q = math.prod(cur[t] for t in tks)
        open_ = [t for t in tks if 0.02 < cur[t] < 0.98]
        if not open_:
            return None
        if c["kind"] == "combo":
            est = kalshi_discount(True) * q * P
        else:
            x = cur[tks[0]]
            est = P * max(x - single_fee(x) - 0.01, 0)
        lam = 0.35 * lm * sum(SWING.get(ticker_sport(t) or "", 1.0) for t in open_) / len(open_)
        floor = max(q * P - lam * P * math.sqrt(max(q * (1 - q), 0)), fl * stake)
        if q >= 0.5 and est >= floor:
            return round(est - stake, 2), "smart"
        if loss and q <= loss and est > 0.02 * stake and round(ts) in (cut_at or ()):
            return round(est - stake, 2), "cut loss"
        peak = max(peak, est)
        if trail and peak >= max(TRAIL_ARM * P, fl * stake) and est <= (1 - TRAIL_DROP) * peak and est >= 1.1 * stake:
            return round(est - stake, 2), "lock in"
    return None


def sim_exit(c):
    """What smart sell (with today's settings for that league) would have done with this bet, on its recorded
    game prices: (profit or loss, why) if it would have sold, None if it would have ridden."""
    if not STORE["db"] or c.get("kind") == "early" or not c.get("kick"):
        return None
    pr = smart_params([l["ticker"] for l in c["legs"]])
    cut_at = _cut_guard_ts(c, _sl_paths(c), pr["loss"]) if pr["loss"] else None
    return _replay(c, _paths(c), pr["floor"], pr["lam"], pr["loss"], cut_at=cut_at)


def _tune_items(days=60):
    """Settled bets with recorded game prices: panel, paper and lab bets, and your real combos."""
    cut = time.time() - days * 86400
    out = []
    _panel_table()
    for r in store_rows("select body from panel where (mode in ('real','paper','lab') or mode like 'real#%') and ts > ?", (cut,)):
        for c in json.loads(r["body"]).get("items", []):
            if c.get("result") and c.get("kind") != "early" and c.get("kick") and c.get("pl") is not None:
                out.append(c)
    for r in store_rows("select combo, cost, pays, legs, status, first_seen from bets where status in ('won','lost') and settled > ?", (cut,)):
        try:
            tks = json.loads(r["legs"] or "[]")
        except ValueError:
            continue
        if tks and r["cost"]:
            out.append({"id": r["combo"], "kind": "combo", "stake": r["cost"], "pays": r["pays"], "kick": r["first_seen"],
                        "legs": [{"ticker": t} for t in tks], "pl": (r["pays"] if r["status"] == "won" else 0) - r["cost"]})
    return out


def _sl_played(code, text):
    """(share of the game played or None, at a break?) from a recorded score line like 'NYK 54–60 BOS Q3 5:42'."""
    t = (text or "").strip()
    n_per = (SPORTS.get(code) or {}).get("periods") or 4
    if not t or t.startswith("Final") or t.endswith("Final") or "Final" in t.split()[-2:]:
        return None, False
    if t.endswith("Half"):
        return 0.5, True
    m = re.search(r"\bEnd (?:Q|P|H)(\d+)$", t)
    if m:
        return min(int(m.group(1)) / n_per, 1.0), True
    if re.search(r"\b(OT|SO)\b", t):
        return 0.96, False
    m = re.search(r"\b(?:Q|P|H)(\d+) ([\d:.']+)\S*$", t)
    if not m:
        return None, False
    frac = _frac_left(code, {"period": int(m.group(1)), "displayClock": m.group(2)}, n_per, "in")
    return round(1 - frac, 3), bool(re.fullmatch(r"0:00|0\.0", m.group(2)))


def _sl_paths(c):
    """A combo's recorded game prices with their score lines: [(time, {ticker: (chance, score line)})]."""
    tks = [l["ticker"] for l in c["legs"]]
    q_ = ",".join("?" * len(tks))
    rows = store_rows(f"select ts, ticker, chance, score from ticks where ticker in ({q_}) and ts >= ? and chance is not null "
                      f"order by ts", (*tks, (c.get("kick") or 0) - 3600))
    cur = {l["ticker"]: (l.get("p") or 0.5, "") for l in c["legs"]}
    out, by = [], defaultdict(list)
    for r in rows:
        by[round(r["ts"])].append(r)
    for ts in sorted(by):
        for r in by[ts]:
            cur[r["ticker"]] = (r["chance"], r["score"] or "")
        out.append((ts, dict(cur)))
    return out


def _sl_held(c, path, prog, drop, also=None):
    """Walks a bet's recorded prices and score lines with the live loss guards (a pick late enough, not at a break,
    under 50% and far enough below its pregame chance, plus `also(cur)` if given, held 3+ checks over 3+ minutes)
    and yields (time, prices) at each check where all of them held. Stops once every pick is decided."""
    tks = [l["ticker"] for l in c["legs"]]
    pre = {l["ticker"]: l.get("p") for l in c["legs"]}
    seen = []
    for ts, cur in path:
        if not any(0.02 < cur[t][0] < 0.98 for t in tks):
            return
        hit = False
        for t in tks:
            ch, txt = cur[t]
            played, brk = _sl_played(ticker_sport(t) or "", txt)
            if played is None:
                if not txt:
                    pre[t] = ch                           # before the game: the latest pregame chance
                continue
            if not brk and played >= prog and pre[t] is not None and ch < 0.5 and pre[t] - ch >= drop:
                hit = True
        if hit and also is not None and not also(cur):
            hit = False
        if not hit:
            seen = []
            continue
        if seen and ts - seen[-1] > SL_GAP:
            seen = []
        seen.append(ts)
        if len(seen) >= SL_CHECKS and ts - seen[0] >= SL_SPAN:
            yield ts, cur


def _sl_replay(c, path, prog, drop):
    """What the stop-loss switch, with these settings and the same guards as live (late enough, not at a break,
    far below the pregame chance, held 3+ checks over 3+ minutes), would have got for this combo: the loss when
    it would have sold, None when it would have held."""
    P, stake = c.get("pays") or 0, c["stake"]
    tks = [l["ticker"] for l in c["legs"]]
    if not P or len(path) < SL_CHECKS:
        return None
    for ts, cur in _sl_held(c, path, prog, drop):
        est = kalshi_discount(True) * math.prod(cur[t][0] for t in tks) * P
        return round(est - stake, 2) if est < stake else None
    return None


def _cut_guard_ts(c, slp, loss, prog=None, drop=None):
    """The times at which the learned loss cut's guards held for this bet (the same as live: under the cut-off and
    every stop-loss guard, confirmed), so the replay that learns the cut only cuts where live would have. With no
    prog/drop given, the league's current stop-loss settings."""
    if not loss or not slp or len(slp) < SL_CHECKS:
        return set()
    tks = [l["ticker"] for l in c["legs"]]
    if prog is None or drop is None:
        pr = stoploss_params(tks)
        prog, drop = pr["prog"], pr["drop"]
    return {round(ts) for ts, _ in _sl_held(c, slp, prog, drop,
                                            also=lambda cur: math.prod(cur[t][0] for t in tks) <= loss)}


def _sl_tune(e, rows):
    """One league's stop-loss settings: replay its combos with nearby settings and move one small step toward what
    clearly did better (only with SL_MIN_N combos; on a tie the smallest change wins). Updates `e`, returns why or ''."""
    cur = {"prog": float(e.get("sl_prog", SL_DEFAULT["prog"])), "drop": float(e.get("sl_drop", SL_DEFAULT["drop"]))}
    n = len(rows)
    e["sl_n"] = n
    e.setdefault("sl_prog", cur["prog"])
    e.setdefault("sl_drop", cur["drop"])
    if n < SL_MIN_N:
        return ""
    staked = sum(c["stake"] for c, _ in rows) or 1

    def score(prog, drop):
        tot = 0.0
        for c, path in rows:
            r = _sl_replay(c, path, prog, drop)
            tot += r if r is not None else c["pl"]
        return tot / staked
    here = (cur["prog"], cur["drop"])
    base = score(*here)
    best, best_v = here, base

    def clamp(v, k):
        return round(min(max(v, SL_BOUNDS[k][0]), SL_BOUNDS[k][1]), 2)
    for a in sorted({clamp(cur["prog"] + d, "prog") for d in (-SL_STEP, 0, SL_STEP)}):
        for b in sorted({clamp(cur["drop"] + d, "drop") for d in (-SL_STEP, 0, SL_STEP)}):
            v = score(a, b)
            moves = sum(1 for x, y in zip((a, b), here) if x != y)
            if v > best_v + 1e-9 or (abs(v - best_v) <= 1e-9 and moves < sum(1 for x, y in zip(best, here) if x != y)):
                best, best_v = (a, b), v
    if best == here or best_v - base < SL_MIN_GAIN:
        return ""
    parts = []
    if best[0] != here[0]:
        parts.append(f"waits until {best[0]:.0%} of the game is played (was {here[0]:.0%})")
    if best[1] != here[1]:
        parts.append(f"needs a {best[1] * 100:.0f}-point fall from the pregame chance (was {here[1] * 100:.0f})")
    why = (f"Stop-loss {' and '.join(parts)}: in {n} recent combos that would have returned {best_v:+.0%} on what "
           f"was staked, vs {base:+.0%} with the old settings")
    e.update(sl_prog=best[0], sl_drop=best[1], sl_why=why, sl_at=int(time.time()))
    return why


def _grid(cur):
    f, l, s = cur["floor"], cur["lam"], cur["loss"]
    lo_f, hi_f = SMART_BOUNDS["floor"]
    lo_l, hi_l = SMART_BOUNDS["lam"]
    floors = sorted({round(min(max(x, lo_f), hi_f), 2) for x in (f - 0.1, f, f + 0.1)})
    lams = sorted({round(min(max(x, lo_l), hi_l), 3) for x in (l * 0.85, l, l * 1.15)})
    losses = [None, 0.15] if s is None else sorted({x for x in (None if s - 0.05 < SMART_BOUNDS["loss"][0] else round(s - 0.05, 2),
                                                                s, round(min(s + 0.05, SMART_BOUNDS["loss"][1]), 2))},
                                                     key=lambda v: -1 if v is None else v)
    return [(a, b, c) for a in floors for b in lams for c in losses]


def smart_tune(force=False):
    """Once a week: for each league (then each sport, then everything), replay its settled bets with nearby
    settings and move one small step toward whatever did clearly better. Returns what changed, in words."""
    d = load_json(SMART_FILE, {})
    if not force and time.time() - d.get("_at", 0) < 7 * 86400:
        return []
    if not STORE["db"]:
        return []
    items = _tune_items()
    groups, sl_groups = defaultdict(list), defaultdict(list)
    for c in items:
        tks = [l["ticker"] for l in c["legs"]]
        path = _paths(c)
        if len(path) < 3:
            continue
        k = bet_key(tks)
        slp = _sl_paths(c)
        c = dict(c, _slp=slp)                            # the score lines, for the loss cut's guards in the replay
        for key in {k, ticker_sport(tks[0]) if k != "mix" else None, "all"}:
            if key:
                groups[key].append((c, path))
                if c.get("kind") == "combo" and slp and len(slp) >= SL_CHECKS:
                    sl_groups[key].append((c, slp))
    moved = []
    for key, rows in groups.items():
        cur = {**SMART_DEFAULT, **{x: (d.get(key) or {}).get(x, SMART_DEFAULT[x]) for x in SMART_DEFAULT}}
        n = len(rows)
        staked = sum(c["stake"] for c, _ in rows) or 1

        guards = {}                                      # the loss cut only where the live guards would have let it

        def score(fl, lm, loss):
            tot = 0.0
            for i, (c, path) in enumerate(rows):
                if loss and (i, loss) not in guards:
                    guards[(i, loss)] = _cut_guard_ts(c, c.get("_slp"), loss)
                r = _replay(c, path, fl, lm, loss, cut_at=guards.get((i, loss)))
                tot += r[0] if r else c["pl"]
            return tot / staked
        base = score(cur["floor"], cur["lam"], cur["loss"])
        best, best_v = (cur["floor"], cur["lam"], cur["loss"]), base
        here = (cur["floor"], cur["lam"], cur["loss"])
        moves = lambda g: sum(1 for a, b in zip(g, here) if a != b)
        if n >= SMART_MIN_N:
            for g in _grid(cur):
                v = score(*g)
                if v > best_v + 1e-9 or (abs(v - best_v) <= 1e-9 and moves(g) < moves(best)):
                    best, best_v = g, v       # on a tie, the smallest change wins
        e = dict(d.get(key) or {}, n=n, ret=round(base, 4))
        if n >= SMART_MIN_N and best_v - base >= SMART_MIN_GAIN and best != (cur["floor"], cur["lam"], cur["loss"]):
            parts = []
            if best[0] != cur["floor"]:
                parts.append(f"profit floor {cur['floor']:g}× → {best[0]:g}×")
            if best[1] != cur["lam"]:
                parts.append("holds a bit longer" if best[1] < cur["lam"] else "takes profits a bit sooner")
            if best[2] != cur["loss"]:
                parts.append("may now cut a loss once the chance falls under " + f"{best[2]:.0%}" if best[2] and not cur["loss"]
                             else "stops cutting losses" if not best[2] else f"cuts losses under {best[2]:.0%}")
            why = (f"{', '.join(parts)}: in {n} recent bets that would have returned {best_v:+.0%} on what was staked, "
                   f"vs {base:+.0%} with the old settings")
            e.update(floor=best[0], lam=best[1], loss=best[2], why=why, at=int(time.time()))
            moved.append(f"{league_label(key)}: {why}")
        else:
            e.update({x: cur[x] for x in SMART_DEFAULT})
        d[key] = e
    for key, rows in sl_groups.items():                  # the stop-loss switch's guards, same league-by-league way
        e = dict(d.get(key) or {})
        why = _sl_tune(e, rows)
        if why:
            moved.append(f"{league_label(key)}: {why}")
        d[key] = e
    d["_at"] = time.time()
    save_json(SMART_FILE, d)
    SMART_CACHE["at"] = 0
    return moved


def smart_summary():
    """Each league's smart-sell settings for the Results page."""
    d = load_json(SMART_FILE, {})
    out = []
    for k, e in sorted(d.items()):
        if k.startswith("_"):
            continue
        out.append({"key": k, "name": league_label(k), "floor": e.get("floor", 1.5), "lam": e.get("lam", 1.0),
                    "loss": e.get("loss"), "n": e.get("n", 0), "ret": e.get("ret"), "why": e.get("why", ""),
                    "at": e.get("at"), "own": e.get("n", 0) >= SMART_MIN_N,
                    "sl_prog": e.get("sl_prog", SL_DEFAULT["prog"]), "sl_drop": e.get("sl_drop", SL_DEFAULT["drop"]),
                    "sl_n": e.get("sl_n", 0), "sl_own": e.get("sl_n", 0) >= SL_MIN_N, "sl_why": e.get("sl_why", "")})
    return out


def prune_drafts(now=None):
    """Unapproved panels (today's, each sport's, and the New-since-you-approved extras) lose any bet whose game
    starts within 20 minutes (it can come back priced live once it's under way), any bet priced live when games
    under way are switched off, and any live-priced bet whose price is older than LIVE_POOL_AGE."""
    if not STORE["db"]:
        return
    now = now or time.time()
    _panel_table()
    day = _panel_day(now)
    for r in store_rows("select mode from panel where day=? and status='draft'", (day,)):
        mode = r["mode"]

        def fn(cur, st):
            if st != "draft" or not cur:
                return None
            keep = [c for c in cur["items"] if _start_ok(c, now, 20 * 60)
                    and not (c.get("live") and now - (cur.get("at") or 0) > LIVE_POOL_AGE)]
            if len(keep) == len(cur["items"]):
                return None
            return dict(cur, items=keep), "draft"
        got = panel_tx(day, mode, fn)
        if got and not got[0]["items"] and not got[0].get("longer"):
            store_x("delete from panel where day=? and mode=? and status='draft'", (day, mode))


def panel_pass(log=print):
    """After each round of collecting: rebuild today's draft, and start the paper copy for the day."""
    prune_drafts()
    for code in list(PANEL_POOL):                      # one-sport panels for the sport chips
        v = build_panel(codes=[code])
        if v["items"] or v["longer"]:
            panel_save_draft(v, f"view:{code}")
    out = []
    real = panel_get("real")
    if real and real["status"] == "approved":          # still looking: good bets that turned up since you approved
        active = [c for c in real["items"] if c.get("state") in ("scheduled", "buying", "bought", "check")]
        left = float(real.get("budget") or CFG.get("panel_budget", PANEL["budget"])) - sum(c["stake"] for c in active)
        x = build_panel(budget=max(left, 0), exclude={e for c in active for e in _events_of(c)})
        # only a skipped, swapped or left-out bet may come back if it's good again; today's panel is read again
        # here because building took a while and an Add may have landed meanwhile
        x["items"] = _extras_filter(x["items"], panel_get("real") or real)
        told_box = {}

        def put(old, st):
            told = set((old or {}).get("told", [])) if old and _panel_day(old["at"]) == _panel_day(x["at"]) else set()
            told_box["new"] = [c for c in x["items"] if c["id"] not in told]
            x["told"] = sorted(told | {c["id"] for c in x["items"]})
            return x, "draft"
        panel_tx(_panel_day(x["at"]), "extra", put)
        new = told_box.get("new") or []
        if new and left >= 2:
            names = "; ".join(bet_text(c) for c in new[:3])
            out.append(f"🆕 New good bet{'s' if len(new) > 1 else ''} since you approved today's panel: {names}"
                       f"{' and more' if len(new) > 3 else ''}. Add {'them' if len(new) > 1 else 'it'} in Build.")
        return out
    p = build_panel()
    if not p["items"]:
        return []
    panel_save_draft(p, "real")
    q = dict(p, items=[dict(c, state="scheduled") for c in p["items"]])
    panel_tx(_panel_day(p["at"]), "paper", lambda cur, st: None if cur else (q, "paper"))   # the day's first draft, as-is
    return out + [f"panel: {len(p['items'])} bets, {p['stats']['p_ahead']:.0%} chance to finish ahead"]


# ---------------------------------------------------------------- "cover the early games" paper test
# Pete's idea: $5 full-slate combos on every possible result of the Sunday early games, so exactly one
# survives to midday, then cash it out. Tracked on paper only: no quotes, no money. Prices are Kalshi's own
# (each game's two prices scaled to add to 100%); what Kalshi pays for a combo and for a cash-out uses the
# same measured ratios the rest of the planner uses.
COVER = {"stake": 5.0, "window_min": 45, "max_games": 14}
NFL_ALIAS = {"WSH": ("WAS",), "WAS": ("WSH",), "JAX": ("JAC",), "JAC": ("JAX",), "LAR": ("LA",), "LA": ("LAR",)}


def _cover_kicks(day):
    """ESPN kickoff times for that day's NFL games: [(abbrs, iso)]."""
    out = []
    for ev in _espn_board("nfl", day.strftime("%Y%m%d"), max_age=3600):
        comp = (ev.get("competitions") or [{}])[0]
        ab = [((c.get("team") or {}).get("abbreviation") or "").upper() for c in comp.get("competitors") or []]
        if ev.get("date") and all(ab):
            out.append((ab, ev["date"]))
    return out


def _cover_games(day):
    """That day's NFL games on Kalshi: [{event, kick (unix), sides:[{ticker, abbr, p}]}], p scaled to 100%."""
    by = defaultdict(list)
    for m in fetch_series("KXNFLGAME"):
        if game_date(m) != day or is_tie_market(m):
            continue
        p = live_price(m)
        if p:
            by[m["event_ticker"]].append({"ticker": m["ticker"], "abbr": m["ticker"].rsplit("-", 1)[-1].upper(),
                                          "p": p, "exp": m.get("expected_expiration_time") or ""})
    kicks = _cover_kicks(day)
    out = []
    for e, sd in by.items():
        if len(sd) != 2:
            continue
        tot = sd[0]["p"] + sd[1]["p"]
        for x in sd:
            x["p"] = round(x["p"] / tot, 4)
        tail = e.rsplit("-", 1)[-1].upper()
        kick = None
        for ab, iso in kicks:
            if all(any(a in tail for a in (b,) + NFL_ALIAS.get(b, ())) for b in ab):
                kick = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
                break
        if kick is None:
            try:
                kick = dt.datetime.fromisoformat(sd[0]["exp"].replace("Z", "+00:00")).timestamp() - game_hours(e) * 3600
            except ValueError:
                continue
        out.append({"event": e, "kick": kick, "sides": [{k: x[k] for k in ("ticker", "abbr", "p")} for x in sd]})
    return sorted(out, key=lambda g: g["kick"])


def _cover_r_buy():
    """What Kalshi pays for a long NFL combo as a share of fair, from your real quotes (median)."""
    rows = store_rows("select pct from quotes where sport='nfl' and pct is not null and n>=6 order by ts desc limit 200")
    if len(rows) < 10:
        rows = store_rows("select pct from quotes where pct is not null and n>=5 order by ts desc limit 200")
    xs = sorted(r["pct"] for r in rows if r["pct"])
    return round(min(max(xs[len(xs) // 2], 0.4), 1.0), 3) if len(xs) >= 10 else 0.85


def cover_math(early, r_buy, r_sell, stake=None):
    """Before kickoff: cost, expected midday value and the chance it ends up ahead."""
    stake = stake or COVER["stake"]
    k = len(early)
    cost = stake * 2 ** k
    win_p = 0.0
    if k <= COVER["max_games"]:
        for picks in itertools.product(*[[x["p"] for x in g["sides"]] for g in early]):
            pe = math.prod(picks)
            if stake * r_buy * r_sell / pe > cost:
                win_p += pe
    return {"k": k, "cost": cost, "expect": round(cost * r_buy * r_sell, 2), "p_ahead": round(win_p, 4)}


def _cover_week_days(sunday):
    """The NFL week's days around its anchoring Sunday (Wed-Mon), in order (same window week_games uses)."""
    return [sunday + dt.timedelta(days=d) for d in range(-4, 2)]


def _cover_week_slots(sunday):
    """Every game on this NFL week's slate, grouped into ordered kickoff checkpoints (~90-min buckets), so a
    Thursday-night game, Sunday's early window, the later windows and Monday night each become their own slot:
    [{slot_key, day_label, kick_start, games:[...]}], earliest first. Replaces the single early/late split."""
    days = {d: DAY_ORDER[i] for i, d in enumerate(_cover_week_days(sunday))}
    games = []
    for day, label in days.items():
        for g in _cover_games(day):
            games.append({**g, "day": label})
    by_slot = defaultdict(list)
    for g in games:
        by_slot[round(g["kick"] / 5400)].append(g)
    slots = []
    for key in sorted(by_slot):
        gs = sorted(by_slot[key], key=lambda g: g["kick"])
        slots.append({"slot_key": key, "day_label": gs[0]["day"], "kick_start": gs[0]["kick"], "games": gs})
    return slots


def cover_pass(log=print, alert=None):
    """Through the NFL week: snapshot the earliest checkpoint's games before kickoff and cover both sides, then as
    each later checkpoint settles work out what the one surviving full-slate combo would be worth, and replay smart
    sell on its still-live later legs. Paper only: no quotes, no money."""
    try:                                              # must never stop the real panel_loop (paper test only)
        return _cover_pass(log, alert)
    except Exception as err:
        log("cover test skipped:", type(err).__name__, err)
        return []


def _cover_survivor_combo(early, winners, later_games, r_buy, stake):
    """The surviving full-slate combo as a replayable bet dict: its early legs are the winners (so it survived the
    early checkpoint), carried together with every still-live later leg's value-picked (higher-p) side. `pays` is the
    survivor's gross payout (stake over the product of all entry prices, with the measured combo haircut), so _replay
    (which already applies the cash-out discount) lands on the right scale. kick = the first later leg's kickoff."""
    later_picks = [max(g["sides"], key=lambda x: x["p"]) for g in later_games]
    legs = [{"ticker": w["ticker"], "p": w["p"]} for w in winners] + [{"ticker": p["ticker"], "p": p["p"]} for p in later_picks]
    pe = math.prod(l["p"] for l in legs)
    pays = round(stake / pe * r_buy, 2) if pe else 0.0
    return {"kind": "combo", "stake": stake, "pays": pays, "legs": legs, "lgs": ["nfl"],
            "kick": min((g["kick"] for g in later_games), default=None)}


def _cover_pass(log=print, alert=None):
    now, did = time.time(), []
    today = dt.datetime.now(PACIFIC).date()           # the anchoring Sunday of the current NFL week (Monday's
    sunday = today - dt.timedelta(days=1) if today.weekday() == 0 \
        else today + dt.timedelta(days=(6 - today.weekday()) % 7)   # game belongs to the week that just ended)
    week_end = _nfl_week_end(now)
    key = sunday.isoformat()
    # First pass of the week, from the earliest kickoff on: snapshot the slate's checkpoints, cover the first one.
    if now < week_end and not store_rows("select 1 from cover where sunday=?", (key,)):
        slots = _cover_week_slots(sunday)
        if slots and now >= slots[0]["kick_start"] - 3 * 3600:
            first = slots[0]
            kkey = week_of(first["games"][0]["sides"][0]["ticker"]) or sunday
            key = kkey.isoformat()
            if not store_rows("select 1 from cover where sunday=?", (key,)):
                if now <= first["kick_start"] - 120:
                    r_buy, r_sell = _cover_r_buy(), kalshi_discount(live=False)
                    store_x("insert or ignore into cover values(?,?,?,?,?,?,?,?)",
                            (key, now, json.dumps(slots), None, r_buy, r_sell, "open", None))
                    m = cover_math(first["games"], r_buy, r_sell)
                    did.append(f"cover test: {m['k']} games in the first ({first['day_label']}) checkpoint, "
                               f"${m['cost']:,.0f} on paper, {m['p_ahead']:.0%} chance to end up ahead")
                elif now > first["kick_start"] - 120:
                    store_x("insert or ignore into cover values(?,?,?,?,?,?,?,?)",
                            (key, now, json.dumps(slots), None, 0, 0, "missed", None))
    for row in store_rows("select * from cover where status='open'"):
        did += _cover_resolve(row, now, alert)
    return did


def _cover_resolve(row, now, alert):
    """One open week: as each later checkpoint settles, record the surviving combo's worth there and its smart-sell
    replay exit; when the whole week is settled, decide whether the exits beat the cost of covering both sides."""
    did = []
    slots = json.loads(row["early"])
    if not slots:
        return did
    stake, r_buy, r_sell = COVER["stake"], row["r_buy"], row["r_sell"]
    first, later = slots[0], slots[1:]
    early = first["games"]
    k = len(early)
    cost_both = stake * 2 ** k
    res = fetch_results([x["ticker"] for g in early for x in g["sides"]])
    if any(not any(res.get(x["ticker"]) for x in g["sides"]) for g in early):
        if now - row["ts"] > 7 * 86400:               # a whole week went by with the first checkpoint unsettled
            store_x("update cover set status='stale' where sunday=?", (row["sunday"],))
        return did
    winners = [next((x for x in g["sides"] if res.get(x["ticker"]) == "yes"), None) for g in early]
    state = json.loads(row["result"]) if row["result"] else {}
    done_slots = {c["slot_key"] for c in state.get("checkpoints", [])}
    if any(w is None for w in winners):               # a tie in the covered checkpoint: every combo loses
        survivor, survivor_pays, pe = ["tie"], 0.0, 0.0
        combo = None
    else:
        survivor = [w["abbr"] for w in winners]
        pe = math.prod(w["p"] for w in winners)
        later_live = [g for s in later for g in s["games"]]
        combo = _cover_survivor_combo(early, winners, later_live, r_buy, stake)
        survivor_pays = combo["pays"]
    # measure each not-yet-recorded later checkpoint that has now settled
    checkpoints = list(state.get("checkpoints", []))
    for s in later:
        if s["slot_key"] in done_slots:
            continue
        r2 = fetch_results([x["ticker"] for g in s["games"] for x in g["sides"]])
        settled = all(any(r2.get(x["ticker"]) for x in g["sides"]) for g in s["games"])
        if not settled:
            continue
        picks = [max(g["sides"], key=lambda x: x["p"]) for g in s["games"]]
        slot_won = all(r2.get(p["ticker"]) == "yes" for p in picks)
        worth = 0.0
        if combo and slot_won:                        # the survivor's value-picks held through this checkpoint
            q = pe * math.prod(p["p"] for p in picks)
            worth = round(stake / q * r_buy * r_sell, 2) if q else 0.0
        replay_exit = None
        if combo:
            ex = sim_exit(combo)                       # smart-sell replay on the survivor's still-live later legs
            if ex:
                replay_exit = {"exit": round(ex[0] + stake, 2), "pl": ex[0], "why": ex[1]}
        checkpoints.append({"label": s["day_label"], "slot_key": s["slot_key"], "worth": worth,
                            "replay_exit": replay_exit, "settled": True})
    # is the week finished? (every later checkpoint recorded, or there were none)
    all_done = all(s["slot_key"] in {c["slot_key"] for c in checkpoints} for s in later)
    out = {"cost_both": round(cost_both, 2), "survivor": survivor, "survivor_pays": round(survivor_pays, 2),
           "checkpoints": checkpoints, "k": k, "cost": round(cost_both, 2)}
    # one-sided baseline: the single $5 value-picked combo the panel would build on the same early games
    one_pe = math.prod(max(g["sides"], key=lambda x: x["p"])["p"] for g in early)
    one_cost = stake
    one_survived = all(w is not None and w["p"] == max(g["sides"], key=lambda x: x["p"])["p"]
                       for g, w in zip(early, winners))
    best_exit = max((c["replay_exit"]["exit"] for c in checkpoints if c.get("replay_exit")), default=None)
    if combo and one_survived and best_exit is not None:
        one_sided_result = best_exit if one_pe else 0.0
    elif one_survived:
        one_sided_result = round(stake / one_pe * r_buy * r_sell, 2) if one_pe else 0.0
    else:
        one_sided_result = 0.0
    out["one_sided_cost"] = round(one_cost, 2)
    out["one_sided_result"] = round(one_sided_result, 2)
    out["one_sided_pl"] = round(one_sided_result - one_cost, 2)
    if best_exit is not None:
        out["sim_pl"] = round(best_exit - cost_both, 2)
        out["beat_cost"] = best_exit > cost_both
    else:                                             # no later legs to sell: fall back to the settled worth
        wk = checkpoints[-1]["worth"] if checkpoints else (round(stake / pe * r_buy * r_sell, 2) if (combo and pe) else 0.0)
        out["sim_pl"] = round(wk - cost_both, 2)
        out["beat_cost"] = wk > cost_both
    out["pl"] = out["sim_pl"]
    if all_done:
        store_x("update cover set status='done', result=? where sunday=?", (json.dumps(out), row["sunday"]))
        upsets = sum(1 for w in winners if w and w["p"] < 0.5)
        msg = (f"📒 Cover-the-early-games test (paper, {row['sunday']}): {k} games covered both sides, {upsets} upset"
               f"{'' if upsets == 1 else 's'}. Covering both cost ${cost_both:,.0f}; smart sell's best exit on the "
               f"survivor was ${(best_exit or 0):,.0f} ({'beat' if out['beat_cost'] else 'under'} the cost): "
               f"{'+' if out['pl'] >= 0 else '−'}${abs(out['pl']):,.0f} vs one-sided {'+' if out['one_sided_pl'] >= 0 else '−'}${abs(out['one_sided_pl']):,.0f}.")
        did.append(msg)
        if alert:
            alert(msg)
    else:                                             # record progress, keep the week open
        store_x("update cover set result=? where sunday=?", (json.dumps(out), row["sunday"]))
    return did


def cover_ticks(log=print):
    """Record the current prices of each open cover week's surviving combo's still-live later legs, so the smart-sell
    replay has a path to work with (lab_ticks only scans the panel table, which cover never touches). state='sim',
    like lab_ticks. Paper only, and fully defensive: never propagates to the watcher loop."""
    try:
        return _cover_ticks(log)
    except Exception as err:
        log("cover ticks skipped:", type(err).__name__, err)
        return 0


def _cover_ticks(log=print):
    if not STORE["db"]:
        return 0
    want = set()
    for row in store_rows("select * from cover where status='open'"):
        slots = json.loads(row["early"])
        if not slots:
            continue
        early = slots[0]["games"]
        res = fetch_results([x["ticker"] for g in early for x in g["sides"]])
        winners = [next((x for x in g["sides"] if res.get(x["ticker"]) == "yes"), None) for g in early]
        if any(w is None for w in winners):           # first checkpoint not settled, or a tie: nothing to carry yet
            continue
        for s in slots[1:]:
            for g in s["games"]:
                want.add(max(g["sides"], key=lambda x: x["p"])["ticker"])
    want = sorted(want)
    saved, now = 0, time.time()
    for i in range(0, len(want), 50):
        try:
            r = requests.get(f"{KALSHI}/markets", params={"tickers": ",".join(want[i:i + 50])}, timeout=15)
            r.raise_for_status()
            for m in r.json().get("markets", []):
                lp = 1.0 if m.get("result") == "yes" else 0.0 if m.get("result") == "no" else live_price(m)
                if lp is not None and 0.02 <= lp <= 0.98:
                    store_x("insert into ticks values(?,?,?,?,?)", (now, m.get("ticker"), lp, "sim", (m.get("status") or "")[:12]))
                    saved += 1
        except (requests.RequestException, ValueError):
            continue
    return saved


def cover_summary():
    rows = store_rows("select * from cover order by sunday desc limit 20") if STORE["db"] else []
    weeks = []
    for r in rows:
        x = {"sunday": r["sunday"], "status": r["status"]}
        if r["result"]:
            x.update(json.loads(r["result"]))
        elif r["status"] == "open":                   # waiting on the first checkpoint to settle
            try:
                slots = json.loads(r["early"]) or []
                early = slots[0]["games"] if slots else []
                x.update(cover_math(early, r["r_buy"], r["r_sell"]))
            except (ValueError, KeyError, IndexError, TypeError):
                pass
        weeks.append(x)
    done = [w for w in weeks if w["status"] == "done"]
    for w in done:                                    # tolerate old-schema rows that predate the multi-day result
        w.setdefault("sim_pl", w.get("pl", 0.0))
        w.setdefault("cost_both", w.get("cost", 0.0))
        w.setdefault("one_sided_pl", 0.0)
        w.setdefault("beat_cost", w.get("sim_pl", 0.0) > 0)
    return {"weeks": weeks, "n": len(done), "cost": round(sum(w.get("cost_both", w.get("cost", 0.0)) for w in done), 2),
            "sim_pl": round(sum(w.get("sim_pl", 0.0) for w in done), 2),
            "one_sided_pl": round(sum(w.get("one_sided_pl", 0.0) for w in done), 2),
            "beat": sum(1 for w in done if w.get("beat_cost")),
            "pl": round(sum(w.get("sim_pl", 0.0) for w in done), 2)}


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
            "min_pct": st["min_pct"], "recent": st["bets"][-8:],
            "same_game": {"n": sum(1 for b in done if b.get("same_game")),
                          "pl": round(sum(b.get("payout", 0) - b["stake"] for b in done if b.get("same_game")), 2),
                          "open": sum(1 for b in st["bets"] if b.get("same_game") and b["status"] == "open")}}


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


def book_levels(ob, side):
    """One side of a Kalshi order book as [(price in dollars, contracts)], lowest price first. Reads the dollar
    rows ('yes_dollars': [["0.45", "120.00"], ...]) or, failing that, the old whole-cent rows ('yes': [[45, 120]]).
    Rows it can't read, prices outside 0-1 dollars and empty sizes are skipped; never raises."""
    if not isinstance(ob, dict):
        return []
    rows, cents = ob.get(f"{side}_dollars"), False
    if not rows:
        rows, cents = ob.get(side), True
    out = []
    for row in rows if isinstance(rows, (list, tuple)) else ():
        try:
            p, q = float(row[0]), float(row[1])
            if cents and p >= 1:                  # old rows are whole cents (45); anything under 1 is already dollars
                p /= 100
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if 0 < p < 1 and 0 < q < float("inf"):
            out.append((p, q))
    return sorted(out)


def book_info(payload):
    """{'bid', 'ask', 'spread', 'ask_size', 'thin'} from a Kalshi order book answer, in dollars. Kalshi now sends
    {'orderbook_fp': {'yes_dollars': [...], 'no_dollars': [...]}} (dollar strings); it used to send
    {'orderbook': {'yes': [[cents, n]...], 'no': [...]}}. Both read the same. An empty or odd answer = no prices."""
    books = [(book_levels(ob, "yes"), book_levels(ob, "no"))
             for ob in ((payload.get(k) if isinstance(payload, dict) else None) for k in ("orderbook_fp", "orderbook"))]
    # the first key with both sides wins; else the first with either side
    yes, no = next((b for b in books if b[0] and b[1]), None) or next((b for b in books if b[0] or b[1]), ([], []))
    if not yes or not no:
        return {"bid": yes[-1][0] if yes else None, "ask": 1 - no[-1][0] if no else None,
                "spread": None, "ask_size": no[-1][1] if no else 0, "thin": True}
    bid, ask = yes[-1][0], 1 - no[-1][0]
    spread = round(ask - bid, 4)                  # rounded: 0.53 - 0.49 is 0.04000000000000001 in floats
    return {"bid": bid, "ask": ask, "spread": spread, "ask_size": no[-1][1],
            "thin": spread > 0.04 or no[-1][1] < 100}


def book_depth(ticker, max_age=60):
    """Kalshi's order book for one pick: {'bid', 'ask', 'spread', 'ask_size' (contracts at the best
    ask), 'thin'}. Thin = wide spread or little size, so the price isn't reliable. None if unknown."""
    now = time.time()
    got = BOOK_DEPTH.get(ticker)
    if got and now - got[0] < max_age:
        return got[1]
    try:
        r = requests.get(f"{KALSHI}/markets/{ticker}/orderbook", timeout=10)
        if not r.ok:
            return None                           # 429/5xx: unknown, not an empty book (and not cached)
        info = book_info(r.json())
    except (requests.RequestException, ValueError):
        return None
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


# ================================================================ history (the Mac keeps everything)
# One SQLite file next to the engine: every Kalshi quote, every live tick of your picks, every cash-out
# offer, and when you bought what. Only the Mac opens it (store_open); on the phone it stays off.
STORE = {"db": None, "path": None, "last": {}}
_SLOCK = threading.RLock()
_SCHEMA = """
create table if not exists cover(sunday text primary key, ts real, early text, late text, r_buy real, r_sell real,
  status text, result text);
create table if not exists ticks(ts real, ticker text, chance real, state text, score text);
create table if not exists pulse(ts real, worth real, staked real);
create index if not exists ticks_t on ticks(ticker, ts);
create table if not exists offers(ts real, combo text, p real, pays real, hold real, offer real, real_offer int, verdict text);
create index if not exists offers_c on offers(combo, ts);
create table if not exists quotes(ts real, source text, sport text, n int, legs text, stake real, pays real,
  fair real, kalshi real, pct real, hours real, outcome text, resolved real);
create index if not exists quotes_r on quotes(outcome, ts);
create table if not exists bets(combo text primary key, first_seen real, cost real, pays real, legs text,
  sports text, status text, back real, settled real, p_first real);
create table if not exists events(ts real, kind text, combo text, text text);
create table if not exists plays(ts real, ticker text, me int, opp int, detail text);
create table if not exists fairs(ts real, ticker text, fair real, price real);
create index if not exists fairs_t on fairs(ticker, ts);
create table if not exists maker(ts real, ticker text, pick text, mode text, price real, n int, fair real,
  status text, order_id text, filled real, outcome text, updated real, kick real, why text);
create table if not exists killer(ts real, kind text, legs text, picks text, mode text, status text, stake real,
  pays real, pct real, why text, outcome text);
create index if not exists plays_t on plays(ticker, ts);
create table if not exists suggestions(id text primary key, ts real, lg text, legs text, picks text, n int,
  pct real, pays real, stake real, fair real, kick real);
"""


def store_open(path=None):
    """Open (or create) the history file. Safe to call more than once."""
    import sqlite3
    with _SLOCK:
        if STORE["db"]:
            return STORE["db"]
        path = path or os.path.join(HERE, "combo_history.db")
        db = sqlite3.connect(path, timeout=10, check_same_thread=False, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("pragma journal_mode=wal")
        db.execute("pragma busy_timeout=8000")
        db.executescript(_SCHEMA)
        try:
            db.execute("alter table suggestions add column live int")   # added after the first release
        except Exception:
            pass
        for col in ("note text", "pfair real"):
            try:
                db.execute(f"alter table suggestions add column {col}")
            except Exception:
                pass
        STORE.update(db=db, path=path)
        return db


def store_x(sql, args=()):
    db = STORE["db"]
    if not db:
        return None
    with _SLOCK:
        try:
            return db.execute(sql, args)
        except Exception as err:                     # history is best-effort: never break a trade over it
            console_note(f"history: {type(err).__name__}: {err}")
            return None


def store_rows(sql, args=()):
    with _SLOCK:                                     # fetch under the lock too: threads share one connection, and
        cur = store_x(sql, args)                     # reading a cursor while another thread uses it can crash sqlite
        return [dict(r) for r in cur.fetchall()] if cur is not None else []


def _hours_to(legs):
    ts = [x for x in (_kick_ts(l) for l in legs) if x]
    return round((min(ts) - time.time()) / 3600, 2) if ts else None


def store_quote(c, stake, pays, pct, source=None):
    """Every combo quote Kalshi gives (yours, the shadow's), with what the market and the books said."""
    if not STORE["db"]:
        return
    k = stake / max(CTX.get("stake") or stake, 0.01)
    legs = [[l["ticker"], round(l.get("p") or 0, 4), round(l.get("fair") or 0, 4)] for l in c["legs"]]
    sports = sorted({ticker_sport(l["ticker"]) or "other" for l in c["legs"]})
    store_x("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours) values(?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), source or CTX.get("source") or "build", ",".join(sports), len(c["legs"]), json.dumps(legs),
             stake, round(pays, 2), round((c.get("fair") or 0) * k, 2), round((c.get("kalshi") or 0) * k, 2),
             round(pct, 4) if pct else None, _hours_to(c["legs"])))


def resolve_quotes(limit=200):
    """Mark old quotes won or lost once Kalshi settles their games (for the back-test and the predictor)."""
    rows = store_rows("select rowid, legs from quotes where outcome is null and ts < ? order by ts limit ?",
                      (time.time() - 3 * 3600, limit))
    if not rows:
        return 0
    legs = {r["rowid"]: [x[0] for x in json.loads(r["legs"])] for r in rows}
    res = fetch_results({t for v in legs.values() for t in v})
    n = 0
    for rid, ts in legs.items():
        rs = [res.get(t) for t in ts]
        out = "lost" if "no" in rs else "won" if all(r == "yes" for r in rs) else None
        if out:
            store_x("update quotes set outcome=?, resolved=? where rowid=?", (out, time.time(), rid))
            n += 1
    return n


def record_view(view):
    """Called each time the Mac refreshes Live: writes ticks and offers that changed, notes new bets and
    results, and returns the events worth pushing to open screens (scores, big swings, settled combos)."""
    if not STORE["db"] or not view:
        return []
    now, last, ev = time.time(), STORE["last"], []

    def _legs(t, legs):
        for lg in legs:
            if lg.get("res"):
                continue
            ch = lg["live"] if lg.get("live") is not None else lg.get("chance")
            key = ("tick", lg["ticker"])
            sc = lg.get("sc") or {}
            pts = (sc.get("me"), sc.get("opp")) if sc else None
            # a Kalshi-data score (display only) never changes how often prices are recorded: smart sell's tuning
            # replays these ticks, so they're sampled exactly as before
            sig = (round(ch or 0, 3), lg.get("state"), (lg.get("score") or "") if lg.get("src") != "kalshi" else "")
            prev = last.get(key)
            if not prev or prev[1] != sig and now - prev[0] > 4 or now - prev[0] > 300:
                last[key] = (now, sig)
                store_x("insert into ticks values(?,?,?,?,?)", (now, lg["ticker"], ch, lg.get("state"), lg.get("score")))
            # a score change, once per game (not per combo, not when only the clock moves)
            pkey = ("pts", lg["ticker"])
            if pts and pts[0] is not None and last.get(pkey) != pts:
                had = last.get(pkey)
                last[pkey] = pts
                hoops = lg.get("sport") in ("nba", "ncaamb", "ncaawb", "euroleague", "tennis")
                flip = had is not None and (pts[0] > pts[1]) != (had[0] > had[1]) and pts[0] != pts[1]
                if had is not None and hoops:            # baskets come every minute: only lead changes
                    if flip or now - last.get(("play", lg["ticker"]), 0) > 60:
                        last[("play", lg["ticker"])] = now
                        store_x("insert into plays values(?,?,?,?,?)", (now, lg["ticker"], pts[0], pts[1], sc.get("detail") or ""))
                    if flip:
                        ev.append({"kind": "score", "combo": t, "ticker": lg["ticker"], "good": pts[0] > pts[1],
                                   "text": f"Your {short_name(lg['name'])} {'take the lead' if pts[0] > pts[1] else 'fall behind'}"
                                           f" {pts[0]}–{pts[1]} vs {short_name(lg.get('opp') or sc.get('opp_abbr', ''))}"
                                           + (f" · {sc['detail']}" if sc.get("detail") else "")})
                elif had is not None:
                    store_x("insert into plays values(?,?,?,?,?)", (now, lg["ticker"], pts[0], pts[1], sc.get("detail") or ""))
                    mine = pts[0] - had[0] > 0
                    word = SPORT_SCORE_WORD.get(lg.get("sport"), "Score")
                    me_n, opp_n = short_name(lg["name"]), short_name(lg.get("opp") or sc.get("opp_abbr", ""))
                    lead = "lead" if pts[0] > pts[1] else "trail" if pts[0] < pts[1] else "tied"
                    ev.append({"kind": "score", "combo": t, "ticker": lg["ticker"], "good": mine,
                               "text": (f"{word} for your {me_n}! " if mine else f"{opp_n} {word.lower()} against your {me_n}. ")
                                       + (f"Tied {pts[0]}–{pts[1]}" if lead == "tied" else
                                          f"{'Up' if lead == 'lead' else 'Down'} {max(pts)}–{min(pts)}")
                                       + (f" · {sc['detail']}" if sc.get("detail") else "")})
                else:
                    store_x("insert into plays values(?,?,?,?,?)", (now, lg["ticker"], pts[0], pts[1], sc.get("detail") or ""))
            skey = ("swing", lg["ticker"])
            if ch is not None and lg.get("state") == "live":
                base = last.get(skey)
                if base is None:
                    last[skey] = ch
                elif abs(ch - base) >= 0.12:              # a real swing, once per game, not per combo
                    last[skey] = ch
                    ev.append({"kind": "swing", "combo": t, "ticker": lg["ticker"],
                               "text": f"{short_name(lg['name'])} {'up' if ch > base else 'down'} to {ch:.0%} to win"})

    for v in view.get("combos") or []:
        t = v["t"]
        if v["group"] == "pending":
            if ("bet", t) not in last:
                last[("bet", t)] = 1
                store_x("insert or ignore into bets(combo, first_seen, cost, pays, legs, sports, status, p_first) "
                        "values(?,?,?,?,?,?,?,?)", (t, now, v["cost"], v["pays"], json.dumps([l["ticker"] for l in v["legs"]]),
                                                    ",".join(v.get("sports") or []), "pending", v.get("p")))
            key = ("off", t)
            sig = (round(v.get("p") or 0, 3), round(v.get("offer") or 0), v.get("verdict"), bool(v.get("offer_real")))
            prev = last.get(key)
            if not prev or prev[1] != sig and now - prev[0] > 20 or now - prev[0] > 120:
                last[key] = (now, sig)
                store_x("insert into offers values(?,?,?,?,?,?,?,?)",
                        (now, t, v.get("p"), v.get("pays"), v.get("hold_value"), v.get("offer"),
                         int(bool(v.get("offer_real"))), v.get("verdict")))
                if prev and prev[1][2] != sig[2] and sig[2] in ("sell", "half"):
                    ev.append({"kind": "advice", "combo": t, "text": f"{v['label']}: time to {'cash out' if sig[2] == 'sell' else 'cash out half'}"})
            _legs(t, v["legs"])
        elif ("done", t) not in last:
            last[("done", t)] = 1
            cur = store_rows("select status from bets where combo=?", (t,))
            if cur and cur[0]["status"] == "pending":
                store_x("update bets set status=?, back=?, settled=? where combo=?",
                        (v["group"], v.get("back") if v["group"] == "cashed" else v["pays"] if v["group"] == "won" else 0,
                         now, t))
                ev.append({"kind": "settled", "combo": t, "text": f"{v['label']} {v['group']}"})
    try:                                             # the day's value line for the top of Live
        pend = [v for v in view.get("combos") or [] if v.get("group") == "pending"]
        open_s = [x for x in view.get("singles") or [] if x.get("state") in ("live", "pre")]
        worth = sum(v.get("offer") or 0 for v in pend) + sum(x.get("worth") or 0 for x in open_s)
        staked = sum(v.get("cost") or 0 for v in pend) + sum(x.get("cost") or 0 for x in open_s)
        if (pend or open_s) and now - last.get(("pulse",), 0) >= 120:
            last[("pulse",)] = now
            store_x("create table if not exists pulse(ts real, worth real, staked real)")
            store_x("insert into pulse values(?,?,?)", (now, round(worth, 2), round(staked, 2)))
    except Exception:
        pass
    for x in view.get("singles") or []:             # single bets and spreads: their game's story too
        if x.get("state") in ("live", "pre") and x.get("ticker"):
            _legs(x["t"], [x])
    for e in ev:
        store_x("insert into events values(?,?,?,?)", (now, e["kind"], e.get("combo"), e["text"]))
    if len(last) > 20000:
        STORE["last"] = {k: v for k, v in list(last.items())[-10000:]}
    return ev


SPORT_SCORE_WORD = {"nhl": "Goal", "ahl": "Goal", "soccer": "Goal", "nfl": "Score", "ncaaf": "Score"}


def short_name(name):
    w = (name or "").split()
    return w[-1] if len(w) > 1 and len(name) > 12 else name


def pulse_series(hours=16, points=150):
    """What your open bets were worth through the day (every 2 minutes), thinned to ~150 points."""
    if not STORE["db"]:
        return []
    store_x("create table if not exists pulse(ts real, worth real, staked real)")
    rows = store_rows("select ts, worth, staked from pulse where ts > ? order by ts", (time.time() - hours * 3600,))
    step = max(1, len(rows) // points)
    out = [[round(r["ts"]), r["worth"], r["staked"]] for r in rows[::step]]
    if rows and (not out or out[-1][0] != round(rows[-1]["ts"])):
        out.append([round(rows[-1]["ts"]), rows[-1]["worth"], rows[-1]["staked"]])
    return out


def game_story(ticker, hours=8):
    """One game's live story for the game screen: its win chance over time and every score change."""
    return {"ticks": store_rows("select ts, chance, state, score from ticks where ticker=? and ts > ? order by ts",
                                (ticker, time.time() - hours * 3600))[-500:],
            "plays": store_rows("select ts, me, opp, detail from plays where ticker=? and ts > ? order by ts",
                                (ticker, time.time() - hours * 3600))}


def store_trim(days=120):
    """Keep the file a sensible size: ticks for 30 days, everything else for `days`."""
    cut = time.time() - days * 86400
    store_x("delete from ticks where ts < ?", (time.time() - 30 * 86400,))
    try:
        store_x("delete from pulse where ts < ?", (time.time() - 30 * 86400,))
    except Exception:
        pass
    store_x("delete from offers where ts < ?", (cut,))
    store_x("delete from events where ts < ?", (cut,))


# ---- the quote predictor: what share of fair Kalshi will pay, before asking
def _hbucket(h):
    return "?" if h is None else "<2h" if h < 2 else "2-8h" if h < 8 else "8h+"


def _nbucket(n):
    return str(n) if n <= 4 else "5-6" if n <= 6 else "7+"


def quote_model(days=60):
    """Learn Kalshi's combo pricing from every recorded quote: quote ÷ Kalshi's own single-game prices,
    by number of picks, time to game and sport, each pulled toward the overall typical value when it has
    few quotes (so one odd quote can't swing it). Also how far quotes scatter around that."""
    rows = store_rows("select n, hours, sport, pays, kalshi, pct, fair from quotes where ts > ? and kalshi > 0 and pays > 0",
                      (time.time() - days * 86400,))
    if len(rows) < 5:
        return None
    r_all = [math.log(r["pays"] / r["kalshi"]) for r in rows]
    mu = statistics.mean(r_all)
    sd = statistics.pstdev(r_all) if len(r_all) > 2 else 0.1
    groups = {}
    for r, x in zip(rows, r_all):
        for key in (("n", _nbucket(r["n"])), ("h", _hbucket(r["hours"])), ("s", r["sport"] or "?")):
            groups.setdefault(key, []).append(x)
    k0 = 6.0                                             # quotes it takes to trust a group halfway
    eff = {k: (sum(v) + k0 * mu) / (len(v) + k0) - mu for k, v in groups.items()}
    resid = []
    for r, x in zip(rows, r_all):
        pred = mu + sum(eff.get(k, 0) for k in (("n", _nbucket(r["n"])), ("h", _hbucket(r["hours"])), ("s", r["sport"] or "?")))
        resid.append(x - pred)
    # honest spread: never under 8%, and wider while there are few quotes to learn from
    sd_r = max(statistics.pstdev(resid) if len(resid) > 2 else sd, 0.08) * math.sqrt(1 + 12 / len(rows))
    return {"mu": mu, "eff": {f"{a}:{b}": round(v, 4) for (a, b), v in eff.items()}, "sd": sd_r, "n": len(rows),
            "at": time.time()}


QMODEL = {"m": None, "at": 0}


def predict_quote(c, model=None):
    """{'pct': expected share of fair, 'p_clear': chance it clears your cut-off, 'n': quotes learned from}
    for a suggested combo, or None until enough quotes are recorded."""
    m = model or QMODEL["m"]
    if (m is None or time.time() - QMODEL["at"] > 600) and STORE["db"] and model is None:
        QMODEL.update(m=quote_model(), at=time.time())
        m = QMODEL["m"]
    if not m or not c.get("kalshi") or not c.get("fair"):
        return None
    n = len(c["legs"])
    sport = ",".join(sorted({ticker_sport(l["ticker"]) or "other" for l in c["legs"]}))
    e = m["eff"]
    lr = m["mu"] + e.get(f"n:{_nbucket(n)}", 0) + e.get(f"h:{_hbucket(_hours_to(c['legs']))}", 0) + e.get(f"s:{sport}", 0)
    base = c["kalshi"] / c["fair"]
    pct = base * math.exp(lr)
    cut = CFG["accept_pct"] / 100
    z = (math.log(cut / base) - lr) / m["sd"]
    p_clear = min(0.95, max(0.05, 0.5 * math.erfc(z / math.sqrt(2))))   # a model is never certain
    return {"pct": round(pct, 4), "p_clear": round(p_clear, 3), "n": m["n"]}


# ---- sizing across combos: don't pile more on a team you already need
def exposure_factor(legs):
    """1.0 when the picks are new to you; down to 0.5 when you already need one of them in combos
    that pay a big share of everything riding."""
    hold = MINE.get("hold") or {}
    total = sum(h.get("pays", 0) for h in hold.values())
    if not total:
        return 1.0, None
    worst, name = 0.0, None
    for l in legs:
        on = sum(h["pays"] for h in hold.values() if any(k[1] == l["ticker"] for k, _ in h.get("need") or []))
        if on / total > worst:
            worst, name = on / total, l.get("pick") or l["ticker"]
    return round(max(0.5, 1 - worst * 0.6), 2), (name if worst >= 0.25 else None)


# ---- back-test: what each fair-price cut-off would have earned on the quotes Kalshi actually gave
def backtest(days=120):
    rows = store_rows("select pct, pays, stake, outcome from quotes where outcome is not null and pct is not null and ts > ?",
                      (time.time() - days * 86400,))
    out = []
    for cut in range(70, 121, 5):
        take = [r for r in rows if r["pct"] * 100 >= cut]
        staked = sum(r["stake"] for r in take)
        back = sum(r["pays"] for r in take if r["outcome"] == "won")
        out.append({"cut": cut, "n": len(take), "staked": round(staked, 2), "pl": round(back - staked, 2),
                    "roi": round((back - staked) / staked, 4) if staked else None})
    return {"rows": out, "quotes": len(rows)}


def combo_history(t):
    """A live combo's story for the detail screen: its value over time and each pick's chance over time."""
    offers = store_rows("select ts, p, hold, offer, real_offer, verdict from offers where combo=? order by ts", (t,))
    legs = store_rows("select legs from bets where combo=?", (t,))
    ticks = {}
    if legs:
        for tk in json.loads(legs[0]["legs"]):
            ticks[tk] = store_rows("select ts, chance, state, score from ticks where ticker=? and ts > ? order by ts",
                                   (tk, time.time() - 3 * 86400))
    return {"offers": offers[-600:], "ticks": {k: v[-400:] for k, v in ticks.items()}}


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
