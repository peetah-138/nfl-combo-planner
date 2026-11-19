import sys, os, json, time, importlib.util, re
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: None; W.CONF = "run/test_watcher_conf.json"; W.HOME = "run"
M.MINE["hold"] = {"KXMVENFL-1": {"label": "Combo 1", "cost": 5, "pays": 40, "p": 0.31, "left": 2,
                                  "need": [(("yes", "A"), "Buffalo Bills"), (("yes", "B"), "Detroit Lions")]}}
M.get_cash_offer = lambda t: {"rfq": "r", "quote": "q", "offer": 17.5, "at": time.time(), "price": 0.44, "contracts": 40}
M.accept_cash = lambda t: "✅ <b>Combo 1</b> cashed out for about $17.50."
conf = {"topic": "t", "secret": "s", "hub_port": 8796, "web_pass": "pass1234"}
srv = W.start_hub(conf, M)
import requests
B = "http://127.0.0.1:8796"
r = requests.get(B + "/", headers={"X-Forwarded-For":"1.2.3.4"}); print("not signed in -> login page:", "Passcode" in r.text, r.url)
r = requests.post(B + "/login", data={"pass": "nope"}); print("wrong passcode:", "isn&#x27;t right" in r.text)
s = requests.Session()
s.post(B + "/login", data={"pass": "pass1234"}); r = s.get(B + "/simple"); print("right passcode -> dashboard:", "Live combos (1)" in r.text, "| cookie:", "cw" in s.cookies)
tok = re.search(r"name='tok' value='([^']+)'", r.text).group(1)
ck = s.cookies.get("cw"); r = s.post(B + "/app/mac-info", data="{}", headers={"X-CW": ck, "X-Forwarded-For": "100.1.2.3"}); print("mac-info remote:", r.status_code, r.text[:160])
r = requests.post(B + "/app/mac-info", data="{}"); print("mac-info no session:", r.status_code)
r = s.post(B + "/app/mac-check", data="{}", headers={"X-CW": ck, "X-Forwarded-For": "100.1.2.3"}); print("mac-check remote:", r.status_code, conf.get("update_now"))
if r.status_code != 200 or not conf.get("update_now"): print("PROBLEMS: remote update check didn't reach the Mac")
r = requests.post(B + "/app/mac-check", data="{}"); print("mac-check no session:", r.status_code)
if r.status_code != 403: print("PROBLEMS: update check works without signing in")
r = s.post(B + "/app/mac-info", data="{}", headers={"X-CW": ck}); print("checked field:", "checked" in r.json())
if "checked" not in r.json(): print("PROBLEMS: no last-checked time")
r = s.post(B + "/act", data={"t": "KXMVENFL-1", "do": "quote", "tok": tok}); print("quote:", re.search(r"class='msg'>([^<]+)", r.text).group(1), "| sell button:", "Sell now for $17.50" in r.text)
r = s.post(B + "/act", data={"t": "KXMVENFL-1", "do": "sell", "tok": tok}); print("sell:", re.search(r"class='msg'>([^<]+)", r.text).group(1))
r = s.post(B + "/act", data={"t": "KXMVENFL-1", "do": "sell"}); print("no page token (forged form):", r.status_code)
r = requests.post(B + "/act", data={"t": "KXMVENFL-1", "do": "sell", "tok": tok}); print("token but no cookie:", r.status_code)
for _ in range(5): requests.post(B + "/login", data={"pass": "x"})
print("lockout after 5 wrong:", "Too many" in requests.post(B + "/login", data={"pass": "pass1234"}).text)
print("phone API still works:", requests.post(B + "/v1", data=b"junk").status_code == 403)
srv.shutdown()
