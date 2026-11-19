import os, importlib.util, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
t = "KXAHLGAME-26NOV191900HERCHA-HER"
ok("AHL is a league of its own with sportsbook odds", "ahl" in E.LEAGUES and E.LEAGUES["ahl"]["odds"] == "icehockey_ahl" and E.LEAGUES["ahl"]["require_line"])
ok("AHL tickers read as AHL, not NHL", E.ticker_sport(t) == "ahl" and E.ticker_sport("KXNHLGAME-26NOV18SJSVGK-SJS") == "nhl")
ok("the game date reads right even with a start time in the code", E.ticker_day(t) == dt.date(2026, 11, 19) and E.game_date({"event_ticker": "KXAHLGAME-26NOV191900HERCHA"}) == dt.date(2026, 11, 19))
ok("a daily league", E.week_of(t) == dt.date(2026, 11, 19))
ok("hockey shapes: goals, swing, game spread", E.SCORE_UNIT["ahl"] == (1, "goal") and E.SWING["ahl"] >= E.SWING["nhl"] and "ahl" in E.GAME_SD)
E.set_league("ahl"); ok("switches to AHL", E.LEAGUE["code"] == "ahl" and E.LG()["series"] == "KXAHLGAME")
