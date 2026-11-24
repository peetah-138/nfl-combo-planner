# CHECK: group=engine
# Every bet says what it is on (issue #381): a CBB total used to read just "Over 144.5 points" with no teams. The label
# helper turns a total, a spread, a moneyline and each leg of a combo into plain English with the game's matchup, and
# says "game not found" (never nothing) when it can't name the teams. Display only: nothing about prices or buying moves.
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

TOT = "KXNCAAMBTOTAL-26NOV23DUKEUNC-144"
SPR = "KXNCAAMBSPREAD-26NOV23DUKEUNC-DUKE7"
WIN = "KXNCAAMBGAME-26NOV23DUKEUNC-DUKE"
E.PICK_NAME.update({"KXNCAAMBGAME-26NOV23DUKEUNC-DUKE": "Duke", "KXNCAAMBGAME-26NOV23DUKEUNC-UNC": "UNC"})

# ---- a total: the number, "total points", and the game
d = E.bet_describe(TOT, "yes", "Over 144.5 points", "Over 144.5 points", "ncaamb")
ok("total yes: 'Over 144.5 total points'", d["plain"] == "Over 144.5 total points")
ok("total names the matchup from the ticker + known names", d["matchup"] == "Duke vs UNC" and d["found"])
ok("total names the league", d["league"] != "")
ok("total no-side flips to Under", E.bet_describe(TOT, "no", "Over 144.5 points", "", "ncaamb")["plain"] == "Under 144.5 total points")
ok("total 'Not: Over' reads Under", E.bet_describe(TOT, "no", "Not: Over 144.5 points", "", "ncaamb")["plain"] == "Under 144.5 total points")

# ---- a spread: the team on the bet, the line, what has to happen
d = E.bet_describe(SPR, "yes", "Duke wins by over 6.5 points", "", "ncaamb")
ok("spread yes: 'Duke -6.5 (wins by 7+)'", d["plain"] == "Duke -6.5 (wins by 7+)")
d = E.bet_describe(SPR, "no", "Duke wins by over 6.5 points", "", "ncaamb")
ok("spread no: the other team, plus the line", d["plain"] == "UNC +6.5 (loses by 6 or fewer, or wins)")
ok("spread no without a known opponent still says what it is", E.bet_describe("KXNCAAMBSPREAD-26NOV23ABCXYZ-ABC7", "no", "Abc wins by over 6.5", "", "ncaamb")["plain"].startswith("Not Abc -6.5"))

# ---- a moneyline
ok("moneyline yes: 'Duke to win'", E.bet_describe(WIN, "yes", "Duke", "", "ncaamb")["plain"] == "Duke to win")
ok("moneyline no: the other team", E.bet_describe(WIN, "no", "Duke", "", "ncaamb")["plain"] == "UNC to win")
ok("moneyline 'X to win' label is not doubled", E.bet_describe(WIN, "yes", "Duke to win", "", "ncaamb")["plain"] == "Duke to win")

# ---- the matchup from the title, when the title has it
d = E.bet_describe("KXNBATOTAL-26NOV23LALBOS-220", "yes", "Over 220.5 points", "Lakers at Celtics: Total Points", "nba")
ok("title 'A at B' gives the matchup", d["matchup"] == "Lakers vs Celtics" and d["found"] and d["plain"] == "Over 220.5 total points")

# ---- combo legs: spread and total legs carry the same wording; a flipped win leg is not flipped twice
legs = [{"ticker": TOT, "name": "Over 144.5 points", "side": "yes", "sport": "ncaamb", "opp": ""},
        {"ticker": SPR, "name": "Not: Duke wins by over 6.5 points", "side": "no", "sport": "ncaamb", "opp": ""},
        {"ticker": WIN, "name": "UNC", "side": "no", "sport": "ncaamb", "opp": "Duke"}]
E.label_bets([], [{"legs": legs}])
ok("combo total leg", legs[0]["plain"] == "Over 144.5 total points" and legs[0]["matchup"] == "Duke vs UNC")
ok("combo spread leg (Not:)", legs[1]["plain"] == "UNC +6.5 (loses by 6 or fewer, or wins)")
ok("combo 'no' win leg already names the team it needs", legs[2]["plain"] == "UNC to win")

# ---- not found: ticker-derived best effort, found False, never blank
E.PICK_NAME.clear()
d = E.bet_describe("KXNCAAMBTOTAL-26NOV23ZZZYYY-150", "yes", "Over 150.5 points", "Over 150.5 points", "ncaamb")
ok("unresolved game: best effort matchup, found False", d["matchup"] and not d["found"] and d["plain"] == "Over 150.5 total points")
d = E.bet_describe("WEIRD", "yes", "", "", None)
ok("garbage ticker never raises and is not blank", d["plain"] and d["found"] is False)
singles = [{"t": "KXNCAAMBTOTAL-26NOV23ZZZYYY-150", "side": "yes", "label": "Over 150.5 points", "game": "", "sport": "ncaamb", "opp": ""}]
E.label_bets(singles, [])
ok("single gets plain/matchup/league/found", all(k in singles[0] for k in ("plain", "matchup", "league", "found")) and singles[0]["found"] is False)
ok("label_bets leaves money and buttons alone", singles[0]["side"] == "yes" and "cost" not in singles[0])

# ---- a total with no names of its own borrows them from a spread on the same game
tot = {"t": TOT, "side": "yes", "label": "Over 144.5 points", "game": "Over 144.5 points", "sport": "ncaamb", "opp": ""}
spr = {"t": SPR, "side": "yes", "label": "Duke wins by over 6.5 points", "game": "", "sport": "ncaamb", "opp": "UNC"}
E.PICK_NAME.clear()
E.label_bets([tot, spr], [])
ok("a total borrows team names from the spread on the same game", tot["matchup"] == "Duke vs UNC" and tot["found"])
d = E.bet_describe("KXNBAGAME-26NOV23DENLAL-DEN", "yes", "Denver Nuggets to win", "Denver at Los Angeles Winner?", "nba")
ok("a title's names are not cut to their last word ('Los Angeles', not 'Angeles')", d["matchup"] == "Denver vs Los Angeles")
d = E.bet_describe("KXNBAGAME-26NOV23DENLAL-DEN", "no", "Against Denver", "", "nba", flipped=True)
ok("a combo 'Against Denver' leg stays 'Against Denver' (never turned into 'Denver to win')", d["plain"] == "Against Denver")
d = E.bet_describe("KXEPLGAME-26NOV23ARSCHE-ARS", "no", "Arsenal doesn't win", "", "soccer", flipped=True)
ok("a 3-way \"doesn't win\" leg keeps its words", d["plain"] == "Arsenal doesn't win")
d = E.bet_describe("KXNCAAMBTOTAL-26NOV23DUKEUNC-144", "yes", "Over 144. points", "", "ncaamb")
ok("a stray trailing dot in a line cannot break the label", "Over 144" in d["plain"])
