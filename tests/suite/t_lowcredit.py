# CHECK: group=engine
# Low-credit mode and buying: while odds credits are low, panel bets and Buy ideas with a game-winner pick more than
# 4 hours away that only has free lines (no odds-service line) are LEFT OUT. Remove-only: nothing added, no stake or
# order changed; normal mode is unchanged; spreads/totals and live picks are untouched; errors keep the bet.
# Also: build_panel's stats recompute falls back to the ungated panel if it fails. Everything is faked.
import os, time, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db"))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def leg(t, ev, kick, sharp=False, live=False):
    E.KICKOFF[ev] = E.dt.datetime.fromtimestamp(kick, E.dt.timezone.utc).isoformat()
    return {"ticker": t, "event": ev, "pick": t, "p": 0.5, "fair": 0.55, "sharp_line": sharp, "live": live}


def bet(i, legs, stake=5.0):
    kicks = [E._kick_ts(x) for x in legs]
    return {"id": f"b{i}", "kind": "combo" if len(legs) > 1 else "single", "code": "nba", "legs": legs,
            "stake": stake, "kick": min(kicks), "last": max(kicks)}


def sec_a():
    near = leg("KXNBAGAME-26NOV21AAABBB-AAA", "KXNBAGAME-26NOV21AAABBB", NOW + 3600)
    far_free = leg("KXNBAGAME-26NOV23CCCDDD-CCC", "KXNBAGAME-26NOV23CCCDDD", NOW + 2 * 86400)
    far_sharp = leg("KXNBAGAME-26NOV23EEEFFF-EEE", "KXNBAGAME-26NOV23EEEFFF", NOW + 2 * 86400, sharp=True)
    far_spread = leg("KXNBASPREAD-26NOV23GGGHHH-GGG5", "KXNBASPREAD-26NOV23GGGHHH", NOW + 2 * 86400)
    E.KICKOFF["KXNBAGAME-26NOV23GGGHHH"] = E.KICKOFF["KXNBASPREAD-26NOV23GGGHHH"]
    far_live = leg("KXNBAGAME-26NOV23IIIJJJ-III", "KXNBAGAME-26NOV23IIIJJJ", NOW + 2 * 86400, live=True)
    items = [bet(1, [near]), bet(2, [far_free], 7), bet(3, [far_sharp]), bet(4, [near, far_free]),
             bet(5, [far_spread]), bet(6, [far_live]), bet(7, [near, far_sharp], 9)]
    snap = [dict(c, legs=[dict(x) for x in c["legs"]]) for c in items]
    kept, dropped = E.low_credit_filter(items, NOW, saving=False)
    ok("A: normal mode: every bet kept, same objects, same order", kept == items and not dropped
       and all(a is b for a, b in zip(kept, items)))
    kept, dropped = E.low_credit_filter(items, NOW, saving=True)
    ok("A: low mode drops only the far free-lines-only picks (single and the combo holding one)",
       [c["id"] for c in kept] == ["b1", "b3", "b5", "b6", "b7"] and sorted(x["id"] for x in dropped) == ["b2", "b4"])
    ok("A: remove-only: kept bets are the same dicts, order and stakes, nothing new",
       all(c is next(x for x in items if x["id"] == c["id"]) for c in kept) and
       [c["stake"] for c in kept] == [5.0, 5.0, 5.0, 5.0, 9])
    ok("A: inputs not modified", items == snap)
    ok("A: dropped carry a plain reason, their stake and games (the extras budget keeps them)",
       all(x["why"] == E.LOW_CREDIT_WHY and x["credits"] and x["events"] for x in dropped)
       and next(x for x in dropped if x["id"] == "b2")["stake"] == 7)
    unknown = {"ticker": "KXNBAGAME-26NOV30ZZZYYY-ZZZ", "event": "KXNBAGAME-26NOV30ZZZYYY", "pick": "Z"}
    kept, dropped = E.low_credit_filter([{"id": "u", "legs": [unknown]}], NOW, saving=True)
    ok("A: low mode, unknown start and no sharp line: left out (fails closed)", not kept and len(dropped) == 1)
    real = E._free_only_far
    E._free_only_far = lambda *a, **k: 1 / 0
    try:
        kept, dropped = E.low_credit_filter(items, NOW, saving=True)
    finally:
        E._free_only_far = real
    ok("A: an error checking a bet keeps it (today's rules)", kept == items and not dropped)
    real_s = E.odds_saving
    E.odds_saving = lambda now=None: 1 / 0
    try:
        kept, dropped = E.low_credit_filter(items, NOW)
    finally:
        E.odds_saving = real_s
    ok("A: credits unreadable: everything kept", kept == items and not dropped)


def sec_b():
    def idea(i, info, kick=None):
        return {"idea_id": f"i{i}", "picks": f"pick {i}", "legs_info": info, "kick": kick}
    ideas = [idea(1, [{"kind": "win", "kick": NOW + 3600, "sharp": False}]),
             idea(2, [{"kind": "win", "kick": NOW + 86400, "sharp": False}]),
             idea(3, [{"kind": "win", "kick": NOW + 86400, "sharp": True}]),
             idea(4, [{"kind": "spread", "kick": NOW + 86400}]),
             idea(5, [{"kind": "win", "kick": NOW + 86400}]),                          # an older idea: no record
             idea(6, [{"kind": "win", "kick": NOW - 600, "live": True}])]
    kept, dropped = E.low_credit_ideas(ideas, NOW, saving=False)
    ok("B: ideas, normal mode: all kept", kept == ideas and not dropped)
    kept, dropped = E.low_credit_ideas(ideas, NOW, saving=True)
    ok("B: ideas, low mode: far free-only (and unrecorded) win picks go, the rest stay in order",
       [r["idea_id"] for r in kept] == ["i1", "i3", "i4", "i6"] and [x["id"] for x in dropped] == ["i2", "i5"]
       and all(x["credits"] for x in dropped))


def sec_c():
    ok("C: attach_fair marks a side priced on the odds service's line",
       "s[\"sharp_line\"] = bool(g and g.get(\"sharp\"))" in open("wahome/engine.py").read())
    ok("C: sharp_snapshot tags its games sharp", "sharp=True) for g in gs]" in open("wahome/engine.py").read())
    ok("C: the idea leg facts carry it", E.idea_legs_info([{"ticker": "KXNBAGAME-26NOV21AAABBB-AAA", "pick": "A",
                                                            "sharp_line": True}])[0]["sharp"] is True)


def sec_d():
    near = leg("KXNBAGAME-26NOV21KKKLLL-KKK", "KXNBAGAME-26NOV21KKKLLL", NOW + 3600)
    far = leg("KXNBAGAME-26NOV24MMMNNN-MMM", "KXNBAGAME-26NOV24MMMNNN", NOW + 3 * 86400)
    a, b = bet(1, [near]), bet(2, [far])
    E.choose_panel = lambda today, budget, base, size=6: ([dict(a), dict(b)], {"p_ahead": 0.6, "ev": 1.0, "stake": 10})
    E.PANEL_POOL.clear()
    E.PANEL_POOL["nba"] = (NOW, [dict(a, ret=0.2), dict(b, ret=0.2)])
    E._qualifies = lambda c: True
    E.odds_saving = lambda now=None: (True, {})
    E.smart_buy_on = lambda: False
    real_sim = E._sim_panel
    E._sim_panel = lambda items, **k: [1.0, -0.5, 2.0]
    try:
        p = E.build_panel(codes=["nba"], budget=50, now=NOW)
        ok("D: build_panel in low mode leaves the far free-lines bet out, keeps the near one",
           [c["id"] for c in p["items"]] == ["b1"] and [x["id"] for x in p.get("sb_skipped", [])] == ["b2"])
        E._sim_panel = lambda items, **k: 1 / 0
        p = E.build_panel(codes=["nba"], budget=50, now=NOW)
        E._sim_panel = lambda items, **k: [1.0, -0.5, 2.0]
        ok("D: stats recompute fails: the skips stand (nothing put back), the old numbers marked stale",
           [c["id"] for c in p["items"]] == ["b1"] and [x["id"] for x in p.get("sb_skipped", [])] == ["b2"]
           and p["stats"].get("stale") is True)
        E.odds_saving = lambda now=None: (False, {})
        p = E.build_panel(codes=["nba"], budget=50, now=NOW)
        ok("D: normal mode: the panel as choose_panel picked it", sorted(c["id"] for c in p["items"]) == ["b1", "b2"]
           and not p.get("sb_skipped"))
    except Exception:
        print("FAIL D raised: " + traceback.format_exc().strip().splitlines()[-1])
    finally:
        E._sim_panel = real_sim


for name, fn in (("A", sec_a), ("B", sec_b), ("C", sec_c), ("D", sec_d)):
    section(name, fn)
