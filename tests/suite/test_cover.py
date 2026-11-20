import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

# Two finished weeks: one where smart sell beat the doubled cost, one where it did not, plus the aggregate.
COVER = {"n": 2, "cost": 60.0, "sim_pl": 6.0, "one_sided_pl": -3.0, "beat": 1, "pl": 6.0, "weeks": [
    {"sunday": "2026-11-16", "status": "done", "k": 3, "cost": 40.0, "cost_both": 40.0,
     "survivor": ["KC", "DAL", "PHI"], "survivor_pays": 120.0, "sim_pl": 14.0, "one_sided_pl": 9.0, "beat_cost": True,
     "one_sided_cost": 5.0, "one_sided_result": 14.0, "checkpoints": [
        {"label": "Sunday", "slot_key": 100, "worth": 52.0, "replay_exit": {"exit": 54.0, "pl": 49.0, "why": "smart"}, "settled": True},
        {"label": "Monday", "slot_key": 101, "worth": 48.0, "replay_exit": None, "settled": True}]},
    {"sunday": "2026-11-09", "status": "done", "k": 2, "cost": 20.0, "cost_both": 20.0,
     "survivor": ["BUF", "SF"], "survivor_pays": 30.0, "sim_pl": -8.0, "one_sided_pl": -5.0, "beat_cost": False,
     "one_sided_cost": 5.0, "one_sided_result": 0.0, "checkpoints": [
        {"label": "Sunday", "slot_key": 50, "worth": 12.0, "replay_exit": {"exit": 12.0, "pl": 7.0, "why": "smart"}, "settled": True}]}]}
RES = {"balance": 100.0, "settled": 0, "won": 0, "cashed": 0, "staked": 0, "returned": 0, "pl": 0.0, "roi": None,
       "best": 0, "weeks": [], "history": [], "shadow": None, "accuracy": None, "accuracy_text": "",
       "edge": {}, "backtest": None, "model": None, "by_tier": {}, "proof": None, "killer": None,
       "cover": COVER, "panel": None}

with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app/api/results", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RES)))
    pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"at": 0})))
    pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('results')"); time.sleep(6)

    card = pg.locator(".card", has_text="Cover the early games")
    print("cover card:", card.count())
    if card.count() != 1:
        print("PROBLEMS: cover card missing from Results")
    t = card.inner_text() if card.count() else ""
    # both weeks render, with survivors and the covering-both-sides cost
    if "2026-11-16" not in t or "2026-11-09" not in t:
        print("PROBLEMS: both weeks don't render:", t[:300])
    if "KC + DAL + PHI" not in t or "BUF + SF" not in t:
        print("PROBLEMS: survivors not shown:", t[:300])
    # per-checkpoint worth and the replay exit
    if "Sunday" not in t or "Monday" not in t or "sold" not in t:
        print("PROBLEMS: per-checkpoint detail / replay exit missing:", t[:400])
    # the beat-cost flag, both true and false
    if "beat the doubled cost" not in t or "did not beat the doubled cost" not in t:
        print("PROBLEMS: beat-cost flag not shown for both weeks:", t[:400])
    # the one-sided baseline
    if "One-sided combo on the same early games" not in t:
        print("PROBLEMS: one-sided baseline missing:", t[:400])
    # the aggregate line (sim_pl, one-sided, beat count)
    if "over 2 weeks" not in t or "beat the cost 1/2" not in t or "one-sided" not in t:
        print("PROBLEMS: aggregate line missing:", t[:400])

    # the card must live in edgeBlock (next to the paper gate), NOT inside anBlock ("What's working")
    in_an = pg.evaluate("""() => {
        const an = document.querySelector('.an');
        const cov = [...document.querySelectorAll('.card h3')].find(h => h.textContent.includes('Cover the early games'));
        if (!cov) return 'missing';
        return an && an.contains(cov) ? 'inside-an' : 'outside-an';
    }""")
    print("cover card placement:", in_an)
    if in_an != "outside-an":
        print("PROBLEMS: cover card is not in edgeBlock (it must stay out of 'What's working'/anBlock):", in_an)

    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
        print("PROBLEMS: Results scrolls sideways on a phone with the cover card")
    print("errs:", errs)
