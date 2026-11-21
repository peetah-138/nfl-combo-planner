# The check list's test names and how they are split up. run_checks.sh reads this; so does CI (one job per shard).
#   python checklist.py engine                -> every engine test (t_*.py)
#   python checklist.py page [i/N]            -> the page tests (test_*.py), or only shard i of N
#   python checklist.py lanes K name ...      -> the names spread over K lanes, one line per lane
#   python checklist.py retry                 -> the page tests allowed one automatic retry (CI only, CHECK_RETRY=1)
# Splits are deterministic: longest first, each to the lightest bin (ties: lowest bin), using the seconds below.
# Every test lands in exactly one shard and one lane (t_shards.py checks it). Add every new test to a list here.
import sys

ENGINE = """t_review t_review2 t_lines t_restart t_extra t_own t_started t_smart t_lab t_tune t_ahl t_ahl_scores
t_settings t_https_push t_tailscale_safe t_status t_league t_hubcache t_kalshi_live t_robust t_stoploss t_cutloss
t_live_panel t_hedge t_rebuild t_buynow t_addonce t_panelgame t_orderbook t_gamedetail t_realdate t_orders_v2
t_buyfunds t_capmsg t_kalshi_feed_watch t_cover t_offer_live t_gametabs t_push_target t_linemodel t_singlebuy
t_ideacards t_ideas_ration t_shards t_spa_files t_spa_update t_spa_transition t_safety t_pottransfer t_profit t_exitpolicy t_smartbuy t_oddscredits
t_sbgate t_lowcredit t_refusals t_scoreboard t_linesel t_bestbets t_ownstake t_gamestart""".split()

PAGE = """test_settings test_tap test_days test_singles_live test_analytics test_buildguard test_spa test_adv
test_panel_ui test_panel_ui2 test_fun test_hist test_web3 test_speed test_sweep test_chips test_restart2
test_extra_ui test_mix test_allchip test_updbtn test_https test_settled test_buildsec test_ui_fixes test_login_faceid
test_motion test_livefresh test_klive test_makeover2 test_makeover3 test_rebuild_ui test_loadwidth test_addonce_ui
test_haptics test_hsw test_chips_stay test_fieldstrip test_gamedetail_api test_realdate test_tabbar_stays
test_orderblock test_buildbuttons test_cover test_pbptabs test_gamecard_opp test_offerlive test_gametabs
test_singlebuy_ui test_ideacards test_ideas2 test_pottransfer_ui test_oddscredits test_refusals test_scoreboard test_linesel_ui test_bestbets test_ownstake_ui""".split()

# Rough seconds each page test takes on a CI runner (measured on PR #157's run; only the balance of the split
# depends on them, a missing or stale number never drops or doubles a test). Unknown tests count as DEFAULT.
# The longest test (test_hsw, ~160 s) sets the floor for a shard's time, so 5 shards of 3 lanes is about as fast as
# it gets: more shards would only add runners.
DEFAULT = 45
SECS = {"test_hsw": 160, "test_makeover3": 159, "test_sweep": 111, "test_gamedetail_api": 94, "test_motion": 93,
        "test_gametabs": 66, "test_singlebuy_ui": 65, "test_ui_fixes": 61, "test_ideacards": 55, "test_ideas2": 60,
        "test_loadwidth": 53, "test_buildbuttons": 52, "test_makeover2": 49, "test_settings": 46, "test_tap": 40,
        "test_pbptabs": 39, "test_panel_ui": 37, "test_allchip": 37, "test_days": 37, "test_panel_ui2": 31,
        "test_updbtn": 31, "test_chips_stay": 30, "test_tabbar_stays": 29, "test_spa": 24, "test_speed": 23,
        "test_settled": 23, "test_extra_ui": 22, "test_restart2": 21, "test_livefresh": 20, "test_adv": 20,
        "test_addonce_ui": 20, "test_mix": 19, "test_buildsec": 19, "test_haptics": 18, "test_fun": 17,
        "test_chips": 17, "test_hist": 16, "test_rebuild_ui": 16, "test_cover": 13, "test_https": 12,
        "test_realdate": 11, "test_analytics": 11, "test_fieldstrip": 10, "test_klive": 9, "test_singles_live": 8,
        "test_orderblock": 8, "test_gamecard_opp": 8, "test_buildguard": 6, "test_login_faceid": 6,
        "test_bestbets": 45, "test_offerlive": 4, "test_web3": 1}

# Page tests allowed ONE automatic rerun in CI (CHECK_RETRY=1), logged as "passed on retry". Keep it empty unless a
# test is timing-bound by nature; a flaky test should be fixed at the root first.
# test_rebuild_ui: its own race (a page load replacing the card mid-check) is fixed, but on a badly overloaded
# machine the web app's background warm-up (watcher code, which this test can't hold off) can keep the engine lock
# for minutes and the progress poll gets no answer (2 of 20 runs with 8 lanes on a loaded Mac; 0 in CI so far).
RETRY = ["test_rebuild_ui"]


def secs(name):
    return SECS.get(name, DEFAULT)


def split(names, n):
    """names -> n bins, longest first into the lightest bin; the same input always gives the same bins."""
    n = max(1, int(n))
    bins, load = [[] for _ in range(n)], [0.0] * n
    for t in sorted(dict.fromkeys(names), key=lambda t: (-secs(t), t)):
        k = min(range(n), key=lambda b: (load[b], b))
        bins[k].append(t); load[k] += secs(t)
    return bins


def shard(names, spec):
    """spec "i/N" (1-based) -> the names in shard i; "" or "1/1" -> all of them, in their listed order."""
    if not spec:
        return list(names)
    i, n = (int(x) for x in spec.split("/"))
    if not 1 <= i <= n:
        raise ValueError("shard %s is out of range" % spec)
    keep = set(split(names, n)[i - 1])
    return [t for t in names if t in keep]


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["engine"]:
        print(" ".join(ENGINE))
    elif a[:1] == ["page"]:
        print(" ".join(shard(PAGE, a[1] if len(a) > 1 else "")))
    elif a[:1] == ["lanes"]:
        for b in split(a[2:], int(a[1])):
            print(" ".join(b))
    elif a[:1] == ["retry"]:
        print(" ".join(RETRY))
    else:
        sys.exit("usage: checklist.py engine | page [i/N] | lanes K names... | retry")
