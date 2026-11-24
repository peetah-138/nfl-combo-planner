# CHECK: group=engine
# Tapping a trade alert opens that combo or bet (Pete, 2026-11-23). The ntfy Click header is built from the app's own
# configured address at send time: a combo gives '/#c=<ticker>', a single '/#b=<ticker>'; with no address configured
# no Click header is sent at all (exactly as before); the link carries only the ticker, never a key, topic, secret or
# account id. Every network call is faked.
import sys, importlib.util
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: None
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
SECRET, TOPIC, KEYID = "s3cr3t-value-xyz", "topic-abc-123", "key-id-777"
class _E:
    CFG = {}
    MINE = {"hold": {"KXMVE-24": {"label": "Combo 24"}}, "snap": {"KXMVE-24": {"label": "Combo 24"}}, "cash": {}}
    SINGLES = {"items": [{"t": "KXNBAGAME-26NOV19LALBOS-LAL", "label": "Lakers to win"},
                         {"t": "KXNBAGAME-26NOV19LALBOS-LAL2", "label": "Lakers to win by 10"},
                         {"t": "KXNBASPREAD-26NOV19-BOS5", "label": "Celtics -4.5"},
                         {"t": "bad<x>/y", "label": "Weird bet"}]}
L = W.trade_link
ok("combo: '/#c=<ticker>'", L(_E, "🤖 Took the profit: Combo 24 cashed out for about $3.61: +$1.42 profit (paid $2.19).") == "/#c=KXMVE-24")
ok("single: '/#b=<ticker>'", L(_E, "🤖 Take profit: sold Celtics -4.5 for about $5: +$1 profit (paid $4).") == "/#b=KXNBASPREAD-26NOV19-BOS5")
ok("a label inside a longer matching label does not make it ambiguous", L(_E, "🤖 sold Lakers to win by 10 for $5") == "/#b=KXNBAGAME-26NOV19LALBOS-LAL2")
ok("two different bets named: no link", L(_E, "sold Celtics -4.5 and Lakers to win by 10") is None)
ok("nothing named: no link", L(_E, "⏸ Paused for today") is None)
ok("an unsafe ticker is never put in a link", L(_E, "sold Weird bet") is None)
ok("never raises on junk", L(None, None) is None and L(object(), "x") is None)

# ---- the ntfy Click header, with and without a configured address
posts = []
class R:
    status_code = 200; ok = True; text = ""
W.requests.post = lambda url, **kw: (posts.append((url, kw)), R())[1]
W.web_push = lambda *a, **k: None
W.hub_address = lambda: ""                       # no Tailscale address in tests
conf0 = {"topic": TOPIC, "secret": SECRET, "kalshi_key_id": KEYID}
W.push(conf0, "sold Celtics -4.5", click=L(_E, "sold Celtics -4.5"))
h = posts[-1][1]["headers"]
ok("no address configured: no Click header, send is as before", "Click" not in h and h.get("Title") == "Combo planner", h)
conf1 = dict(conf0, https={"url": "https://mac.example.ts.net"})
W.push(conf1, "sold Celtics -4.5", click=L(_E, "sold Celtics -4.5"))
h = posts[-1][1]["headers"]
ok("address configured: Click = address + '/#b=<ticker>'", h.get("Click") == "https://mac.example.ts.net/#b=KXNBASPREAD-26NOV19-BOS5", h)
W.push(conf1, "Combo 24 sold", click=L(_E, "Combo 24 sold"))
h = posts[-1][1]["headers"]
ok("combo push: Click = address + '/#c=<ticker>'", h.get("Click") == "https://mac.example.ts.net/#c=KXMVE-24", h)
W.push(conf1, "Paused", click=L(_E, "Paused"))
ok("no bet named: no Click header", "Click" not in posts[-1][1]["headers"])
blob = " ".join(str(v) for _, kw in posts for v in kw["headers"].values() if v and str(v).startswith("http"))
ok("no secret, topic or key id appears in any link", not any(s in blob for s in (SECRET, TOPIC, KEYID)), blob)
ok("the link part is only '#b=' or '#c=' plus a ticker (letters, digits, dash)", all(__import__("re").fullmatch(r"/#[bc]=[A-Za-z0-9._-]+", L(_E, m) or "/#b=X") for m in ("sold Celtics -4.5", "Combo 24 sold")))

# ---- the notifier: an automatic single sale is pushed at once and tappable
sent = []
W.push = lambda conf, msg, **kw: sent.append((msg, kw))
W.BUS.publish = lambda ev: None
n = W.Notifier({"topic": "t"}, _E)
n.add("🤖 Take profit: sold Celtics -4.5 for about $5: +$1 profit (paid $4).")
ok("Notifier: an automatic single sale goes out at once with the bet's link", sent and sent[-1][1].get("click") == "/#b=KXNBASPREAD-26NOV19-BOS5", sent)
n.add("🤖 Took the profit: Combo 24 cashed out for about $3: +$1 profit (paid $2).")
ok("Notifier: an automatic combo cash-out links to the combo", sent[-1][1].get("click") == "/#c=KXMVE-24", sent[-1])
