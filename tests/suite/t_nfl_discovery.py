# CHECK: group=engine
# tools/research/nfl_discovery.py (offline NFL trend discovery). The pure-Python parts (multiple-testing control,
# season stability, decay tracker, leak guard, data-stays-outside-the-repo guard) always run. The end-to-end run on
# synthetic data with a PLANTED effect (indoor home teams worth +6 points, every season) needs numpy/pandas/scikit-learn
# and is skipped with a message when they are absent: it must find the planted effect, must not report the pure-noise
# features (referee, wind) as findings, and the random-sign placebo must reject about nothing.
import os, importlib.util, traceback, tempfile, random
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("ND", os.path.join(REPO, "tools", "research", "nfl_discovery.py"))
ND = importlib.util.module_from_spec(spec); spec.loader.exec_module(ND)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def pure():
    q = ND.bh_adjust([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])   # the textbook BH example
    ok("BH q-values: monotone and match the step-up rule", all(q[i] <= q[i + 1] + 1e-12 for i in range(9))
       and abs(q[0] - 0.01) < 1e-9 and abs(q[1] - 0.04) < 1e-9 and abs(q[4] - 0.084) < 1e-9, q)
    ok("BH on an empty family is empty", ND.bh_adjust([]) == [])
    rng = random.Random(1)
    p = [rng.random() for _ in range(5000)]
    ok("BH on pure noise rejects (almost) nothing at 0.05", sum(x < 0.05 for x in ND.bh_adjust(p)) <= 2)
    p2 = p[:4900] + [1e-9] * 100
    ok("BH keeps a real signal inside a big family", sum(x < 0.05 for x in ND.bh_adjust(p2)) >= 100)
    share, n = ND.sign_stability({2000 + i: (1.0 if i < 7 else -1.0, 50) for i in range(10)}, 1)
    ok("sign stability: 7 of 10 seasons positive = 70%", abs(share - 0.7) < 1e-9 and n == 10, (share, n))
    share, n = ND.sign_stability({2000: (1.0, 5), 2001: (1.0, 80)}, 1)
    ok("sign stability ignores seasons with too few games", n == 1 and share == 1.0, (share, n))
    steady = {2000 + i: (10.0, 100) for i in range(12)}
    fade = {2000 + i: (max(0.0, 12.0 - 1.5 * i) + (0.1 if i % 2 else -0.1), 100) for i in range(12)}
    ok("decay tracker: a steady effect is holding", ND.decay_status(steady, 10.0)["status"] == "holding")
    d = ND.decay_status(fade, sum(v for v, _ in fade.values()) / 12)
    ok("decay tracker: an effect that withers is retired or fading", d["status"] in ("retire", "fading"), d)
    ok("decay tracker: 4 seasons is too few to judge", ND.decay_status({2000 + i: (5.0, 90) for i in range(4)}, 5.0)["status"] == "too_few_seasons")
    ok("leak guard: end-of-play score columns are on the banned list", {"total_home_score", "total_away_score"} <= ND.LEAKY)
    ok("leak guard: no model feature is banned", not (set(ND.BASE) | {f for g in ND.GROUPS.values() for f in g}) & ND.LEAKY)
    inside = os.path.join(REPO, "nfl_data_should_not_live_here")
    try:
        ND.ensure_outside_repo(inside)
        ok("data folder inside the repo is refused", False)
    except SystemExit:
        ok("data folder inside the repo is refused", True)
    ok("data folder outside the repo is accepted", str(ND.ensure_outside_repo(tempfile.mkdtemp())).startswith(("/", "C:")))
    ok("anecdotes: about a dozen, unique ids, all with a plain-English claim",
       len(ND._anecdotes()) >= 12 and len({a["id"] for a in ND._anecdotes()}) == len(ND._anecdotes())
       and all(a["claim"] for a in ND._anecdotes()))


def heavy():
    if ND.np is None or ND.pd is None:
        print("PASS synthetic end-to-end run skipped: numpy/pandas not installed here (research venv only)")
        return
    try:
        import sklearn  # noqa: F401
    except ImportError:
        print("PASS synthetic end-to-end run skipped: scikit-learn not installed here (research venv only)")
        return
    plays, games = ND.synthetic_raw()
    cfg = {"test_start": 2005, "max_iter": 150, "lr": 0.15, "min_n": 60, "min_seasons": 4, "placebo": 3, "n_boot": 80,
           "perm_repeats": 1, "log": lambda *a: None}      # the same settings as `run --synthetic`
    res = ND.run_pipeline(plays, games, cfg)
    sc = res["scan"]
    ok("synthetic: hypotheses are counted", sc["hypotheses_tested"] > 500 and sc["cells_enumerated"] >= sc["hypotheses_tested"], sc["hypotheses_tested"])
    labels = [s["label"] for s in sc["survivors"]]
    dome = [s for s in sc["survivors"] if "indoors" in s["label"]]
    ok("synthetic: the planted dome edge is found, with the right sign",
       any(("at home" in s["label"] and s["effect_wp_pts"] > 0) or ("on the road" in s["label"] and s["effect_wp_pts"] < 0) for s in dome), labels[:6])
    ok("synthetic: the planted effect is big and stable in the survivors", all(s["same_sign_share"] >= 0.7 and abs(s["effect_wp_pts"]) >= 2 for s in sc["survivors"]))
    ok("synthetic: pure-noise features (referee, wind) are not findings",
       not any(("referee" in l or "wind" in l) for l in labels), [l for l in labels if "referee" in l or "wind" in l])
    ok("synthetic: random-sign placebo rejects about nothing", max(sc["placebo_bh_rejections_per_rep"]) <= 2, sc["placebo_bh_rejections_per_rep"])
    ok("synthetic: walk-forward never scores a season with a model that saw it",
       res["data"]["test_seasons"][0] >= 2005 and res["data"]["seasons"][0] == 2000)
    ok("synthetic: aggregates only (no game ids in the output)", "2005_" not in ND.render_markdown(res))
    ok("synthetic: richer model is compared with the baseline and a verdict table exists", "improvement" in res["evaluation"])


section("pure-python parts", pure)
section("synthetic end-to-end", heavy)
