# combo_watcher.py: the Kalshi combo planner's always-on watcher, for a Raspberry Pi or a Mac.
#
# Runs the same engine as the phone planner, with no screens. Every refresh (15 s by default):
#   - reads your live combos in every sport, the scores, and Kalshi's in-game prices,
#   - sends push notifications through ntfy (picks won/lost, "worth cashing out", games turning),
#   - if you turned on Auto cash-out in the phone's Settings: cashes out a combo when its card would
#     say Cash out (a pick already won, and Kalshi's offer beats waiting at your Let it ride level).
#     While the watcher runs, only it auto-sells, so nothing is sold twice. Off unless you turn it on.
#
# Files live in ~/combowatch (or $COMBOWATCH_HOME):
#   engine.py                  the planner engine, downloaded from GitHub and kept up to date
#   watcher.json               your ntfy topic and pairing secret (made by the installer)
#   combo_settings.json        Kalshi Key ID and the settings the phone sends over
#   kalshi_private_key.pem     this watcher's own Kalshi private key (readable only by this user)
import base64, hashlib, hmac, importlib.util, json, os, re, sys, threading, time, traceback

import requests

HOME = os.environ.get("COMBOWATCH_HOME") or os.path.expanduser("~/combowatch")
ENGINE = os.path.join(HOME, "engine.py")
CONF = os.path.join(HOME, "watcher.json")
REPO = "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/"
NTFY = os.environ.get("COMBOWATCH_NTFY", "https://ntfy.sh")
WATCHER_VERSION = "2026.11.17.52"

# Settings the phone may change on the watcher. Keys and anything else are never accepted.
SYNCED = ("bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap",
          "auto_hedge", "hedge_cap", "prefer_hedge")


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_conf():
    with open(CONF, encoding="utf-8") as f:
        return json.load(f)


def push(conf, msg, title="Combo planner", priority="default", topic=None, pause_button=False):
    """A notification on your phone (ntfy app subscribed to your topic). With pause_button, it
    carries a "Pause auto cash-out" button that stops automatic sales until you resume."""
    headers = {"Title": title, "Priority": priority, "Tags": "moneybag"}
    if pause_button:
        headers["Actions"] = f"http, Pause auto cash-out, {NTFY}/{conf['topic']}-pause, method=POST, body=pause, clear=true"
    try:
        requests.post(f"{NTFY}/{topic or conf['topic']}", data=msg.encode("utf-8"), timeout=10, headers=headers)
    except requests.RequestException as err:
        log("push failed:", err)


def sign(secret, body):
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def fetch_settings(conf, E):
    """Apply the latest settings the phone sent, if they carry a valid signature."""
    try:
        r = requests.get(f"{NTFY}/{conf['topic']}-cfg/json", params={"poll": "1", "since": "all"}, timeout=10)
        lines = [json.loads(x) for x in r.text.splitlines() if x.strip()] if r.ok else []
    except (requests.RequestException, ValueError):
        return False
    applied = False
    for m in lines:
        try:
            env = json.loads(m.get("message") or "{}")
            body, sig = env["body"], env["sig"]
        except (ValueError, KeyError, TypeError):
            continue
        if not hmac.compare_digest(sign(conf["secret"], body), sig):
            log("ignored a settings message with a bad signature")
            continue
        data = json.loads(body)
        if data.get("at", 0) <= conf.get("settings_at", 0):
            continue
        for k in SYNCED:
            if k in data.get("cfg", {}):
                E.CFG[k] = data["cfg"][k]
        if isinstance(data.get("approve"), dict) and data["approve"].get("version"):
            if data["approve"].get("version") != getattr(E, "VERSION", "") and \
                    data["approve"] != conf.get("approve"):
                conf["update_now"] = True              # your phone just updated: follow it right away
            conf["approve"] = data["approve"]          # the exact update files your phone installed
        if conf.get("paused"):
            if data.get("at", 0) > conf["paused"] and data.get("cfg", {}).get("auto_sell"):
                conf.pop("paused")                     # you saved Settings with Auto cash-out on: resume
                push(conf, "▶️ Auto cash-out resumed on the Pi.", priority="low")
            else:
                E.CFG["auto_sell"] = False
        if isinstance(data.get("discount"), dict):          # what Kalshi buyers really pay, learned on the phone
            E.save_json(E.DISCOUNT_FILE, data["discount"])
        conf["settings_at"] = data["at"]
        applied = True
    if applied:
        E.save_json(E.SAVED, E.CFG)
        E.save_json(CONF, conf)
        log("applied settings from the phone:", {k: E.CFG.get(k) for k in SYNCED},
            "| updates allowed:", (conf.get("approve") or {}).get("version"))
    return applied


def listen_for_settings(conf, E, lock):
    """Keeps a connection open to the settings channel, so a change you save on the phone lands
    here within a second or two. Reconnects on its own; the minute-by-minute check stays as backup."""
    import threading

    def run():
        while True:
            try:
                t = conf["topic"]
                with requests.get(f"{NTFY}/{t}-cfg,{t}-pause/json", stream=True, timeout=(10, 120)) as r:
                    for line in r.iter_lines():
                        ev = json.loads(line) if line else {}
                        if ev.get("event") != "message":
                            continue
                        with lock:
                            if ev.get("topic", "").endswith("-pause"):
                                pause(conf, E)
                            elif fetch_settings(conf, E):
                                E.CFG["auto_cash"] = False
            except Exception as err:          # dropped connection, Wi-Fi blip: wait and reconnect
                log("settings listener reconnecting:", type(err).__name__)
                time.sleep(15)

    threading.Thread(target=run, daemon=True).start()


def pause(conf, E):
    """The Pause button on a notification: no automatic sales until you save Settings with
    Auto cash-out on. Pausing needs no signature (it can only make things safer)."""
    if conf.get("paused"):
        return
    conf["paused"] = int(time.time())
    E.CFG["auto_sell"] = False
    E.save_json(CONF, conf)
    log("auto cash-out paused from a notification")
    push(conf, "⏸ Auto cash-out paused on the Pi. Alerts continue. To resume, open the planner and save "
               "Settings with Auto cash-out on.", priority="high")


def heartbeat(conf, E, note="", err=""):
    """A small status message the phone reads to show the watcher is alive."""
    holds = E.MINE.get("hold") or {}
    live = sum(1 for h in holds.values() if h.get("left", 1) > 0)
    playing = sum(1 for h in holds.values() if any(lv for _, lv, _ in h.get("legs_left") or []))
    upcoming = [ts for h in holds.values() for _, lv, ts in h.get("legs_left") or [] if not lv and time.time() < ts < 9e12]
    acts = (E.MINE.get("plan") or {}).get("acts") or {}
    cash = [holds[t]["label"] for t, f in acts.items() if f and t in holds]
    body = json.dumps({"at": int(time.time()), "v": WATCHER_VERSION, "engine": E.VERSION, "live": live,
                       "orders": sum(len(v) for v in (E.MINE.get("tp") or {}).values()), "note": note,
                       "paused": bool(conf.get("paused")), "waiting": conf.get("waiting") or "",
                       "playing": playing, "next": int(min(upcoming)) if upcoming else None, "cash": cash[:4],
                       "err": err[:160]})
    try:
        requests.post(f"{NTFY}/{conf['topic']}-hb", data=body.encode(), timeout=10,
                      headers={"Cache": "yes"})
    except requests.RequestException:
        pass
    if conf.get("healthcheck_url"):                    # dead-man switch: it alerts you when these stop
        try:
            requests.get(conf["healthcheck_url"], timeout=10)
        except requests.RequestException:
            pass


def send_report(conf, E):
    """The edge report, sealed with the pairing secret, for the phone's Results screen."""
    try:
        st = E.edge_stats(E.fetch_account(every_league=True)[0])
        requests.post(f"{NTFY}/{conf['topic']}-report", data=E.seal(conf["secret"], {"stats": st}).encode(),
                      timeout=15, headers={"Cache": "yes"})
        return st
    except Exception as err:
        log("report skipped:", type(err).__name__, err)
        return None


def load_engine():
    spec = importlib.util.spec_from_file_location("combo_engine", ENGINE)
    E = importlib.util.module_from_spec(spec)
    sys.argv = [ENGINE]
    spec.loader.exec_module(E)
    return E


def update_if_newer(E, conf):
    """Install a newer engine and watcher from GitHub, but only the exact files your phone
    installed (it sends their SHA-256, signed). Returns True if the watcher should restart."""
    try:
        latest = requests.get(REPO + "version.txt", params={"t": int(time.time())}, timeout=15,
                              headers={"Cache-Control": "no-cache"}).text.strip()
    except requests.RequestException:
        return False
    if not re.fullmatch(r"[0-9.]+", latest) or latest == getattr(E, "VERSION", ""):
        conf.pop("waiting", None)
        return False
    ok = conf.get("approve") or {}
    if ok.get("version") != latest:
        if conf.get("waiting") != latest:
            conf["waiting"] = latest
            log(f"version {latest} is out; waiting until your phone updates to it")
        return False
    try:
        sb = requests.get(REPO + "nfl_combo_planner.py", params={"t": int(time.time())}, timeout=30).content
        wb = requests.get(REPO + "watcher/combo_watcher.py", params={"t": int(time.time())}, timeout=30).content
        if hashlib.sha256(sb).hexdigest() != ok.get("engine") or hashlib.sha256(wb).hexdigest() != ok.get("watcher"):
            log(f"update {latest} skipped: the files don't match what your phone approved")
            return False
        src, wsrc = sb.decode("utf-8"), wb.decode("utf-8")
        compile(src, "engine.py", "exec")
        compile(wsrc, "combo_watcher.py", "exec")
    except (requests.RequestException, SyntaxError, UnicodeDecodeError) as err:
        log("update skipped:", err)
        return False
    if f'VERSION = "{latest}"' not in src or "def main():" not in src:
        return False
    with open(ENGINE + ".new", "w", encoding="utf-8") as f:
        f.write(src)
    os.replace(ENGINE + ".new", ENGINE)
    me = os.path.abspath(__file__)
    with open(me + ".new", "w", encoding="utf-8") as f:
        f.write(wsrc)
    os.replace(me + ".new", me)
    conf.pop("waiting", None)
    log("updated to", latest, "(approved by your phone) - restarting")
    return True


def estimate_offers(E):
    """The watcher doesn't ask Kalshi for a cash-out quote on every combo (that would cancel the
    phone's), so it estimates them: fair value times the discount Kalshi buyers usually take.
    With Auto cash-out on, a combo with a pick already won that's estimated within 10% of its
    Let it ride price gets a real Kalshi offer (at most every few minutes), so the sell decision
    is made on a real price."""
    now = time.time()
    real_every = max(3, int(E.CFG.get("cash_every", 3))) * 60
    asked = E.MINE.setdefault("pi_asked", {})
    for t, h in (E.MINE.get("hold") or {}).items():
        if h.get("left", 1) <= 0:
            continue
        cur = E.MINE["cash"].get(t) or {}
        if cur.get("rfq") not in (None, "estimate") and now - cur.get("at", 0) <= E.offer_life():
            continue                                  # a real offer is still good
        live = any(lv for _, lv, _ in h.get("legs_left") or [])
        price = min(E.kalshi_discount(live) * h["p"], 0.99)
        est = {"offer": round(price * h["pays"], 2), "contracts": h["pays"], "price": price,
               "rfq": "estimate", "quote": None, "frac": 1.0, "at": now}
        E.MINE["cash"][t] = est
        if not (E.CFG.get("auto_sell") and h.get("won_some")) or now - asked.get(t, 0) < real_every:
            continue
        thr = E.wait_threshold(t)
        if thr and est["offer"] >= 0.9 * thr:
            asked[t] = now
            real = E.get_cash_offer(t)
            if real.get("offer"):
                E.MINE["cash"][t] = real
                log(f"real offer for {h['label']}: ${real['offer']:.2f} (sells at ${thr:.2f}+)")



# ---------------------------------------------------------------- Mac hub: the phone's data and trades
HUB_PATHS = re.compile(r"^/(portfolio|communications|markets|events|multivariate_event_collections|series)(/|$)")


def hub_address():
    """This machine's Tailscale address (100.64.0.0/10), or ''."""
    import subprocess
    for cmd in (["ifconfig"], ["ip", "-4", "addr"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for ip in re.findall(r"inet (100\.(\d+)\.\d+\.\d+)", out):
            if 64 <= int(ip[1]) <= 127:
                return ip[0]
    return ""


class HubCache:
    """Recent public reads, kept fresh in the background for whatever the phone asked for lately."""
    def __init__(self, E):
        self.E, self.lock = E, threading.Lock()
        self.data, self.wanted = {}, {}

    @staticmethod
    def ttl(url):
        if "espn.com" in url:
            return 20
        if "/multivariate_event_collections" in url or "/series" in url:
            return 120
        return 12

    def get(self, url, params, fresh=False):
        key = url + "?" + json.dumps(params, sort_keys=True)
        now = time.time()
        with self.lock:
            self.wanted[key] = (now, url, params)
            hit = self.data.get(key)
        if hit and not fresh and now - hit[0] < self.ttl(url):
            return hit[1]
        r = requests.get(url, params=params, timeout=20)
        val = {"status": r.status_code, "text": r.text}
        if r.ok:
            with self.lock:
                self.data[key] = (time.time(), val)
        return val

    def warm(self):
        while True:
            time.sleep(8)
            now = time.time()
            with self.lock:
                for k in [k for k, (t, _, _) in self.wanted.items() if now - t > 1800]:
                    self.wanted.pop(k, None)
                    self.data.pop(k, None)
                todo = [(u, p) for k, (t, u, p) in self.wanted.items()
                        if now - (self.data.get(k) or (0,))[0] > self.ttl(u) - 6][:60]
            for u, p in todo:
                try:
                    self.get(u, p, fresh=True)
                except Exception as err:          # one bad read doesn't stop the rest
                    log("hub warm skipped:", type(err).__name__, err)


def start_hub(conf, E):
    """Serve the phone over Tailscale (or your home network). Every request must be sealed with the
    pairing secret, recent, and not a replay; anything else gets a bare 403."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    secret, cache, seen = conf["secret"], HubCache(E), {}
    seen_lock = threading.Lock()
    threading.Thread(target=cache.warm, daemon=True, name="hub-warm").start()

    def handle(req):
        op = req.get("op")
        if op == "ping":
            return {"v": WATCHER_VERSION, "engine": E.VERSION, "trade": E.can_trade(), "at": time.time()}
        if op == "account":
            return {"value": list(E.fetch_account(max_age=15, every_league=True))}
        if op == "get":
            url = str(req.get("url", ""))
            if not url.startswith(E.HUB_GET_HOSTS):
                return {"status": 403, "text": "not allowed"}
            return cache.get(url, req.get("params") or {})
        if op == "kalshi":
            method, path = str(req.get("method", "GET")).upper(), str(req.get("path", ""))
            if method not in ("GET", "POST", "PUT", "DELETE") or not HUB_PATHS.match(path):
                return {"err": "kalshi", "msg": "That request isn't allowed through the Mac."}
            if method != "GET":
                log("phone trade:", method, path)
            try:
                return {"json": E.kalshi_send(method, path, req.get("body"), req.get("params") or None)}
            except PermissionError as err:
                return {"err": "perm", "msg": str(err)}
            except (RuntimeError, ValueError, OSError, requests.RequestException) as err:
                return {"err": "kalshi", "msg": str(err)}
        return {"err": "kalshi", "msg": "unknown request"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if self.path != "/v1" or not 0 < n < 2_000_000:
                return self._send(403, b"")
            req = E.hub_unseal(secret, self.rfile.read(n))
            now = time.time()
            if not isinstance(req, dict) or abs(now - float(req.get("ts", 0))) > 300 or not req.get("n"):
                return self._send(403, b"")
            with seen_lock:
                if req["n"] in seen:
                    return self._send(403, b"")
                seen[req["n"]] = now
                if len(seen) > 5000:
                    for k in [k for k, t in seen.items() if now - t > 600]:
                        del seen[k]
            try:
                out = handle(req)
            except Exception as err:
                log("hub request failed:", req.get("op"), type(err).__name__, err)
                out = {"err": "kalshi", "msg": f"The Mac hit an error: {type(err).__name__}"}
            out["re"] = req["n"]
            self._send(200, E.hub_seal(secret, out))

        def do_GET(self):
            self._send(404, b"")

        def _send(self, code, body):
            self.send_response(code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    port = int(conf.get("hub_port") or 8765)
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    except OSError as err:
        log(f"hub not started (port {port}):", err)
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="hub").start()
    ip = hub_address()
    log(f"hub serving the phone on port {port}" + (f" at http://{ip}:{port}" if ip else " (no Tailscale address found)"))
    return srv


def main():
    conf = load_conf()
    E = load_engine()
    # headless: nothing to draw, notifications go to ntfy, no cash-out quotes from here
    E.present = lambda *a, **k: None
    E.loading = lambda *a, **k: None
    E.notify = lambda msg: push(conf, msg.replace("Open the planner to confirm.", "Open the planner to cash out."),
                                pause_button=bool(E.CFG.get("auto_sell")))
    E.console_note = lambda msg: log(msg)
    E.auto_cash_checks = lambda: []        # no quotes on every combo; see estimate_offers
    E.set_league("nfl")                    # Live covers every sport; this only picks the main game list
    fetch_settings(conf, E)
    E.CFG["auto_cash"] = False
    if conf.get("paused"):
        E.CFG["auto_sell"] = False
    if not E.can_trade():
        push(conf, "The watcher can't reach your Kalshi account: check the Key ID and key file on the watcher.",
             priority="high")
        log("no Kalshi access; waiting 10 minutes")
        time.sleep(600)
        return 1
    bets, balance, note = E.fetch_account(max_age=0, every_league=True)
    if bets is None:                                     # a real call, not just "the key file exists"
        push(conf, f"The watcher couldn't read your Kalshi account: {note or 'no answer'}. Check its key "
                   "(run its installer with --new-key).", priority="high")
        log("Kalshi check failed:", note)
        time.sleep(600)
        return 1
    log(f"Kalshi OK: {sum(1 for b in bets if b['status'] == 'pending')} live combos, balance ${balance or 0:.2f}")
    import threading
    lock = threading.Lock()
    listen_for_settings(conf, E, lock)
    if conf.get("hub", sys.platform == "darwin"):      # the Mac hub; a Pi only if asked
        start_hub(conf, E)
    log("watcher", WATCHER_VERSION, "engine", E.VERSION, "started")
    push(conf, f"Watcher started (planner {E.VERSION}). It's keeping an eye on your combos.", priority="low")
    last = {"hb": 0, "cfg": 0, "upd": time.time(), "sell": 0, "init": 0, "rep": 0}
    while True:
        t0 = time.time()
        try:
            if t0 - last["cfg"] > 60:
                last["cfg"] = t0
                with lock:
                    fetch_settings(conf, E)
                    E.CFG["auto_cash"] = False
            if not E.MINE.get("all_games") or t0 - last["init"] > 3600:      # this week's games, hourly
                last["init"] = t0
                games, days, sunday = E.week_games(E.fetch_markets(), loose=True)
                E.MINE.update({"all_games": games, "days": days, "sunday": sunday, "book": {},
                               "notes": [], "live": True, "last": None})
                E.ACCT_CACHE["at"] = 0
                _, E.MINE["snap"] = E.mine_page(live=True)
            estimate_offers(E)
            E.ACCT_CACHE["at"] = 0
            alerts = E.live_check(None)            # also auto cash-out, if the phone turned it on
            if alerts:
                log("alerts:", alerts)
            if t0 - last["sell"] > 60:
                last["sell"] = t0
                done = E.autosell_pass()
                if done:
                    log("auto-sell placed or moved:", done)
            if t0 - last["hb"] > 55:                 # the phone takes over if this stops for 3 minutes
                last["hb"] = t0
                heartbeat(conf, E)
            if t0 - last["rep"] > 1800:
                last["rep"] = t0
                st = send_report(conf, E)
                now = time.localtime()
                wk = time.strftime("%G-W%V")
                if st and now.tm_wday == 0 and now.tm_hour >= 9 and conf.get("report_week") != wk:
                    conf["report_week"] = wk               # Monday morning, once a week
                    E.save_json(CONF, conf)
                    push(conf, E.weekly_text(st), title="Weekly report", priority="low")
            if conf.pop("update_now", False) or t0 - last["upd"] > 1800:
                last["upd"] = t0
                if update_if_newer(E, conf):
                    return 0                      # systemd starts the new version
        except Exception as err:
            log("check failed:", type(err).__name__, err)
            traceback.print_exc()
            if time.time() - last["hb"] > 55:      # still report in, with the error, so the phone shows it
                last["hb"] = time.time()
                try:
                    heartbeat(conf, E, err=f"{type(err).__name__}: {err}")
                except Exception:
                    pass
            time.sleep(30)
        time.sleep(max(5, int(E.CFG.get("refresh_secs", 15)) - (time.time() - t0)))


if __name__ == "__main__":
    sys.exit(main() or 0)
