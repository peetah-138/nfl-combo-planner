# CHECK: group=engine
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))  # midday "Pacific" whenever it runs, so the fake games (2.5 h out) are in today's panel day
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp(); E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "flag"); E.HELD_FILE = os.path.join(E.HERE, "held.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.fetch_account = lambda **k: ([], 300.0, None)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


def mk(t, ev, f, p, k):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", "nhl", [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


# a draft built earlier; then time passes and one game starts
E.PANEL_POOL = {"nhl": (now, [mk("H1", "KXNHLGAME-1", .62, .52, now + 3600), mk("H2", "KXNHLGAME-2", .6, .5, now + 9000)])}
E.panel_pass()
d = E.panel_get("real"); ok("draft built", d and len(d["items"]) == 2)
body = dict(d); [c.update(kick=now - 600) for c in body["items"] if "H1" in c["id"]]
E.store_x("update panel set body=? where mode='real'", (json.dumps(body),))
okA, msg = E.panel_approve(None, "all")
p = E.panel_get("real"); st = {c["id"][:9]: c["state"] for c in p["items"]}
h1 = next(c for c in p["items"] if "H1" in c["id"]); h2 = next(c for c in p["items"] if "H2" in c["id"])
ok("approving never schedules a pre-game-priced bet whose game already started", h1["state"] == "skipped" and "started" in h1.get("note", "") and h2["state"] == "scheduled")

# all started: nothing approved, and the Mac is asked for a fresh panel
E.store_x("delete from panel")
E.PANEL_POOL = {"nhl": (now, [mk("H3", "KXNHLGAME-3", .62, .52, now + 3600)])}
E.panel_pass(); d = E.panel_get("real"); body = dict(d); [c.update(kick=now - 600) for c in body["items"]]
E.store_x("update panel set body=? where mode='real'", (json.dumps(body),))
okA, msg = E.panel_approve(None, "all")
ok("all games started: not approved, you're told why", not okA and "already started" in msg and (E.panel_get("real") or {}).get("status") != "approved")
ok("...and a fresh panel is asked for", os.path.exists(E.REBUILD_FLAG))
ok("the dead draft is cleared off the screen", E.panel_get("real") is None)

# a scheduled bet whose game started is marked skipped even while paused, so no stale buy time
E.store_x("delete from panel")
E.PANEL_POOL = {"nhl": (now, [mk("H4", "KXNHLGAME-4", .62, .52, now + 3600)])}
E.panel_pass(); E.panel_approve(None, "all")
p = E.panel_get("real"); [c.update(kick=now - 60, buy_at=now - 3000) for c in p["items"]]
E.store_x("update panel set body=? where mode='real'", (json.dumps(p),))
E.panel_exec(paused=True)
ok("a pre-game-priced bet whose game started is skipped even when paused", E.panel_get("real")["items"][0]["state"] == "skipped")

# a skipped spread comes back as a New-since-you-approved bet when it's good again, and can be added
E.store_x("delete from panel")
E.PANEL_POOL = {"nhl": (now, [mk("H5", "KXNHLGAME-5", .62, .52, now + 9000), mk("H6", "KXNHLGAME-6", .6, .5, now + 9000)])}
E.panel_pass(); E.panel_approve(None, "all")
p = E.panel_get("real"); h5 = next(c for c in p["items"] if "H5" in c["id"])
E._set_items(E._panel_day(), "real", {h5["id"]: {"state": "skipped", "note": "no longer priced well enough"}})
E.panel_pass()
x = E.panel_get("extra")
ok("a skipped bet that's good again shows up as new", x and any(c["id"] == h5["id"] for c in x["items"]))
okA, msg = E.panel_add([h5["id"]], "extra")
p = E.panel_get("real"); same = [c for c in p["items"] if c["id"] == h5["id"]]
ok("adding it replaces the skipped entry", okA and len(same) == 1 and same[0]["state"] == "scheduled")
ok("a bet already scheduled isn't offered again", not any(c["id"] == h5["id"] for c in (E.panel_pass() and E.panel_get("extra") or E.panel_get("extra"))["items"]))

# drafts for each sport lose started games
E.store_x("delete from panel")
E.PANEL_POOL = {"nhl": (now, [mk("H7", "KXNHLGAME-7", .62, .52, now + 3600)])}
E.panel_pass(); v = E.panel_get("view:nhl"); [c.update(kick=now - 60) for c in v["items"]]
E.store_x("update panel set body=? where mode='view:nhl'", (json.dumps(v),))
E.PANEL_POOL = {}
E.prune_drafts()
ok("sport drafts drop pre-game-priced bets on started games", E.panel_get("view:nhl") is None)

# Pete's call: a game under way may be in the panel, but only priced live on a fresh score (see t_live_panel.py)
E.save_json(E.MAIN_SAVED, {"panel_live": True})
E.comeback_judge = (lambda c, now=None, sim=None: (lambda o: {"ok": o, "old": o, "new": o, "pregame": True,   # (#348)
                    "why": None if o else E.IN_PLAY_WHY})(E.smart_buy_ok(sim if sim is not None else E._sb_sim(c, now))))
# ^ today's gate only: this checks the draft rules; the comeback model (fresh score, features) is t_comeback's
E.store_x("delete from panel")
lv = mk("H8", "KXNHLGAME-8", .62, .52, now - 600)
lv.update(live=True, kick_pre=None)
lv["legs"][0]["live"] = True
E.PANEL_POOL = {"nhl": (now, [lv])}
E.panel_pass()
ok("a live-priced bet on a game under way stays in the draft", any(c["id"] == lv["id"] for c in (E.panel_get("view:nhl") or {}).get("items", [])))
okA, msg = E.panel_approve(None, "all")
ok("...and approving schedules it", okA and E.panel_get("real")["items"][0]["state"] == "scheduled")
