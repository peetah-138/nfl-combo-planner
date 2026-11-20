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
WATCHER_VERSION = "2026.11.20.123"

# Settings the phone may change on the watcher. Keys and anything else are never accepted.
SYNCED = ("take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap",
          "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news",
          "killer_mode", "maker_mode", "accept_pct", "size_min", "size_max", "budget", "include_live", "live_min", "panel_live")


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_conf():
    with open(CONF, encoding="utf-8") as f:
        return json.load(f)


PUSHLOG = {"at": 0, "ok": None, "title": "", "msg": "", "code": 0}


def hub_base(conf):
    """Where Combo Hub opens from the phone: the https address when the Mac has it, else Tailscale's."""
    url = (conf.get("https") or {}).get("url")
    if url:
        return url
    ip = hub_address()
    return f"http://{ip}:{conf.get('hub_port', 8765)}" if ip else ""


WEB_SYNC = False          # tests set this so the web push runs inline instead of in a thread
_WEB_SEEN = {}            # (title, body) -> when it last went to web push (so one alert isn't sent twice)
_WEB_LOCK = threading.Lock()


def web_push(title, body, url="/app", tag=None, urgent=False):
    """Send one notification to the devices signed up for Combo Hub notifications (Web Push), in the
    background. The same title+text within 2 minutes is sent once. Does nothing when no device is signed up."""
    key = (title, body)
    now = time.time()
    with _WEB_LOCK:
        for k in [k for k, t in _WEB_SEEN.items() if now - t > 120]:
            _WEB_SEEN.pop(k, None)
        if key in _WEB_SEEN:
            return False
        _WEB_SEEN[key] = now
    if WEB_SYNC:
        PUSH.send(title, body, url=url, tag=tag, urgent=urgent)
    else:
        threading.Thread(target=PUSH.send, args=(title, body), kwargs={"url": url, "tag": tag, "urgent": urgent},
                         daemon=True, name="webpush").start()
    return True


def push(conf, msg, title="Combo planner", priority="default", topic=None, pause_button=False, click=None,
         web=True, web_title=None, web_msg=None, web_urgent=None, tag=None):
    """A notification on your phone (ntfy app subscribed to your topic). With pause_button, it
    carries a "Pause auto cash-out" button that stops automatic sales until you resume. With click,
    tapping it opens that Combo Hub page. Unless it goes to another topic (topic=...) or web=False, it
    also goes to the phones signed up for Combo Hub notifications (web_title / web_msg / web_urgent:
    different wording for those, urgent defaults to ntfy's high priority)."""
    headers = {"Title": title, "Priority": priority, "Tags": "moneybag"}
    if click and hub_base(conf):
        headers["Click"] = hub_base(conf) + click
    if pause_button:
        headers["Actions"] = f"http, Pause auto cash-out, {NTFY}/{conf['topic']}-pause, method=POST, body=pause, clear=true"
    if web and not topic:
        try:
            urgent = priority in ("high", "urgent") if web_urgent is None else web_urgent
            base = hub_base(conf)                    # absolute so iOS Home Screen apps can resolve the tap target (#79)
            web_url = (base + (click or "/app")) if base else (click or "/app")
            web_push(web_title or title, web_msg or msg, url=web_url, tag=tag, urgent=urgent)
        except Exception as err:
            log("web push skipped:", type(err).__name__, err)
    try:
        r = requests.post(f"{NTFY}/{topic or conf['topic']}", data=msg.encode("utf-8"), timeout=10, headers=headers)
        if not topic:
            PUSHLOG.update(at=time.time(), ok=r.ok, title=title, msg=msg[:120], code=r.status_code)
    except requests.RequestException as err:
        log("push failed:", err)
        PUSHLOG.update(at=time.time(), ok=False, title=title, msg=f"failed: {err}"[:120], code=0)


def sign(secret, body):
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def save_settings(E, keys=None):
    """Write only the settings the watcher changed into the settings file, leaving the rest as
    they are, so the watcher's copy never overwrites what you changed in Combo Hub."""
    cur = E.load_json(E.SAVED, {})
    cur.update({k: E.CFG[k] for k in (keys or SYNCED) if k in E.CFG})
    E.save_json(E.SAVED, cur)
    if getattr(E, "MAIN_SAVED", E.SAVED) != E.SAVED:
        main = E.load_json(E.MAIN_SAVED, {})
        main.update({k: E.CFG[k] for k in (keys or SYNCED) if k in E.CFG and k in getattr(E, "SHARED_KEYS", ())})
        E.save_json(E.MAIN_SAVED, main)


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
            if data.get("at", 0) > conf["paused"] and (data.get("cfg", {}).get("auto_sell") or
                                                        data.get("cfg", {}).get("killer_mode") == "on" or
                                                        data.get("cfg", {}).get("maker_mode") == "on"):
                conf.pop("paused")                     # you saved Settings with Auto cash-out on: resume
                push(conf, "▶️ Auto cash-out resumed on the Pi.", priority="low")
            else:
                E.CFG["auto_sell"] = False
                if E.CFG.get("killer_mode") == "on":
                    E.CFG["killer_mode"] = "watch"
                if E.CFG.get("maker_mode") == "on":
                    E.CFG["maker_mode"] = "watch"
        if isinstance(data.get("discount"), dict):          # what Kalshi buyers really pay, learned on the phone
            E.save_json(E.DISCOUNT_FILE, data["discount"])
        conf["settings_at"] = data["at"]
        applied = True
    if applied:
        save_settings(E)
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
    if E.CFG.get("killer_mode") == "on":
        E.CFG["killer_mode"] = "watch"             # pausing also stops killer-deal buying
    if E.CFG.get("maker_mode") == "on":
        E.CFG["maker_mode"] = "watch"              # ...and standing orders, which are cancelled now
        try:
            E.maker_cancel_all("paused from a notification", log)
        except Exception as err:
            log("cancelling standing orders failed:", err)
    save_settings(E, ("auto_sell", "killer_mode", "maker_mode"))
    E.save_json(CONF, conf)
    log("auto cash-out paused from a notification")
    push(conf, "⏸ Automatic selling and killer-deal buying are paused. Alerts continue. To resume, turn them back "
               "on in Combo Hub's Settings.", priority="high")


def mac_alive(conf):
    """For a backup watcher: has the main watcher (the Mac) checked in within 3 minutes?"""
    try:
        r = requests.get(f"{NTFY}/{conf['topic']}-hb/json", params={"poll": "1", "since": "10m"}, timeout=8)
        msgs = [json.loads(x) for x in r.text.splitlines() if x.strip()] if r.ok else []
        hb = json.loads(msgs[-1]["message"]) if msgs else {}
        return time.time() - float(hb.get("at", 0)) < 180
    except (requests.RequestException, ValueError, KeyError):
        return True                                   # can't tell: stay quiet rather than double up


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
                       "host": "Mac" if sys.platform == "darwin" else "Pi",
                       "err": err[:160]})
    try:
        requests.post(f"{NTFY}/{conf['topic']}-hb{'2' if conf.get('role') == 'backup' else ''}", data=body.encode(), timeout=10,
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
    E.DEPRECATION_HOOK = deprecation_alert         # Kalshi retiring something: one push a day per notice
    return E


DEP = {"conf": None}                               # set by main(); the web app's copy only logs
DEP_FILE = os.path.join(HOME, "kalshi_retired.json")
_DEP_LOCK = threading.Lock()


def deprecation_alert(code, conf=None):
    """Kalshi answered with a retirement notice (410, a "deprecated" error code, a Deprecation/Sunset header):
    one plain-English push (web push + ntfy) per code per day. The raw code goes in the log. Returns True if sent."""
    conf = conf or DEP["conf"]
    code = re.sub(r"[^A-Za-z0-9_.:-]", "", str(code))[:60] or "deprecated"
    if not conf or not conf.get("topic"):
        log("Kalshi retirement notice (no push from this copy):", code)
        return False
    day = time.strftime("%Y-%m-%d")
    with _DEP_LOCK:
        try:
            with open(DEP_FILE, encoding="utf-8") as f:
                seen = json.load(f)
        except (OSError, ValueError):
            seen = {}
        if not isinstance(seen, dict) or seen.get(code) == day:
            return False
        seen = {k: v for k, v in seen.items() if v == day}
        seen[code] = day
        try:
            with open(DEP_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(seen, f)
            os.replace(DEP_FILE + ".tmp", DEP_FILE)
        except OSError as err:
            log("retirement notice not saved:", err)
    log("Kalshi retirement notice:", code)
    push(conf, f"Kalshi is retiring something the app uses ({code[:32]}). Claude is looking at it.",
         title="Kalshi change", priority="high", tag="kalshi-retired")
    return True


def auto_updates(conf):
    """Install new versions as soon as they're out, no approval needed. On by default on the Mac
    (you chose this); a Pi keeps waiting for the phone unless turned on."""
    return bool(conf.get("auto_update", sys.platform == "darwin"))


def repo_now():
    """The repo at its newest commit. Plain raw links to main can be up to 5 minutes stale right after a
    publish, so this asks GitHub for the latest commit and reads the files at exactly that commit."""
    try:
        r = requests.get("https://api.github.com/repos/peetah-138/nfl-combo-planner/commits/main", timeout=10,
                         headers={"Accept": "application/vnd.github.sha"})
        sha = r.text.strip()
        if r.ok and re.fullmatch(r"[0-9a-f]{40}", sha):
            return REPO.replace("/main/", f"/{sha}/")
    except requests.RequestException:
        pass
    return REPO


def update_if_newer(E, conf):
    """Install a newer engine and watcher from GitHub. With automatic updates on, any new version
    whose two files agree on it; otherwise only the exact files your phone installed (it sends
    their SHA-256, signed). Returns True if the watcher should restart."""
    base = repo_now()
    try:
        latest = requests.get(base + "version.txt", params={"t": int(time.time())}, timeout=15,
                              headers={"Cache-Control": "no-cache"}).text.strip()
    except requests.RequestException:
        return False
    if re.fullmatch(r"[0-9.]+", latest):
        LATEST_SEEN.update(v=latest, at=time.time())
    if not re.fullmatch(r"[0-9.]+", latest) or latest == getattr(E, "VERSION", ""):
        conf.pop("waiting", None)
        return False
    ok = conf.get("approve") or {}
    auto = auto_updates(conf) and ok.get("version") != latest
    if ok.get("version") != latest and not auto:
        if conf.get("waiting") != latest:
            conf["waiting"] = latest
            log(f"version {latest} is out; waiting until your phone updates to it")
        return False
    try:
        sb = requests.get(base + "nfl_combo_planner.py", params={"t": int(time.time())}, timeout=30).content
        wb = requests.get(base + "watcher/combo_watcher.py", params={"t": int(time.time())}, timeout=30).content
        if not auto and (hashlib.sha256(sb).hexdigest() != ok.get("engine") or
                         hashlib.sha256(wb).hexdigest() != ok.get("watcher")):
            log(f"update {latest} skipped: the files don't match what your phone approved")
            return False
        src, wsrc = sb.decode("utf-8"), wb.decode("utf-8")
        if auto and f'WATCHER_VERSION = "{latest}"' not in wsrc:
            log(f"update {latest} waiting: GitHub is still sending older files")   # mid-publish or a stale copy
            return False
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
    log("updated to", latest, "(automatic)" if auto else "(approved by your phone)", "- restarting")
    return True


UPDATED = {}


def update_loop(E, conf):
    """Checks for new versions on its own thread, so nothing else going wrong in the watcher can ever
    stop an update (a fix) from arriving. After installing, the watcher exits and launchd starts the new one."""
    time.sleep(30)
    last = 0.0
    while True:
        try:
            if conf.pop("update_now", False) or time.time() - last > (600 if auto_updates(conf) else 1800):
                last = time.time()
                if update_if_newer(E, conf):
                    UPDATED["now"] = True
                    time.sleep(20)                  # let the main loop exit cleanly; if it's stuck, exit anyway
                    log("restarting for the update")
                    os._exit(0)
        except Exception as err:
            log("update check failed:", type(err).__name__, err)
        time.sleep(15)


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


ACT_WAIT = 20                    # most seconds a tap (sell, hedge, buy) waits for the web app's lock before "busy"


class ActBusy(Exception):
    """A tap gave up waiting for the web app's lock; nothing was done."""


class TapLock:
    """How a tap takes the web app's lock: the wait is capped at ACT_WAIT seconds (nothing is done when it runs
    out, so a timed-out sell is never sent twice), and while a tap waits, background Live rebuilds stand aside."""

    def __init__(self, lock):
        self.lock, self.count, self.waiting = lock, threading.Lock(), 0

    def hold(self, timeout=None):
        return _TapHold(self, ACT_WAIT if timeout is None else timeout)


class _TapHold:
    def __init__(self, tl, timeout):
        self.tl, self.timeout = tl, timeout

    def __enter__(self):
        with self.tl.count:
            self.tl.waiting += 1
        try:
            got = self.tl.lock.acquire(timeout=self.timeout)
        finally:
            with self.tl.count:
                self.tl.waiting -= 1
        if not got:
            raise ActBusy()
        return self

    def __exit__(self, *exc):
        self.tl.lock.release()
        return False


class RateLimit:
    """A shared token bucket: at most `rate` requests a second on average, bursts up to `burst`."""

    def __init__(self, rate, burst):
        self.rate, self.burst, self.lock = float(rate), float(burst), threading.Lock()
        self.tokens, self.at = float(burst), time.monotonic()

    def take(self, wait=True):
        """Take one token; with wait=True sleep until there is one, else False when there isn't."""
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.burst, self.tokens + (now - self.at) * self.rate)
                self.at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                need = (1 - self.tokens) / self.rate
            if not wait:
                return False
            time.sleep(need)


class HubCache:
    """Recent public reads, kept fresh in the background for whatever the phone asked for lately.
    Display only: nothing that trades reads through here. Polite by design: an entry is only kept warm while
    somebody has asked for it in the last 30 minutes (warming itself never counts as asking), it is warmed
    quickly only while the phone is actually looking and slowly otherwise, a host that answers 429 or 5xx is
    backed off, and the last good copy is served while a host is struggling."""
    FAST, SLOW, STALE_OK = 3, 60, 300            # warm loop beat; idle refresh period; oldest last-good copy served
    RATE, BURST = 6, 20                          # all outbound reads together: ~6 a second on average (the old pace)

    def __init__(self, E):
        self.E, self.lock = E, threading.Lock()
        self.limit = RateLimit(self.RATE, self.BURST)
        self.data, self.wanted, self.cool = {}, {}, {}

    @staticmethod
    def ttl(url):
        if "espn.com" in url or "hockeytech.com" in url:
            return 6                                # live scores: the phone's view is at most ~6s behind the feed
        if "/multivariate_event_collections" in url or "/series" in url:
            return 120
        return 12

    @staticmethod
    def host(url):
        return url.split("//", 1)[-1].split("/", 1)[0] or url

    def get(self, url, params, fresh=False, touch=True):
        key = url + "?" + json.dumps(params, sort_keys=True)
        now = time.time()
        host = self.host(url)
        with self.lock:
            if touch:
                self.wanted[key] = (now, url, params)
            hit = self.data.get(key)
            cool = self.cool.get(host)
        if hit and not fresh and now - hit[0] < self.ttl(url):
            return hit[1]
        if cool and now < cool[1]:                  # this host said slow down: last good copy, or nothing
            if hit and now - hit[0] < self.STALE_OK:
                return hit[1]
            raise requests.ConnectionError(f"backing off {host}")
        self.limit.take()                           # shared with the warm loop: caps the total request rate
        try:
            r = requests.get(url, params=params, timeout=20)
        except requests.RequestException:
            self.note(host, False)
            if hit and now - hit[0] < self.STALE_OK:
                return hit[1]
            raise
        if r.status_code == 429 or r.status_code >= 500:
            self.note(host, False, r.headers.get("Retry-After"))
            if hit and now - hit[0] < self.STALE_OK:
                return hit[1]
        else:
            self.note(host, True)
        val = {"status": r.status_code, "text": r.text}
        if r.ok:
            with self.lock:
                self.data[key] = (time.time(), val)
        return val

    def note(self, host, good, retry_after=None):
        """Count a host's failures in a row: back off 5s, 10s, 20s ... up to a minute (or its Retry-After)."""
        with self.lock:
            if good:
                self.cool.pop(host, None)
                return
            n = (self.cool.get(host) or (0, 0))[0] + 1
            wait = min(60, 5 * 2 ** (n - 1))
            try:
                wait = max(wait, min(120, float(retry_after)))
            except (TypeError, ValueError):
                pass
            self.cool[host] = (n, time.time() + wait)

    def warm(self):
        while True:
            time.sleep(self.FAST)
            now = time.time()
            with self.lock:
                for k in [k for k, (t, _, _) in self.wanted.items() if now - t > 1800]:
                    self.wanted.pop(k, None)
                    self.data.pop(k, None)
                todo = []
                for k, (t, u, p) in self.wanted.items():
                    age = now - (self.data.get(k) or (0,))[0]
                    # asked for in the last minute: keep it as fresh as its ttl; otherwise only a slow refresh
                    if age > (self.ttl(u) - self.FAST if now - t < 60 else self.SLOW):
                        todo.append((-age, u, p))
                todo = [(u, p) for _, u, p in sorted(todo, key=lambda x: x[0])[:60]]   # the stalest first
            for u, p in todo:
                try:
                    self.get(u, p, fresh=True, touch=False)
                except Exception as err:          # one bad read doesn't stop the rest
                    log("hub warm skipped:", type(err).__name__, err)


class HubOdds:
    """Sportsbook lines for the phone, from a second copy of the engine (so changing league here never
    touches the watcher's own). Free lines (ESPN, Polymarket) refresh every 3 minutes; the paid odds
    service is asked at most every 6 hours per league, or every 40 minutes once its games are near,
    so the phone's builds share one set of credits instead of spending them on every tap."""
    FREE_TTL, SHARP_TTL, SHARP_NEAR_TTL, NEAR = 180, 6 * 3600, 40 * 60, 4 * 3600

    def __init__(self):
        self.H, self.lock, self.free, self.sharp = None, threading.RLock(), {}, {}
        self.pending, self.told = {}, {}

    def engine(self):
        if self.H is None:
            self.H = load_engine()
            self.H.present = self.H.loading = lambda *a, **k: None
            try:                                    # the shadow, buy ideas and killer deals write history too
                self.H.store_open(os.path.join(HOME, "combo_history.db"))
            except Exception as err:
                log("history off for the odds engine:", err)
            self.H.console_note = lambda msg: log(msg)
        return self.H

    @staticmethod
    def soonest(snap):
        import datetime as dt
        now, best = time.time(), None
        for start in (snap.get("kick") or {}).values():
            try:
                t = dt.datetime.fromisoformat(str(start).replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if t > now and (best is None or t < best):
                best = t
        return best

    def note_moves(self, league, old, new):
        """Remember sharp moves (8+ points) on games within a day."""
        import datetime as dt
        soon = time.time() + 86400
        for team, v in new["fair"].items():
            was = old["fair"].get(team)
            if not was or abs(v[0] - was[0]) < 0.08 or team in self.told.get(league, {}):
                continue
            try:
                kick = dt.datetime.fromisoformat(str(new["kick"].get(team)).replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if time.time() < kick < soon:
                self.pending.setdefault(league, []).append((team, was[0], v[0], new["opp"].get(team, "")))
                self.told.setdefault(league, {})[team] = time.time()

    def moves(self, league, held):
        """Messages for line moves since last asked: games you hold first, then other near games."""
        with self.lock:
            got = self.pending.pop(league, [])
            for t, at in list(self.told.get(league, {}).items()):
                if time.time() - at > 6 * 3600:
                    del self.told[league][t]
        out = []
        for team, a, b, opp in got:
            if b < a:                                 # report each game once, from the side that rose
                continue
            mine = team in held or opp in held
            out.append(f"{'⚠️ Your game: ' if mine else '📉 '}sportsbooks moved to {team} {b:.0%} "
                       f"(from {a:.0%}) vs {opp}. Often injury or lineup news.")
        return out

    def get(self, league, key):
        with self.lock:
            H = self.engine()
            H.set_league(league)
            now = time.time()
            f = self.free.get(league)
            if not f or now - f[0] > self.FREE_TTL:
                old = f
                f = (now, H.free_snapshot(H.league_codes()))
                self.free[league] = f
                if old:
                    self.note_moves(league, old[1], f[1])
            sh = self.sharp.get(league)
            if key:
                soon = self.soonest(f[1])
                ttl = self.SHARP_NEAR_TTL if soon and soon - now < self.NEAR else self.SHARP_TTL
                if not sh or now - sh[0] > ttl:
                    got = H.sharp_snapshot(key)
                    if got["fair"] or not sh:
                        sh = (now, got)
                        self.sharp[league] = sh
                    log(f"odds service asked for {league}: {len(got['fair'])} teams")
            snap = H.merge_books(sh[1] if sh else H.empty_snapshot(), f[1])
            if sh:
                snap["note"] += f" Sportsbook lines checked {int((now - sh[0]) / 60)} min ago (shared by the Mac)."
            return snap


class Notifier:
    """Urgent alerts (cash-outs, hedges, anything done automatically, combos at risk) go out at once.
    Everything else waits and goes out together, at most once every 30 minutes, never 10 PM-7 AM.
    Each kind can be switched off in the phone's Settings."""
    URGENT = ("cash out", "cashing out", "cashed out", "cash-out", "hedge", "auto", "turning", "at risk", "can't", "couldn't",
              "refused", "paused")
    SWITCH = {"value": "notify_value", "price": "notify_price", "cash": "notify_cash", "news": "notify_news"}

    def __init__(self, conf, E, every=1800):
        self.conf, self.E, self.every = conf, E, every
        self.q, self.last, self.lock = [], 0.0, threading.Lock()

    def add(self, msg, kind=None, url=None):
        low = msg.lower()
        if kind in ("value", "price") and url:          # a buy idea: worth seeing now, while the price holds
            BUS.publish({"kind": "idea", "text": msg})
            if not self.E.CFG.get(self.SWITCH[kind], True):
                return False
            now, hour = time.time(), time.localtime().tm_hour
            if 7 <= hour < 22 and now - getattr(self, "last_idea", 0) >= 600:
                self.last_idea = now
                push(self.conf, msg, title="Buy idea", priority="default", click=url, tag="idea")
                return True
            return True                                  # it's waiting in Combo Hub's Do now list
        kind = kind or ("cash" if ("cash" in low or "hedge" in low) else "info")
        auto_done = "auto" in low and ("cashed" in low or "hedged" in low or "sold" in low)
        if kind in self.SWITCH and not self.E.CFG.get(self.SWITCH[kind], True) and not auto_done:
            return False                              # switched off (actions it took are always reported)
        if kind in ("cash", "info") and any(w in low for w in self.URGENT):
            push(self.conf, msg.replace("Open the planner to confirm.", "Open the planner to cash out."),
                 pause_button=bool(self.E.CFG.get("auto_sell")), web_title="Combo Hub", web_urgent=True, tag="urgent",
                 web_msg=msg.replace("Open the planner to confirm.", "Tap to decide."))
            BUS.publish({"kind": "alert", "text": msg})
            return True
        with self.lock:
            if msg not in self.q:
                self.q.append(msg)
        return True

    def flush(self, now=None):
        now = now or time.time()
        hour = time.localtime(now).tm_hour
        with self.lock:
            if not self.q or hour >= 22 or hour < 7 or now - self.last < self.every:
                return 0
            msgs, self.q = self.q, []
        self.last = now
        body = "\n".join("• " + m for m in msgs[:8]) + (f"\n(+{len(msgs) - 8} more)" if len(msgs) > 8 else "")
        push(self.conf, body, title=f"{len(msgs)} update{'s' * (len(msgs) != 1)}", priority="low", tag="digest")
        return len(msgs)


class Bus:
    """Live events for open Combo Hub screens (scores, swings, advice, settled combos, refreshes)."""
    def __init__(self):
        self.subs, self.lock, self.n = [], threading.Lock(), 0

    def sub(self):
        import queue
        q = queue.Queue(maxsize=200)
        with self.lock:
            self.subs.append(q)
        return q

    def unsub(self, q):
        with self.lock:
            if q in self.subs:
                self.subs.remove(q)

    def publish(self, ev):
        with self.lock:
            self.n += 1
            ev = dict(ev, id=self.n, at=time.time())
            for q in list(self.subs):
                try:
                    q.put_nowait(ev)
                except Exception:
                    pass


BUS = Bus()


def is_local(handler):
    """A request from this Mac itself, not one that came in through Tailscale's https front door
    (which also arrives from 127.0.0.1, but carries forwarding headers)."""
    h = handler.headers
    return (handler.client_address[0] == "127.0.0.1" and not h.get("X-Forwarded-For")
            and not h.get("Tailscale-User-Login") and not h.get("Forwarded"))


def is_https(handler):
    """The request reached us through Tailscale's https front door (it says so in X-Forwarded-Proto)."""
    return (handler.headers.get("X-Forwarded-Proto") or "").lower() == "https"


# ---- https through Tailscale (a private address with a real certificate; needed for iPhone notifications)
# Where the Tailscale command line lives. The wrapper in /usr/local/bin is the safe one under launchd; the app's own
# binary only acts as a command line when TAILSCALE_BE_CLI=1 is set (otherwise it says "GUI failed to start"), so it is last.
TS_CLI_PATHS = ("/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale")
TS_CLI_PATHS_LATE = ("/usr/bin/tailscale",)
TS_APP_BIN = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
TS_WAIT = 120             # seconds to wait for the first certificate after `serve` (it can take a minute or two)
TS_PROBE_SLEEP = 3
TS_RETRY = 300            # while the secure address isn't on, look again every 5 minutes
TS_RECHECK = 1800         # once on, make sure it is still serving every 30 minutes
HTTPS_LOCK = threading.Lock()
ENABLE_HTTPS_HELP = ("HTTPS certificates are not enabled in Tailscale admin. On the Mac or iPhone open "
                     "login.tailscale.com/admin/dns, sign in, scroll to HTTPS Certificates, tap Enable HTTPS..., "
                     "confirm, then tap Try again here.")
ADMIN_DNS_URL = "https://login.tailscale.com/admin/dns"


TS_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def tailscale_clis():
    """Every Tailscale command line on this Mac, best first (no duplicates): the wrapper script and Homebrew, then
    whatever is on PATH, the app's own binary last. Each is tried in turn until one answers."""
    import shutil
    out = []
    for p in (*TS_CLI_PATHS, shutil.which("tailscale"), *TS_CLI_PATHS_LATE, TS_APP_BIN):
        if p and p not in out and os.path.exists(p):
            out.append(p)
    return out


def tailscale_cli():
    clis = tailscale_clis()
    return clis[0] if clis else None


def tailscale_env():
    """launchd gives the watcher a bare environment (PATH /usr/bin:/bin:/usr/sbin:/sbin, maybe no HOME). Add the
    usual places, keep HOME and set TAILSCALE_BE_CLI=1 so the app's binary acts as a command line."""
    env = dict(os.environ)
    parts = [x for x in (env.get("PATH") or "").split(":") if x]
    parts += [x for x in TS_PATH.split(":") if x not in parts]
    env["PATH"] = ":".join(parts)
    env.setdefault("HOME", os.path.expanduser("~"))
    env["TAILSCALE_BE_CLI"] = "1"
    return env


# Where a real install keeps its files. Anything else (a test's temp folder, dev.sh's throwaway home) is not allowed to
# run the Tailscale command line at all: `tailscale serve` re-points Pete's real secure address, and a test run once
# pointed it at a fake hub that then went away. COMBO_NO_TAILSCALE=1 (set by every test harness) blocks it too.
TS_FAKE_OK = False        # only the secure-address test sets this, and then only a fake command line in a temp folder runs


def tailscale_blocked():
    """Why the Tailscale command line must not run in this process (a short reason), or '' when it may."""
    if os.environ.get("COMBO_NO_TAILSCALE", "").strip() not in ("", "0"):
        return "COMBO_NO_TAILSCALE is set (a test or dev run)"
    real = {os.path.realpath(os.path.expanduser("~/combowatch")), os.path.realpath("/var/lib/combowatch")}
    if os.path.realpath(HOME) not in real:
        return f"{HOME} is not a real install folder (a test or dev run)"
    return ""


def tailscale_run(cli, args, timeout):
    """Run the Tailscale command line the way it needs under launchd: no terminal (stdin closed), a sane PATH and
    TAILSCALE_BE_CLI=1 so the app's own binary acts as a command line instead of starting the GUI.
    Hard safety net: refuses (OSError) outside a real install. The secure-address test may run its own fake script
    from a temp folder (TS_FAKE_OK), never a real one."""
    import subprocess, tempfile
    why = tailscale_blocked()
    if why:
        fake = TS_FAKE_OK and os.path.realpath(cli).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep)
        if not fake:
            raise OSError(f"refusing to run tailscale {' '.join(args[:1])}: {why}")
    return subprocess.run([cli, *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                          env=tailscale_env())


# What the command line prints when it can't reach the Tailscale app (as opposed to failing to start itself).
TS_NO_DAEMON = ("failed to connect to local tailscale", "is tailscale running", "connection refused",
                "tailscaled", "localapi", "local api", "socket")
TS_CLI_BROKEN = ("gui failed to start", "clierror", "cli failed to start", "system extension")
# What `tailscale serve` prints when the tailnet hasn't turned on HTTPS certificates.
TS_HTTPS_OFF = re.compile(r"serve is not enabled|https (?:certificates )?(?:is |are )?not enabled|enable https|"
                          r"certificates? (?:is |are )?not enabled|https is disabled", re.I)
# The real reason and the next step for each BackendState that isn't Running.
TS_BACKEND = {
    "NeedsLogin": ("signed-out", "Tailscale says this Mac is signed out (NeedsLogin). Open the Tailscale app on the "
                                 "Mac, sign in, then tap Try again."),
    "NeedsMachineAuth": ("needs-approval", "This Mac is signed in to Tailscale but waits for approval "
                                           "(NeedsMachineAuth). Approve it at login.tailscale.com/admin/machines, "
                                           "then tap Try again."),
    "Stopped": ("ts-off", "Tailscale is signed in but switched off on this Mac (Stopped). Open the Tailscale app, "
                          "turn it on (Connect), then tap Try again."),
}


def tailscale_status():
    """Ask each Tailscale command line for `status --json` until one gives a JSON object.
    Returns (cli, status, None), or (None, None, (state, detail)) with the real reason it couldn't."""
    import subprocess
    clis = tailscale_clis()
    if not clis:
        log("https: no Tailscale command line found")
        return None, None, ("no-cli", "No Tailscale command line on this Mac (looked in /usr/local/bin, "
                                      "/opt/homebrew/bin, PATH and the Tailscale app). Install the Tailscale app, "
                                      "open it once, then tap Try again.")
    fails = []
    for cli in clis:
        try:
            p = tailscale_run(cli, ["status", "--json"], 15)
        except subprocess.TimeoutExpired:
            log("https: `tailscale status` timed out:", cli)
            fails.append(("timeout", "no answer in 15 s"))
            continue
        except (OSError, subprocess.SubprocessError) as err:
            log("https: couldn't run", cli, type(err).__name__, str(err)[:120])
            fails.append(("oserror", str(err)[:120]))
            continue
        raw = (p.stdout or "").strip()
        try:
            st = json.loads(raw)
            if not isinstance(st, dict):
                raise ValueError("not an object")
            return cli, st, None
        except ValueError:
            seen = " ".join(((p.stderr or "").strip() + " " + raw).split())[:160]
            log(f"https: `{cli} status --json` gave nothing usable (exit {p.returncode}): {seen!r}")
            fails.append(("output", seen))
    said = " | ".join(s for _, s in fails if s)
    low = said.lower()
    if any(k in low for k in TS_NO_DAEMON):
        return None, None, ("no-daemon", f"Couldn't read Tailscale's status: the command line can't talk to the "
                                         f"Tailscale app ({said[:120]}). Open the Tailscale app on the Mac, check it "
                                         "says Connected, then tap Try again.")
    if any(k in low for k in TS_CLI_BROKEN):
        return None, None, ("cli-broken", f"Couldn't read Tailscale's status: its command line wouldn't start from "
                                          f"the watcher ({said[:120]}). On the Mac open Tailscale's settings, install "
                                          "the command line (CLI integration), then tap Try again.")
    if all(k == "timeout" for k, _ in fails):
        return None, None, ("no-status", "Couldn't read Tailscale's status: Tailscale didn't answer in time. "
                                         "It checks again by itself in a few minutes.")
    return None, None, ("no-status", f"Couldn't read Tailscale's status: {said[:140] or 'no output'}. "
                                     "Open the Tailscale app on the Mac, then tap Try again.")


def _https_set(conf, state, **kw):
    conf["https"] = dict({"state": state}, **kw)
    return None


def tailscale_https(conf, port):
    """Ask Tailscale to serve Combo Hub at https://<this-mac>.<tailnet>.ts.net. If the tailnet hasn't
    allowed https yet, keep the one-time link that turns it on, for Settings > This Mac.
    Every way out is logged and leaves conf["https"] saying what is actually wrong."""
    import subprocess
    blocked = tailscale_blocked()
    if blocked and not TS_FAKE_OK:
        log("https: not touching Tailscale:", blocked)
        return _https_set(conf, "off-in-tests", detail="Secure address is off here: " + blocked + ".")
    with HTTPS_LOCK:
        cli, st, why = tailscale_status()
        if why:
            log("https not on yet:", why[0], why[1][:160])
            return _https_set(conf, why[0], detail=why[1])
        backend = str(st.get("BackendState") or "")
        name = ((st.get("Self") or {}).get("DNSName") or "").rstrip(".")
        if backend and backend != "Running":      # only BackendState itself may say signed out
            state, detail = TS_BACKEND.get(backend, ("starting", f"Tailscale is still starting on this Mac ({backend}). "
                                                                 "It checks again by itself in a few minutes."))
            log("https: Tailscale isn't running:", backend)
            return _https_set(conf, state, detail=detail)
        if not backend and not name:
            log("https: Tailscale's status had no BackendState and no name")
            return _https_set(conf, "no-status", detail="Couldn't read Tailscale's status: it answered without a "
                                                        "state. Open the Tailscale app on the Mac, then tap Try again.")
        if not name:
            log("https: Tailscale is running but this Mac has no machine name (is MagicDNS on?)")
            return _https_set(conf, "no-name", detail="Tailscale gave this Mac no name. Turn MagicDNS on at "
                                                       "login.tailscale.com/admin/dns.")
        certs_off = not st.get("CertDomains")
        url = f"https://{name}"
        try:
            r = requests.get(url + "/sw.js", timeout=8)
            if r.ok and b"Combo Hub" in r.content:
                conf["https"] = {"state": "on", "url": url}
                log("https on:", url)
                return url
        except requests.RequestException:
            pass
        try:
            p = tailscale_run(cli, ["serve", "--bg", str(port)], 25)
            out = (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired as err:
            out = ((err.stdout or b"").decode() if isinstance(err.stdout, bytes) else (err.stdout or "")) + \
                  ((err.stderr or b"").decode() if isinstance(err.stderr, bytes) else (err.stderr or ""))
            log("https: `tailscale serve` didn't finish in 25 s:", out.strip()[-120:])
        except (OSError, subprocess.SubprocessError) as err:
            out = str(err)
            log("https: couldn't run `tailscale serve`:", out[:120])
        link = re.search(r"https://login\.tailscale\.com/\S+", out)
        certs_off = certs_off or bool(TS_HTTPS_OFF.search(out))
        tls_seen, deadline = False, time.time() + TS_WAIT
        while True:
            try:
                r = requests.get(url + "/sw.js", timeout=8)
                if r.ok and b"Combo Hub" in r.content:
                    conf["https"] = {"state": "on", "url": url}
                    log("https on:", url)
                    return url
            except requests.exceptions.SSLError:
                tls_seen = True                  # the name answers but its certificate isn't issued yet
            except requests.RequestException:
                pass
            if link or certs_off or time.time() + TS_PROBE_SLEEP >= deadline:
                break
            time.sleep(TS_PROBE_SLEEP)
        tail = out.strip()[-300:]
        if link:
            state, extra = "need-enable", {"link": link.group(0), "detail": tail}
        elif certs_off:
            state, extra = "need-enable", {"link": "", "admin": ADMIN_DNS_URL, "detail": ENABLE_HTTPS_HELP}
        elif tls_seen:
            state, extra = "issuing", {"detail": "Tailscale is still making the certificate. This can take a few minutes."}
        else:
            state, extra = "failed", {"link": "", "detail": tail}
        conf["https"] = dict({"state": state}, **extra)
        log("https not on yet:", state, extra.get("link") or extra.get("detail", "")[-160:])
        return None


def https_loop(conf, port):
    """Keep trying: enabling HTTPS in Tailscale's admin, or Tailscale finishing its start at login, is picked up
    without a tap. Quiet once it is on (a light check every 30 minutes)."""
    if tailscale_blocked() and not TS_FAKE_OK:
        log("https: not checking Tailscale:", tailscale_blocked())
        return
    while True:
        try:
            tailscale_https(conf, port)
        except Exception as err:
            log("https check failed:", type(err).__name__, err)
            conf["https"] = {"state": "failed", "detail": f"{type(err).__name__}: {str(err)[:100]}"}
        time.sleep(TS_RECHECK if (conf.get("https") or {}).get("state") == "on" else TS_RETRY)


# ---- iPhone notifications (Web Push from the home screen app; needs the https address)
def _b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Push:
    """VAPID keys made on this Mac, subscriptions from your devices, and the encrypted send (RFC 8291)."""
    def __init__(self, home):
        self.key_path = os.path.join(home, "vapid_private.pem")
        self.sub_path = os.path.join(home, "push_subs.json")
        self.lock = threading.Lock()
        self.key = None

    def ok(self):
        try:
            import cryptography  # noqa: F401
            return True
        except ImportError:
            return False

    def private(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        if self.key:
            return self.key
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as fh:
                self.key = serialization.load_pem_private_key(fh.read(), None)
        else:
            self.key = ec.generate_private_key(ec.SECP256R1())
            pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(pem)
        return self.key

    def public_b64(self):
        from cryptography.hazmat.primitives import serialization
        return _b64u(self.private().public_key().public_bytes(serialization.Encoding.X962,
                                                               serialization.PublicFormat.UncompressedPoint))

    def subs(self):
        try:
            with open(self.sub_path) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return []

    def add(self, sub, label=""):
        if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://"):
            return False
        keys = sub.get("keys") or {}
        if not keys.get("p256dh") or not keys.get("auth"):
            return False
        with self.lock:
            cur = [x for x in self.subs() if x.get("endpoint") != sub["endpoint"]]
            cur.append({"endpoint": sub["endpoint"], "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]},
                        "label": str(label)[:60], "at": int(time.time())})
            fd = os.open(self.sub_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump(cur[-10:], fh)
        return True

    def remove(self, endpoint):
        with self.lock:
            cur = [x for x in self.subs() if x.get("endpoint") != endpoint]
            fd = os.open(self.sub_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump(cur, fh)

    @staticmethod
    def encrypt(sub, payload):
        """aes128gcm content encoding for one subscription (RFC 8188 + RFC 8291)."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ua_pub = _b64u_dec(sub["keys"]["p256dh"])
        auth = _b64u_dec(sub["keys"]["auth"])
        eph = ec.generate_private_key(ec.SECP256R1())
        as_pub = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
        ikm = HKDF(hashes.SHA256(), 32, auth, b"WebPush: info\x00" + ua_pub + as_pub).derive(shared)
        salt = os.urandom(16)
        cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
        nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
        body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
        rs = 4096
        return salt + rs.to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + body

    def vapid(self, endpoint):
        from urllib.parse import urlparse
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        u = urlparse(endpoint)
        head = _b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
        claims = _b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                                   "sub": "https://github.com/peetah-138/nfl-combo-planner"}, separators=(",", ":")).encode())
        msg = f"{head}.{claims}".encode()
        r, s_ = decode_dss_signature(self.private().sign(msg, ec.ECDSA(hashes.SHA256())))
        jwt = f"{head}.{claims}.{_b64u(r.to_bytes(32, 'big') + s_.to_bytes(32, 'big'))}"
        return f"vapid t={jwt}, k={self.public_b64()}"

    def send(self, title, body, url="/app", tag=None, urgent=False):
        if not self.ok():
            return 0
        subs, sent = self.subs(), 0
        data = json.dumps({"title": title, "body": body[:400], "url": url, "tag": tag or ""}).encode()
        for sub in subs:
            try:
                r = requests.post(sub["endpoint"], data=self.encrypt(sub, data), timeout=10, headers={
                    "Authorization": self.vapid(sub["endpoint"]), "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream", "TTL": "3600", "Urgency": "high" if urgent else "normal"})
                if r.status_code in (404, 410):
                    self.remove(sub["endpoint"])          # that device unsubscribed
                elif r.ok:
                    sent += 1
                else:
                    log("push refused:", r.status_code, r.text[:120])
            except Exception as err:
                log("push failed:", type(err).__name__, err)
        return sent


PUSH = Push(HOME)
ICON_PNG = "iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAIAAACyr5FlAAAPYklEQVR42u2dWYwcVxWGv3urx+7N0+OETRgTxzbgIewQwhYJxAu8gEQISwQoxEtYsvEAWcwqREBISDwgwDsGZSGASLATwHYgJg6EXYASg4AYiS2I1ZOZXsZddXmo6qmqrqqe6ur29HZalmLn1lTXf+qbu5x7zznq6m0GMHgfo1p/ARTRJu+fKvD/267spin+e7tsSv/woqsrXdr9b+srUK0LVfB7AiJU6+/+j3TT1HbD+O9drin+keIeXnRl0+V+9LLfp1pNqtXUix2VCdwtqx1DN8lqR9HVocm9iU7Jo+rr75nqx++Z6sfvmejq0KS7/T7VVzuqfthR9cOOoivapMWOoiupSYsdRVdSkxY7iq6kJi12FF1JTVrsKLqSHl6LHUVX0sPrXvwtYsfx1qX75W8RPsZPl0bsKLo6OMHEjqIr0QlGJqe92HHsdenofqDYUXSpJQ+p2FF0JTrBxI6iK94JJnYUXUm6tNhRdLXpUm1OMLGj6IqeH9NiR9GV1H9osaPoSmrSYkfRlRTfoMWOoispvkGLHUVXUpMWO4qupCYtdhRdSU1a7Ci6kpq02FF0JTVpsaPoSmrSYkfR1asTTOw4gbp0L/kkxI7jrUvTp3wSwsf46dK956MRO46rLh2b8kfsKLpUzIRU7Ci6TIddWbGj6DLB1YrwIbpinGAgfIiueCdYaLUifIiu9tAE4UN0xeXH1cH7Ch+iKxSa0HZf4UN0+aEJKnJf4UN0EZxzKOFDdEXqN4QO+wgfoiuYryXgBBM+VlaXUig11LrCTjDhY0X2wS2NArtJ08YYcrrd5kOiy49bET5WYp9TYducnqfpMF2iUsTS/G+eM2ew1NDpyqnW/EMF5iLKeKW/3Fa/yaCUf70J/tN4RcVU9MqEJvcOKBRxV6Zrar8y8oRdNaV/+Ay6tGahRmUNr3slL3kO654Ahv8+xs9OcuzH/P7PTJdxAu9m8Lo+fpkxhErAmUAFORMgxpydencZitpFm3op1hf/SP3WZWmqDTau5+rLOH8dbZ/5Kl/4Ovf9gkLe42MYdGmMP47I+HKW/NCWptbgnGk+9h7OX0fTxjGY1h/bplzk/e/gwmeyUPMWkMOgK7LxJnz02w+tNY1FykV2XsmaErZDzkKr1mpFYVk4Dsbwvst4/AzN5rDMT3W0qqDw0Uc+cprFBqU8H7uKTetxHCxN9KM1jqFS5qJnUWug1VDo0iqu6qTw0Rc+LE19kVKBj17FxqdgO+g4MoIz0BdfgKVbtx20Lt329cJHX/hwO4NGg3KBj1zFxvXYCX1GiA9FaTUWw6JLR4c34aNXPgw5zeIipQIfTk2G+2k6vu9g4Lp0sICx8NEXPixNvUGpwEeu7oIM936/+QNN21/pDFaX7z5XwkdfxmlNY5FSgQ9dzfnpyTAAjsODv2L1lOfqGLgu3Z59UvjogQ9LtUaTa7obTRyDpfnKYR75M/mpQJGTgerSMdlJhY9MfHhrkzwfuqa7PsNd3x4+zjfvpVTAcYZFlx9lL3z0YkfL9XQV+OC13ZFhDFqz6w4+dyurVw2XLh2MohY+stlRaxp1SgV2ZiJj9x3cdS/nVLKUzDq7utqi7IWP9HZ0m7xVazFjn7H7Du68l7UVbBt3n2tIdKmYuBXho5umpVXrzuvYkK3POMbaaWx7uHTFO8GEj5RN3o5ag1KBm65lw3psuzsy9nyVbx1jbQXHHtJ+Mew+Fz5SN3k7akVuuo4NT8W2sazuyZjGsYe3X4y4z4WPFE3uaFIscGNWMg4dC8wzhrBfXHKCKYMSPlIPxlp5fcaN78tCxt7bOXSUmeA8Y/j48EMTiL5+4SOhydKcWaRY5IZMZOy7nUOB0WTI51XtTjDho7Oxmk2mprg+Gxm3cegoayvYzmjMq2KcYKPOh1Io7cWG9NGOSmEcFhtc8fYsZOy/ncPHmJnGbo7MvDsctzKafKjA+9MaY9OoUa1yZtFbcPZuR6XAUK9z5VZeelH3ZNzGoaPMVLx9k1GZd0fmHCPIx9I5XsdmYZ6pVWx+Os9+Lk95KhgWHkMpX2cGO2oFDvU6O7Zy8cuzkHH4qOfpGq11WS4Uy7R0tkD5gUyhuKZwNBGBsCKlIvdZwfionEV1geIaXvN6LrqYc84FcGz+/jfuO8qJ+9A5pqb8wT59fBQKY6jV2b4tCxkHbuPuo8xUvLXJaMV9qc++2bTHMhGKijHRuCYVE+m0FN3Ufp+zHx+lcyzMc95G3raDdef5r0e1LvvlT7nlANUqq1Z7fKSMj3ItVauzfSuveEUWMg4fYaaC7Yxk3JdWJiFuZUTGF8tiYY5Nz+Canaw7D9v2TlV5PZnBtnn+hVz7AYoFFhu+h3vZet1ufEC9lpWMW7n7iO8dH8V1u1/Ga/T4MFgW84+xeQvv+QCFIo6DZfkdhouIZWHbrN/AtddTSMfHUn9br7NtWxYyvnQr9xwJzzNGkA+tArcbLT5yFvNzPG0L777eIyMpKsSycGzWb+C6FHx4vY6hXmNrJjIO3so9R7x5RtsZ4hHz6wQ9piPEh5Vjfo7NW3jXcmR4K47UfOjWqnXb9i7IcI8Ha81Xbufu7zBTae2ojXL+oPDG24jw4c4zNs/yrhtSkZGeD60wDvUaW7fz8m7IcK88foJ7vstMBbs5DvmlInErQ89HLsf8aTZt4cpuyEjDh1IYQ6POFZnIuP8B9h6gXMKYMck/Fhe3MsR8WBbzc2yezUJGIh9Wa57hUHfJuDgLGbv3kV/d8hyMRX66ULnyIefDyrEwx6Yt7LgxIxmxfDTq5CxvbXLFdl7WPRknHmDPPgp5b/9lbPIXhtznw8xHziVjtlcyonyUitSqLDZ4546sZOwln/fWOOOU31IrE8lBOXx8WBbzp9k0y/Z+kNHOxw2Uy7xjayYyTnhkaDDOuOU/VZ+/1ATd2zF+ccUg/eugp5ifY+Ms227qGxm+68FBaapVisWQxz0lGXv3ki94+y/Dk3+sX/51rcK/vsPWf1g5Fk6zcZbt3ZDhxhim+SiNMRnJ2LeXQj7sPRuv/Mm67djgUPHhzjNcMvJFTGoy3IMdmHR8qK7JeOAE+/Z48ww3GeNY5tdud4INCR9La5ONs2zb6ZGhdCo3pVLMz3H0Lq+3NyYVH92SUXDnGWYM868vvescgZMWJnD8gsgJDPe4wMqc/3C94xtnuaJLMrSmVmXfZ/j1zzn9X954eStoPd3rX56M+9m/h0JrnuEe0Rj+/Lh02eTeKy5uZdD9h2VRPZ2djF2f5A8P86Qn871DfO0AWqftP5Yl44f3cyA4mgQmh2PZf4Q8pMPARy5H9TTnz/LObsgwLTJ2f4pHfkt5DWcaVGb4/uE+8LFExv7d5PPe/osa9/oe/mEfhoMPbTH3HzZcwOUf7I4MpalV2fNJHnmYcisqxG72gQ+/z9hNodCavY57/Rf/8OyQ8KE1jSovejWX78xIxh9PUl6Dfcb/oh75cMn40f18aTd5d9XqTER9oFAg9cD50Ir6As94AW+6jrzrdeiGjL03e31GKJdBb3wskXFgV2s0MZNVPyoQtzJAPhT2GWbO5Q3vxRiMk2pxESLjJOVpnGa8sTLw4fcZuzxPlzETV18sHLcyID60ZrHOlgspVboeTfbdzKmTlKexm52M1RUfHhk/4OAXAztqk1d/Tre/10Hw4R4VfvoL03oqXTLqVfZ9glMPUVrjxRh2Pj/Wxoe7+o3xu9tYFg/+gC9/sbWjZia0PqGOea8rzoc7suSLXZPxp5OUpnGaac8X+nzs9w4DOzaO0/pjoxTa4off58u7yC+tTSa1fmWuPRCtdalRId/lWfWfuhcvzRjSkLG/RYbbZ5jU8XN2k+kZjn+bR//CpVt5Urho0vwch7/O8SMUSv5e69jXF0vSpfa/0cRulJvw3m5oP73f+/vKojrHq97KK9+CY6OtTjtq9QUO3MypkxSnvXO8GeLndI5aldV5nnsRT7uAtedSq/LH3/HLB/nXvyiUwMGZjPpiHR5eHbjEmPBPrjwfSnOmwePWs+MzYFA6Znxxj9LUaxy8mVMPUarQtHuKr1QWjk2t5rHixsatyjM1hWMmq/5c0sMnJIxb4fmHw6o8j57ie7egLYzjoeDvm9gojdLc8mlOPUS54me5yBzfYGyUolSmVCa/mkKR8jS5HI4j9W/DZ0iVGSQf7qvKF/nRXfzkHrTlrWZdn4frVl+sc+cXeOTXrGnNM/oSH2Ucr76ascNBrcIHqIOXmOiIMJDxxV08VR/jea/mwtfy5E3e5KNR408PcfwbnHqYUgXHlvqmKzS+qIOXhCekg+ZDWdQW0DmeuIFSBeDfj/LPv6JzrCr40afCxwrwkaNtXWr80ysrv7414NjkSxjDP05h2xiwpiiUMAbTDC35pH722V7fxsWtmAHPT40NhlWryZcolJiawjjt1yP518/+/KPdfT4kfODufTgeFpL/dCB86Ki5h4cPyX86WD50rLmFD+GjU7ly4WNi+VDtTjDhQ/gI53Vl2XLlwsck9x/LlysXPia2/4iLWxE+Jp6PUKUmhA/hg2gxHoPwIXzENunoyxM+hA/fzyF8CB+JoQnCh/AR26STcqcIH8KH7pBbR/iYcD606ph7SfiYZD50/HsVPoSPaLly4UP48IvxYBA+hI94J5iK/IDwIXyo0FJW+BA+ok4wf1dW+BA+ovk5om9I+BA+4uJWhA/hI+gEEz6Ej2VOggkfwkfECRZnbuFjkvlQvhMswdzCx8TyQcgJJnwIH3H9xzLlyoWPSe4/li9XLnxMIB8JcSvCh/DhhyZE36vwIXwsTUiFD+GDDikYhA/hIyYPaYdcW8LHhPOho7YTPoQPFZpzCB/CR6RJJ9lO+BA+tEq2nfAx4XzoJAMJH8KH7mAg4WPC+UiotyJ8CB/Bwz7Ch/ARU4xH+BA+4p1gBIJWhA/hI+QEI06w8CF8tG/ZCx/CR7sTTPgQPjo5wYQP4aOTE0z4ED46OcGED+GjkxNM+BA+/GI8nctRCx8TyAehk2DCh/AR13+EMvsIH8JHpDpkCnMLHxPFR7wTTPgQPpaeXCfZVPiQ/kOTbFPhY8L50FHbCR/CR/thH+FD+IjJQyp8CB+xTVol2074mHA+dNSswofwQXy9lTg++uVf71d+KfrEB33igz7xQQo+eq8znZ6PuLiV5N+tHvnoV/4xlZ4P04mP2KdSpms+lj2+H8NHx76wAx+qh/4jaECVgg8da+5sfNAnPugTH/HPsywfHe7TYaxM0X8s8zyp+ehL/0GK/uP/bBblkfvF4wkAAAAASUVORK5CYII="

SW_JS = """// Combo Hub service worker: shows the Mac's notifications and opens the right screen when tapped.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data.json(); } catch (x) { d = {title: 'Combo Hub', body: e.data ? e.data.text() : ''}; }
  e.waitUntil(self.registration.showNotification(d.title || 'Combo Hub',
    {body: d.body || '', tag: d.tag || undefined, data: {url: d.url || '/app'}, icon: '/icon.png', badge: '/icon.png'}));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || '/app', self.location.origin).href;
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(cs => {
    for (const c of cs) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
"""

MANIFEST = json.dumps({"name": "Combo Hub", "short_name": "Combo Hub", "start_url": "/", "scope": "/", "display": "standalone",
                       "background_color": "#0b0d12", "theme_color": "#0b0d12",
                       "icons": [{"src": "/icon.png", "sizes": "180x180", "type": "image/png"}]})


def ensure_crypto():
    """iPhone notifications need the cryptography package; an update that came in without the installer
    adds it quietly the first time (uv is what the installer set the Mac up with)."""
    if PUSH.ok() or sys.platform != "darwin":
        return
    import shutil, subprocess
    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    if not os.path.exists(uv):
        return
    try:
        subprocess.run([uv, "pip", "install", "-q", "--python", sys.executable, "cryptography"], timeout=300,
                       capture_output=True)
        log("installed cryptography for iPhone notifications" if PUSH.ok() else "couldn't install cryptography")
    except (OSError, subprocess.SubprocessError) as err:
        log("cryptography install failed:", err)


def panel_wait(H, every, step=2):
    """Sleep until the next buying pass: `every` seconds, or sooner (within `step`) once Approve / Add asks for one.
    Clears the request, so the pass that follows covers it and a tap during that pass asks again."""
    end = time.time() + every
    while time.time() < end:
        if H is not None and H.buy_asked():
            return True
        time.sleep(min(step, max(0.0, end - time.time())))
    return bool(H is not None and H.buy_asked())


def panel_loop(odds, conf, every=60):
    """Buys approved panel bets right after approval (rechecked, swapped if needed): every minute, and within a
    couple of seconds of an Approve / Add tap. Also runs the paper panel."""
    time.sleep(180)
    settled = time.time()
    H = None
    while True:
        try:
            with odds.lock:
                H = odds.engine()
                H.buy_asked()                             # this pass covers anything asked for so far
                out = H.panel_exec(log=log, paused=bool(conf.get("paused")), may_trade=H.can_trade())
                if time.time() - settled >= 5 * 60:       # results, exits and game-time prices: every 5 minutes
                    settled = time.time()
                    H.panel_settle()
                lt = time.localtime()
                if lt.tm_hour == 8 and conf.get("recap_day") != time.strftime("%Y-%m-%d"):
                    conf["recap_day"] = time.strftime("%Y-%m-%d")
                    r = H.recap()
                    if r.get("bets"):
                        out.append(f"☀️ Yesterday: {'+' if r['pl'] >= 0 else '−'}${abs(r['pl']):.2f} · {r['won']} up, {r['lost']} down"
                                   + (f" · 🔥 {r['streak']} days up in a row" if r.get("streak", 0) > 1 else "")
                                   + (f". Best: {r['best']['what']}." if r.get("best") and r["best"]["pl"] > 0 else "."))
            for m in out:
                log(m)
                push(conf, m)
        except Exception as err:
            log("panel buying skipped:", type(err).__name__, err)
        try:
            panel_wait(H, every)
        except Exception as err:                          # never let a wait problem stop the buying loop
            log("panel wait:", type(err).__name__, err)
            time.sleep(every)


def rebuild_loop(odds, notifier=None, every=2):
    """'Build a fresh panel' / 'Look now' starts at once: the tap leaves a flag, this sees it within a couple of
    seconds and looks at every sport right away (not at the shadow's next 10-minute round), noting progress for the
    Build page. It only makes drafts; buying stays with panel_loop (Pause, started games and all)."""
    while True:
        time.sleep(every)
        try:
            with odds.lock:
                H = odds.engine()
                if not H.rebuild_pending():
                    continue
            did = H.panel_rebuild(lambda code: H.panel_collect(odds.get(code, ""), code, log=log), SHADOW_LEAGUES,
                                  lock=odds.lock, log=log)
            if did:
                log("panel:", "; ".join(did))
            for m in did if notifier else []:
                if m.startswith("🆕"):
                    notifier.add(m, "idea")
        except Exception as err:
            log("panel rebuild skipped:", type(err).__name__, err)


def history_loop(E, every=900):
    """Settle recorded quotes once their games finish, and keep the history file trimmed."""
    n = 0
    while True:
        try:
            E.killer_resolve()
            E.maker_resolve()
            got = E.resolve_quotes()
            E.resolve_closes()
            if got:
                log(f"history: {got} quotes settled")
            n += 1
            if n % 96 == 1:
                E.store_trim()
        except Exception as err:
            log("history loop:", type(err).__name__, err)
        time.sleep(every)


SHADOW_LEAGUES = ("nfl", "nba", "nhl", "ncaaf", "ncaamb", "ahl")


def held_teams(odds):
    """Team names in your live combos."""
    E = WATCHER.get("E")
    out = set()
    for h in ((E.MINE.get("hold") or {}).values() if E else []):
        for item in h.get("need") or []:
            try:
                out.add(str(item[1]))
            except (IndexError, TypeError):
                pass
    return out


WATCHER = {}


def shadow_loop(odds, notifier=None, every=600):
    """Paper full-auto trading on the Mac (see the planner's shadow section). Real quotes, no money."""
    time.sleep(120)
    while True:
        for code in SHADOW_LEAGUES:
            try:
                with odds.lock:
                    snap = odds.get(code, "")            # free lines + any sharp lines already cached
                    did = odds.engine().shadow_pass(snap, log=log, alert=notifier.add if notifier else None)
                    try:                                  # single games: value without a combo maker's cut
                        did = (did or []) + odds.engine().single_pass(snap, alert=notifier.add if notifier else None, log=log)
                    except Exception as err:
                        log(f"singles {code} skipped:", type(err).__name__, err)
                    try:                                  # spreads and totals, priced with the score model
                        did = (did or []) + odds.engine().line_pass(code, alert=notifier.add if notifier else None, log=log)
                    except Exception as err:
                        log(f"lines {code} skipped:", type(err).__name__, err)
                    try:                                  # the daily panel's candidates for this league
                        odds.engine().panel_collect(snap, code, log=log)
                    except Exception as err:
                        log(f"panel {code} skipped:", type(err).__name__, err)
                    for m in odds.moves(code, held_teams(odds)) if notifier else []:
                        notifier.add(m, "news")
                if did:
                    log(f"shadow {code}:", "; ".join(did))
            except Exception as err:
                log(f"shadow {code} skipped:", type(err).__name__, err)
        try:                                              # rebuild today's panel; settle; weekly cut-off review
            with odds.lock:
                H = odds.engine()
                did = H.panel_pass(log=log) + H.panel_settle() + [f"cut-off {m}" for m in H.adjust_cutoffs()] \
                    + [f"smart sell {m}" for m in H.smart_tune()]
                n_lab = H.lab_pass()
            if n_lab:
                log(f"combo lab: paper-bought {n_lab} at different price levels")
            if did:
                log("panel:", "; ".join(did))
            for m in did if notifier else []:
                if m.startswith("🆕"):
                    notifier.add(m, "idea")
        except Exception as err:
            log("panel skipped:", type(err).__name__, err)
        try:                                              # "cover the early games" paper test, over the NFL week
            # Runs OUTSIDE odds.lock on purpose: both bodies do batched Kalshi requests.get (via fetch_results and
            # cover_ticks' own calls, up to 15-20 s each) and the lock is the same one panel_loop holds to place a
            # real approved buy (panel_exec). Holding it here could stall a real purchase. The cover path is paper
            # only and coordinates with the trading loop solely through SQLite (its own `cover` table and state='sim'
            # ticks), which store_x/store_rows already guard with their own lock + WAL + busy_timeout, so it is safe
            # off odds.lock. odds.engine() is a ready singleton (the panel passes above already built it).
            H = odds.engine()
            H.cover_ticks(log=log)                         # game prices for the survivor's smart-sell replay
            did = H.cover_pass(log=log, alert=notifier.add if notifier else None)
            if did:
                log("cover test:", "; ".join(did))
        except Exception as err:
            log("cover test skipped:", type(err).__name__, err)
        quick_rounds(odds, notifier, until=time.time() + every)


def quick_rounds(odds, notifier, until, gap=150):
    """Between full rounds: every 2.5 minutes, look again at the sports with a game starting in the next two
    hours (that's when prices move and good bets come and go), and refresh the panel from them."""
    while time.time() < until:
        time.sleep(min(gap, max(until - time.time(), 1)))
        if time.time() >= until:
            break
        try:
            with odds.lock:
                H = odds.engine()
                near = H.sports_near()
                for code in near:
                    H.panel_collect(odds.get(code, ""), code, log=log)
                did = H.panel_pass(log=log) if near else []
                H.lab_ticks()                              # game prices for the smart-sell replay
            for m in did if notifier else []:
                if m.startswith("🆕"):
                    notifier.add(m, "idea")
        except Exception as err:
            log("quick check skipped:", type(err).__name__, err)



# ---------------------------------------------------------------- web view (any browser on your Tailscale network)
WEB_CSS = """:root{--bg:#f4f5f7;--card:#fff;--ink:#16181d;--mute:#6b7280;--line:#e5e7eb;--good:#15803d;--bad:#b91c1c;--acc:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#181b21;--ink:#eef0f3;--mute:#9aa1ad;--line:#2a2e36;--good:#4ade80;--bad:#f87171;--acc:#5b9dff}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px -apple-system,system-ui,sans-serif}
main{max-width:720px;margin:0 auto;padding:16px}h1{font-size:26px;margin:8px 0 4px}h2{font-size:15px;color:var(--mute);margin:22px 0 8px;text-transform:uppercase;letter-spacing:.04em}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:8px 0}
.row{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.mute{color:var(--mute);font-size:14px}
button,input{font:inherit;border-radius:10px;border:1px solid var(--line);padding:9px 14px}button{background:var(--acc);color:#fff;border:0;cursor:pointer}
button.sell{background:var(--good)}.msg{padding:10px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);margin:8px 0}
pre{white-space:pre-wrap;font-size:12px;color:var(--mute)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 10px}.tab{padding:7px 12px;border-radius:999px;border:1px solid var(--line);color:var(--ink);text-decoration:none;background:var(--card)}
.tab.on{background:var(--acc);color:#fff;border-color:var(--acc)}"""


LOGIN_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Combo Hub">
<meta name="theme-color" content="#0b0d12"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/manifest.webmanifest">
<title>Combo Hub</title><style>
:root{--bg:#0b0d12;--panel:#151821;--line:#262a35;--ink:#f2f4f8;--mute:#8b93a3;--acc:#4f8cff;--bad:#ff6b6b}
@media (prefers-color-scheme:light){:root{--bg:#f3f5f9;--panel:#fff;--line:#dde1e8;--ink:#12151b;--mute:#667085;--acc:#2f6bff;--bad:#d92d20}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:radial-gradient(1200px 600px at 50% -10%,color-mix(in srgb,var(--acc) 22%,transparent),transparent 60%),var(--bg);
 color:var(--ink);font:16px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;display:flex;align-items:center;justify-content:center;
 padding:max(24px,env(safe-area-inset-top)) 20px max(24px,env(safe-area-inset-bottom))}
.box{width:100%;max-width:360px;text-align:center}
.logo{width:76px;height:76px;border-radius:20px;box-shadow:0 12px 40px color-mix(in srgb,var(--acc) 40%,transparent);margin-bottom:18px}
h1{font-size:28px;letter-spacing:-.02em;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 26px;font-size:15px}
.fid{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;border:0;border-radius:14px;padding:15px;font-weight:600;font-size:17px;font-family:inherit;
 background:var(--acc);color:#fff;cursor:pointer}.fid svg{width:24px;height:24px}
.fid.nudge{animation:nud 1.6s ease-in-out infinite}@keyframes nud{50%{box-shadow:0 0 0 7px color-mix(in srgb,var(--acc) 28%,transparent)}}@media(prefers-reduced-motion:reduce){.fid.nudge{animation:none}}
.or{display:flex;align-items:center;gap:12px;color:var(--mute);font-size:13px;margin:20px 0}.or:before,.or:after{content:"";flex:1;height:1px;background:var(--line)}
.field{position:relative}
input{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:14px;color:var(--ink);padding:15px 52px 15px 16px;
 font:600 20px ui-monospace,"SF Mono",Menlo,monospace;letter-spacing:.18em;text-align:center;outline:none;transition:border-color .15s,box-shadow .15s}
input::placeholder{letter-spacing:normal;font:400 16px -apple-system,system-ui,sans-serif;color:var(--mute)}
input:focus{border-color:var(--acc);box-shadow:0 0 0 4px color-mix(in srgb,var(--acc) 22%,transparent)}
.eye{position:absolute;right:8px;top:50%;transform:translateY(-50%);border:0;background:none;color:var(--mute);padding:8px;cursor:pointer}
.go{width:100%;margin-top:12px;border:1px solid var(--line);border-radius:14px;padding:14px;font:600 17px -apple-system,system-ui,sans-serif;background:var(--panel);color:var(--ink);cursor:pointer}
.solo .go{background:var(--acc);color:#fff;border:0}
.msg{color:var(--bad);font-size:14px;min-height:20px;margin-top:12px}.hint{color:var(--mute);font-size:13px;margin-top:22px}.hint a{color:var(--acc)}
.shake{animation:sh .4s}@keyframes sh{20%,60%{transform:translateX(-8px)}40%,80%{transform:translateX(8px)}}
.spin{width:18px;height:18px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:r .7s linear infinite;display:inline-block}@keyframes r{to{transform:rotate(1turn)}}
/* the same motion as the app: a soft entrance, press feedback, a haptic tick on every tap */
:root{color-scheme:dark;--spring:cubic-bezier(.2,.9,.25,1.12);--ease:cubic-bezier(.2,.8,.2,1)}@media (prefers-color-scheme:light){:root{color-scheme:light}}
.box>*{animation:rise .5s var(--ease) both}.box>*:nth-child(2){animation-delay:.06s}.box>*:nth-child(3){animation-delay:.12s}.box>*:nth-child(4){animation-delay:.18s}.box>*:nth-child(5){animation-delay:.24s}.box>*:nth-child(n+6){animation-delay:.3s}
.logo{animation:pop .6s var(--spring) both!important}@keyframes pop{from{transform:scale(.6);opacity:0}to{transform:none;opacity:1}}
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.fid,.go,.eye{transition:transform .14s var(--ease),filter .15s,background-color .15s;-webkit-tap-highlight-color:transparent}.fid:active,.go:active{transform:scale(.97)}.eye:active{transform:translateY(-50%) scale(.88)}
.fid:hover,.solo .go:hover{filter:brightness(1.07)}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}
</style></head><body><div class="box" id="box">
<img class="logo" src="data:image/png;base64,__ICON__" alt="">
<h1>Combo Hub</h1><p class="sub" id="sub">Your Mac's betting desk</p>
<div id="fidwrap" style="display:none"><button class="fid" id="fid" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2M9 9v1.5M15 9v1.5M12 9v4.5h-1M9.5 16c1.5 1.2 3.5 1.2 5 0"/></svg><span id="fidt">Unlock with Face ID</span></button>
<div class="or">or use your passcode</div></div>
<form method="post" action="/login" id="f"><div class="field"><input name="pass" id="p" type="password" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="Passcode" required>
<button class="eye" type="button" aria-label="Show passcode" onclick="var p=document.getElementById('p');p.type=p.type==='password'?'text':'password'"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button></div>
<button class="go" id="go">Unlock</button></form>
<div class="msg" id="msg">__MSG__</div>
<div class="hint" id="hint">The passcode is in Settings › This Mac, on the Mac.</div>
</div><script>
const FID="__FID__",HTTPS="__HTTPS__",box=document.getElementById('box'),msg=document.getElementById('msg');
/* haptics, the same way as the app (iOS: a tiny see-through switch toggled inside the tap; elsewhere vibrate); __haps is for tests */
function hap(k){k=k||'light';(window.__haps=window.__haps||[]).push(k);try{if(!(/iP(hone|ad|od)/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1))&&navigator.vibrate){navigator.vibrate(k==='error'?[25,60,25,60,25]:8);return;}
 let l=document.getElementById('hapl');if(!l){l=document.createElement('label');l.id='hapl';l.setAttribute('aria-hidden','true');l.style.cssText='position:fixed;left:8px;bottom:8px;width:2px;height:2px;opacity:.01;overflow:hidden;z-index:-1';l.innerHTML='<input type="checkbox" switch tabindex="-1">';document.body.appendChild(l);}
 (k==='error'?[0,80,160]:[0]).forEach(d=>d?setTimeout(()=>l.click(),d):l.click());}catch(e){}}
addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('button,a');if(b&&!b.closest('#hapl'))hap('light');},true);
if(msg.textContent.trim())box.classList.add('shake');
document.getElementById('f').addEventListener('submit',()=>{document.getElementById('go').innerHTML='<span class="spin"></span>';});
const b64=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
const e64=a=>btoa(String.fromCharCode(...new Uint8Array(a))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const can=window.PublicKeyCredential&&location.protocol==='https:';
if(FID&&can){document.getElementById('fidwrap').style.display='';document.getElementById('hint').textContent='';}
else{box.classList.add('solo');if(location.protocol!=='https:'&&HTTPS)document.getElementById('hint').innerHTML='Face ID works on the secure address: <a href="'+HTTPS+'">'+HTTPS.replace('https://','')+'</a>';}
async function unlock(auto){const btn=document.getElementById('fid');const old=btn.innerHTML;
 try{const o=await (await fetch('/auth/begin',{method:'POST',body:'{}'})).json();if(!o.ok)return;
  btn.innerHTML='<span class="spin"></span>';
  const c=await navigator.credentials.get({publicKey:{challenge:b64(o.challenge),rpId:o.rp,userVerification:'required',timeout:60000,
   allowCredentials:o.ids.map(id=>({type:'public-key',id:b64(id)}))}});
  const r=await (await fetch('/auth/finish',{method:'POST',body:JSON.stringify({id:c.id,clientDataJSON:e64(c.response.clientDataJSON),
   authenticatorData:e64(c.response.authenticatorData),signature:e64(c.response.signature)})})).json();
  if(r.ok){location.replace('/');return;}msg.textContent=r.msg||'Face ID didn\'t work.';hap('error');box.classList.remove('shake');void box.offsetWidth;box.classList.add('shake');
 }catch(e){
  if(auto){/* iOS often refuses Face ID without a tap: say so and make the button the obvious thing to tap */
   msg.textContent='';btn.classList.add('nudge');}
  else msg.textContent=(e&&e.name==='NotAllowedError')?'Face ID was cancelled. Use the passcode or tap the button to try again.':'Face ID isn\'t available here. Use the passcode.';}
 btn.innerHTML=old;if(auto&&btn.classList.contains('nudge'))document.getElementById('fidt').textContent='Tap to unlock with Face ID';}
document.getElementById('fid').onclick=()=>{document.getElementById('fid').classList.remove('nudge');unlock(false);};
if(FID&&can&&!msg.textContent.trim())unlock(true);else document.getElementById('p').focus();
</script></body></html>"""


SESSIONS_FILE = os.path.join(HOME, "hub_sessions.json")    # sign-ins survive restarts and updates (hashed)


def _cbor(b, i=0):
    """Just enough CBOR to read a passkey's public key. Returns (value, next index)."""
    ib = b[i]
    mt, ai = ib >> 5, ib & 31
    i += 1
    if ai < 24:
        n = ai
    elif ai in (24, 25, 26, 27):
        size = 1 << (ai - 24)
        n = int.from_bytes(b[i:i + size], "big")
        i += size
    else:
        raise ValueError("unsupported CBOR")
    if mt == 0:
        return n, i
    if mt == 1:
        return -1 - n, i
    if mt in (2, 3):
        v = b[i:i + n]
        return (v if mt == 2 else v.decode()), i + n
    if mt == 4:
        out = []
        for _ in range(n):
            v, i = _cbor(b, i)
            out.append(v)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(n):
            k, i = _cbor(b, i)
            v, i = _cbor(b, i)
            out[k] = v
        return out, i
    if mt == 7:
        return {20: False, 21: True, 22: None}.get(ai), i
    raise ValueError("unsupported CBOR")


def _b64d(s):
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Web:
    """A small page for any browser on your Tailscale network: your live combos with a real cash-out
    button, the shadow record, and what the Mac has been doing. Passcode or Face ID (a passkey) required;
    sign-ins last 30 days and survive restarts."""
    def __init__(self, conf, E):
        import secrets
        self.conf, self.E, self.fails = conf, E, []
        if not conf.get("web_pass"):
            conf["web_pass"] = "".join(secrets.choice("23456789abcdefghjkmnpqrstuvwxyz") for _ in range(8))
            E.save_json(CONF, conf)
        self.lock = threading.Lock()
        self.challenges = {}
        try:
            with open(SESSIONS_FILE) as f:
                self.sessions = {k: v for k, v in json.load(f).items() if v > time.time()}
        except (OSError, ValueError):
            self.sessions = {}

    @staticmethod
    def _h(tok):
        return hashlib.sha256(tok.encode()).hexdigest()

    def _save_sessions(self):
        try:
            now = time.time()
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            tmp = SESSIONS_FILE + ".tmp"
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                json.dump(self.sessions, f)
            os.replace(tmp, SESSIONS_FILE)
        except OSError:
            pass

    def keep_only(self, tok):
        """After a passcode change: every other device signs in again, and every Face ID sign-in is removed
        (one added from a stolen session must not survive the change). Turn Face ID back on afterwards."""
        h = self._h(tok or "")
        self.sessions = {k: v for k, v in self.sessions.items() if k == h}
        self._save_sessions()
        if self.conf.get("passkeys"):
            log(f"passcode changed: removed {len(self.conf['passkeys'])} Face ID sign-in(s)")
            self.conf["passkeys"] = []
            self.E.save_json(CONF, self.conf)

    def session(self, handler):
        import http.cookies
        c = http.cookies.SimpleCookie(handler.headers.get("Cookie") or "")
        tok = c["cw"].value if "cw" in c else ""
        exp = self.sessions.get(self._h(tok)) if tok else None
        return tok if exp and exp > time.time() else None

    # ---- Face ID / Touch ID: passkeys (WebAuthn, ES256), only on the secure https address
    @staticmethod
    def rp_of(handler):
        return (handler.headers.get("Host") or "").split(":")[0].lower()

    def passkeys(self, rp=None):
        return [p for p in self.conf.get("passkeys") or [] if rp is None or p.get("rp") == rp]

    def challenge(self, kind):
        import secrets
        now = time.time()
        self.challenges = {k: v for k, v in self.challenges.items() if v[1] > now}
        if len(self.challenges) > 50:                     # unauthenticated callers can't grow this without limit
            for k in sorted(self.challenges, key=lambda k: self.challenges[k][1])[:len(self.challenges) - 50]:
                self.challenges.pop(k, None)
        c = secrets.token_urlsafe(32)
        self.challenges[c] = (kind, now + 120)
        return c

    def _client(self, cdj, kind, rp):
        cd = json.loads(cdj)
        want = {"get": "webauthn.get", "reg": "webauthn.create"}[kind]
        ch = self.challenges.pop(cd.get("challenge", ""), None)
        if cd.get("type") != want or not ch or ch[0] != kind or ch[1] < time.time():
            raise ValueError("challenge")
        if cd.get("origin") != f"https://{rp}":
            raise ValueError("origin")

    def _check_auth_data(self, ad, rp):
        if len(ad) < 37 or ad[:32] != hashlib.sha256(rp.encode()).digest():
            raise ValueError("rp")
        if not ad[32] & 0x01 or not ad[32] & 0x04:       # user present and verified (Face ID)
            raise ValueError("not verified")

    def passkey_register(self, d, rp, name):
        cdj, att = _b64d(d.get("clientDataJSON")), _b64d(d.get("attestationObject"))
        self._client(cdj, "reg", rp)
        obj, _ = _cbor(att)
        ad = obj["authData"]
        self._check_auth_data(ad, rp)
        if not ad[32] & 0x40:
            raise ValueError("no key")
        ln = int.from_bytes(ad[53:55], "big")
        cid = ad[55:55 + ln]
        key, _ = _cbor(ad, 55 + ln)
        if key.get(1) != 2 or key.get(3) != -7 or key.get(-1) != 1:
            raise ValueError("Only Face ID / Touch ID keys (ES256) are supported.")
        b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")
        pk = {"id": b(cid), "x": b(key[-2]), "y": b(key[-3]), "rp": rp, "name": name[:40] or "Device",
              "added": int(time.time())}
        self.conf["passkeys"] = [p for p in self.passkeys() if p["id"] != pk["id"]] + [pk]
        self.E.save_json(CONF, self.conf)
        log("Face ID sign-in added:", pk["name"])
        return pk

    def passkey_login(self, d, rp):
        now = time.time()                                 # its own lockout: failed Face ID can't lock out the passcode
        self.pk_fails = [x for x in getattr(self, "pk_fails", []) if now - x < 600]
        if len(self.pk_fails) >= 5:
            return None, "Face ID is paused for 10 minutes after failed tries. Use the passcode."
        try:
            pk = next((p for p in self.passkeys(rp) if p["id"] == str(d.get("id") or "").rstrip("=")), None)
            if not pk:
                raise ValueError("unknown key")
            cdj, ad, sig = _b64d(d.get("clientDataJSON")), _b64d(d.get("authenticatorData")), _b64d(d.get("signature"))
            self._client(cdj, "get", rp)
            self._check_auth_data(ad, rp)
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            pub = ec.EllipticCurvePublicNumbers(int.from_bytes(_b64d(pk["x"]), "big"), int.from_bytes(_b64d(pk["y"]), "big"),
                                                ec.SECP256R1()).public_key()
            pub.verify(sig, ad + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256()))
        except Exception as err:
            self.pk_fails.append(now)
            log("Face ID sign-in refused:", type(err).__name__, str(err)[:60])
            return None, "Face ID didn't work. Use the passcode."
        pk["used"] = int(now)
        self.E.save_json(CONF, self.conf)
        return self.new_session(), ""

    def login(self, form):
        import hmac as _h
        now = time.time()
        self.fails = [t for t in self.fails if now - t < 600]
        if len(self.fails) >= 5:
            return None, "Too many tries. Wait 10 minutes."
        if not _h.compare_digest(form.get("pass", "").strip(), self.conf["web_pass"]):
            self.fails.append(now)
            return None, "That passcode isn't right."
        return self.new_session(), ""

    def new_session(self):
        import secrets
        tok = secrets.token_urlsafe(24)
        self.sessions[self._h(tok)] = time.time() + 30 * 86400
        self._save_sessions()
        return tok

    def issue_once(self):
        """A one-time sign-in link for the phone (asked for over the sealed hub channel); 60 seconds."""
        import secrets
        t = secrets.token_urlsafe(24)
        now = time.time()
        self.once = {k: v for k, v in getattr(self, "once", {}).items() if v > now}
        self.once[t] = now + 60
        return "/once?t=" + t

    def use_once(self, t):
        exp = getattr(self, "once", {}).pop(t, None)
        return self.new_session() if exp and exp > time.time() else None

    def page(self, tok, note="", build=""):
        import html as h
        E = self.E
        e = h.escape
        holds = E.MINE.get("hold") or {}
        rows = []
        for t, x in sorted(holds.items(), key=lambda kv: kv[1].get("label", "")):
            if x.get("left", 1) <= 0:
                continue
            o = (E.MINE.get("cash") or {}).get(t) or {}
            real = bool(o.get("rfq")) and time.time() - o.get("at", 0) < 25
            picks = ", ".join(str(n) for _, n in x.get("need") or [])
            act = (f"<form method='post' action='/act'><input type='hidden' name='t' value='{e(t)}'>"
                   f"<input type='hidden' name='tok' value='{e(tok)}'>"
                   + (f"<button class='sell' name='do' value='sell'>Sell now for {E.money(o['offer'])}</button>" if real else
                      "<button name='do' value='quote'>Get cash-out offer</button>") + "</form>")
            rows.append(f"<div class='card'><div class='row'><b>{e(x.get('label', 'Combo'))}</b>"
                        f"<span class='mute'>paid {E.money(x.get('cost', 0))} · pays {E.money(x.get('pays', 0))} · "
                        f"{x.get('p', 0):.0%} to hit</span></div><div class='mute'>Still needs: {e(picks)}</div>"
                        f"<div class='row' style='margin-top:8px'>{act}</div></div>")
        try:
            sm = E.shadow_text(E.shadow_summary())
        except Exception:
            sm = "Shadow record not available yet."
        try:
            with open(os.path.join(HOME, "watcher.log"), encoding="utf-8", errors="replace") as f:
                tail = "".join(f.readlines()[-25:])
        except OSError:
            tail = ""
        return ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>Combo Hub</title><style>{WEB_CSS}</style><meta http-equiv='refresh' content='60'></head><body><main>"
                f"<h1>Combo Hub</h1><div class='mute'>Your Mac · planner {e(E.VERSION)} · {time.strftime('%-I:%M %p')}</div>"
                + (f"<div class='msg'>{e(note)}</div>" if note else "")
                + f"<h2>Live combos ({len(rows)})</h2>" + ("".join(rows) or "<div class='card mute'>Nothing riding right now.</div>")
                + f"<h2>Build &amp; buy</h2>{build}"
                + f"<h2>Shadow auto-trading</h2><div class='card'>{e(sm)}</div>"
                + f"<h2>Which odds are most accurate</h2><div class='card'>{e(E.accuracy_text(E.accuracy_summary()))}</div>"
                + f"<h2>What the Mac has been doing</h2><div class='card'><pre>{e(tail)}</pre></div>"
                "</main></body></html>")

    def act(self, form):
        E, t, do = self.E, form.get("t", ""), form.get("do", "")
        if t not in (E.MINE.get("hold") or {}):
            return "That combo isn't live any more."
        with self.lock:
            E.MINE["busy"] = True                     # keep automatic cash-outs out of the way meanwhile
            try:
                if do == "quote":
                    o = E.get_cash_offer(t)
                    if o.get("error"):
                        return o["error"]
                    E.MINE["cash"][t] = o
                    return f"Kalshi offers {E.money(o['offer'])}. Tap Sell now within 20 seconds to take it."
                if do == "sell":
                    log("web cash-out:", t)
                    return E.re.sub("<[^>]+>", "", E.accept_cash(t))
                return "Unknown action."
            finally:
                E.MINE["busy"] = False

    def login_page(self, msg="", rp=""):
        import html as h
        fid = bool(rp) and bool(self.passkeys(rp))
        https = (self.conf.get("https") or {}).get("url") or ""
        return LOGIN_HTML.replace("__MSG__", h.escape(msg)).replace("__FID__", "1" if fid else "") \
            .replace("__HTTPS__", h.escape(https)).replace("__ICON__", ICON_PNG)


WEB_LEAGUES = (("nfl", "NFL"), ("nba", "NBA"), ("nhl", "NHL"), ("ncaaf", "CFB"), ("ncaamb", "CBB"))


class WebBuild:
    """Build and buy from the web view, using the hub's second engine (same lock as odds and shadow),
    so nothing here touches the watcher's own live state."""
    def __init__(self, odds):
        self.odds, self.cur = odds, None

    def build(self, lg):
        import random
        o = self.odds
        with o.lock:
            snap = o.get(lg, "")
            H = o.engine()
            games, _, _ = H.week_games(H.fetch_markets())
            book = H.load_book_state(snap)
            H.attach_fair(games, book)
            combos, _ = H.build_combos(games, {}, random.Random(int(time.time() // 600))) if games else ([], None)
            combos = [c for c in combos if not any(H.started(l) for l in c["legs"])][:12]
            rows = []
            for c in combos:
                est = H.est_offer(c)
                rows.append({"est": est[0], "est_pct": est[1], "thin": H.thin_legs(c["legs"])})
            self.cur = {"lg": lg, "combos": combos, "rows": rows, "stake": H.CFG["stake"], "offers": {},
                        "cut": H.CFG["accept_pct"], "at": time.time(), "name": H.LG()["name"]}
        return self.cur

    def quote(self, i):
        b = self.cur
        if not b or not 1 <= i <= len(b["combos"]) or time.time() - b["at"] > 1800:
            return "Those suggestions are out of date. Build again."
        o = self.odds
        with o.lock:
            H = o.engine()
            H.set_league(b["lg"])
            H.CTX.clear()
            H.CTX.update(combos=b["combos"], stake=b["stake"], offers={}, build_id=None)
            r = H.get_offer(i)
            if r.get("error"):
                return r["error"]
            b["offers"][i] = dict(H.CTX["offers"][i], got=time.time(), pct=r.get("pct"), ok=r.get("ok"))
        pct = f" ({r['pct']:.0%} of fair)" if r.get("pct") else ""
        verdict = "" if r.get("ok") else f" That's under your {b['cut']}% cut-off."
        return f"Kalshi offers {H.money(r['pays'])} for {H.money(r['stake'])}{pct}.{verdict} Buy within 20 seconds."

    def buy(self, i):
        b = self.cur
        off = (b or {}).get("offers", {}).get(i)
        if not off or time.time() - off["got"] > 20:
            return "That price expired. Tap Get price again."
        o = self.odds
        with o.lock:
            H = o.engine()
            H.set_league(b["lg"])
            H.CTX.clear()
            H.CTX.update(combos=b["combos"], stake=b["stake"], offers={i: off}, build_id=None)
            log("web buy:", b["lg"], "combo", i, f"${off['stake']}")
            r = H.accept_offer(i)
        b["offers"].pop(i, None)
        if r.get("error"):
            return r["error"]
        return f"✅ Bought: {H.money(off['stake'])} to win {H.money(r['pays'])}. It shows under Live within a minute."

    def html(self, tok):
        import html as h
        e = h.escape
        b = self.cur
        tabs = "".join(f"<a class='tab{' on' if b and b['lg'] == lg else ''}' href='/simple?build={lg}'>{nm}</a>"
                       for lg, nm in WEB_LEAGUES)
        if not b:
            return f"<div class='tabs'>{tabs}</div><div class='card mute'>Pick a league to build suggestions.</div>"
        if not b["combos"]:
            return f"<div class='tabs'>{tabs}</div><div class='card mute'>No {e(b['name'])} games to build from right now.</div>"
        H = self.odds.engine()
        cards = []
        for i, (c, row) in enumerate(zip(b["combos"], b["rows"]), 1):
            picks = " + ".join(f"{e(l['pick'])} <span class='mute'>{l['fair']:.0%}</span>" for l in c["legs"])
            est = (f"Kalshi will likely pay about {H.money(row['est'] * b['stake'] / H.CFG['stake'])} "
                   f"({row['est_pct']:.0%} of fair)" if row.get("est") else "")
            thin = (f"<div class='mute'>⚠️ Thin Kalshi order book on {e(', '.join(row['thin']))}: its price may be off.</div>"
                    if row["thin"] else "")
            off = b["offers"].get(i)
            fresh = off and time.time() - off["got"] < 20
            btn = (f"<button class='sell' name='do' value='bbuy'>Buy {H.money(off['stake'])} to win {H.money(off['pays'])}"
                   f"{'' if off.get('ok') else ' (under cut-off)'}</button>" if fresh else
                   "<button name='do' value='bquote'>Get price</button>")
            cards.append(f"<div class='card'><div><b>{len(c['legs'])} picks</b> · fair pays "
                         f"{H.money(c['fair'])} for {H.money(b['stake'])}</div><div style='margin:6px 0'>{picks}</div>"
                         f"<div class='mute'>{est}</div>{thin}<form method='post' action='/act' style='margin-top:8px'>"
                         f"<input type='hidden' name='tok' value='{e(tok)}'><input type='hidden' name='i' value='{i}'>"
                         f"{btn}</form></div>")
        return (f"<div class='tabs'>{tabs}</div><div class='mute'>{e(b['name'])} suggestions · built "
                f"{time.strftime('%-I:%M %p', time.localtime(b['at']))} · your weekly cap still applies</div>"
                + "".join(cards))


# ---------------------------------------------------------------- the planner app, in a browser
# The Mac runs a separate copy of the planner (its own process) for Combo Hub's screens (the SPA below). It keeps
# stand-ins for Pythonista's modules (`ui` and friends) so the engine imports and behaves as it does on the phone.
# The old "Classic screens" (the phone UI drawn in the browser through a bridge) are gone: the SPA is the only UI.
# The hub (port 8765) signs you in and passes requests through to it on this Mac only (port 8766).
WEBAPP_PORT = int(os.environ.get("CW_WEBAPP_PORT") or 8766)   # the check suite moves it, so tests never reach the real app

SPA = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="Combo Hub"><link rel="apple-touch-icon" href="/icon.png"><link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0b0d12" media="(prefers-color-scheme: dark)"><meta name="theme-color" content="#f6f7fa" media="(prefers-color-scheme: light)"><title>Combo Hub</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0b0d12;--panel:#12151c;--panel2:#181c26;--hover:#1d2230;--line:#232836;--ink:#eef1f6;--sub:#a1aabb;--mute:#6b7488;
 --yes:#16c784;--yesbg:rgba(22,199,132,.13);--no:#ff5c6c;--nobg:rgba(255,92,108,.13);--acc:#4c8dff;--accbg:rgba(76,141,255,.15);
 --live:#ff9f1c;--livebg:rgba(255,159,28,.14);--r:14px}
@media (prefers-color-scheme:light){:root{--bg:#f6f7fa;--panel:#fff;--panel2:#f2f4f8;--hover:#eef1f7;--line:#e4e7ee;--ink:#0e1320;--sub:#4c5568;--mute:#8a93a6;
 --yesbg:rgba(22,170,110,.12);--yes:#0f9e64;--no:#e5394b;--nobg:rgba(229,57,75,.1);--acc:#2468ff;--accbg:rgba(36,104,255,.1);--live:#d97706;--livebg:rgba(217,119,6,.12)}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;font-feature-settings:"tnum" 1,"cv11" 1}
button{font:inherit;color:inherit;cursor:pointer}a{color:var(--acc);text-decoration:none}
.top{position:sticky;top:0;z-index:20;height:calc(62px + env(safe-area-inset-top));display:flex;align-items:center;gap:22px;padding:0 24px;padding-top:env(safe-area-inset-top);
 border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--bg) 82%,transparent);-webkit-backdrop-filter:saturate(180%) blur(18px);backdrop-filter:saturate(180%) blur(18px)}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:16px;letter-spacing:-.02em;white-space:nowrap}
.mk{width:28px;height:28px;border-radius:8px;background:linear-gradient(145deg,#2f8cff,#7a5cff 60%,#c84bff);display:grid;place-items:center;flex:none}
.nav{display:flex;gap:2px}.nav button{border:0;background:none;padding:8px 14px;border-radius:9px;color:var(--sub);font-weight:600}
.nav button.on{color:var(--ink);background:var(--panel2)}.nav button:hover{color:var(--ink)}
.tr{margin-left:auto;display:flex;align-items:center;gap:20px}
.ts{text-align:right;line-height:1.2}.ts span{display:block;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}.ts b{font-size:15px}
.status{display:flex;align-items:center;gap:7px;color:var(--sub);font-size:12.5px;font-weight:600;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;background:var(--yes);box-shadow:0 0 0 4px var(--yesbg)}.dot.off{background:var(--no);box-shadow:0 0 0 4px var(--nobg)}
.cta{border:0;background:var(--acc);color:#fff;border-radius:10px;padding:9px 14px;font-weight:700;white-space:nowrap}
.cta:hover{filter:brightness(1.08)}
main{max-width:1520px;margin:0 auto;padding:22px 24px 60px;overflow-x:clip}
.grid>*,.trow>*,.kpi,.name,.legs{min-width:0}.name span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:22px}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{border:1px solid var(--line);background:var(--panel);color:var(--sub);border-radius:99px;padding:6px 12px;font-weight:600;font-size:12.5px;white-space:nowrap}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}.chip:hover:not(.on){color:var(--ink)}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-bottom:6px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:15px 17px;min-width:0}
.kpi span{color:var(--mute);font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}.kpi b{display:block;font-size:25px;letter-spacing:-.03em;margin-top:3px;font-weight:700;white-space:nowrap}
.kpi small{color:var(--sub);font-weight:500;font-size:13px}
.up{color:var(--yes)}.down{color:var(--no)}.m{color:var(--mute)}.s{color:var(--sub)}
h2{font-size:12.5px;color:var(--sub);text-transform:uppercase;letter-spacing:.07em;margin:24px 0 10px;font-weight:700;display:flex;align-items:center;gap:8px}
h2 .n{background:var(--panel2);color:var(--ink);border-radius:6px;padding:1px 7px;font-size:12px;letter-spacing:0}
h2 .r{margin-left:auto;text-transform:none;letter-spacing:0}
.alert{display:flex;align-items:center;gap:16px;background:linear-gradient(90deg,var(--yesbg),transparent 75%),var(--panel);border:1px solid color-mix(in srgb,var(--yes) 40%,transparent);border-radius:var(--r);padding:15px 17px;margin-bottom:10px}
.alert .ic{width:38px;height:38px;border-radius:10px;background:var(--yesbg);color:var(--yes);display:grid;place-items:center;font-size:18px;flex:none}
.alert b{font-size:15px}.alert p{margin:2px 0 0;color:var(--sub)}
.btn{border-radius:10px;padding:8px 13px;font-weight:700;font-size:13px;border:1px solid var(--line);background:var(--panel2);white-space:nowrap}
.btn:hover{background:var(--hover)}.btn.yes{background:var(--yes);color:#04150c;border-color:transparent}.btn.acc{background:var(--acc);color:#fff;border-color:transparent}
.btn.ghost{background:none}.btn[disabled]{opacity:.5;pointer-events:none}
.own{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:2px 7px;border-radius:999px;background:rgba(245,158,11,.16);color:#f5b544;vertical-align:middle;margin-left:4px}.own.app{background:var(--panel2);color:var(--mute)}.name span.own{display:inline-block;white-space:nowrap}
.legs .up{color:var(--yes)}.legs .down{color:var(--no)}
.ss{display:inline-flex;align-items:center;gap:4px;margin:6px 0 2px;padding:5px 10px;border-radius:999px;border:1px solid var(--line);background:var(--panel2);color:var(--ink);font:inherit;font-size:12px;font-weight:600;cursor:pointer;width:max-content;max-width:100%}.ss.me{background:rgba(245,158,11,.14);border-color:rgba(245,158,11,.4);color:#f5b544}.ss.dim{opacity:.6}
.an{padding:16px 18px;margin:18px 0}.anh{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px}
.ant{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.ant button{flex:1 1 auto}
.annotes{margin:0 0 6px 18px;padding:0;font-size:13.5px;line-height:1.5}
.anrow{display:grid;grid-template-columns:1.4fr repeat(5,1fr);gap:8px;padding:9px 0;border-top:1px solid var(--line);font-size:13px;align-items:center}
@media (max-width:760px){.anrow.h{display:none}.anrow{display:flex;flex-wrap:wrap;gap:6px 14px;padding:11px 0}.anrow>div:first-child{flex-basis:100%;font-size:14px}
 .anrow>div[data-l]:not([data-l=""])::before{content:attr(data-l);display:block;color:var(--mute);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}}
.anrow.h{border-top:0;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
/* ---- motion & feel ---- */
:root{--spring:cubic-bezier(.2,.9,.25,1.12);--ease:cubic-bezier(.2,.8,.2,1)}
button,.trow,.chip,.pitem,.kpi,.moment,.ss{transition:transform .14s var(--ease),background-color .18s,color .18s,box-shadow .18s,opacity .18s}
button:active:not(:disabled),.trow:active,.chip:active,.pitem:active,.moment:active,.ss:active{transform:scale(.97)}
main.enter{animation:pgin .32s var(--ease)}
@keyframes pgin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
::view-transition-old(root),::view-transition-new(root){animation-duration:.24s}
.fl-up{animation:flup .9s var(--ease)}.fl-down{animation:fldn .9s var(--ease)}
@keyframes flup{0%{color:var(--yes);text-shadow:0 0 18px var(--yesbg)}100%{}}
@keyframes fldn{0%{color:var(--no);text-shadow:0 0 18px var(--nobg)}100%{}}
.rowpop{animation:rowpop 1.2s var(--ease)}
@keyframes rowpop{0%{background:var(--livebg)}100%{}}
.modal{display:flex!important;opacity:0;pointer-events:none;transition:opacity .22s var(--ease)}
.modal.on{opacity:1;pointer-events:auto}
.modal .sheet{transform:translateY(24px) scale(.98);transition:transform .34s var(--spring)}
.modal.on .sheet{transform:none}
@media (max-width:760px){.modal .sheet{transform:translateY(100%)}.modal.on .sheet{transform:none}
 .modal .sheet.drag{transition:none}.sheet .grab{display:block;width:38px;height:5px;border-radius:3px;background:var(--line);margin:-6px auto 12px}}
.sheet .grab{display:none}
.toast{transition:transform .38s var(--spring),opacity .2s!important}
.tabbar button.on svg{animation:tabpop .38s var(--spring)}
@keyframes tabpop{0%{transform:scale(.8)}60%{transform:scale(1.12)}100%{transform:none}}
#ptr{position:fixed;left:50%;top:calc(70px + env(safe-area-inset-top));width:34px;height:34px;margin-left:-17px;border-radius:50%;background:var(--panel);border:1px solid var(--line);
 display:grid;place-items:center;z-index:25;opacity:0;transform:translateY(-40px);pointer-events:none;box-shadow:0 6px 20px rgba(0,0,0,.3)}
#ptr i{width:16px;height:16px;border-radius:50%;border:2px solid var(--acc);border-top-color:transparent}
#ptr.go i{animation:sp .7s linear infinite}
/* ---- stage 2: every screen ---- */
.stag>*{animation:rise .42s var(--ease) both;animation-delay:calc(var(--i,0)*38ms)}
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
main.sw-l{animation:swl .3s var(--ease)}main.sw-r{animation:swr .3s var(--ease)}
@keyframes swl{from{opacity:0;transform:translateX(28px)}to{opacity:1;transform:none}}
@keyframes swr{from{opacity:0;transform:translateX(-28px)}to{opacity:1;transform:none}}
.chip.on{animation:chipon .32s var(--spring)}@keyframes chipon{0%{transform:scale(.92)}100%{transform:none}}
.seg,.ant{position:relative}.segind{position:absolute;border-radius:8px;background:var(--panel);box-shadow:0 1px 3px rgba(0,0,0,.3);transition:left .32s var(--spring),width .32s var(--spring),top .32s var(--spring);z-index:0;pointer-events:none}
.seg.hasind button,.ant.hasind button{position:relative;z-index:1}.seg.hasind button.on,.ant.hasind button.on{background:transparent!important;box-shadow:none!important}
.tabbar{position:fixed;transform:translateY(var(--tbo,0px))}.tabind{position:absolute;top:4px;height:3px;border-radius:3px;background:var(--acc);transition:left .36s var(--spring),width .36s var(--spring);pointer-events:none}
/* live scores on Build */
.lvsc{display:inline-flex;align-items:center;gap:6px;font-weight:700;color:var(--live);font-size:11.5px;letter-spacing:.02em;white-space:nowrap}
.pickbtn .scr{font-weight:800;font-size:15px;margin-right:8px;min-width:22px;display:inline-block;font-variant-numeric:tabular-nums}
.pickbtn.lead .scr{color:var(--yes)}.pickbtn.trail .scr{color:var(--no)}
.mrow.livegame{box-shadow:inset 3px 0 0 var(--live)}
.legsc{display:block;font-size:10.5px;font-weight:700;margin-top:2px;letter-spacing:.01em}
.legsc.up{color:var(--yes)}.legsc.down{color:var(--no)}.legsc.even{color:var(--live)}
/* the moment: bought, sold, approved */
.okcard{text-align:center;padding:10px 4px 4px}
.okcard svg{width:84px;height:84px;display:block;margin:4px auto 10px}
.okcard circle{stroke:var(--yes);stroke-width:4;fill:var(--yesbg);stroke-dasharray:240;stroke-dashoffset:240;animation:okc .6s var(--ease) forwards}
.okcard path{stroke:var(--yes);stroke-width:5;fill:none;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:60;stroke-dashoffset:60;animation:okc .38s .42s var(--ease) forwards}
@keyframes okc{to{stroke-dashoffset:0}}
.okcard h3{font-size:22px!important;margin:0 0 4px!important;animation:rise .4s .3s both}
.okcard .amt{font-size:34px;font-weight:800;letter-spacing:-.04em;color:var(--yes);animation:rise .4s .45s both}
.okcard p{animation:rise .4s .55s both}
.okcard.bad circle{stroke:var(--no);fill:var(--nobg)}.okcard.bad path{stroke:var(--no)}.okcard.bad .amt{color:var(--no)}
/* Results */
.chart rect{transform-box:fill-box;transform-origin:center bottom;animation:barup .6s var(--spring) both}
.chart rect:nth-child(n){animation-delay:calc(var(--i,0)*45ms)}
@keyframes barup{from{transform:scaleY(0)}to{transform:none}}
.gt.live{animation:none}.gt.scored{animation:rowpop 1.4s var(--ease)}
.stp button{transition:transform .12s var(--ease),background-color .15s}.stp button:active{transform:scale(.86)}
.tg{transition:background-color .2s}.tg:active{transform:scale(.94)}
.empty[data-ic]:before{content:attr(data-ic)}.empty b{display:block}.empty:before{content:"✨";display:block;width:44px;height:44px;line-height:44px;font-size:22px;text-align:center;margin:0 auto 10px;border-radius:14px;background:linear-gradient(145deg,var(--accbg),transparent);animation:floaty 3s ease-in-out infinite}
@keyframes floaty{50%{transform:translateY(-4px)}}
/* ---- the hero on Live ---- */
.kpis.hero{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:0;background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden;margin-bottom:14px;position:relative}
.kpis.hero:before{content:"";position:absolute;inset:0;background:radial-gradient(120% 90% at 0% 0%,var(--hglow,transparent),transparent 60%);pointer-events:none}
.hv{padding:18px 20px 12px;position:relative;min-width:0}
.hv .hl{color:var(--mute);font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hv .big{display:block;font-size:40px;font-weight:800;letter-spacing:-.045em;line-height:1.05;margin:6px 0 4px;font-variant-numeric:tabular-nums}
.hv .delta{font-weight:700;font-size:14px;display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px}
.hv .delta.up{color:var(--yes);background:var(--yesbg)}.hv .delta.down{color:var(--no);background:var(--nobg)}.hv .delta.flat{color:var(--sub);background:var(--panel2)}
.sparkw{position:relative;margin-top:10px}.hv .spark{display:block;width:100%;height:64px}
.sdot{position:absolute;width:10px;height:10px;border-radius:50%;box-shadow:0 0 0 0 currentColor;animation:sdot 1.8s infinite}
@keyframes sdot{0%{box-shadow:0 0 0 0 color-mix(in srgb,currentColor 60%,transparent)}100%{box-shadow:0 0 0 10px transparent}}
.hs{display:grid;grid-template-columns:1fr 1fr;border-left:1px solid var(--line);position:relative}
.hs>div{padding:13px 16px;border-bottom:1px solid var(--line);border-right:1px solid var(--line);min-width:0}
.hs>div:nth-child(2n){border-right:0}.hs>div:nth-last-child(-n+2){border-bottom:0}
.hs .hk{display:block;color:var(--mute);font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hs b{display:block;font-size:21px;font-weight:750;letter-spacing:-.03em;margin-top:3px;white-space:nowrap;font-variant-numeric:tabular-nums}
.hs small{display:block;color:var(--sub);font-size:12px;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ring{width:22px;height:22px;flex:none;vertical-align:-4px;margin-right:6px}
.livedot{width:7px;height:7px;border-radius:50%;background:var(--live);display:inline-block;animation:pulse 1.6s infinite}
@media (max-width:760px){.kpis.hero{grid-template-columns:1fr;border-radius:20px}.hs{border-left:0;border-top:1px solid var(--line)}.hv .big{font-size:44px}}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}
.sech{cursor:pointer;user-select:none;-webkit-user-select:none}.sech .chev{display:inline-block;width:16px;color:var(--mute);transition:transform .2s var(--ease)}
.secfold{font-size:12px;margin:-4px 2px 14px;cursor:pointer}
.btn.warn{background:#f5b544;color:#1c1405;border-color:transparent}.btn.warn:hover{filter:brightness(1.05)}
.tbl{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.thead,.trow{display:grid;grid-template-columns:minmax(170px,1.25fr) minmax(200px,2fr) 82px 82px 110px 130px 92px;align-items:center;gap:12px;padding:0 16px}
.thead{height:40px;background:var(--panel2);color:var(--mute);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--line)}
.trow{min-height:66px;border-bottom:1px solid var(--line);cursor:pointer}.trow:hover{background:var(--hover)}
.tbl>div:last-child{border-bottom:0}
.num{text-align:right;font-weight:600}.name b{font-size:14.5px;display:block}.name span{color:var(--sub);font-size:12.5px}
.legs{display:flex;gap:4px;flex-wrap:wrap}.leg{font-size:11.5px;font-weight:700;padding:3px 7px;border-radius:6px;background:var(--panel2);color:var(--sub);white-space:nowrap}
.leg.won{background:var(--yes);color:#04130c}.leg.lost{background:var(--nobg);color:var(--no);text-decoration:line-through;opacity:.85}
.leg.live,.leg.up,.leg.down{background:transparent;box-shadow:inset 0 0 0 1.5px currentColor;padding:2px 7px}
.leg.live{color:var(--live)}.leg.up{color:var(--yes)}.leg.down{color:var(--no)}
.leg .pd{display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;margin-right:5px;vertical-align:1px;animation:pulse2 1.6s infinite}
@keyframes pulse2{0%,100%{opacity:1}50%{opacity:.35}}
.bar{height:5px;border-radius:9px;background:var(--panel2);overflow:hidden;width:84px;margin:6px 0 0 auto}.bar i{display:block;height:100%;background:var(--acc)}
.verdict{font-size:11px;font-weight:800;padding:4px 8px;border-radius:6px;letter-spacing:.03em;justify-self:end}
.verdict.pl{text-align:right;padding:5px 9px;line-height:1.15}.verdict.pl b{display:block;font-size:14px;letter-spacing:-.01em}.verdict.pl small{display:block;font-size:10px;font-weight:700;opacity:.8;letter-spacing:.04em;text-transform:uppercase}
.sbar{display:flex;flex-direction:column;gap:8px;margin:-2px 0 12px}.snet{font-size:13px;color:var(--sub)}
.verdict.hold{background:var(--accbg);color:var(--acc)}.verdict.sell,.verdict.won{background:var(--yesbg);color:var(--yes)}.verdict.out,.verdict.lost{background:var(--nobg);color:var(--no)}.verdict.cashed{background:var(--panel2);color:var(--sub)}
.offer b{display:block}.offer small{color:var(--mute);font-size:11.5px;font-weight:500}
.exp{background:var(--panel2);border-bottom:1px solid var(--line);padding:6px 16px 14px}
.lrow{display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line)}
.lrow:last-of-type{border-bottom:0}.lrow .who b{font-weight:600}.lrow .who span{color:var(--sub);font-size:12.5px}
.mark{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:800;background:var(--panel);color:var(--mute);border:1px solid var(--line)}
.mark.won{background:var(--yes);color:#fff;border:0}.mark.lost{background:var(--no);color:#fff;border:0}.mark.live{border:2px solid var(--live);background:var(--livebg)}.mark.up{border:2px solid var(--yes);background:var(--yesbg)}.mark.down{border:2px solid var(--no);background:var(--nobg)}
.acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding-top:12px}.acts .s{font-size:12.5px;margin-right:auto}
.side .card,.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:15px 17px;margin-bottom:14px}
.card h3{margin:0 0 10px;font-size:14px;display:flex;justify-content:space-between;align-items:center}.card h3 span{color:var(--mute);font-size:12px;font-weight:600}
.g{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:1px 10px;padding:10px 0;border-top:1px solid var(--line)}.g:first-of-type{border-top:0;padding-top:2px}
.g .t{font-weight:600}.g .x{color:var(--sub);font-size:12.5px}.g .e{grid-row:span 2;align-self:center;text-align:right;font-size:12px;color:var(--sub)}.g .e b{display:block;color:var(--ink);font-size:13.5px}
.tag{font-size:10px;font-weight:800;padding:2px 6px;border-radius:5px;background:var(--livebg);color:var(--live);margin-left:6px;vertical-align:1px;letter-spacing:.03em}
.mini{display:flex;justify-content:space-between;padding:6px 0;color:var(--sub)}.mini b{color:var(--ink)}
.empty{padding:40px 20px;text-align:center;color:var(--sub)}.empty b{display:block;color:var(--ink);font-size:16px;margin-bottom:4px}
.skel{background:linear-gradient(90deg,var(--panel2),var(--hover),var(--panel2));background-size:200% 100%;animation:sk 1.2s infinite;border-radius:10px}
@keyframes sk{to{background-position:-200% 0}}
/* build */
.board{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.mrow{display:grid;grid-template-columns:96px minmax(0,1fr) minmax(0,1fr);gap:10px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line)}
.mrow:last-child{border-bottom:0}.mrow .when{color:var(--sub);font-size:12px;font-weight:600}
.pickbtn{display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid var(--line);background:var(--panel2);border-radius:10px;padding:9px 11px;text-align:left;min-width:0}
.pickbtn:hover{border-color:color-mix(in srgb,var(--acc) 50%,var(--line))}
.pickbtn.on{border-color:var(--acc);background:var(--accbg)}
.pickbtn .nm{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pickbtn .short{display:none}.pickbtn .pr{text-align:right;line-height:1.15;flex:none}
.pickbtn .pr b{display:block;font-size:14px}.pickbtn .pr span{font-size:11px;color:var(--mute)}
.val{font-size:10px;font-weight:800;color:var(--yes);background:var(--yesbg);padding:1px 5px;border-radius:4px;margin-left:5px}
.slip{position:sticky;top:84px}
.slip .pick{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:5px 0}.slip .pick .lrow{flex:1}
.slip .pick button{border:0;background:none;color:var(--mute);font-size:16px;padding:0 4px}
.sum{display:flex;justify-content:space-between;padding:6px 0;color:var(--sub)}.sum b{color:var(--ink)}
.big{font-size:28px;font-weight:800;letter-spacing:-.03em}
.ccard{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
.ccard .hd{display:flex;justify-content:space-between;align-items:flex-start}.ccard .hd b{font-size:22px;letter-spacing:-.02em}
.tier{font-size:11px;font-weight:700;color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
input.stake{width:72px;border:1px solid var(--line);background:var(--panel2);color:var(--ink);border-radius:9px;padding:7px 9px;font:600 14px Inter;text-align:right}
/* results */
.chart{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
.hrow{display:grid;grid-template-columns:90px minmax(0,1fr) 80px 90px 90px;gap:12px;padding:11px 16px;border-bottom:1px solid var(--line);align-items:center}
.toast{position:fixed;left:50%;bottom:calc(84px + env(safe-area-inset-bottom));transform:translateX(-50%) translateY(20px);opacity:0;background:var(--ink);color:var(--bg);
 padding:11px 16px;border-radius:12px;font-weight:600;transition:.25s;z-index:50;max-width:min(560px,92vw);text-align:center;pointer-events:none}.toast.good{background:var(--yes);color:#04130c}.toast.bad{background:var(--no);color:#fff}
.toast.on{opacity:1;transform:translateX(-50%)}.toast[hidden]{display:none!important}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:60;padding:20px}
.modal.on{display:flex}.sheet{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:22px;max-width:420px;width:100%;box-shadow:0 30px 80px rgba(0,0,0,.45)}
.sheet h3{margin:0 0 6px;font-size:19px;letter-spacing:-.02em}.sheet p{color:var(--sub);margin:0 0 18px}.sheet .row{display:flex;gap:10px;justify-content:flex-end}
.spin{width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;display:inline-block;animation:sp .7s linear infinite;vertical-align:-2px}
@keyframes sp{to{transform:rotate(360deg)}}
.tabbar{display:none}
/* phase 3 */
.doit{display:grid;gap:10px;margin:4px 0 18px}
.dcard{background:linear-gradient(100deg,var(--yesbg),transparent 70%),var(--panel);border:1px solid color-mix(in srgb,var(--yes) 45%,transparent);border-radius:var(--r);padding:16px 18px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 18px;align-items:center}
.dcard.idea{background:linear-gradient(100deg,var(--accbg),transparent 70%),var(--panel);border-color:color-mix(in srgb,var(--acc) 45%,transparent)}
.dcard.gone{opacity:.6;filter:saturate(.4);animation:goneout .5s ease 3.8s forwards}@keyframes goneout{to{opacity:0;transform:scale(.97)}}
.dcard.warn{background:linear-gradient(100deg,var(--livebg),transparent 70%),var(--panel);border-color:color-mix(in srgb,var(--live) 45%,transparent)}
.dcard h4{margin:0;font-size:15.5px;letter-spacing:-.01em}.dcard p{margin:2px 0 0;color:var(--sub);font-size:13px}
.dnums{display:flex;gap:18px;margin-top:8px;flex-wrap:wrap}.dnums div{font-size:11px;color:var(--mute);font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.dnums b{display:block;color:var(--ink);font-size:16px;letter-spacing:-.01em;text-transform:none}
.dbtns{display:flex;gap:8px;grid-row:span 2}
.calm{display:flex;align-items:center;gap:12px;color:var(--sub);background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:12px 16px;margin:4px 0 18px;font-size:13.5px}
.calm i{width:8px;height:8px;border-radius:50%;background:var(--yes);box-shadow:0 0 0 4px var(--yesbg);flex:none}
.why{color:var(--sub);font-size:12.5px;margin-top:6px}
.moment{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;padding:8px 0;border-top:1px solid var(--line);font-size:13px}
.moment:first-of-type{border-top:0}.moment .k{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;background:var(--panel2);font-size:13px}
.moment time{color:var(--mute);font-size:11.5px}
.flash{animation:fl 1.6s ease}@keyframes fl{0%{background:var(--accbg)}100%{background:transparent}}
.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.gt{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px;display:grid;gap:10px}
.gt.live{border-color:color-mix(in srgb,var(--live) 50%,transparent)}.gt.live.up{border-color:color-mix(in srgb,var(--yes) 55%,transparent)}.gt.live.down{border-color:color-mix(in srgb,var(--no) 55%,transparent)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--mute);margin:10px 2px 0}.legend .leg{font-size:11px}
.gt .top2{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.gt .tm{font-weight:700;font-size:15px}.gt .vs{color:var(--mute);font-size:12.5px}
.gt .sc{font-size:24px;font-weight:800;letter-spacing:-.02em;text-align:right;line-height:1}.gt .sc small{display:block;font-size:11.5px;color:var(--mute);font-weight:600;margin-top:4px}
.gt .ch{display:flex;align-items:baseline;gap:8px}.gt .ch b{font-size:22px}.gt .ch span{color:var(--mute);font-size:12px}
.gt svg{width:100%;height:56px;display:block}
.gt .ft{display:flex;justify-content:space-between;color:var(--sub);font-size:12.5px;border-top:1px solid var(--line);padding-top:10px}
.board2{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;background:var(--panel2);border-radius:14px;padding:16px 18px;margin-bottom:14px;box-shadow:inset 0 0 0 1.5px var(--line)}
.board2.up{box-shadow:inset 0 0 0 1.5px color-mix(in srgb,var(--yes) 60%,transparent)}.board2.down{box-shadow:inset 0 0 0 1.5px color-mix(in srgb,var(--no) 60%,transparent)}
.tm2{display:flex;align-items:center;gap:12px}.tm2.r{justify-content:flex-end}.tm2 span{font-weight:700;color:var(--sub)}.tm2 b{font-size:38px;letter-spacing:-.03em;line-height:1}
.mid2{text-align:center}.mid2 .clk{font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
.fresh{font-size:11.5px;font-weight:500;letter-spacing:0;text-transform:none;color:var(--mute);margin-left:auto;white-space:nowrap;font-variant-numeric:tabular-nums}
.fresh.old{color:var(--no)}
.sheet.wide{max-width:880px;max-height:calc(100vh - 40px);overflow:auto;padding:24px}
.dhead{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}
.dkpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}
.dkpis div{background:var(--panel2);border-radius:12px;padding:10px 12px}.dkpis span{display:block;color:var(--mute);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.dkpis b{font-size:17px}
.chartbox{background:var(--panel2);border-radius:12px;padding:12px 12px 6px;margin-bottom:16px}.chartbox svg{width:100%;display:block}
.key{display:flex;gap:14px;font-size:12px;color:var(--sub);margin:2px 0 8px}.key i{display:inline-block;width:10px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
.dlegs .lg{display:grid;grid-template-columns:minmax(0,1fr) 120px 56px;gap:12px;align-items:center;padding:9px 0;border-top:1px solid var(--line)}
.dlegs svg{width:120px;height:28px}
.bars2 .br{display:grid;grid-template-columns:110px minmax(0,1fr) 92px;gap:10px;align-items:center;font-size:12.5px;padding:5px 0}
.bars2 .tr2{height:10px;background:var(--panel2);border-radius:6px;position:relative;overflow:hidden}.bars2 .tr2 i{position:absolute;top:0;bottom:0;border-radius:6px}
.sgt{display:grid;grid-template-columns:minmax(0,1fr) 46px 54px 66px;gap:7px 8px;font-size:12.5px;align-items:center}
.sgt>span{text-align:right}.sgt>span:nth-child(-n+4){color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.sgt b{font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;line-height:1.25}.sgt b small{font-weight:500}
.lines .lhd{padding:10px 16px 6px;font-weight:700;font-size:13px;border-top:1px solid var(--line)}
.lrow2{display:grid;grid-template-columns:minmax(0,1fr) 48px 48px 78px;gap:8px;align-items:center;padding:6px 16px;font-size:13px}
.lrow2 .btn{padding:5px 8px;font-size:12px}
.daybar{margin:-2px 0 12px;width:max-content;max-width:100%}
.qline{display:flex;flex-direction:column;gap:2px;border-radius:10px;padding:9px 12px;font-size:12.5px;background:var(--panel2)}.qline span{color:var(--sub)}
.qline.good{background:var(--yesbg)}.qline.good b{color:var(--yes)}.qline.bad{background:var(--nobg)}.qline.bad b{color:var(--no)}
.pred{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;border-radius:99px;padding:3px 9px;background:var(--panel2);color:var(--sub)}
.pred.good{background:var(--yesbg);color:var(--yes)}.pred.bad{background:var(--nobg);color:var(--no)}
.live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--yes);margin-right:6px;animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--yes) 60%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
@media (max-width:900px){.dcard{grid-template-columns:minmax(0,1fr)}.dbtns{grid-row:auto}.dbtns .btn{flex:1}.dkpis{grid-template-columns:repeat(2,minmax(0,1fr))}
 .modal{padding:0;align-items:flex-end}.sheet.wide{max-height:92vh;border-radius:18px 18px 0 0;padding:18px 16px calc(18px + env(safe-area-inset-bottom))}
 .dlegs .lg{grid-template-columns:minmax(0,1fr) 84px 46px}.dlegs svg{width:84px}.games{grid-template-columns:minmax(0,1fr)}}
/* live field strip (football game page; our own art). .fld (not .field, which is the login passcode wrapper). */
.fstrip{margin:0 0 16px}
.fld{position:relative;height:84px;border-radius:12px;overflow:hidden;box-shadow:inset 0 0 0 1.5px var(--line);background:#0b5d2a}
.fld .grass{position:absolute;inset:0 8.333% 20px 8.333%;background:repeating-linear-gradient(90deg,#0b5d2a 0,#0b5d2a 10%,#0c6a30 10%,#0c6a30 20%)}
.fld .ez{position:absolute;top:0;bottom:20px;width:8.333%;display:grid;place-items:center;opacity:.92}
.fld .ez.l{left:0}.fld .ez.r{right:0}
.fld .ez span{color:#fff;font-weight:800;font-size:11px;letter-spacing:.04em;writing-mode:vertical-rl;transform:rotate(180deg);text-shadow:0 1px 2px rgba(0,0,0,.5)}
.fld .grass i{position:absolute;top:0;bottom:0;width:0}
/* The ball and possession arrow sit on the field's vertical midline (centred by their own translate(..,-50%)); the rule above would pin their box top to 0 and clip the top half, so win the cascade and put them back on 50% (#93). */
.fld .grass i.fball,.fld .grass i.fdir{top:50%;bottom:auto}
.fld .grass>i:not(.fball):not(.fdir):not(.fdline):not(.frz){border-left:1px solid rgba(255,255,255,.28)}
.fld .frz{background:rgba(220,40,40,.28);width:auto}
.fld .fdline{border-left:3px solid #f5d020;box-shadow:0 0 6px rgba(245,208,32,.7);z-index:3}
.fld .fball{width:24px;height:14px;top:50%;transform:translate(-50%,-50%);z-index:4;transition:left .5s var(--ease)}
.fstrip.noanim .fball{transition:none}
.fld .fball svg{width:24px;height:14px}.fld .fball ellipse{fill:#8a4b1e;stroke:#fff;stroke-width:1.2}.fld .fball line{stroke:#fff;stroke-width:1.2}
.fld .fdir{top:50%;color:#fff;font-size:13px;z-index:4;text-shadow:0 1px 2px rgba(0,0,0,.6);transition:left .5s var(--ease);width:auto}
.fstrip.noanim .fdir{transition:none}
.fld .ruler{position:absolute;left:0;right:0;bottom:0;height:20px;background:rgba(0,0,0,.35)}
.fld .ruler span{position:absolute;transform:translateX(-50%);top:3px;color:#dfe8e0;font-size:10px;font-weight:700;font-variant-numeric:tabular-nums}
.situ{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:10px;font-size:13.5px}
.situ .dd{font-weight:800}.situ .rzt{color:#fff;background:var(--no);border-radius:6px;padding:1px 7px;font-size:10.5px;font-weight:800;letter-spacing:.04em}
.lastplay{display:flex;gap:8px;align-items:baseline;margin-top:8px;font-size:12.5px;color:var(--sub);background:var(--panel2);border-radius:10px;padding:8px 11px}
.lastplay .lpt{font-weight:800;color:var(--ink);text-transform:uppercase;font-size:10.5px;letter-spacing:.04em;white-space:nowrap}
.tdots{display:flex;gap:3px;justify-content:center;margin-top:4px}.tdots i{width:7px;height:4px;border-radius:2px;background:var(--line)}.tdots i.on{background:var(--sub)}
.poss{color:var(--live);font-size:11px;margin-left:4px}
/* game page tabs (a horizontally scrolling row with a sliding underline) and the play-by-play tab */
.gtabs{position:relative;display:flex;gap:2px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;scrollbar-width:none;border-bottom:1px solid var(--line);margin:2px 0 14px}
.gtabs::-webkit-scrollbar{display:none}
.gtab{flex:0 0 auto;border:0;background:none;color:var(--sub);font-weight:700;font-size:12.5px;letter-spacing:.04em;text-transform:uppercase;padding:11px 14px;white-space:nowrap;scroll-snap-align:center}
.gtab.on{color:var(--ink)}
.gtabind{position:absolute;bottom:0;left:0;width:0;height:3px;border-radius:3px 3px 0 0;background:var(--acc);transition:left .28s var(--spring),width .28s var(--spring);pointer-events:none}
.gpanel[hidden]{display:none}
.pcard{background:var(--panel2);border-radius:14px;padding:12px;margin-bottom:6px}
.pcard.sc{background:var(--yesbg)}.pcard.to{background:var(--nobg)}
.pch{display:flex;align-items:center;gap:8px}.pcm{flex:1;min-width:0;text-align:center}
.pct{font-weight:800;font-size:15px;overflow-wrap:anywhere}.pcs{font-size:12px;color:var(--sub);margin-top:2px}
.pstep{flex:0 0 38px;width:38px;height:38px;border-radius:50%;border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:20px;line-height:1;display:grid;place-items:center;padding:0}
.pstep:disabled{opacity:.35}
.pctx{margin-top:10px;font-size:13.5px;line-height:1.45;overflow-wrap:anywhere}
.pcf{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:10px;font-size:12px;color:var(--sub)}
.plive{border:0;border-radius:99px;background:var(--live);color:#1a1100;font-weight:800;font-size:12px;padding:6px 12px}.plive[hidden]{display:none}
.pnote{font-size:11.5px;color:var(--mute);margin:2px 2px 12px}
.pq{width:100%;display:flex;align-items:center;justify-content:space-between;border:0;background:none;color:var(--ink);font-weight:800;font-size:15px;padding:12px 2px;border-top:1px solid var(--line)}
.pdr{width:100%;display:flex;align-items:center;gap:8px;border:0;background:var(--panel2);border-radius:10px;padding:9px 10px;margin:6px 0 4px;color:var(--ink);text-align:left;font-size:13px;min-width:0}
.pdr .pres{font-weight:800}.pdr .psum{margin-left:auto;font-size:12px;white-space:nowrap}
.pdr.sc .pres{color:var(--yes)}.pdr.to .pres{color:var(--no)}
.pdot{width:10px;height:10px;border-radius:50%;box-shadow:0 0 0 1.5px var(--line);flex:0 0 auto}
.chev{flex:0 0 auto;transition:transform .2s var(--ease)}[aria-expanded=false]>.chev{transform:rotate(-90deg)}
.pp{display:grid;grid-template-columns:84px minmax(0,1fr);gap:10px;padding:9px 8px;border-bottom:1px solid var(--line);font-size:13px;cursor:pointer}
.pp:last-child{border-bottom:0}.pp.sc{background:var(--yesbg)}.pp.to{background:var(--nobg)}.pp.cur{box-shadow:inset 3px 0 0 var(--acc)}
.ppm b{display:block;font-size:12.5px}.ppm .m{font-size:11.5px}.ppt{overflow-wrap:anywhere;line-height:1.4}
.situ .rzt.rpl{background:var(--acc)}
/* play illustrations on the field strip (illustrative only; .noanim / reduced motion turns them all off) */
.fld .grass .fproj{position:absolute;top:50%;width:11px;height:11px;margin:-5px 0 0 -5px;z-index:6;transition:left var(--dur,600ms) linear}
.fproj b{display:block;width:100%;height:100%;border-radius:50%;background:#8a4b1e;box-shadow:0 0 0 1.5px #fff;animation:arcY var(--dur,600ms) both}
@keyframes arcY{0%{transform:translateY(0);animation-timing-function:ease-out}50%{transform:translateY(calc(var(--ah,20px)*-1));animation-timing-function:ease-in}100%{transform:translateY(0)}}
.fld .grass .ftrail{position:absolute;top:50%;height:5px;margin-top:-2px;border-radius:3px;background:rgba(255,255,255,.8);z-index:3;animation:trailIn .9s ease-out both}
.fld .grass .ftrail.red{background:rgba(255,80,80,.9)}
@keyframes trailIn{0%{transform:scaleX(0);opacity:.95}55%{transform:scaleX(1);opacity:.95}100%{transform:scaleX(1);opacity:0}}
.fld .grass .fflag{position:absolute;top:8px;margin-left:-9px;font-size:18px;z-index:7;transform-origin:bottom center;animation:flagPop 1.4s ease-out both}
@keyframes flagPop{0%{transform:scale(0) rotate(-30deg);opacity:0}25%{transform:scale(1.3) rotate(8deg);opacity:1}40%{transform:scale(1) rotate(0)}85%{opacity:1}100%{opacity:0}}
.fld .grass .ftag{position:absolute;left:50%;top:6px;transform:translateX(-50%);z-index:8;padding:2px 9px;border-radius:99px;background:rgba(0,0,0,.7);color:#fff;font-weight:800;font-size:11px;letter-spacing:.06em;white-space:nowrap;animation:tagPop 1.3s ease-out both}
.fld .grass .ftag.good{background:var(--yes)}.fld .grass .ftag.bad{background:var(--no)}
@keyframes tagPop{0%{opacity:0;transform:translateX(-50%) scale(.6)}20%{opacity:1;transform:translateX(-50%) scale(1.12)}35%{transform:translateX(-50%) scale(1)}85%{opacity:1}100%{opacity:0}}
.fld .ez.tdflash{animation:tdf .55s ease-in-out 2}@keyframes tdf{0%,100%{filter:none}50%{filter:brightness(2.1) saturate(1.5)}}
.fld .fball.turn ellipse{animation:turnf .5s ease-in-out 3}@keyframes turnf{0%,100%{fill:#8a4b1e}50%{fill:#ff3b4a}}
/* settings */
.set{display:grid;grid-template-columns:210px minmax(0,820px);gap:32px;justify-content:center}.set>*{min-width:0}
.sidx{position:sticky;top:86px;align-self:start;display:grid;gap:2px}
.sidx a{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:9px;color:var(--sub);font-weight:600;font-size:13.5px}
.sidx a:hover{background:var(--panel2);color:var(--ink)}.sidx .sv{margin-top:14px;padding:0 12px;color:var(--mute);font-size:12px}
.shead{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin:2px 0 18px}.shead h1{margin:0;font-size:24px;letter-spacing:-.02em}
.shead p{margin:4px 0 0;color:var(--mute)}.saved{margin-left:auto;font-size:12.5px;font-weight:700;color:var(--mute);display:flex;align-items:center;gap:7px}
.saved.ok{color:var(--yes)}
.scard{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);margin-bottom:18px;scroll-margin-top:84px}
.scard>header{padding:18px 22px 14px;display:flex;gap:12px;align-items:flex-start}.scard>header .ic{font-size:18px;line-height:1.2}
.scard h3{margin:0;font-size:15.5px;letter-spacing:-.01em}.scard header p{margin:3px 0 0;color:var(--mute);font-size:12.5px;max-width:560px}
.srow{display:flex;align-items:center;gap:18px;padding:13px 22px;border-top:1px solid var(--line);min-height:58px}
.srow .l{flex:1;min-width:0}.srow .l b{font-weight:600;display:block}.srow .l small{color:var(--mute);font-size:12.5px;display:block;margin-top:1px}
.srow.dim{opacity:.45;pointer-events:none}
.hxbtn{display:flex;align-items:center;gap:10px;width:100%;white-space:normal;text-align:left;font-weight:600;position:relative;min-height:44px}.hxid{display:inline-grid;place-items:center;flex:none;width:24px;height:24px;border-radius:8px;background:var(--acc);color:#fff;font-weight:800;font-size:13px}
.hxbtn input[switch]:not(.tg){margin-left:auto;flex:none}.hxbtn input.hxnat{position:absolute;right:12px;top:50%;width:2px;height:2px;opacity:.01;margin:0}.hxbtn input.tg{margin-left:auto}
.hxs{min-width:92px;text-align:right;color:var(--sub);font-weight:700;font-size:13px;opacity:0}.hxs.on{opacity:1;animation:obump .32s var(--spring)}
.hxrow .l small{margin-top:6px}
.rng{display:flex;align-items:center;gap:14px;width:min(340px,48%)}.rng output{min-width:70px;text-align:right;font-weight:700;font-size:14.5px}
input[type=range]{-webkit-appearance:none;appearance:none;flex:1;height:6px;border-radius:9px;outline:none;
 background:linear-gradient(90deg,var(--acc) var(--p,50%),var(--panel2) var(--p,50%))}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;background:#fff;border:0;box-shadow:0 1px 4px rgba(0,0,0,.45),0 0 0 1px rgba(0,0,0,.06)}
input[type=range]::-moz-range-thumb{width:20px;height:20px;border-radius:50%;background:#fff;border:0;box-shadow:0 1px 4px rgba(0,0,0,.45)}
.tg{-webkit-appearance:none;appearance:none;width:44px;height:26px;border-radius:99px;background:var(--panel2);border:1px solid var(--line);position:relative;flex:none;cursor:pointer;transition:background .18s}
.tg::after{content:"";position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.4);transition:transform .18s}
.tg:checked{background:var(--yes);border-color:var(--yes)}.tg:checked::after{transform:translateX(18px)}
.seg{display:flex;background:var(--panel2);border-radius:10px;padding:3px;gap:2px;flex-wrap:wrap}
.seg button{border:0;background:none;padding:7px 11px;border-radius:8px;color:var(--sub);font-weight:600;font-size:12.5px}
.seg button.on{background:var(--panel);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.3)}
.mixl>.mixr{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;padding:12px 22px;border-top:1px solid var(--line)}
.mixr b{display:block;font-weight:600}.mixr small{color:var(--mute);font-size:12px}
.mixs{display:flex;flex-direction:column;gap:8px;font-size:13px;color:var(--mute)}.mixs>div{display:flex;align-items:center;gap:8px}.mixs>div>span:first-child{min-width:84px}
.mixt{display:grid;grid-template-columns:minmax(0,1fr) repeat(3,minmax(96px,126px));align-items:center;border-top:1px solid var(--line)}
.mixt>div{padding:11px 22px 11px 0;border-top:1px solid var(--line)}.mixt>div:nth-child(4n+1){padding-left:22px}
.mixt .h{border-top:0;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding-top:12px;padding-bottom:6px}
.mixt b{display:block;font-weight:600}.mixt small{color:var(--mute);font-size:12px}
.stp{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:9px;background:var(--panel2);overflow:hidden}
.stp button{border:0;background:none;width:30px;height:30px;color:var(--sub);font-size:16px;font-weight:600}.stp button:hover{color:var(--ink);background:var(--hover)}
.stp span{min-width:28px;text-align:center;font-weight:700}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));border-top:1px solid var(--line);overflow:hidden}
.kv>div{padding:13px 22px;box-shadow:1px 1px 0 var(--line)}.kv>div>span{display:block;color:var(--mute);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.kv b{font-size:14.5px;display:flex;align-items:center;gap:7px;margin-top:2px;word-break:break-all}
.sact{display:flex;gap:8px;flex-wrap:wrap;padding:14px 22px;border-top:1px solid var(--line)}
.code{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px;word-break:break-all;user-select:all}
.logbox{font:11.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--sub);background:var(--bg);border-top:1px solid var(--line);padding:12px 22px;max-height:220px;overflow:auto;white-space:pre-wrap;word-break:break-word;border-radius:0 0 var(--r) var(--r)}
input.txt{width:100%;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:10px 12px;color:var(--ink);font:inherit}
@media (max-width:1100px){.set{grid-template-columns:minmax(0,1fr)}.sidx{position:static;display:flex;overflow-x:auto;scrollbar-width:none;gap:4px;margin-bottom:6px}.sidx a{white-space:nowrap;background:var(--panel);border:1px solid var(--line);border-radius:99px;padding:6px 12px;font-size:12.5px}.sidx .sv{display:none}}
@media (max-width:640px){.srow{flex-wrap:wrap;gap:10px;padding:13px 16px}.srow .rng{width:100%}.scard>header{padding:16px 16px 12px}.kv>div{padding:12px 16px}.sact{padding:12px 16px}
 .mixt{grid-template-columns:minmax(0,1fr) repeat(3,auto)}.mixt small{display:none}.mixt>div{padding:10px 6px 10px 0}.mixt>div:nth-child(4n){padding-right:16px}.mixt>div:nth-child(4n+1){padding-left:16px}.stp button{width:24px;height:28px}.stp span{min-width:18px}.seg button{padding:7px 8px}}
/* medium windows */
@media (max-width:1360px){
 .grid{grid-template-columns:minmax(0,1fr)}.side{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}.side .card{margin:0}
 .kpis{grid-template-columns:repeat(5,minmax(0,1fr))}.kpi:nth-child(n+4){display:block}
 .thead{display:none}
 .trow{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"name ver" "legs legs" "nums nums";gap:8px;padding:14px;min-height:0}
 .trow .name{grid-area:name}.trow .legs{grid-area:legs}.trow .verdict{grid-area:ver}.trow .numwrap{grid-area:nums;display:grid!important;grid-template-columns:repeat(4,1fr);gap:6px}
 .trow .numwrap>div{text-align:left!important}.trow .numwrap>div::before{content:attr(data-l);display:block;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
 .bar{margin-left:0}.status span:last-child{display:none}
 h2{flex-wrap:wrap}h2 .r{margin-left:0;width:100%;order:3}
 .chips{flex-wrap:wrap}}
/* phone */
@media (max-width:900px){
 .top{height:auto;padding:calc(10px + env(safe-area-inset-top)) 16px 10px;gap:10px}
 .nav,.status,.cta,.ts.wk{display:none}.tr{gap:12px}
 main{padding:14px 14px calc(96px + env(safe-area-inset-bottom))}
 .grid{grid-template-columns:minmax(0,1fr)}.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.kpi:first-child{grid-column:span 2}
 .kpi b{font-size:22px}.thead{display:none}
 .trow{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"name ver" "legs legs" "nums nums";gap:8px;padding:14px;min-height:0}
 .trow .name{grid-area:name}.trow .legs{grid-area:legs}.trow .verdict{grid-area:ver}.trow .numwrap{grid-area:nums;display:grid!important;grid-template-columns:repeat(4,1fr);gap:6px}
 .trow .numwrap>div{text-align:left!important}.trow .numwrap>div::before{content:attr(data-l);display:block;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
 .bar{margin-left:0}
 .alert{flex-wrap:wrap}.alert .acts2{width:100%;display:flex;gap:8px}.alert .acts2 .btn{flex:1}
 .mrow{grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-areas:"when when" "a b"}.mrow .when{grid-area:when}
 .slip{position:static}
 .chips{flex-wrap:wrap;gap:6px}.chips .chip{padding:6px 11px;font-size:12.5px}
 h2{flex-wrap:wrap}h2 .r{margin-left:0;width:100%;order:3}
 .pickbtn .full{display:none}.pickbtn .short{display:inline}
 .hrow{grid-template-columns:minmax(0,1fr) auto auto;grid-template-areas:"p p p" "w n v"}.hrow .hp{grid-area:p}
 .tabbar{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:30;justify-content:space-around;padding:7px 6px calc(6px + env(safe-area-inset-bottom));
  background:color-mix(in srgb,var(--bg) 92%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);border-top:1px solid var(--line)}
 .tabbar button{flex:1;border:0;background:none;color:var(--mute);display:flex;flex-direction:column;align-items:center;gap:3px;font-size:10.5px;font-weight:700}
 .tabbar button svg{width:25px;height:25px}.tabbar button.on{color:var(--acc)}
}
.trow .name b .sweat,.sweat{display:inline-flex!important;flex-direction:row;gap:3px;margin:0 0 0 9px;vertical-align:middle;position:relative;top:-1px;font-size:0}
.sweat i{display:block;width:12px;height:6px;border-radius:3px;background:var(--line)}.sweat i.w{background:var(--yes)}
.sweat i.u{background:color-mix(in srgb,var(--yes) 45%,var(--line))}.sweat i.x{background:var(--no)}
.trow.hot{box-shadow:inset 3px 0 0 var(--yes)}
.moment-bar{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 14px;margin:0 0 12px;border-radius:14px;
 background:color-mix(in srgb,var(--yes) 14%,var(--panel));border:1px solid color-mix(in srgb,var(--yes) 45%,transparent);animation:glow 2.4s ease-in-out infinite}
.moment-bar b{display:block;font-size:14.5px}.moment-bar span{font-size:12.5px;color:var(--sub)}
@keyframes glow{50%{box-shadow:0 0 0 4px color-mix(in srgb,var(--yes) 18%,transparent)}}
.recap .rh{display:flex;justify-content:space-between;align-items:flex-start}.recap .x{border:0;background:none;color:var(--mute);font-size:16px;cursor:pointer}
.confetti{position:fixed;inset:0;pointer-events:none;z-index:99;overflow:hidden}.confetti i{position:absolute;top:-12px;width:8px;height:12px;border-radius:2px;animation:fall 2.2s cubic-bezier(.2,.6,.4,1) forwards}
@keyframes fall{to{top:105vh;transform:rotate(720deg) translateX(40px);opacity:.9}}
.whatif{display:grid;grid-template-columns:1fr 1fr;gap:8px}.wi{padding:10px 12px;border-radius:12px;background:var(--panel2)}.wi span{display:block;font-size:12px;color:var(--sub)}
.wi b{font-size:20px}.wi.up b{color:var(--yes)}.wi.down b{color:var(--no)}.wi small{display:block;font-size:11.5px;color:var(--mute)}
@media (prefers-reduced-motion:reduce){.moment-bar{animation:none}.confetti{display:none}}
.hfilters{display:flex;flex-direction:column;gap:8px;margin-bottom:8px}.hfilters .chips{flex-wrap:wrap;align-items:center}
.hfilters .chip{flex:none}.hsort{flex:none;margin-left:auto;background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font:inherit;font-size:13px}
.hrow2{padding:12px 14px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:7px}.hrow2:last-child{border-bottom:0}
.hd2{display:flex;align-items:center;gap:8px;min-width:0}.hd2 .hs{font-size:16px}.hd2 .m{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hn{display:flex;gap:16px;font-size:12.5px;color:var(--sub)}.hn b{color:var(--ink)}
.rbtrack{height:6px;border-radius:3px;background:var(--panel2);overflow:hidden;margin:12px 0 8px}.rbtrack i{display:block;height:100%;border-radius:3px;background:var(--acc);transition:width .6s cubic-bezier(.2,.8,.2,1)}
.rbstrip{display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--sub);margin:0 2px 10px}
.panel{padding:16px}.phead{display:flex;gap:14px;align-items:center;justify-content:space-between;margin-bottom:10px}
.pring{--p:0;flex:none;width:74px;height:74px;border-radius:50%;display:grid;place-content:center;text-align:center;
 background:radial-gradient(closest-side,var(--panel) 79%,transparent 80% 100%),conic-gradient(var(--yes) calc(var(--p)*1%),var(--panel2) 0)}
.pring b{font-size:18px;line-height:1}.pring small{font-size:9.5px;color:var(--mute);font-weight:600}
.plist{display:flex;flex-direction:column;gap:8px}.pitem{display:flex;gap:10px;align-items:flex-start;padding:11px 12px;border-radius:12px;background:var(--panel2)}
.pitem .pliv{color:var(--live)}.pitem.off{opacity:.4}.pitem .pi{font-size:20px;line-height:1.2}.pitem .pm{flex:1;min-width:0}.pitem .pk{font-size:11px;font-weight:700;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}
.pitem .pm b{display:block;font-size:15px;line-height:1.3;margin:2px 0;overflow-wrap:anywhere}.pitem .pg{font-size:12.5px;color:var(--sub);line-height:1.35;overflow-wrap:anywhere}.pitem .pg:empty{display:none}.pitem .pg div+div{margin-top:1px}.pitem .pn{font-size:12.5px;color:var(--sub)}.pitem .pw{font-size:12px;color:var(--mute);margin-top:4px;line-height:1.4}
.pitem .ps{display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex:none}.pitem .ps b{font-size:15px}.pitem .x{border:0;background:none;color:var(--mute);font-size:15px;cursor:pointer;padding:2px 4px}
.bets{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:12px}
.bet{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:12px}
.bet .bt{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.bet .bt b{display:block;font-size:17px;line-height:1.3;margin-top:3px}
.bet .kind{font-size:11.5px;font-weight:700;color:var(--sub);text-transform:uppercase;letter-spacing:.05em}
.bet .ret{flex:none;text-align:right;color:var(--yes);font-weight:800;font-size:22px;line-height:1}.bet .ret small{display:block;font-size:10.5px;font-weight:600;color:var(--mute);margin-top:3px}
.bnums{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.bnums div{background:var(--panel2);border-radius:10px;padding:8px 10px;font-size:11.5px;color:var(--mute)}
.bnums b{display:block;font-size:15px;color:var(--ink);margin-top:2px}.bet .why{font-size:12.5px;color:var(--sub);line-height:1.45}
.lrows{display:flex;flex-direction:column;gap:6px}.lrow{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:10px;background:var(--panel2);border:1px dashed transparent;min-width:0}
.lrow.flip{cursor:pointer}.lrow.flip:hover{border-color:var(--acc)}.lrow .li{font-size:19px;line-height:1;flex:none;width:24px;text-align:center}.lrow .lm{flex:1;min-width:0}
.lrow .lm b{display:block;font-size:14.5px;line-height:1.25;overflow-wrap:anywhere}.lrow .lm small{display:block;font-size:12px;color:var(--mute);line-height:1.3;overflow-wrap:anywhere}
.lrow .lp{flex:none;font-weight:800;font-size:14px;color:var(--sub);white-space:nowrap}.lrow .lp i{font-style:normal;margin-left:6px;color:var(--mute);font-weight:600}
.mrow .when .wlg{font-size:11px;font-weight:800;letter-spacing:.03em;color:var(--mute);text-transform:uppercase}
.slipbar{display:none}.leg.flip{cursor:pointer;border:1px dashed transparent}.leg.flip:hover{border-color:var(--acc)}
.flipnote{font-size:12.5px;line-height:1.4;padding:9px 11px;border-radius:9px;background:var(--panel2);margin:2px 0 4px}.flipnote b.v{display:inline-block;margin-right:6px}
.flipnote.good b.v{color:var(--yes)}.flipnote.bad b.v{color:var(--no)}.flipnote.mid b.v{color:var(--warn,#e0a040)}
@media (max-width:900px){.slipbar{display:flex;position:fixed;left:12px;right:12px;bottom:calc(74px + env(safe-area-inset-bottom));z-index:29;align-items:center;gap:10px;
 padding:10px 12px 10px 14px;border-radius:14px;background:var(--acc);color:#fff;box-shadow:0 8px 28px rgba(0,0,0,.35);font-weight:700;font-size:14px}
 .slipbar span{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.slipbar button{border:0;border-radius:9px;padding:8px 12px;font-weight:800;background:#fff;color:var(--acc)}
 .slipbar .x{background:transparent;color:#fff;padding:8px 6px}}
@media (min-width:1361px){.numwrap{display:contents}}
/* ---- makeover 1: press feedback on everything, push sheets, the hero chart ---- */
:root{--out:cubic-bezier(.22,.8,.24,1)}
.prs{transform:scale(.965)!important;transition:transform .08s var(--ease)!important}
.trow.prs,.pitem.prs,.gt.prs,.dcard.prs,.ccard.prs,.bet.prs,.mrow.prs{transform:scale(.985)!important}
.srow.prs,.moment.prs,.g.prs,.lrow.prs,.sech.prs,.mixr.prs,.hrow2.prs{transform:none!important;background:var(--hover)}
a.prs{opacity:.6}.tabbar button.prs,.nav button.prs{transform:scale(.88)!important}
.bar i{transition:width .65s var(--ease)}
.modal.push{opacity:1;padding:0;align-items:stretch;justify-content:flex-end;background:rgba(0,0,0,0);transition:background-color .27s var(--out);overflow:hidden}
.modal.push.on{background:rgba(0,0,0,.5)}
.modal.push .sheet{width:min(880px,100%);max-width:none;height:100%;max-height:none;border-radius:0;border:0;border-left:1px solid var(--line);padding:0 0 calc(28px + env(safe-area-inset-bottom));
 overflow-y:auto;overscroll-behavior:contain;transform:translateX(100%);transition:transform .27s var(--out);box-shadow:-24px 0 60px rgba(0,0,0,.35)}
.modal.push.on .sheet{transform:none}.modal.push .sheet.drag{transition:none}.modal.push .sheet .grab{display:none}
.pbar{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:6px;padding:calc(8px + env(safe-area-inset-top)) 10px 8px;
 background:color-mix(in srgb,var(--panel) 86%,transparent);-webkit-backdrop-filter:saturate(180%) blur(16px);backdrop-filter:saturate(180%) blur(16px);border-bottom:1px solid var(--line)}
.pbar .back{border:0;background:none;color:var(--acc);font-weight:700;font-size:16px;padding:6px 8px 6px 2px;display:inline-flex;align-items:center;gap:1px;flex:none}
.pbar .back svg{width:22px;height:22px}.pbar .pt{font-weight:700;font-size:14px;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pbody{padding:16px 22px 0}
main,.top{transition:transform .27s var(--out),filter .27s var(--out)}
body.pushed main,body.pushed .top{filter:brightness(.5)}
@media (max-width:900px){body.pushed main,body.pushed .top{transform:translateX(-30%)}.pbody{padding:14px 16px 0}}
.psk{display:grid;gap:12px}.psk i{display:block;background:var(--panel2);border-radius:12px}
.fadein{animation:fadein .2s var(--ease)}@keyframes fadein{from{opacity:0}to{opacity:1}}
.hv .big.scrub{color:var(--ink)}
.sparkw{touch-action:pan-y;user-select:none;-webkit-user-select:none;cursor:crosshair}
.hv .spark{height:76px}
.spark.draw{animation:reveal .75s var(--out)}@keyframes reveal{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
.sparkw .sdot.draw{animation:fadein .3s .6s both,sdot 1.8s .9s infinite}
.sdot{z-index:1;box-shadow:0 0 0 3px color-mix(in srgb,currentColor 28%,transparent),0 0 14px 2px color-mix(in srgb,currentColor 55%,transparent)}
@keyframes sdot{0%{box-shadow:0 0 0 0 color-mix(in srgb,currentColor 60%,transparent),0 0 14px 2px color-mix(in srgb,currentColor 55%,transparent)}100%{box-shadow:0 0 0 12px transparent,0 0 14px 2px color-mix(in srgb,currentColor 55%,transparent)}}
.scrl{position:absolute;top:0;bottom:0;width:1.5px;margin-left:-.75px;background:var(--sub);opacity:0;pointer-events:none;transition:opacity .15s}
.scrd{position:absolute;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;border:2px solid var(--panel);opacity:0;pointer-events:none;transition:opacity .15s;z-index:2}
.sparkw.on .scrl,.sparkw.on .scrd{opacity:1}.sparkw.on .sdot{opacity:.25}
.sbase{position:absolute;left:0;right:0;border-top:1px dashed var(--line);pointer-events:none}
.saxis{display:flex;justify-content:space-between;align-items:center;margin-top:6px;font-size:11px;color:var(--mute);font-weight:600}
.rng2{display:flex;gap:2px}.rng2 button{border:0;background:none;color:var(--mute);font-weight:700;font-size:12px;letter-spacing:.04em;padding:4px 8px;border-radius:7px}
.rng2 button.on{color:var(--ink)}
.sread{position:absolute;top:-2px;transform:translateX(-50%);font-size:11px;font-weight:700;color:var(--sub);white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .15s}
.sparkw.on .sread{opacity:1}
.hsk{display:grid;gap:10px;padding:18px 20px}.hsk i{display:block;background:var(--panel2);border-radius:10px}
.empty .btn{margin-top:14px}
@media (prefers-reduced-motion:reduce){.prs{transform:none!important;opacity:.7;transition:none!important}main,.top{transform:none!important}}
/* ---- makeover phase 2: live game cards, the Sold moment, the big hit, Results charts you can scrub */
.gc{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 16px 12px;display:grid;gap:10px;cursor:pointer;position:relative;overflow:hidden;transition:border-color .3s}
.gc.live{border-color:color-mix(in srgb,var(--live) 45%,transparent)}.gc.live.lup{border-color:color-mix(in srgb,var(--yes) 50%,transparent)}.gc.live.ldown{border-color:color-mix(in srgb,var(--no) 50%,transparent)}
.gc .gh{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:11.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mute)}
.gc .gh .lv{color:var(--live);display:flex;align-items:center;gap:6px;text-transform:none;letter-spacing:0;font-size:12px}
.gc .gh .lv i{width:7px;height:7px;border-radius:50%;background:var(--no);animation:pulse2 1.4s infinite}
.gc .tms{display:grid;gap:4px}.gc .gtr{display:flex;align-items:center;gap:10px;font-size:16px}.gc .gtr .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:700}
.gc .gtr.them .nm{font-weight:500;color:var(--sub)}.gc .gtr .pts{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.02em;min-width:30px;text-align:right}
.gc .gtr.them .pts{color:var(--sub)}.gc .gtr .mine{font-size:10.5px;font-weight:800;letter-spacing:.06em;color:var(--acc);background:var(--accbg);padding:2px 6px;border-radius:6px}
.gc .gl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:14px;align-items:center}
.gc .gl .ch b{display:block;font-size:24px;font-weight:800;letter-spacing:-.03em;line-height:1}.gc .gl .ch small{color:var(--mute);font-size:11.5px}
.gc .gl .gbar{height:3px;border-radius:2px;background:var(--line);margin-top:6px;overflow:hidden}.gc .gl .gbar i{display:block;height:100%;border-radius:2px;transition:width .6s var(--ease)}
.mline{position:relative;height:46px}.mline svg{width:100%;height:46px;display:block;overflow:visible}
.mline .sdot{width:8px;height:8px;margin:-4px 0 0 -4px}
.gc .bets{display:flex;flex-wrap:wrap;gap:6px;border-top:1px solid var(--line);padding-top:10px;align-items:center}
.gc .bets .bt{font-size:12px;font-weight:600;padding:3px 8px;border-radius:999px;background:var(--panel2);color:var(--sub);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gc .bets .bt.s{color:var(--ink);box-shadow:inset 0 0 0 1px var(--line)}.gc .bets .rd{margin-left:auto;font-weight:700;font-size:12.5px;color:var(--ink)}
.gc.scored{animation:scored 1.6s var(--ease)}.gc.scored.good{--sg:var(--yes)}.gc.scored.bad{--sg:var(--no)}
@keyframes scored{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--sg,var(--live)) 70%,transparent);background:color-mix(in srgb,var(--sg,var(--live)) 16%,var(--panel))}40%{box-shadow:0 0 0 10px transparent}100%{}}
.gc .pts.bump{animation:bump .7s var(--spring)}@keyframes bump{0%{transform:scale(1)}30%{transform:scale(1.45);color:var(--sg,var(--live))}100%{transform:none}}
.gc.done{opacity:.72}
.gsk{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;display:grid;gap:12px}.gsk i{display:block;background:var(--panel2);border-radius:8px}
.scrub{position:relative;touch-action:pan-y;user-select:none;-webkit-user-select:none;cursor:crosshair}
.scrub .scrl,.scrub .scrd,.scrub .sread{position:absolute}.scrub.on .scrl,.scrub.on .scrd,.scrub.on .sread{opacity:1}
.scrub .sread{top:-4px}
.plc .plh{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:10px}
.plc .plh b{font-size:26px;font-weight:800;letter-spacing:-.03em;display:block;line-height:1.1}.plc .plh small{color:var(--mute);font-size:12px;display:block;min-height:15px}
.plc svg{width:100%;height:150px;display:block}.plc rect.brc{transition:opacity .15s}.plc.on rect.brc{opacity:.35}.plc.on rect.brc.sel{opacity:1}
.plc .xl{display:flex;justify-content:space-between;font-size:11px;color:var(--mute);margin-top:6px}
.plc .rng2{flex:none}.plc .hint{font-size:11.5px;color:var(--mute);margin-top:6px}
.blist .hrow2{margin-bottom:8px}
.okcard .stamp{display:inline-block;font:700 10.5px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.14em;color:var(--sub);border:1px dashed var(--line);border-radius:6px;padding:3px 8px;margin-bottom:8px;animation:rise .4s .25s both}
.okcard .plp{display:inline-block;margin-top:4px;font-weight:800;font-size:14px;padding:4px 12px;border-radius:999px;background:var(--yesbg);color:var(--yes);animation:rise .4s .5s both}
.okcard .tkt{display:flex;justify-content:center;gap:0;margin:14px auto 4px;max-width:300px;border-top:1px dashed var(--line);padding-top:12px;animation:rise .4s .6s both}
.okcard .tkt div{flex:1;font-size:12px;color:var(--mute)}.okcard .tkt b{display:block;font-size:16px;color:var(--ink)}
.okcard.okloss circle{stroke:var(--sub);fill:var(--panel2)}.okcard.okloss path{stroke:var(--sub)}.okcard.okloss .amt{color:var(--ink)}.okcard.okloss .plp{background:var(--nobg);color:var(--no)}
.bigwin{position:fixed;inset:0;z-index:98;display:grid;place-items:center;background:radial-gradient(circle at 50% 42%,color-mix(in srgb,var(--yes) 26%,rgba(6,9,14,.9)),rgba(6,9,14,.94) 60%);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);animation:fadein .3s var(--ease);padding:16px}
.bigwin.out{opacity:0;transition:opacity .35s}
.bigwin .bw{text-align:center;max-width:360px;animation:bwin .7s var(--spring) both}
@keyframes bwin{from{transform:scale(.6);opacity:0}to{transform:none;opacity:1}}
.bigwin .ey{font-size:12px;font-weight:800;letter-spacing:.24em;color:var(--yes);text-transform:uppercase}
.bigwin .amt{font-size:58px;font-weight:900;letter-spacing:-.05em;color:#fff;text-shadow:0 0 34px color-mix(in srgb,var(--yes) 80%,transparent);line-height:1.05;margin:8px 0 4px;font-variant-numeric:tabular-nums}
.bigwin .lb{font-size:16px;font-weight:700;color:#fff}.bigwin .mx{display:inline-block;margin-top:10px;font-weight:800;color:var(--yes);background:rgba(0,0,0,.35);padding:5px 12px;border-radius:999px}
.bigwin .ring2{position:absolute;left:50%;top:42%;width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;border:3px solid var(--yes);animation:ring2 1.4s var(--out) infinite;pointer-events:none}
.bigwin .ring2.b{animation-delay:.45s}@keyframes ring2{from{transform:scale(1);opacity:.9}to{transform:scale(14);opacity:0}}
.bigwin .btn{margin-top:22px}
@media (prefers-reduced-motion:reduce){.bigwin .ring2{display:none}.bigwin .bw{animation:none}.gc.scored{animation:none}}
/* ---- makeover phase 3: every remaining screen in the same motion system ---- */
:root{color-scheme:dark;--fs-xs:11px;--fs-s:12.5px;--fs-m:14px;--fs-l:17px;--sp:16px}
@media (prefers-color-scheme:light){:root{color-scheme:light}
 .own{background:rgba(217,119,6,.13);color:#a85a06}.ss.me{background:rgba(217,119,6,.11);border-color:rgba(217,119,6,.38);color:#a85a06}
 .sheet{box-shadow:0 24px 60px rgba(16,24,40,.18)}.modal:not(.push){background:rgba(15,20,32,.32)}
 .segind,.seg button.on{box-shadow:0 1px 3px rgba(16,24,40,.16)}.tg{background:#e2e6ee}.tg::after{box-shadow:0 1px 3px rgba(16,24,40,.28)}
 .btn.warn{background:#f2a531}.slipbar{box-shadow:0 8px 28px rgba(36,104,255,.28)}#ptr,.netbar{box-shadow:0 6px 20px rgba(16,24,40,.12)}
 .flipnote.mid b.v{color:#b26b00}.kpis.hero:before{opacity:.8}}
/* safe areas for the Home Screen app (notch, rounded corners, home indicator) */
@media (max-width:900px){main{padding-left:max(14px,env(safe-area-inset-left));padding-right:max(14px,env(safe-area-inset-right))}
 .top{padding-left:max(16px,env(safe-area-inset-left));padding-right:max(16px,env(safe-area-inset-right))}
 .modal:not(.push) .sheet{border-radius:22px 22px 0 0;max-width:none;padding-bottom:calc(22px + env(safe-area-inset-bottom));max-height:calc(100dvh - env(safe-area-inset-top) - 18px);overflow:auto;overscroll-behavior:contain}}
/* keyboard-aware sheets: the sheet rides up above the on-screen keyboard */
.modal:not(.push){padding-bottom:var(--kb,0px);transition:opacity .22s var(--ease),padding-bottom .25s var(--out)}
@media (max-width:900px){.modal:not(.push){padding-bottom:var(--kb,0px)}}
.modal.on:not(.push){-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
/* the scroll-linked header: it tucks itself in once you scroll */
.ts span{transition:opacity .2s,max-height .3s var(--ease);max-height:16px;overflow:hidden}
.top{transition:transform .27s var(--out),filter .27s var(--out),padding .3s var(--ease),box-shadow .3s,height .3s var(--ease)}
.brand{transition:transform .3s var(--ease);transform-origin:left center}
body.hc .top{box-shadow:0 8px 24px rgba(0,0,0,.16)}
@media (max-width:900px){body.hc .top{padding-top:calc(5px + env(safe-area-inset-top));padding-bottom:5px}body.hc .brand{transform:scale(.84)}body.hc .ts span{opacity:0;max-height:0}}
/* the calm reconnecting banner */
.netbar{position:fixed;left:50%;top:calc(env(safe-area-inset-top) + 68px);z-index:26;transform:translate(-50%,-16px);opacity:0;pointer-events:none;display:flex;align-items:center;gap:8px;
 padding:8px 14px;border-radius:999px;background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);box-shadow:0 8px 24px rgba(0,0,0,.28);font-size:12.5px;font-weight:650;color:var(--ink);
 -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);transition:transform .4s var(--spring),opacity .25s;white-space:nowrap;max-width:calc(100vw - 32px)}
.netbar.on{opacity:1;transform:translate(-50%,0)}.netbar i{width:8px;height:8px;border-radius:50%;background:var(--live);animation:pulse2 1.4s infinite;flex:none}
.netbar small{color:var(--mute);font-weight:500;font-size:12px;overflow:hidden;text-overflow:ellipsis}.netbar.ok{color:var(--yes)}.netbar.ok i{background:var(--yes);animation:none}
/* pull to refresh, on every tab: rubber band, a ring that fills, a spin, a check */
#ptr svg{width:20px;height:20px;overflow:visible}#ptr circle{fill:none;stroke:var(--acc);stroke-width:2.4;stroke-linecap:round;transform:rotate(-90deg);transform-origin:10px 10px;transition:stroke-dashoffset .05s}
#ptr path{fill:none;stroke:var(--yes);stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:20;stroke-dashoffset:20;opacity:0}
#ptr.go svg{animation:sp .7s linear infinite}#ptr.go circle{stroke-dashoffset:12!important}
#ptr.done circle{stroke:var(--yes);stroke-dashoffset:0!important}#ptr.done path{opacity:1;animation:okc .3s var(--ease) forwards}
#ptr{transition:transform .35s var(--spring),opacity .25s}#ptr.drag{transition:none}
main.ptrd{transition:none!important}
/* switches and sliders */
.tg::after{transition:transform .34s var(--spring),width .18s var(--ease)}.tg:active::after{width:25px}.tg:checked:active::after{transform:translateX(13px)}
.tg:checked{box-shadow:0 0 0 3px color-mix(in srgb,var(--yes) 10%,transparent)}
.rng output{transition:color .2s}.rng output.bump,.saved.bump{animation:obump .32s var(--spring)}@keyframes obump{40%{transform:scale(1.14)}}
.rdet{flex-wrap:wrap;row-gap:6px}.rdet .tks{flex-basis:100%;display:flex;justify-content:space-between;padding:0 8px;margin-right:98px}
.rdet .tks i{width:5px;height:5px;border-radius:50%;background:var(--line);transition:background .25s,transform .3s var(--spring)}.rdet .tks i.on{background:var(--acc)}.rdet .tks i.at{transform:scale(1.7)}
.rdet output{min-width:84px}
/* buttons that report back: working, done, didn't work */
.btn.st-ok{background:var(--yesbg)!important;color:var(--yes)!important;border-color:color-mix(in srgb,var(--yes) 40%,transparent)!important;animation:obump .4s var(--spring)}
.btn.st-bad{background:var(--nobg)!important;color:var(--no)!important;border-color:color-mix(in srgb,var(--no) 40%,transparent)!important;animation:sh3 .4s}
@keyframes sh3{25%,75%{transform:translateX(-4px)}50%{transform:translateX(4px)}}
.btn.arm{position:relative;overflow:hidden;background:var(--live)!important;color:#1b1203!important}
.btn.arm:after{content:"";position:absolute;left:0;bottom:0;height:3px;width:100%;background:rgba(255,255,255,.75);transform-origin:left;animation:qdrain 4s linear forwards}
@keyframes qdrain{from{transform:scaleX(1)}to{transform:scaleX(0)}}
/* Build: the quote countdown, picks, the slip bar, folding sections, panel cards */
.qline,.btn.qb{position:relative;overflow:hidden}.qt{position:absolute;left:0;right:0;bottom:0;height:3px;background:currentColor;opacity:.45;transform-origin:left;animation:qdrain 20s linear forwards}
.brow{display:flex;flex-wrap:wrap;gap:8px}.brow .btn{min-width:0;max-width:100%;white-space:normal;line-height:1.25;text-align:center;overflow-wrap:anywhere}
.brow .btn.pri{flex:3 1 auto}.brow .btn.sec{flex:1 1 auto}
.qline.good .qt{color:var(--yes)}.qline.bad .qt{color:var(--no)}.qline.new{animation:rise .35s var(--ease)}
.pickbtn.pop{animation:chipon .34s var(--spring)}
.slipbar.in{animation:slipin .42s var(--spring)}@keyframes slipin{from{transform:translateY(120%);opacity:0}to{transform:none;opacity:1}}
.sech .chev{transition:transform .28s var(--spring)}.sech:not(.open) .chev{transform:rotate(-90deg)}.sech .chev.from-open{transform:none!important}.sech .chev.from-shut{transform:rotate(-90deg)!important}
.unfold{animation:rise .38s var(--ease)}
.pitem{transition:opacity .28s var(--ease),filter .28s,transform .14s var(--ease)}.pitem.off{filter:saturate(.2)}.pitem.tog{animation:pit .34s var(--spring)}@keyframes pit{40%{transform:scale(.96)}}
.psp{display:block;width:64px;height:22px;margin-top:2px}.psp path{vector-effect:non-scaling-stroke}
.ccard.flash{animation:fl 1.2s ease}
/* Results: bars grow in, the What's working tabs crossfade. (<main> is marked `arrived` for 1.6 s after a screen change; it must never be
   called `fresh`: that is the small "Updated Ns ago" stamp's class, and its nowrap/small-grey rules made every new screen draw too wide.) */
main.arrived .bars2 .tr2 i{animation:grow .7s var(--out) both}@keyframes grow{from{transform:scaleX(0)}to{transform:none}}
.bars2 .tr2 i{transform-origin:left}.bars2 .tr2 i[style*="right:"]{transform-origin:right}
.antab{animation:tabin .3s var(--ease)}@keyframes tabin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.ansk{display:grid;gap:9px;padding:4px 0}.ansk i{display:block;background:var(--panel2);border-radius:8px;height:30px}
/* the morning recap's streak */
.streak{display:flex;align-items:center;gap:10px;margin:10px 0 2px;padding:9px 12px;border-radius:12px;background:var(--panel2);font-size:13px;color:var(--sub)}
.streak b{color:var(--ink);font-size:15px}.streak.hot{background:linear-gradient(100deg,color-mix(in srgb,var(--live) 18%,var(--panel2)),var(--panel2) 75%)}
.streak .fl{font-size:18px;display:inline-block;animation:flick 1.8s ease-in-out infinite;transform-origin:50% 90%}@keyframes flick{0%,100%{transform:rotate(-4deg) scale(1)}50%{transform:rotate(4deg) scale(1.08)}}
.streak .dots{margin-left:auto;display:flex;gap:4px}.streak .dots i{width:8px;height:8px;border-radius:50%;background:var(--live);animation:dotin .4s var(--spring) both;animation-delay:calc(var(--i)*70ms + .2s)}
@keyframes dotin{from{transform:scale(0)}to{transform:none}}
/* errors and empty states */
.card.err{border-color:color-mix(in srgb,var(--no) 35%,var(--line))}.card.err:before{background:linear-gradient(145deg,var(--nobg),transparent)}
.setsk{display:grid;gap:14px}.setsk>div{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;display:grid;gap:12px}.setsk i{display:block;background:var(--panel2);border-radius:9px}
@media (prefers-reduced-motion:reduce){.streak .fl,.netbar i{animation:none}#ptr{transition:none}}
</style></head><body>
<header class="top">
 <div class="brand"><div class="mk"><svg width="16" height="16" viewBox="0 0 24 24"><path d="M4 15.5l4.2-4.2 3.3 3.3L20 6" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>Combo Hub</div>
 <nav class="nav" id="nav"></nav>
 <div class="tr">
  <div class="ts"><span>Balance</span><b id="bal">—</b></div>
  <div class="ts wk"><span>Last 7 days</span><b id="wk">—</b></div>
  <div class="status" id="st"><span class="dot"></span>Mac · live</div>
  <button class="cta" onclick="go('build')">＋ Build combos</button>
 </div>
</header>
<main id="main"></main>
<nav class="tabbar" id="tabbar"></nav>
<div class="toast" id="toast"></div>
<div class="modal" id="modal"><div class="sheet" id="sheet"></div></div>
<script>
const TOK="__CWTOK__",LOCAL=__CWLOCAL__;
const $=s=>document.querySelector(s);
const api=(p,b)=>fetch(p,b===undefined?{credentials:'same-origin',headers:{'X-CW':TOK}}:{method:'POST',credentials:'same-origin',headers:{'X-CW':TOK,'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>{if(r.status==403){location.href='/';throw 0;}netUp(r.ok||r.status<500);return r.json();},e=>{netUp(false);throw e;});
/* Offline/reconnecting: a calm pill under the header ("Reconnecting to your Mac · Updated 40s ago") that appears when
   requests fail or the live link drops for more than a moment, and says "Back online" briefly when it returns. */
function netUp(ok){if(ok){S.okAt=Date.now();if(S.netDown){S.netDown=false;netBanner();}}else if(!S.netDown){S.netDown=true;S.netSince=Date.now();netBanner();}}
function netIsDown(){return !!S.netDown||(S.live_ok===false&&!!S.esEver)||navigator.onLine===false;}   // a live link that never opened (no event stream here) isn't an outage: the page polls instead
function netTxt(){const a=S.okAt?Math.round((Date.now()-S.okAt)/1000):null;return a==null?'':a<3?'Updated just now':a<90?'Updated '+a+'s ago':'Updated '+Math.round(a/60)+' min ago';}
function netBanner(){let el=document.getElementById('netbar');if(!el){el=document.createElement('div');el.id='netbar';el.className='netbar';el.setAttribute('role','status');document.body.appendChild(el);}
 const tb=document.querySelector('.top');if(tb)el.style.top=(tb.getBoundingClientRect().bottom+8)+'px';
 if(netIsDown()){if(S.netShown){const sm=el.querySelector('small');if(sm)sm.textContent=netTxt();return;}
  if(!S.netPend)S.netPend=setTimeout(()=>{S.netPend=0;if(!netIsDown())return;clearTimeout(S.netT);el.className='netbar on';
   el.innerHTML=`<i></i><span>${navigator.onLine===false?'You\'re offline':'Reconnecting to your Mac'}</span><small>${netTxt()}</small>`;S.netShown=true;},S.netNow?0:1200);return;}
 if(S.netPend){clearTimeout(S.netPend);S.netPend=0;}
 if(S.netShown){S.netShown=false;el.className='netbar on ok';el.innerHTML='<i></i><span>Back online</span>';clearTimeout(S.netT);S.netT=setTimeout(()=>{el.classList.remove('on');},1600);}}
addEventListener('online',()=>netBanner());addEventListener('offline',()=>{S.netNow=1;netBanner();S.netNow=0;});
/* the header tucks in once you scroll (with a little hysteresis so it never flickers) */
/* The header tucks (body.hc) only while the page is really scrolled. It is re-read from the page itself (never from a remembered flag) on
   scroll, on every tab switch and every second, so a page that got shorter or was reset without a scroll event can't leave it tucked. */
function hcSync(){const y=scrollY,cur=document.body.classList.contains('hc'),short=document.documentElement.scrollHeight<=innerHeight+1,want=short?false:cur?y>8:y>40;if(want!==cur)document.body.classList.toggle('hc',want);}
(()=>{let raf=0;addEventListener('scroll',()=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;hcSync();});},{passive:true});})();
/* The tab bar never moves: it is fixed to the bottom of the page, but on iPhones the page's height can stay out of step with what is on
   screen (after the keyboard closes, after returning to the Home Screen app), which floated the bar above the bottom. Whenever what is
   visible is taller than the page, the bar is moved down by the difference (--tbo), so it is always flush with the bottom of the screen.
   A shorter visible area is the keyboard: the bar stays where it is, behind it, as before. */
function tbSet(vv){const given=!!vv;vv=vv||window.visualViewport;if(!vv)return;const d=Math.round(vv.height+vv.offsetTop-innerHeight),px=d>0&&d<400?d:0;
 /* a drift must show in two readings in a row (a rubber-band at the page's end passes in a moment); a reading handed in (the test) counts at once */
 const ok=px===0||given||S.tbp===px;S.tbp=px;if(!ok)return;
 if(S.tbo!==px){S.tbo=px;document.documentElement.style.setProperty('--tbo',px+'px');}}
(()=>{const vv=window.visualViewport,f=()=>{tbSet();hcSync();};if(vv){vv.addEventListener('resize',f);vv.addEventListener('scroll',f);}
 addEventListener('resize',f);addEventListener('orientationchange',()=>setTimeout(f,300));addEventListener('pageshow',f);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(f,100);});
 addEventListener('focusout',()=>setTimeout(()=>{const a=document.activeElement;if(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))return;scrollTo(scrollX,scrollY);f();},350));
 setInterval(()=>{if(!document.hidden)f();},1000);})();
/* keyboard-aware sheets: when the on-screen keyboard opens, the bottom sheet rises above it and the field stays in view */
function kbSet(px){px=Math.max(0,Math.round(px||0));document.documentElement.style.setProperty('--kb',px+'px');S.kb=px;
 if(px){const f=document.activeElement;if(f&&f.closest&&f.closest('#sheet'))setTimeout(()=>f.scrollIntoView({block:'center',behavior:'smooth'}),60);}}
(()=>{const vv=window.visualViewport;if(!vv)return;const f=()=>kbSet(innerHeight-vv.height-vv.offsetTop>80?innerHeight-vv.height-vv.offsetTop:0);vv.addEventListener('resize',f);vv.addEventListener('scroll',f);})();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':(Math.abs(x)>=1000?'$'+Math.round(x).toLocaleString():Math.abs(x)>=10?'$'+Math.round(x):'$'+(+x).toFixed(2).replace(/\.00$/,''));
const smoney=x=>x==null?'—':(x>=0?'+':'−')+money(Math.abs(x));
const pct=x=>x==null?'—':x>=.1?Math.round(x*100)+'%':x>=.001?(x*100).toFixed(1)+'%':'<0.1%';
const SPN={mix:'Mix',nfl:'NFL',nba:'NBA',nhl:'NHL',ahl:'AHL',ncaaf:'CFB',ncaamb:'CBB',ncaawb:'WCBB',soccer:'Soccer',ufc:'UFC',tennis:'Tennis',euroleague:'Euro'};
const ICON={nfl:'🏈',nba:'🏀',nhl:'🏒',ahl:'🏒',ncaaf:'🎓',ncaamb:'🏀',ncaawb:'🏀',soccer:'⚽',ufc:'🥊',tennis:'🎾',euroleague:'🏀',other:'🎯'};
const SVG={live:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7" opacity=".45"/></svg>',
 build:'<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
 results:'<svg viewBox="0 0 24 24"><path d="M5 19v-7M12 19V6M19 19v-10" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
 games:'<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="3" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M12 5v14M3.5 12h17" stroke="currentColor" stroke-width="1.5" opacity=".7"/></svg>',
 settings:'<svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="7" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="17" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
 more:'<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg>'};
const S={view:(localStorage.getItem('cw_view')||'live'),live:null,build:null,res:null,open:{},filter:'all',lg:localStorage.getItem('cw_lg')||'nba',slip:[],busy:{}};
/* A toast always goes away. It has a deadline (not just a timer), and the page also checks that deadline on its own
   every second and whenever you touch, scroll or come back to it, because phones pause timers in the background.
   Tap anywhere to dismiss it early. After the fade it is taken out of the layout so it can never linger. */
function toastHide(){const t=$('#toast');if(!t)return;t._until=0;clearTimeout(t._h);t.classList.remove('on');clearTimeout(t._x);t._x=setTimeout(()=>{if(!t.classList.contains('on'))t.hidden=true;},450);}
function toastCheck(){const t=$('#toast');if(t&&t.classList.contains('on')&&Date.now()>=(t._until||0))toastHide();}
function toast(m,ms,tone){if(tone==='good')hap('success');else if(tone==='bad')hap('error');const t=$('#toast');t.hidden=false;t.textContent=(tone==='good'?'✅ ':tone==='bad'?'⚠️ ':'')+m;t.classList.remove('good','bad');if(tone)t.classList.add(tone);
 clearTimeout(t._x);void t.offsetWidth;t.classList.add('on');t._at=Date.now();t._until=Date.now()+(ms||3200);clearTimeout(t._h);t._h=setTimeout(toastHide,ms||3200);}
setInterval(toastCheck,1000);
['touchend','scroll','visibilitychange','focus','pageshow'].forEach(ev=>addEventListener(ev,toastCheck,{passive:true,capture:true}));
addEventListener('pointerdown',()=>{const t=$('#toast');if(t&&t.classList.contains('on')&&Date.now()-(t._at||0)>700)toastHide();},{capture:true,passive:true});
/* Sheets. modal() is the bottom sheet (confirmations, small things). pushOpen()/pushFill() is the Kalshi-style push for
   detail pages (a game, a combo): the page slides in from the right in ~270 ms (ease-out) while the page behind slides a
   third of the way left and dims; flat skeleton blocks show until the content swaps in. Back, a tap on the dimmed
   edge, or a swipe right closes it. Switching between the two modes never animates (no flash of a half-moved sheet). */
function sheetMode(push){const m=$('#modal'),sh=$('#sheet');clearTimeout(S.pushT);if(m.classList.contains('push')===push)return;
 sh.style.transition=m.style.transition='none';m.classList.toggle('push',push);sh.classList.toggle('wide',push);sh.style.transform='';void m.offsetWidth;sh.style.transition=m.style.transition='';void m.offsetWidth;}
function modal(h){sheetMode(false);document.body.classList.remove('pushed');S.gameOpen=null;S.gameSig=null;S.comboOpen=null;const sh=$('#sheet');sh.classList.remove('wide');sh.innerHTML='<i class="grab"></i>'+h;sh.scrollTop=0;
 if(!sh.querySelector('.okcard')&&!matchMedia('(prefers-reduced-motion: reduce)').matches){sh.classList.add('stag');[...sh.children].forEach((c,i)=>c.style.setProperty('--i',i));clearTimeout(S.shT);S.shT=setTimeout(()=>sh.classList.remove('stag'),900);}
 $('#modal').classList.add('on');hap('light');}
function closeModal(){const m=$('#modal');if(m.classList.contains('on'))hap('light');m.classList.remove('on');document.body.classList.remove('pushed');S.gameOpen=null;S.gameSig=null;S.comboOpen=null;
 clearTimeout(S.pushT);if(m.classList.contains('push'))S.pushT=setTimeout(()=>{if(!m.classList.contains('on'))sheetMode(false);},340);else $('#sheet').classList.remove('wide');}
const BACK='<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function pushSkel(){return `<div class="psk"><i style="height:14px;width:28%"></i><i style="height:26px;width:66%"></i><i style="height:84px"></i>
 <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><i style="height:62px"></i><i style="height:62px"></i><i style="height:62px"></i><i style="height:62px"></i></div><i style="height:170px"></i><i style="height:16px;width:40%"></i><i style="height:44px"></i><i style="height:44px"></i></div>`;}
function pushOpen(title){const m=$('#modal'),sh=$('#sheet');const was=m.classList.contains('on')&&m.classList.contains('push');
 if(!was){m.classList.remove('on');sheetMode(true);}
 pushFill(pushSkel(),title,true);sh.scrollTop=0;S.pushAt=performance.now();
 if(!was){m.classList.add('on');document.body.classList.add('pushed');hap('light');}}
/* the content waits for the slide to finish, so the swap never janks the motion */
function pushWait(){const left=(S.pushAt||0)+290-performance.now();return left>0?new Promise(z=>setTimeout(z,left)):Promise.resolve();}
function pushFill(h,title,sk){const sh=$('#sheet');const first=sh.dataset.sk==='1'&&!sk;
 sh.innerHTML=`<div class="pbar"><button class="back" onclick="closeModal()" aria-label="Back">${BACK}Back</button><span class="pt">${esc(title||'')}</span></div><div class="pbody ${first?'fadein':''}">${h}</div>`;
 sh.dataset.sk=sk?'1':'';rollNums(sh);wireScrubs(sh);
 if(first&&!matchMedia('(prefers-reduced-motion: reduce)').matches){const b=sh.querySelector('.pbody');b.classList.add('stag');[...b.children].forEach((c,i)=>c.style.setProperty('--i',i));setTimeout(()=>b.classList.remove('stag'),1200);}}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal();});
(()=>{const sh=$('#sheet');let x0=null,y0=null,dx=0,dy=0,ax=null,past=false;
 const cross=v=>{if(v!==past){past=v;hap(v?'light':'selection');}};
 /* a swipe that starts on the game tab row (or any sideways-scrolling strip) belongs to that strip, never to swipe-back */
 const hscroll=el=>{for(;el&&el!==sh&&el.nodeType===1;el=el.parentElement){if(el.classList.contains('gtabs'))return true;const o=getComputedStyle(el).overflowX;if((o==='auto'||o==='scroll')&&el.scrollWidth>el.clientWidth)return true;}return false;};
 sh.addEventListener('touchstart',e=>{const t=e.touches[0];dx=dy=0;ax=null;past=false;
  if($('#modal').classList.contains('push')){if(hscroll(e.target)){x0=y0=null;return;}x0=t.clientX;y0=t.clientY;return;}x0=null;
  if(sh.scrollTop>0||innerWidth>760){y0=null;return;}y0=t.clientY;},{passive:true});
 sh.addEventListener('touchmove',e=>{const t=e.touches[0];
  if(x0!=null){const mx=t.clientX-x0,my=t.clientY-y0;if(ax==null&&(Math.abs(mx)>8||Math.abs(my)>8))ax=mx>0&&Math.abs(mx)>Math.abs(my)*1.2?'x':'y';
   if(ax!=='x')return;dx=Math.max(0,mx);sh.classList.add('drag');sh.style.transform=`translateX(${dx}px)`;cross(dx>100);return;}
  if(y0==null)return;dy=Math.max(0,t.clientY-y0);if(dy>4){sh.classList.add('drag');sh.style.transform=`translateY(${dy}px)`;cross(dy>110);}},{passive:true});
 sh.addEventListener('touchend',()=>{sh.classList.remove('drag');sh.style.transform='';
  if(x0!=null){x0=null;if(ax==='x'&&dx>100)closeModal();return;}
  if(y0==null)return;if(dy>110)closeModal();y0=null;dy=0;});})();
/* Press feedback and a haptic tick on every interactive thing, in one place, so nothing can be missed: anything
   matching TAP shrinks a touch while pressed (rows and settings lines highlight instead) and ticks when tapped.
   Tabs, chips, segments and switches tick as "selection"; the rest "light". A control's own hap() right after is
   folded into the same tick; success/warning/error always play their own pattern. */
const TAP='button,a[href],[onclick],.chip,.trow,label,select,summary,input[type=checkbox],input[type=range]';
function tapEl(t){const el=t&&t.closest&&t.closest(TAP);return el&&!el.closest('.hapx')&&!el.disabled?el:null;}
(()=>{let held=null;const up=()=>{const el=held;held=null;if(el)setTimeout(()=>el.classList.remove('prs'),70);};
 addEventListener('pointerdown',e=>{if(e.button)return;const el=tapEl(e.target);if(!el)return;up();held=el;el.classList.add('prs');},{capture:true,passive:true});
 ['pointerup','pointercancel','dragstart'].forEach(k=>addEventListener(k,up,{capture:true,passive:true}));addEventListener('scroll',up,{capture:true,passive:true});
 addEventListener('click',e=>{const el=tapEl(e.target);if(!el||el.matches('input[type=range]')||el.closest('[data-hapt]'))return;
  hap(el.matches('.tabbar button,.nav button,.seg button,.gtabs button,.ant button,.rng2 button,.chip,select,input[type=checkbox],label')?'selection':'light');},true);
 addEventListener('input',e=>{if(e.target&&e.target.type==='range')hap('selection');},true);})();
/* swipe left or right anywhere on a page to move between tabs */
(()=>{let x0=null,y0=0,t0=0,ok=true;
 addEventListener('touchstart',e=>{const t=e.target;ok=!(t.closest&&t.closest('.chips,.seg,.ant,.sheet,input,.board,.chartbox,.spark,.sparkw,.scrub,.antbl,svg'));x0=e.touches[0].clientX;y0=e.touches[0].clientY;t0=Date.now();},{passive:true});
 addEventListener('touchend',e=>{if(x0==null||!ok||$('#modal').classList.contains('on'))return;const t=e.changedTouches[0],dx=t.clientX-x0,dy=t.clientY-y0;x0=null;
  if(Math.abs(dx)<80||Math.abs(dy)>Math.abs(dx)*.6||Date.now()-t0>600||innerWidth>900)return;const i=TABS.indexOf(S.view),j=i+(dx<0?1:-1);if(j<0||j>=TABS.length)return;hap('light');go(TABS[j],dx<0?1:-1);},{passive:true});})();
/* Pull down at the top of any tab to refresh it: the page follows the finger with a rubber band, a ring fills as you
   pull, it ticks once at the point where letting go refreshes, spins while loading and ends on a small check. */
(()=>{let y0=null,dy=0,el=null,busy=false;const C=2*Math.PI*8,TH=64;
 const ptr=()=>el||(el=Object.assign(document.createElement('div'),{id:'ptr',innerHTML:'<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" stroke-dasharray="'+C.toFixed(1)+'" stroke-dashoffset="'+C.toFixed(1)+'"/><path d="M6 10.4l2.6 2.6L14 7.6"/></svg>'}),document.body.appendChild(el),el);
 const skip=t=>!!(t&&t.closest&&t.closest('.sheet,.sparkw,.scrub,input,select,textarea,.chips,.seg,.ant,.sidx'));
 const main=()=>$('#main'),reduce=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
 addEventListener('touchstart',e=>{y0=(!busy&&scrollY<=0&&!$('#modal').classList.contains('on')&&!skip(e.target))?e.touches[0].clientY:null;dy=0;},{passive:true});
 addEventListener('touchmove',e=>{if(y0==null)return;const raw=e.touches[0].clientY-y0;if(raw<=0||scrollY>0){if(dy){dy=0;const p=ptr();p.style.opacity=0;const m=main();if(m){m.style.transform='';}}return;}
  dy=110*(1-Math.exp(-raw/150));const p=ptr(),k=Math.min(1,dy/TH);p.classList.add('drag');p.style.opacity=Math.min(1,k*1.4);p.style.transform=`translateY(${-40+k*50}px)`;
  p.querySelector('circle').style.strokeDashoffset=(C*(1-k)).toFixed(1);const m=main();if(m&&!reduce()){m.classList.add('ptrd');m.style.transform=`translateY(${(dy*.45).toFixed(1)}px)`;}
  if(dy>=TH&&!p._hit){p._hit=1;hap('selection');}else if(dy<TH&&p._hit){p._hit=0;}},{passive:true});
 addEventListener('touchend',async()=>{if(y0==null)return;const p=ptr(),m=main();y0=null;p.classList.remove('drag');if(m){m.classList.remove('ptrd');m.style.transform='';}
  if(dy>=TH){busy=true;p.classList.add('go');p.style.transform='translateY(10px)';const v=S.view;await load(v,true).catch(()=>{});
   p.classList.remove('go');p.classList.add('done');hap('success');await new Promise(z=>setTimeout(z,520));busy=false;}
  p.classList.remove('go','done');p._hit=0;p.style.opacity=0;p.style.transform='translateY(-40px)';dy=0;});})();
function chrome(){const tabs=[['live','Live'],['games','Games'],['build','Build'],['results','Results'],['settings','Settings']];
 $('#nav').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${l}</button>`).join('');
 $('#tabbar').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${SVG[k]}${l}</button>`).join('');
}
const TABS=['live','games','build','results','settings'];
function go(v,dir){hap('selection');const same=S.view===v;if(!same)S.entered=true;const from=TABS.indexOf(S.view);S.view=v;try{localStorage.setItem('cw_view',v)}catch(e){};chrome();
 const paint=()=>{render();window.scrollTo(0,0);hcSync();tbSet();};
 if(!same&&!dir&&document.startViewTransition&&!matchMedia('(prefers-reduced-motion: reduce)').matches){document.startViewTransition(paint);}
 else{paint();const m=$('#main');if(m&&!same){const c=dir?(dir>0?'sw-l':'sw-r'):'enter';m.classList.remove('enter','sw-l','sw-r');void m.offsetWidth;m.classList.add(c);}}
 load(v);}
function render(){({live:renderLive,games:renderGames,build:renderBuild,results:renderResults,settings:renderSettings}[S.view]||renderLive)();afterPaint();}
S.nums=S.nums||{};S.sigs=S.sigs||{};S.entered=true;   // the first real paint of the page staggers in too
function fmtNum(v,f){return f==='pct'?pct(v):f==='int'?String(Math.round(v)):f==='cent'?Math.round(v*100)+'¢':f==='spct'?(v>=0?'+':'−')+Math.abs(Math.round(v*100))+'%':money(v);}
function stagger(){if(!S.entered||document.querySelector('#main .skel,#main .hsk'))return;S.entered=false;if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const mn=$('#main');if(mn){mn.classList.add('arrived');clearTimeout(S.arrT);S.arrT=setTimeout(()=>mn.classList.remove('arrived'),1600);}
 document.querySelectorAll('.cgrid,.games,.tbl,.board,.panel-items,.antbl,.hist,.set>div:last-child,.doit,.hs,.plist').forEach(box=>{box.classList.add('stag');[...box.children].slice(0,24).forEach((c,i)=>c.style.setProperty('--i',i));setTimeout(()=>box.classList.remove('stag'),1600);});
 const kp=document.querySelector('.kpis');if(kp){kp.classList.add('stag');[...kp.children].forEach((c,i)=>c.style.setProperty('--i',i));setTimeout(()=>kp.classList.remove('stag'),900);}
 document.querySelectorAll('.chart rect').forEach((r,i)=>r.style.setProperty('--i',i));}
function segInd(){document.querySelectorAll('.seg,.ant').forEach((sg,k)=>{const on=sg.querySelector('button.on');let ind=sg.querySelector(':scope>.segind');
  if(!on){if(ind)ind.remove();return;}if(!ind){ind=document.createElement('i');ind.className='segind';sg.prepend(ind);sg.classList.add('hasind');}
  const key=sg.dataset.k||(sg.className+':'+k);const prev=S.segs&&S.segs[key];S.segs=S.segs||{};
  const to={left:on.offsetLeft,top:on.offsetTop,width:on.offsetWidth,height:on.offsetHeight};
  if(prev&&(prev.left!==to.left||prev.top!==to.top)){ind.style.transition='none';Object.assign(ind.style,{left:prev.left+'px',top:prev.top+'px',width:prev.width+'px',height:prev.height+'px'});void ind.offsetWidth;ind.style.transition='';}
  Object.assign(ind.style,{left:to.left+'px',top:to.top+'px',width:to.width+'px',height:to.height+'px'});S.segs[key]=to;});
 const tb=document.querySelector('.tabbar');const on=tb&&tb.querySelector('button.on');if(on){let ti=tb.querySelector('.tabind');if(!ti){ti=document.createElement('i');ti.className='tabind';tb.appendChild(ti);}
  ti.style.left=(on.offsetLeft+on.offsetWidth/2-14)+'px';ti.style.width='28px';}}
function afterPaint(){stagger();segInd();rollNums(document);wireChart();wireScrubs(document);
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 document.querySelectorAll('[data-sig]').forEach(el=>{const k=el.dataset.key,sg=el.dataset.sig;const old=S.sigs[k];S.sigs[k]=sg;if(old!=null&&old!==sg&&!reduce){el.classList.add('rowpop');setTimeout(()=>el.classList.remove('rowpop'),1300);}});}
/* Numbers roll to their new value frame by frame (~0.65 s, ease-out) with a green/red flash; chance bars slide. */
function rollNums(root){const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;S.bars=S.bars||{};
 root.querySelectorAll('[data-bar]').forEach(el=>{const k=el.dataset.bar,w=el.style.width,old=S.bars[k];S.bars[k]=w;
  if(old==null||old===w||reduce)return;el.style.transition='none';el.style.width=old;void el.offsetWidth;el.style.transition='';el.style.width=w;});
 root.querySelectorAll('[data-num]').forEach(el=>{const k=el.dataset.num,v=parseFloat(el.dataset.v),f=el.dataset.f,pre=el.dataset.pre||'';if(isNaN(v))return;const old=S.nums[k];S.nums[k]=v;
  if(old==null||Math.abs(old-v)<(f==='pct'||f==='spct'?.0005:.005)||reduce)return;el.classList.remove('fl-up','fl-down');void el.offsetWidth;el.classList.add(v>old?'fl-up':'fl-down');
  const t0=performance.now(),dur=650;const step=t=>{const k2=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-k2,3);el.textContent=pre+fmtNum(old+(v-old)*e,f);if(k2<1)requestAnimationFrame(step);};requestAnimationFrame(step);});}
function cget(k){try{const x=JSON.parse(localStorage.getItem('cw_c_'+k)||'null');return x&&Date.now()-x.t<6*3600e3?x.d:null}catch(e){return null}}
function cput(k,d){try{if(d)localStorage.setItem('cw_c_'+k,JSON.stringify({t:Date.now(),d}))}catch(e){}}
function warm(v){/* show the last copy straight away while the fresh one loads */
 if(v==='live'&&!S.live){S.live=cget('live');if(S.live)head(S.live);}
 if(v==='build'&&(!S.build||S.build.lg!==S.lg)){S.build=cget('build_'+S.lg);S.panel=cget('panel_'+(S.pview||'all'))||S.panel;}
 if(v==='results'&&!S.res)S.res=cget('results');if(v==='results'&&!S.an)S.an=cget('analytics');
 if(v==='games'&&!S.games)S.games=cget('games');
 if(S.view===v&&(v!=='build'||S.build))render();}
// ---- freshness: how old the numbers on screen are, counted on the phone between loads. Two separate things:
//   • the snapshot ("prices"): when the dollar numbers on screen were last worked out (the snapshot build) — this is
//     the age the big number actually has, so the stamp leads with it and goes red when it is stale;
//   • the scores: how old the live games' scores are (only while a game is on). Shown alongside so a stale snapshot
//     and stale scores are never conflated into one misleading "Updated N ago".
S.fr={};
function frSet(k,f){if(f&&f.built)S.fr[k]={f:f,recv:Date.now()};}
function frEl(k){const o=S.fr[k];return o?Math.max(0,(Date.now()-o.recv)/1000):0;}        // seconds since this page got it
function frBuilt(k){const o=S.fr[k];if(!o)return null;return Math.max(0,o.f.now-o.f.built+frEl(k));}   // snapshot/prices age
function frScores(k){const o=S.fr[k];if(!o||o.f.scores==null)return null;return Math.max(0,o.f.scores+frEl(k));} // scores age
function agoTxt(a){return a<3?'just now':a<90?Math.round(a)+'s ago':Math.round(a/60)+' min ago';}
function frLive(k){const o=S.fr[k];return !!(o&&o.f.live);}                                                   // is a game under way (server says)
function frTxt(k){const b=frBuilt(k);if(b==null)return '';const s=frScores(k);
 return(!frLive(k)||s==null)?'Updated '+agoTxt(b):'Prices '+agoTxt(b)+' · scores '+agoTxt(s);}
function frTick(){document.querySelectorAll('[data-fr]').forEach(e=>{const k=e.dataset.fr,t=frTxt(k);if(e.textContent!==t)e.textContent=t;e.classList.toggle('old',(frBuilt(k)||0)>60);});}
setInterval(()=>{frTick();clkTick();if(S.netShown||S.netDown||S.live_ok===false)netBanner();},1000);
setInterval(()=>{if(!document.hidden&&S.gameOpen&&$('#modal').classList.contains('on')&&Date.now()-(S.gameAt||0)>5500)drawGame();},2000);
async function load(v,fresh){try{warm(v);
 if(v==='live'){const prev=S.liveNet?S.live:null;S.live=await api('/app/api/live'+(fresh?'?fresh=1':''));head(S.live);cput('live',S.live);frSet('L',S.live.fresh);try{liveMoments(prev,S.live)}catch(e){}S.liveNet=true;}
 if(v==='build'){const lg=S.lg,pv=S.pview||'all';const [b,p]=await Promise.all([api('/app/api/build?lg='+lg+(fresh?'&fresh=1':'')),api('/app/api/panel?v='+pv).catch(()=>null)]);
  if(lg!==S.lg||pv!==(S.pview||'all'))return;S.build=b;S.panel=p;cput('build_'+lg,b);cput('panel_'+pv,p);}
 if(v==='results'){S.res=await api('/app/api/results');head(S.res);cput('results',S.res);
  api('/app/api/analytics').then(a=>{S.an=a;cput('analytics',a);if(S.view==='results')renderResults();}).catch(()=>{});}
 if(v==='games'){S.games=await api('/app/api/games');cput('games',S.games);frSet('N',S.games.fresh);}
 if(v==='settings'){const [st,mac,pk]=await Promise.all([api('/app/api/settings?lg='+(S.slg||S.lg)),LOCAL?api('/app/mac',{a:'status'}).catch(()=>null):api('/app/mac-info',{}).catch(()=>null),api('/app/push',{a:'key'}).catch(()=>null)]);S.set=st;S.mac=mac;S.pk=pk;await fidLoad();try{const pp=await api('/app/api/panel?v=all');S.panelCuts=pp.cutoffs;S.skim={reserved:pp.reserved}}catch(e){}
  try{const reg=navigator.serviceWorker&&await navigator.serviceWorker.getRegistration();const sub=reg&&reg.pushManager&&await reg.pushManager.getSubscription();S.pushOn=!!sub;}catch(e){S.pushOn=false;}}
 if(S.lerr)delete S.lerr[v];if(S.view===v)render();}catch(e){if(e)console.log(e);
  const have={live:S.live,games:S.games,build:S.build,results:S.res,settings:S.set}[v];   // nothing to show yet: say so, with a retry, instead of a skeleton forever
  if(e!==0&&!have){S.lerr=S.lerr||{};S.lerr[v]=navigator.onLine===false?'You\'re offline.':'Couldn\'t reach your Mac. It may be asleep or restarting.';if(S.view===v)render();}}}
/* the error card for a screen that couldn't load: calm, says why, and a Try again that spins while it retries */
function errCard(v){return `<div class="card empty err" data-ic="⚠️"><b>Couldn't load this screen</b>${esc((S.lerr||{})[v]||'')}<br><button class="btn acc" onclick="retry('${v}',this)">Try again</button></div>`;}
async function retry(v,b){btnBusy(b,'Trying…');await load(v,true);
 if((S.lerr||{})[v]&&b&&b.isConnected){btnState(b,false,'Still no answer');setTimeout(()=>{if(b.isConnected){b.className='btn acc';b.textContent='Try again';}},2200);}}
/* A button that reports back: spins while working, then a check and "Done" (green) or a cross (red, a small shake),
   then its old self. */
function btnState(b,ok,label,ms){if(!b||!b.isConnected)return;hap(ok?'success':'error');b.disabled=false;b.classList.remove('st-ok','st-bad');void b.offsetWidth;b.classList.add(ok?'st-ok':'st-bad');
 b.innerHTML=(ok?'✓ ':'✕ ')+esc(label||(ok?'Done':'Didn\'t work'));b.dataset.st=ok?'ok':'bad';
 if(ms!==0){const old=b._old;clearTimeout(b._st);b._st=setTimeout(()=>{if(b.isConnected){b.classList.remove('st-ok','st-bad');delete b.dataset.st;if(old!=null)b.innerHTML=old;b._old=null;}},ms||2200);}}
function btnBusy(b,label){if(!b)return;if(b._old==null)b._old=b.innerHTML;b.disabled=true;b.innerHTML='<span class="spin"></span> '+esc(label||b.textContent.trim());}
function head(d){if(!d)return;if(d.balance!=null)$('#bal').textContent=money(d.balance);
 if(d.week_pl!=null){const w=$('#wk');w.textContent=smoney(d.week_pl);w.className=d.week_pl>=0?'up':'down';}}
function skel(n){return Array.from({length:n},()=>'<div class="skel" style="height:66px;margin-bottom:10px"></div>').join('');}
// ---------------- LIVE
function legCls(l){if(l.res==='yes')return 'won';if(l.res==='no')return 'lost';if(l.state!=='live'||l.phase==='probably_over'||l.phase==='over'||l.phase==='waiting')return '';
 const lead=l.sc?(l.sc.me-l.sc.opp):0;const ch=l.live!=null?l.live:l.chance;
 if(lead>0||(!lead&&ch!=null&&ch>=.6))return 'up';if(lead<0||(!lead&&ch!=null&&ch<=.4))return 'down';return 'live';}
function legTag(l){const c=legCls(l);const sc=l.state==='live'&&l.sc?` ${l.sc.me}–${l.sc.opp}`:'';
 const pre=c==='won'?'✓ ':c==='lost'?'✕ ':['up','down','live'].includes(c)?'<i class="pd"></i>':'';
 const tip=l.phase==='probably_over'?'Probably finished, waiting on Kalshi':l.phase==='waiting'?'Not started yet':c==='up'?'Winning right now':c==='down'?'Losing right now':c==='live'?'Tied or close':c==='won'?'Won':c==='lost'?'Lost':'Not started';
 return `<span class="leg ${c}" title="${tip}">${pre}${esc(short(l.name))}${sc}</span>`;}
function legTags(ls){const o=[...ls].sort((a,b)=>(b.state==='live')-(a.state==='live')||(b.res==='yes')-(a.res==='yes'));
 const max=7;return o.slice(0,max).map(legTag).join('')+(o.length>max?`<span class="leg">+${o.length-max}</span>`:'');}
const PLACE_END=new Set(['City','Orleans','York','Bay','Angeles','Vegas','Francisco','Diego','Jersey','England','Louis','Antonio','Lake','Jose','Carolina','Florida','Dakota','Mexico','Virginia','Kentucky','Michigan','Illinois','Texas','Tech','State','Coast']);
function short(n){n=String(n||'');const p=n.split(' ');if(p.length<2||n.length<=14)return n;const last=p[p.length-1];
 if(PLACE_END.has(last))return p.slice(0,-1).map(w=>w[0]+'.').join('')+' '+last;   // "San Francisco" -> "S. Francisco", never just "City"
 return last;}
function plOf(c){return c.group==='won'?(c.pays||0)-c.cost:c.group==='cashed'?(c.back||0)-c.cost:c.group==='lost'?-c.cost:0;}
function plPill(c){const v=plOf(c);return `<div class="verdict pl ${v>0.004?'won':v<-0.004?'lost':'cashed'}"><b>${v>=0?'+':'−'}${money(Math.abs(v))}</b><small>${c.group==='won'?'Won':c.group==='cashed'?'Cashed out':'Lost'}</small></div>`;}
try{S.sf=JSON.parse(localStorage.getItem('cw_sf')||'null')||{o:'all',sp:'all',sort:'new'}}catch(e){S.sf={o:'all',sp:'all',sort:'new'}}
function setSf(k,v){hap('selection');S.sf[k]=v;try{localStorage.setItem('cw_sf',JSON.stringify(S.sf))}catch(e){}renderLive();}
function settledBar(cs){const done=cs.filter(c=>c.group!=='pending');const f=S.sf;const sps=[...new Set(done.flatMap(c=>c.sports))].filter(s=>SPN[s]);
 const net=done.filter(c=>settledOk(c)).reduce((a,c)=>a+plOf(c),0),n=done.filter(c=>settledOk(c)).length;
 const ch=(k,v,l)=>`<button class="chip ${f[k]===v?'on':''}" onclick="setSf('${k}','${v}')">${l}</button>`;
 return `<div class="sbar"><div class="chips">${ch('o','all','All')}${ch('o','profit','Profit')}${ch('o','loss','Loss')}${ch('o','won','Won')}${ch('o','cashed','Cashed early')}${ch('o','lost','Lost')}</div>
  ${sps.length>1?`<div class="chips">${ch('sp','all','All sports')}${sps.map(s=>ch('sp',s,(ICON[s]||'')+' '+SPN[s])).join('')}</div>`:''}
  <div class="chips">${ch('sort','new','Newest')}${ch('sort','best','Biggest profit')}${ch('sort','worst','Biggest loss')}${ch('sort','pay','Biggest payout')}</div>
  <div class="snet">${n} settled · net <b class="${net>=0?'up':'down'}">${net>=0?'+':'−'}${money(Math.abs(net))}</b></div></div>`;}
function settledOk(c){const f=S.sf,v=plOf(c);return (f.o==='all'||(f.o==='profit'&&v>0)||(f.o==='loss'&&v<0)||f.o===c.group)&&(f.sp==='all'||c.sports.includes(f.sp));}
function verdictOf(c){if(c.group==='won')return['won','WON'];if(c.group==='lost')return['lost','OUT'];if(c.group==='cashed')return['cashed','CASHED'];
 if(c.verdict==='sell')return['sell','SELL'];if(c.verdict==='half')return['sell','SELL ½'];return['hold','HOLD'];}
function nextLine(c){if(c.group!=='pending')return c.preview||'';const lv=c.legs.find(l=>l.state==='live'&&l.score);if(lv)return '● '+lv.score;
 const nt=c.legs.find(l=>!l.res&&l.state==='live'&&l.note);
 if(nt)return short(nt.name)+(nt.phase==='probably_over'?' · probably finished':' · '+nt.short.toLowerCase());
 const up=c.legs.find(l=>!l.res&&l.starts&&l.state!=='live');return up?('Next: '+short(up.name)+' · '+up.starts):(c.when||'');}
function legendFor(pend){const on=new Set();pend.forEach(c=>c.legs.forEach(l=>{const k=legCls(l);if(k)on.add(k);}));if(!on.size)return '';
 const it=[['up','<i class="pd"></i>Winning now'],['down','<i class="pd"></i>Losing now'],['live','<i class="pd"></i>Tied'],['won','✓ Won'],['lost','✕ Lost']].filter(x=>on.has(x[0]));
 return `<div class="legend">${it.map(x=>`<span class="leg ${x[0]}">${x[1]}</span>`).join('')}</div>`;}
/* while a finger is on the chart the page holds still; the refresh that came in meanwhile paints on release */
function renderLive(){if(S.scrub){S.liveDirty=true;return;}_renderLive();afterPaint();}
function liveSkel(){return `<div class="kpis hero"><div class="hsk"><i style="height:12px;width:46%"></i><i style="height:42px;width:58%"></i><i style="height:22px;width:40%"></i><i style="height:76px"></i></div>
 <div class="hsk"><i style="height:50px"></i><i style="height:50px"></i></div></div><div class="hsk" style="padding:4px 0 10px"><i style="height:14px;width:34%"></i></div>`+skel(4);}
function _renderLive(){const d=S.live;const m=$('#main');
 if(!d){m.innerHTML=(S.lerr||{}).live?errCard('live'):liveSkel();return;}
 if(d.error){m.innerHTML=`<div class="card empty err" data-ic="⚠️"><b>Couldn't load your combos</b>${esc(d.error)}<br><button class="btn acc" onclick="retry('live',this)">Try again</button></div>`;return;}
 const cs=(d.combos||[]);const pend=cs.filter(c=>c.group==='pending');const sOpen=(d.singles||[]).filter(x=>x.state==='live'||x.state==='pre');
 const sports=[...new Set(cs.flatMap(c=>c.sports))];
 const shown=cs.filter(c=>S.filter==='all'?c.group==='pending':S.filter==='live'?c.group==='pending'&&c.live:S.filter==='done'?c.group!=='pending'&&settledOk(c):c.group==='pending'&&c.sports.includes(S.filter))
   .sort(S.filter==='done'?((a,b)=>S.sf.sort==='best'?plOf(b)-plOf(a):S.sf.sort==='worst'?plOf(a)-plOf(b):S.sf.sort==='pay'?(b.full||b.pays)-(a.full||a.pays):(String(b.week||'')).localeCompare(String(a.week||''))||b.sort-a.sort)
     :((a,b)=>(b.verdict==='sell')-(a.verdict==='sell')||(b.live-a.live)||a.sort-b.sort));
 const todo=cs.filter(c=>(d.todo||[]).includes(c.t));
 const sumW=(d.cash_now||0)+sOpen.reduce((a,x)=>a+(x.worth||0),0),sumS=d.staked+sOpen.reduce((a,x)=>a+(x.cost||0),0),dl=sumW-sumS;
 m.innerHTML=`<div class="grid"><div>
 ${heroLive(d,pend,sOpen,sumW,sumS,dl)}

 ${recapCard()}${momentBar(cs)}${doNow(d,cs)}
 <h2>Your combos <span class="n">${S.filter==='done'?shown.length:pend.length}</span><span class="r chips">${[['all','Riding'],['live','Live now'],...sports.filter(s=>SPN[s]).map(s=>[s,(ICON[s]||'')+' '+SPN[s]]),['done','Settled']].map(([k,l])=>`<button class="chip ${S.filter===k?'on':''}" onclick="hap('selection');S.filter='${k}';renderLive()">${l}</button>`).join('')}</span></h2>
 ${S.filter==='done'?settledBar(cs):''}
 ${S.filter!=='done'?legendFor(pend):''}
 <div class="tbl"><div class="thead"><div>Combo</div><div>Picks</div><div class="num">Paid</div><div class="num">Pays</div><div class="num">To hit</div><div class="num">Kalshi offer</div><div></div></div>
 ${shown.map(rowLive).join('')||(S.filter==='all'&&!pend.length?'<div class="empty" data-ic="🌤️"><b>Nothing riding right now</b>Bets you place, here or on Kalshi, show up with live scores and cash-out offers.<br><button class="btn acc" onclick="go(\'build\')">See today\'s bets</button></div>':'<div class="empty" data-ic="🗒️"><b>Nothing here</b>Try another filter. Combos show up here with live scores and cash-out offers.</div>')}</div>
 ${singlesLive(d)}
 </div><aside class="side">${sideLive(d)}</aside></div>`;}
function doNow(d,cs){const pend=cs.filter(c=>c.group==='pending');
 const items=[];
 for(const c of pend){
  if((d.todo||[]).includes(c.t))items.push({c,kind:'sell',w:(c.offer||0)});
  else if(c.offer_real&&c.overpay&&c.overpay>=1.03)items.push({c,kind:'overpay',w:(c.offer||0)*1.1});
  else if(c.verdict!=='hold'&&!c.offer_real)items.push({c,kind:'ask',w:(c.offer||0)*.8});
  else if(c.hedge&&!c.hedge.done&&c.hedge.locked>c.cost*1.5&&c.legs.filter(l=>!l.res).length===1)items.push({c,kind:'hedge',w:c.hedge.locked});
 }
 items.sort((a,b)=>b.w-a.w);
 const hid=(()=>{try{return JSON.parse(localStorage.getItem('cw_hide')||'[]')}catch(e){return []}})();
 const ideas=(d.ideas||[]).filter(x=>!hid.includes(x.id));
 if(!items.length&&ideas.length)return ideaBlock(ideas);
 const nS=(d.singles||[]).filter(x=>x.state==='live'||x.state==='pre').length,nAll=pend.length+nS;
 if(!items.length)return nAll?`<div class="calm"><i></i><span><b>Nothing to do right now.</b> ${nAll} bet${nAll>1?'s':''} riding · ${d.auto_sell===false?'the Mac tells you the moment one is worth selling.':'smart sell is watching them.'}</span></div>`:'';
 return `<h2>Do now <span class="n">${items.length}</span></h2><div class="doit">${items.slice(0,4).map(({c,kind})=>{
  const nums=`<div class="dnums"><div>${c.offer_real?'Offer now':'Likely offer'}<b>${c.offer_real?'':'≈ '}${money(offNow(c))}</b></div><div>Holding is worth<b>${money(c.hold_ce!=null?c.hold_ce:c.hold_value)}</b></div>${c.threshold?`<div>Sell after next game at<b>${money(c.threshold)}+</b></div>`:''}<div>You paid<b>${money(c.cost)}</b></div></div>`;
  if(kind==='sell')return `<div class="dcard"><div><h4>${esc(c.label)}: cash out ${c.verdict==='half'?'half ':''}for ${money(c.offer)}</h4><p>${esc(c.why||'')}</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" onclick="openCombo('${c.t}')">Details</button><button class="btn ghost" onclick="act('keep','${c.t}')">Keep</button><button class="btn yes" onclick="sell('${c.t}')">Cash out</button></div></div>`;
  if(kind==='overpay')return `<div class="dcard"><div><h4>${esc(c.label)}: Kalshi is overpaying, ${money(c.offer)}</h4><p>That's ${Math.round((c.overpay-1)*100)}% more than the combo is worth at the market's own chances (${money(c.fair_value)}). Let it ride says hold; the price says sell. Your call.</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" onclick="openCombo('${c.t}')">Details</button><button class="btn yes" onclick="sell('${c.t}')">Cash out</button></div></div>`;
  if(kind==='hedge')return `<div class="dcard warn"><div><h4>${esc(c.label)}: lock in ${money(c.hedge.locked)} with a hedge</h4><p>One game left. Buying ${esc(short(c.hedge.name))} for ${money(c.hedge.cost)} pays out whichever side wins.</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" onclick="openCombo('${c.t}')">Details</button><button class="btn acc" onclick="hedge('${c.t}')">Hedge</button></div></div>`;
  return `<div class="dcard warn"><div><h4>${esc(c.label)}: check Kalshi's price</h4><p>${esc(c.why||'The plan says this one may be worth selling. Get a real offer to decide.')}</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" onclick="openCombo('${c.t}')">Details</button><button class="btn acc" ${S.busy[c.t]?'disabled':''} onclick="ask('${c.t}')">${S.busy[c.t]?'<span class="spin"></span> Asking…':'Get offer'}</button></div></div>`;}).join('')}</div>`+(ideas.length?ideaBlock(ideas):'');}
function ideaBlock(ideas){S.ideaq=S.ideaq||{};
 return `<h2>Buy ideas <span class="n">${ideas.length}</span><span class="r m" style="font-size:12px">Kalshi priced these at or above your cut-off</span></h2><div class="doit">${ideas.map(x=>{const q=S.ideaq[x.id];const fresh=q&&Date.now()/1000-q.at<20;
  const left=fresh?Math.max(0,Math.round(20-(Date.now()/1000-q.at))):0;
  if(S.ideaGone&&S.ideaGone[x.id])return `<div class="dcard idea gone" id="idea-${x.id}"><div><h4>${x.n===1?'🎯':'💡'} ${esc(x.picks)}</h4><p>Not available on Kalshi right now, so this idea is coming off the list.</p></div></div>`;
  if(x.n===1)return `<div class="dcard idea ${S.hl===x.id?'flash':''}" id="idea-${x.id}"><div><h4>🎯 ${esc(x.picks)} <span class="tag" style="background:var(--panel2);color:var(--sub)">SINGLE GAME</span>${x.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">IN PROGRESS</span>':''}</h4>
   <p>${esc(x.sport)} · found ${ago2(x.ts)} ago · Kalshi's price is below the sharp books' chance of winning, after Kalshi's fee. No combo maker taking a cut.</p>
   ${x.note?`<p style="margin-top:6px">🩹 ${esc(x.note)}</p>`:''}
   <div class="dnums">${fresh?`<div>Price now<b>${Math.round(q.price*100)}¢</b></div><div>Fair chance<b>${pct(q.fair)}</b></div><div>Edge after fee<b class="${q.edge>0?'up':'down'}">${(q.edge*100).toFixed(1)}¢</b></div><div>Buy<b>${q.n} for ${money(q.stake)} → ${money(q.pays)}</b></div>`:`<div>Value<b>${pct(x.pct)} of fair</b></div>`}</div></div>
   <div class="dbtns">${fresh?`<button class="btn ghost" onclick="S.ideaq['${x.id}']=null;renderLive()">Pass</button><button class="btn yes qb" ${q.edge>0?'':'disabled'} onclick="buySingle('${x.id}')">${qBar(q)}Buy · ${left}s</button>`:
    `<button class="btn ghost" onclick="hideIdea('${x.id}')">Not now</button><button class="btn acc" id="ib-${x.id}" onclick="priceIdea('${x.id}')">Get today's price</button>`}</div></div>`;
  return `<div class="dcard idea ${S.hl===x.id?'flash':''}" id="idea-${x.id}"><div><h4>💡 ${esc(x.picks)}${x.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">IN PROGRESS</span>':''}</h4><p>${esc(x.sport)} · ${x.n} picks · priced at <b>${pct(x.pct)}</b> of fair ${ago2(x.ts)} ago${x.kick?' · starts '+new Date(x.kick*1000).toLocaleTimeString([],{weekday:'short',hour:'numeric',minute:'2-digit'}):''}</p>
   ${x.note?`<p style="margin-top:6px">🩹 ${esc(x.note)}</p>`:''}
   <div class="dnums"><div>Last price<b>${money(x.stake)} → ${money(x.pays)}</b></div><div>Fair payout<b>${money(x.fair)}</b></div>${fresh?`<div>Your price now<b class="${q.clears?'up':''}">${money(q.stake)} → ${money(q.pays)}</b></div><div>Share of fair<b>${pct(q.pct)}</b></div>`:''}</div></div>
   <div class="dbtns">${fresh?`<button class="btn ghost" onclick="S.ideaq['${x.id}']=null;renderLive()">Pass</button><button class="btn yes qb" onclick="buyIdea('${x.id}')">${qBar(q)}Buy · ${left}s</button>`:
    `<button class="btn ghost" onclick="hideIdea('${x.id}')">Not now</button><button class="btn acc" id="ib-${x.id}" onclick="priceIdea('${x.id}')">Get my price</button>`}</div></div>`;}).join('')}</div>`;}
async function priceIdea(id){const b=$('#ib-'+id);if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';}
 const r=await api('/app/api/act',{a:'idea',id}).catch(()=>({ok:false}));
 if(!r.ok){if(r.gone)return ideaGone(id,r.msg);toast(r.msg||'No price came in. Try again in a minute.',5000);renderLive();return;}
 S.ideaq[id]={i:r.i,pays:r.pays,stake:r.stake,pct:r.pct,clears:r.clears,at:Date.now()/1000,price:r.price,n:r.n,edge:r.edge,fair:r.fair,single:r.single};renderLive();
 clearInterval(S.ideaT);S.ideaT=setInterval(()=>{if(S.view==='live'&&!$('#modal').classList.contains('on'))renderLive();const q=S.ideaq[id];if(!q||Date.now()/1000-q.at>21){clearInterval(S.ideaT);renderLive();}},1000);}
async function buyIdea(id){const q=S.ideaq[id];if(!q)return;const r=await api('/app/api/act',{a:'buy',i:q.i});S.ideaq[id]=null;
 toast(r.ok?`Bought: ${money(q.stake)} to win ${money(r.pays||q.pays)}. It shows in your combos within a minute.`:(r.msg||'Didn\'t go through.'),6000);if(r.ok)hideIdea(id);else renderLive();load('live',true);}
async function buySingle(id){const q=S.ideaq[id];if(!q)return;const r=await api('/app/api/act',{a:'singlebuy',id,n:q.n,price:q.price});S.ideaq[id]=null;
 toast(r.msg||(r.ok?'Bought.':'Didn\'t go through.'),6000,r.ok?'good':null);if(r.ok)hideIdea(id);else renderLive();load('live',true);}
function ideaGone(id,msg){S.ideaGone=S.ideaGone||{};S.ideaGone[id]=1;hap('light');toast(msg||'That idea isn\'t on Kalshi any more.',3500);renderLive();
 setTimeout(()=>{delete S.ideaGone[id];hideIdea(id);},4500);}
function hideIdea(id){try{const h=JSON.parse(localStorage.getItem('cw_hide')||'[]');h.push(id);localStorage.setItem('cw_hide',JSON.stringify(h.slice(-60)))}catch(e){}renderLive();}
function sweat(c){if(c.group!=='pending'||c.legs.length<2)return '';const w=c.legs.filter(l=>l.res==='yes').length;
 const seg=c.legs.map(l=>l.res==='yes'?'w':l.res==='no'?'x':(!l.res&&l.state==='live'&&(l.live??l.chance)>=.5)?'u':'').sort((a,b)=>'wux'.indexOf(a)>-1&&'wux'.indexOf(b)>-1?'wux'.indexOf(a)-'wux'.indexOf(b):a?-1:b?1:0);
 return `<span class="sweat" title="${w} of ${c.legs.length} picks won">${seg.map(s=>`<i class="${s}"></i>`).join('')}</span>`;}
function momentBar(cs){const m=cs.filter(c=>c.group==='pending'&&c.moment&&c.offer).sort((a,b)=>(b.offer-b.cost)-(a.offer-a.cost));if(!m.length)return '';
 const auto=S.live&&S.live.auto_sell;const more=m.length>1?`<div class="m" style="font-size:12px;margin:-6px 4px 12px">${m.length-1} more combo${m.length>2?'s are':' is'} at a good point too. They're marked with a green edge below.</div>`:'';
 return m.slice(0,1).map(c=>`<div class="moment-bar"><div><b>💸 ${auto?'Cashing out':'Good time to cash out'}: ${esc(c.label)}</b><span>Kalshi offers ${money(c.offer)} on ${money(c.cost)} paid (${smoney(c.offer-c.cost)}). ${c.moment.why==='take profit'?'It reached your take-profit level.':c.moment.why==='lock in'?'It\'s slipping from its high.':c.moment.why==='checkpoint'?'The early games came through.':'Locking in beats the risk of holding.'}</span></div>
  ${auto?'<span class="tag good">Auto</span>':`<button class="btn yes" onclick="sell('${c.t}')">Cash out</button>`}</div>`).join('')+more;}
const SKIND={win:'To win',spread:'Spread',total:'Total',other:'Single bet'};
function heroLive(d,pend,sOpen,W,St,dl){const n=pend.length+sOpen.length;const live=pend.some(c=>c.live)||sOpen.some(x=>x.state==='live');
 const ch=1-(1-(d.riding?d.chance_one||0:0))*sOpen.reduce((a,x)=>a*(1-(x.chance||0)),1);
 const most=pend.reduce((a,c)=>a+c.pays,0)+sOpen.reduce((a,x)=>a+(x.pays||0),0);const big=Math.max(d.best||0,...sOpen.map(x=>x.pays||0));
 const cls=Math.abs(dl)<.005?'flat':dl>0?'up':'down';const est=(d.combos||[]).some(c=>c.group==='pending'&&!c.offer_real);
 const ring=v=>{const r=9,c=2*Math.PI*r;return `<svg class="ring" viewBox="0 0 22 22"><circle cx="11" cy="11" r="${r}" fill="none" stroke="var(--line)" stroke-width="3"/><circle cx="11" cy="11" r="${r}" fill="none" stroke="${v>=.5?'var(--yes)':'var(--acc)'}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${(c*Math.max(0,Math.min(1,v))).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 11 11)"/></svg>`;};
 const glow=cls==='up'?'var(--yesbg)':cls==='down'?'var(--nobg)':'transparent';
 return `<div class="kpis hero" style="--hglow:${glow}"><div class="hv"><span class="hl">${live?'<i class="livedot"></i> Live · ':''}Worth now if sold<span class="fresh" data-fr="L">${frTxt('L')}</span></span>
   <b class="big" data-num="h:worth" data-v="${W.toFixed(2)}" data-pre="${est?'≈ ':''}">${est?'≈ ':''}${money(W)}</b>
   <span class="delta ${cls}">${cls==='up'?'▲':cls==='down'?'▼':'•'} <span data-num="h:dl" data-v="${Math.abs(dl).toFixed(2)}">${money(Math.abs(dl))}</span>${St?` (${dl>=0?'+':'−'}${Math.abs(Math.round(dl/St*100))}%)`:''} <span style="font-weight:500;opacity:.8">vs ${money(St)} in</span></span>
   ${heroChart(d,cls)}</div>
  <div class="hs"><div><span class="hk">Riding</span><b><span data-num="h:n" data-v="${n}" data-f="int">${n}</span> bet${n===1?'':'s'}</b><small>${pend.length} combo${pend.length===1?'':'s'} · ${sOpen.length} single${sOpen.length===1?'':'s'}</small></div>
   <div><span class="hk">Staked</span><b data-num="h:st" data-v="${St.toFixed(2)}">${money(St)}</b><small>in play right now</small></div>
   <div><span class="hk">Chance one pays</span><b>${n?ring(ch):''}<span data-num="h:ch" data-v="${ch.toFixed(4)}" data-f="pct">${n?pct(ch):'—'}</span></b><small>${n?'at least one bet wins':'nothing riding'}</small></div>
   <div><span class="hk">Most it can pay</span><b class="up" data-num="h:most" data-v="${most.toFixed(2)}">${money(most)}</b><small>biggest single bet ${money(big)}</small></div></div></div>`;}
/* The hero chart: what the open bets were worth over the Day (16 h) or Week, gradient area, glowing end dot, the
   staked line dashed. Press and drag on it to scrub: a line and dot follow the finger, the big number and the change
   pill show the value at that moment, and every point crossed ticks a haptic. Release puts the live numbers back. */
try{S.rng=localStorage.getItem('cw_rng')==='week'?'week':'day'}catch(e){S.rng='day'}
S.chartDraw=true;
function setRng(k){if(S.rng===k)return;S.rng=k;try{localStorage.setItem('cw_rng',k)}catch(e){}S.chartDraw=true;renderLive();}
function pulseWeek(){const w=S.pulseWeek;if(S.pwBusy||(w&&Date.now()-w.at<120e3))return;S.pwBusy=true;
 api('/app/api/pulse?h=168').then(r=>{S.pulseWeek={at:Date.now(),pts:(r&&r.pulse)||[]};}).catch(()=>{S.pulseWeek={at:Date.now(),pts:[]};})
  .finally(()=>{S.pwBusy=false;S.chartDraw=true;if(S.view==='live'&&S.rng==='week')renderLive();});}
function heroChart(d,cls){if(S.rng==='week')pulseWeek();const wk=S.rng==='week';const pts=wk?(S.pulseWeek||{}).pts:(d.pulse||[]);S.chart=null;
 const sw=`<div class="rng2">${[['day','Day'],['week','Week']].map(([k,l])=>`<button class="${S.rng===k?'on':''}" onclick="setRng('${k}')">${l}</button>`).join('')}</div>`;
 if(!pts)return `<div class="sparkw"><div class="hsk" style="padding:0"><i style="height:76px"></i></div></div><div class="saxis"><span>Loading the week…</span>${sw}</div>`;
 if(pts.length<3)return `<div class="sparkw"><svg class="spark" viewBox="0 0 600 76" preserveAspectRatio="none"><line x1="0" x2="600" y1="52" y2="52" stroke="var(--line)" stroke-width="2" stroke-dasharray="4 6" vector-effect="non-scaling-stroke"/></svg></div>
  <div class="saxis"><span>${wk?'Not enough history for a week yet.':'The day\'s line fills in as the Mac watches your bets.'}</span>${sw}</div>`;
 const W=600,H=76,t0=pts[0][0],t1=pts[pts.length-1][0],vs=pts.map(p=>p[1]),lo=Math.min(...vs),hi=Math.max(...vs),rg=Math.max(hi-lo,.01);
 const X=t=>(t-t0)/Math.max(1,t1-t0)*W,Y=v=>H-6-(v-lo)/rg*(H-14);const path=pts.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');
 const col=cls==='down'?'var(--no)':cls==='up'?'var(--yes)':'var(--acc)';const lx=X(t1),ly=Y(vs[vs.length-1]);const st=pts[pts.length-1][2];
 const lab=t=>{const x=new Date(t*1000);return wk?x.toLocaleDateString([], {weekday:'short'})+' '+x.toLocaleTimeString([], {hour:'numeric'}):x.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});};
 const draw=S.chartDraw?'draw':'';S.chartDraw=false;S.chart={pts,W,X,Y,lab};
 return `<div class="sparkw" data-chart="1"><span class="sread"></span>${st!=null&&st>=lo&&st<=hi?`<i class="sbase" style="top:${Y(st).toFixed(1)}px"></i>`:''}
  <svg class="spark ${draw}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".32"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
  <path d="${path} L${W} ${H} L0 ${H}Z" fill="url(#sg)"/><path d="${path}" fill="none" stroke="${col}" stroke-width="2.4" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
  </svg><i class="sdot ${draw}" style="left:calc(${(lx/W*100).toFixed(2)}% - 5px);top:${(ly-5).toFixed(1)}px;background:${col};color:${col}"></i><i class="scrl"></i><i class="scrd" style="background:${col}"></i></div>
  <div class="saxis"><span>${esc(lab(t0))}</span>${sw}<span>Now</span></div>`;}
function wireChart(){const w=document.querySelector('.sparkw[data-chart]'),c=S.chart;if(!w||!c||w._wired)return;w._wired=1;
 const big=document.querySelector('.hv .big'),dlt=document.querySelector('.hv .delta');let idx=-1,saved=null;
 const at=x=>{const r=w.getBoundingClientRect(),f=Math.max(0,Math.min(1,(x-r.left)/Math.max(1,r.width))),t=c.pts[0][0]+f*(c.pts[c.pts.length-1][0]-c.pts[0][0]);
  let i=0,b=Infinity;c.pts.forEach((p,j)=>{const dd=Math.abs(p[0]-t);if(dd<b){b=dd;i=j;}});return i;};
 const show=i=>{if(i===idx)return;idx=i;const p=c.pts[i],fx=c.X(p[0])/c.W*100;
  w.querySelector('.scrl').style.left=fx+'%';const dot=w.querySelector('.scrd');dot.style.left=fx+'%';dot.style.top=c.Y(p[1])+'px';
  const rd=w.querySelector('.sread');rd.textContent=c.lab(p[0]);rd.style.left=Math.max(10,Math.min(90,fx))+'%';
  if(big){big.textContent=money(p[1]);big.classList.add('scrub');}
  if(dlt&&p[2]!=null){const dl=p[1]-p[2],k=Math.abs(dl)<.005?'flat':dl>0?'up':'down';dlt.className='delta '+k;
   dlt.innerHTML=`${k==='up'?'▲':k==='down'?'▼':'•'} ${money(Math.abs(dl))}${p[2]?` (${dl>=0?'+':'−'}${Math.abs(Math.round(dl/p[2]*100))}%)`:''} <span style="font-weight:500;opacity:.8">vs ${money(p[2])} in</span>`;}
  hap('selection');};
 const end=()=>{if(!S.scrub)return;S.scrub=false;w.classList.remove('on');idx=-1;
  if(saved){if(big){big.innerHTML=saved.b;big.className=saved.bc;}if(dlt){dlt.innerHTML=saved.d;dlt.className=saved.dc;}saved=null;}
  if(S.liveDirty){S.liveDirty=false;renderLive();}};
 w.addEventListener('pointerdown',e=>{if(e.button)return;S.scrub=true;saved={b:big&&big.innerHTML,bc:big&&big.className,d:dlt&&dlt.innerHTML,dc:dlt&&dlt.className};
  w.classList.add('on');idx=-1;show(at(e.clientX));try{w.setPointerCapture(e.pointerId)}catch(x){}});
 w.addEventListener('pointermove',e=>{if(S.scrub)show(at(e.clientX));});
 ['pointerup','pointercancel','lostpointercapture'].forEach(k=>w.addEventListener(k,end));}
function singlesLive(d){const all=d.singles||[];
 const ss=all.filter(x=>S.filter==='all'||S.filter==='done'?true:S.filter==='live'?x.state==='live':x.sport===S.filter);
 if(!all.length)return '';
 return `<h2 style="margin-top:22px">Single bets &amp; spreads <span class="n">${all.length}</span></h2>
 <div class="tbl stbl"><div class="thead"><div>Bet</div><div>Game</div><div class="num">Paid</div><div class="num">Pays</div><div class="num">Chance</div><div class="num">Worth now</div><div></div></div>
 ${ss.map(rowSingle).join('')||'<div class="empty" data-ic="🗒️"><b>Nothing here</b>No single bets or spreads in this view.</div>'}</div>
 `;}
function ssChip(x){const off=S.live&&S.live.auto_sell===false;
 const hint=!x.self&&!off&&x.sell_at?` · sells at ${money(x.sell_at)}+`:'';
 return `<button class="ss ${x.self?'me':''} ${off&&!x.self?'dim':''}" onclick="event.stopPropagation();selfSell('${x.t}',${!x.self})">${x.self?'✋ I\'ll sell it':'🤖 Smart sell'+(off?' · off in Settings':hint)}</button>`;}
async function selfSell(t,mine){hap();const d=S.live;for(const x of [...(d.singles||[]),...(d.combos||[])])if(x.t===t)x.self=mine;renderLive();
 const r=await api('/app/api/act',{a:'selfsell',t,on:mine}).catch(()=>({ok:false}));toast(r.msg||'Couldn\'t reach the Mac.',3500);if(!r.ok){for(const x of [...(d.singles||[]),...(d.combos||[])])if(x.t===t)x.self=!mine;renderLive();}}
function rowSingle(x){const st=x.res?(x.res==='yes'?'<span class="tag good">Won</span>':'<span class="tag bad">Lost</span>'):x.state==='live'||x.on?'<span class="tag live">Live</span>':x.state==='over'?'<span class="tag">Settling</span>':x.phase==='probably_over'||x.phase==='over'?'<span class="tag">Waiting on Kalshi</span>':'';
 const line=x.how||x.score||x.note||(x.starts?'starts '+x.starts:'');
 const cls=/^(Covering|On track|Winning)/.test(x.how||'')?'up':/^(Not|Losing)/.test(x.how||'')?'down':'';
 return `<div class="trow srow1" data-key="s:${x.t}" data-sig="${esc(x.score||'')}" onclick="openGame('${x.t}')"><div class="name"><b>${ICON[x.sport]||'🎯'} ${esc(x.label)}${x.own?' <span class="own">You, on Kalshi</span>':' <span class="own app">From the app</span>'}</b>${x.state==='live'||x.state==='pre'?ssChip(x):''}<span>${esc(SKIND[x.kind]||'')}${(()=>{const g=(x.game||'').replace(/:\s*(Spread|Total.*)$/i,'').replace(/\s*Winner\??$/i,'').replace(/\?$/,'');return g&&g.toLowerCase()!==(x.label||'').toLowerCase()?' · '+esc(g):'';})()}</span></div>
  <div class="legs"><span class="${cls}">${esc(line)}</span> ${st}${x.url?` <a href="${esc(x.url)}" target="_blank" onclick="event.stopPropagation()">game ↗</a>`:''}</div>
  <div class="numwrap"><div class="num" data-l="Paid">${money(x.cost)}</div><div class="num" data-l="Pays">${money(x.pays)}</div>
  <div class="num" data-l="Chance">${x.chance!=null?`<span data-num="sc:${x.t}" data-v="${x.chance}" data-f="pct">${pct(x.chance)}</span>`:'—'}${x.chance!=null?`<div class="bar"><i data-bar="sb:${x.t}" style="width:${Math.max(1,Math.min(100,x.chance*100))}%"></i></div>`:''}</div>
  <div class="num" data-l="Worth now">${x.worth!=null?`<span data-num="w:${x.t}" data-v="${x.worth}">${money(x.worth)}</span>`:'—'}</div></div><div class="verdict"></div></div>`;}
function offNow(c){return(!c.offer_real&&c.offer_live!=null&&c.offer!=null)?c.offer_live:c.offer;}   // display-only; same rule as the hero (hero_worth)
function rowLive(c){const [vc,vt]=verdictOf(c);const open=S.open[c.t];
 const oLive=offNow(c);const oEst=!c.offer_real;
 const offer=c.group!=='pending'?(c.group==='cashed'?`<b>${money(c.back)}</b><small>cashed out</small>`:'—'):c.offer!=null?`<b data-num="o:${c.t}" data-v="${oLive}" data-pre="${oEst?'≈ ':''}">${oEst?'≈ ':''}${money(oLive)}</b><small>${c.offer_real?'vs '+money(c.hold_value)+' holding':'estimate'}</small>`:'<small>—</small>';
 return `<div class="trow ${c.moment?'hot':''}" data-key="c:${c.t}" data-sig="${esc(c.legs.map(l=>l.score||'').join('|'))}" onclick="tog('${c.t}')"><div class="name"><b>${ICON[c.sports[0]]||''} ${esc(c.label)}${sweat(c)}${c.own?' <span class="own">You, on Kalshi</span>':''}</b>${c.group==='pending'?ssChip(c):''}<span>${esc(nextLine(c))}</span></div>
  <div class="legs">${legTags(c.legs)}</div>
  <div class="numwrap"><div class="num" data-l="Paid">${money(c.cost)}</div><div class="num" data-l="${c.group==='cashed'?'Would pay':'Pays'}">${money(c.group==='cashed'?(c.full||c.pays):c.pays)}${c.group==='cashed'&&c.full?'<small style="display:block" class="m">if held</small>':''}</div>
  <div class="num" data-l="To hit">${c.group==='pending'?`<span data-num="p:${c.t}" data-v="${c.p}" data-f="pct">${pct(c.p)}</span>`:'—'}${c.group==='pending'?`<div class="bar"><i data-bar="pb:${c.t}" style="width:${Math.max(1,Math.min(100,c.p*100))}%"></i></div>`:''}</div>
  <div class="num offer" data-l="Offer">${offer}</div></div>${c.group==='pending'?`<div class="verdict ${vc}">${vt}</div>`:plPill(c)}</div>
  ${open?`<div class="exp">${c.legs.map(l=>`<div class="lrow" style="cursor:pointer" onclick="event.stopPropagation();openGame('${l.ticker}')"><span class="mark ${legCls(l)}">${l.res==='yes'?'✓':l.res==='no'?'✕':''}</span>
   <div class="who"><b>${ICON[l.sport]||''} ${esc(l.name)}</b> <span>${l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||(!l.res&&l.note)||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</span>${l.url?` <a href="${esc(l.url)}" target="_blank" onclick="event.stopPropagation()">game ↗</a>`:''}</div>
   <b>${l.res?'':pct(l.live!=null?l.live:l.chance)}${l.live!=null&&!l.res?' <span class="m" style="font-weight:500;font-size:11px">live</span>':''}</b></div>`).join('')}
   ${c.why&&c.group==='pending'?`<div class="why">${esc(c.why)}</div>`:''}
   ${c.group==='pending'?`<div class="acts"><span class="s">${c.offer_real?`Kalshi offers <b>${money(c.offer)}</b> · holding is worth about ${money(c.hold_ce!=null?c.hold_ce:c.hold_value)}${c.threshold?` · sell at ${money(c.threshold)}+`:''}`:'Ask Kalshi what it will pay for this combo right now.'}</span>
    <button class="btn ghost" onclick="event.stopPropagation();openCombo('${c.t}')">Details</button>
    ${c.hedge&&!c.hedge.done?`<button class="btn" onclick="event.stopPropagation();hedge('${c.t}')">Hedge ${esc(short(c.hedge.name))} · ${money(c.hedge.cost)}</button>`:''}
    <button class="btn" ${S.busy[c.t]?'disabled':''} onclick="event.stopPropagation();ask('${c.t}')">${S.busy[c.t]?'<span class="spin"></span> Asking…':c.offer_real?'New offer':'Get cash-out offer'}</button>
    ${c.offer_real?`<button class="btn yes" onclick="event.stopPropagation();sell('${c.t}')">Cash out ${money(c.offer)}</button>`:''}</div>`:''}</div>`:''}`;}
function tog(t){S.open[t]=!S.open[t];renderLive();}
function moments(){const seen=new Set();const ev=(S.events||[]).slice().reverse().filter(e=>{if(seen.has(e.text))return false;seen.add(e.text);return true;}).slice(0,8);if(!ev.length)return '';
 const K={score:'🏟️',swing:'📈',advice:'⚡',settled:'🏁',alert:'🔔'};
 return `<div class="card"><h3><span><span class="live-dot"></span>Moments</span><span>live</span></h3>${ev.map(e=>`<div class="moment" ${e.ticker?`style="cursor:pointer" onclick="openGame('${e.ticker}')"`:''}><span class="k" ${e.kind==='score'?`style="color:${e.good?'var(--yes)':'var(--no)'}"`:''}>${K[e.kind]||'•'}</span><span>${esc(e.text)}</span><time>${ago2(e.at)}</time></div>`).join('')}</div>`;}
function ago2(t){const s=Math.max(0,Date.now()/1000-t);return s<60?'now':s<3600?Math.round(s/60)+'m':Math.round(s/3600)+'h';}
function sideLive(d){const gs=d.games||[];const r=d.risk;
 return moments()+ordersCard(d)+`<div class="card"><h3>Games you need <span>${gs.length}</span></h3>${gs.slice(0,8).map(g=>`<div class="g" style="cursor:pointer" onclick="openGame('${g.ticker||''}')"><div class="t">${ICON[g.sport]||''} ${esc(g.name)}${g.state==='live'&&g.phase!=='probably_over'&&g.phase!=='waiting'?'<span class="tag">LIVE</span>':''}</div>
  <div class="e">${g.state==='live'&&g.sc?`<b>${g.sc.me}–${g.sc.opp}</b>${esc(g.sc.detail||'')}`:`<b>${pct(g.chance)}</b>${esc(g.short||g.starts||'')}`}</div>
  <div class="x">In ${g.combos} combo${g.combos>1?'s':''} · ${money(g.pays)} riding</div></div>`).join('')||'<div class="m">Nothing pending.</div>'}</div>
 ${r?`<div class="card"><h3>If ${esc(short(r.name))} lose <span>biggest risk</span></h3><div class="mini">Combos out<b>${r.combos} of ${d.riding}</b></div><div class="mini">Payout riding<b>${money(r.pays)}</b></div><div class="mini">${esc(short(r.name))} to win<b>${pct(r.chance)}</b></div></div>`:''}
 ${todayCard(d)}`;}
function todayCard(d){const t=d.today;if(!t)return `<div class="card"><h3>Finished <span>recently</span></h3><div class="mini">Won or cashed<b class="up">${money(d.locked)}</b></div><div class="mini">Holding is worth<b>${money(d.hold_value)}</b></div></div>`;
 const n=t.won+t.cashed+t.lost;const bits=[t.won?`${t.won} won`:'',t.cashed?`${t.cashed} cashed`:'',t.lost?`${t.lost} lost`:''].filter(Boolean).join(' · ');
 return `<div class="card"><h3>Today <span>${n?bits:'nothing finished yet'}</span></h3>${n?`<div class="mini">Paid back<b>${money(t.back)}</b></div><div class="mini">They cost<b>${money(t.cost)}</b></div><div class="mini">Profit today<b class="${t.pl>=0?'up':'down'}">${smoney(t.pl)}</b></div>`:''}${d.week_pl!=null?`<div class="mini">Last 7 days<b class="${d.week_pl>=0?'up':'down'}">${smoney(d.week_pl)}</b></div>`:''}<div class="mini">Still riding is worth<b>${money(d.hold_value)}</b></div></div>`;}
async function ask(t){S.busy[t]=true;S.open[t]=true;renderLive();const r=await api('/app/api/act',{a:'ask',t});S.busy[t]=false;
 hap(r.ok?'success':'error');if(!r.ok)toast(r.msg||'No offer came in.');await load('live',true);}
function sell(t){const c=(S.live.combos||[]).find(x=>x.t===t);if(!c)return;
 modal(`<h3>Cash out ${esc(c.label)} for ${money(c.offer)}?</h3><p>You paid ${money(c.cost)} (${smoney(c.offer-c.cost)}). If you hold instead: ${pct(c.p)} chance of ${money(c.pays)}. Kalshi's offer only lasts a few seconds.</p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn yes" id="sellgo" onclick="doSell('${t}')">Cash out</button></div>`);}
async function doSell(t){hap();const c=(S.live.combos||[]).find(x=>x.t===t)||{};$('#sellgo').innerHTML='<span class="spin"></span>';const r=await api('/app/api/act',{a:'go',t});closeModal();
 if(r.ok&&/^✅/.test(r.msg||'')){S.momSeen=S.momSeen||{};S.momSeen['s:'+t]=1;setTimeout(()=>soldSheet({label:c.label,back:r.offer!=null?r.offer:c.offer,cost:c.cost}),360);}   // the Sold moment
 else{hap(r.ok?'success':'error');toast(r.msg||(r.ok?'Done.':'Didn\'t go through.'),5000);}load('live',true);}
async function hedge(t){const c=(S.live.combos||[]).find(x=>x.t===t);modal(`<h3>Hedge ${esc(c.label)}?</h3><p>Buys the other side of its last game for about ${money(c.hedge.cost)}, so you collect about ${money(c.hedge.locked)} whichever team wins.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();api('/app/api/act',{a:'hedgego',t:'${t}'}).then(r=>{toast(r.msg||'Done.',5000);load('live',true)})">Place hedge</button></div>`);}
async function act(a,t){const r=await api('/app/api/act',{a,t});if(r.msg)toast(r.msg);load('live',true);}
// ---------------- BUILD
function buildSkel(){/* the panel's shape while it loads: header, a few bet rows with a price block, the Approve bar */
 return `<div class="card hsk" style="margin-bottom:14px"><i style="height:16px;width:42%"></i><i style="height:11px;width:70%"></i>${'<div style="display:grid;grid-template-columns:1fr 64px;gap:12px;align-items:center"><div style="display:grid;gap:6px"><i style="height:14px;width:80%"></i><i style="height:10px;width:50%"></i></div><i style="height:34px"></i></div>'.repeat(4)}<i style="height:44px;border-radius:12px"></i></div>`+skel(3);}
/* Build redraws itself often (picks, quotes, folds), so its numbers roll on every redraw, not only on page loads */
function renderBuild(){const keep=[...document.querySelectorAll('#main .ccard[data-ph]')].filter(n=>n.dataset.ph!=='idle');_renderBuild();
 keep.forEach(old=>{const nw=document.querySelector(`#main .ccard[data-i="${old.dataset.i}"]`);   // same card, same phase: keep the very same button (no flicker, no lost tap)
  if(nw&&nw!==old&&nw.dataset.ph===old.dataset.ph&&nw.dataset.sig===old.dataset.sig){nw.replaceWith(old);
   const q=S.quotes&&S.quotes[old.dataset.i];      // putting a node back restarts its CSS animations: keep the draining bar where it was, and don't replay the entrance
   old.querySelectorAll('.qline.new').forEach(e=>e.classList.remove('new'));
   if(q)old.querySelectorAll('.qt').forEach(t=>{t.style.animationDelay='-'+Math.max(0,Date.now()/1000-q.at).toFixed(2)+'s';});}});
 rollNums($('#main'));rbWatch();}
function _renderBuild(){const d=S.build;const m=$('#main');
 /* The chip row never changes while a league loads: the list of leagues and the per-league game counts are remembered
    (also on this phone) instead of read from the data that is cleared on a tap; the built-in list is only for a phone that has never loaded */
 if(d&&d.leagues&&d.leagues.length>1){S.lgs=d.leagues;try{localStorage.setItem('cw_leagues',JSON.stringify(d.leagues))}catch(e){}}
 if(S.panel){S.gn=S.panel.games||null;try{localStorage.setItem('cw_gn',JSON.stringify(S.gn))}catch(e){}}   /* a panel replaces the counts; none at all while one loads */
 const lgs=S.lgs||Object.keys(SPN).map(k=>[k,SPN[k],ICON[k]||'🎲']);
 const pv=S.pview||'all';const gameN=S.gn;const chipRow=`<div class="chips" style="margin-bottom:14px"><button class="chip ${pv==='all'?'on':''}" onclick="setPview('all')">⭐ All</button>${lgs.filter(([k])=>k!=='mix'&&(k===pv||k===S.lg||!gameN||gameN[k]==null||gameN[k]>0)).map(([k,n,i])=>`<button class="chip ${pv===k?'on':''}" onclick="setPview('${k}')">${esc(i||'')} ${esc(SPN[k]||n)}</button>`).join('')}</div>`;
 if(!d||d.lg!==S.lg){m.innerHTML=chipRow+((S.lerr||{}).build&&!d?errCard('build'):'<div class="grid"><div>'+buildSkel()+'</div><div class="skel" style="height:300px"></div></div>');return;}
 const best=bestBets(d);const adv=S.adv||S.slip.length>0;
 m.innerHTML=chipRow+`<div class="grid"><div>
  <div id="pblock">${panelBlock(S.panel)}</div>
  <button class="btn ghost" style="width:100%;margin:18px 0 6px;justify-content:center" onclick="toggleAdv()">${adv?'Hide the full board ▴':`Build your own · all ${d.board.length} games${(d.lines||[]).length?', spreads & totals':''} ▾`}</button>
  ${adv?`${secHead('games',`${esc(d.icon)} ${esc(d.name)} games`,d.board.length,'Kalshi price · fair chance from the sportsbooks')}
  ${secOpen('games')?`<div class="board">${d.board.map(g=>{const sc=g.sc;return `<div class="mrow ${g.started?'livegame':''}" data-key="b:${g.event}" data-sig="${sc?sc.me+'-'+sc.opp:''}"><div class="when">${SPN[g.sport]?`<div class="wlg">${ICON[g.sport]||''} ${esc(SPN[g.sport])}</div>`:''}${g.started?(sc?`<span class="lvsc"><i class="livedot"></i>${esc(sc.detail||'LIVE')}</span>`:'<span class="lvsc"><i class="livedot"></i>LIVE</span>'):esc(g.label||'')}</div>
   ${g.sides.filter(s=>!s.tie).map(s=>{const on=S.slip.includes(s.ticker);const mine=sc?(s.ticker===g.first?sc.me:sc.opp):null,their=sc?(s.ticker===g.first?sc.opp:sc.me):null;
    return `<button class="pickbtn ${on?'on':''} ${on&&S.justPicked===s.ticker?'pop':''} ${mine!=null?(mine>their?'lead':mine<their?'trail':''):''}" onclick="pick('${s.ticker}','${g.event}')"><span class="nm">${mine!=null?`<em class="scr">${mine}</em>`:''}<span class="full">${esc(s.pick)}</span><span class="short">${esc(short(s.pick))}</span>${s.edge!=null&&s.edge>=.01?'<span class="val">VALUE</span>':''}</span>
    <span class="pr"><b ${s.p!=null?`data-num="bp:${s.ticker}" data-v="${s.p}" data-f="cent"`:''}>${s.p!=null?Math.round(s.p*100)+'¢':'—'}</b><span>${s.fair!=null?'fair '+pct(s.fair):''}</span></span></button>`}).join('')}</div>`;}).join('')||'<div class="empty"><b>No games right now</b>Try another sport.</div>'}</div>`:''}
  ${linesBlock(d)}
  ${secHead('combos','More combo ideas',d.combos.length,'',`<button class="btn" id="rebuildb" onclick="event.stopPropagation();rebuild(this)">Rebuild</button>`)}
  ${secOpen('combos')?`<div class="m" style="font-size:12px;margin:-4px 2px 10px">Fairly priced combos built to your mix. They aren't value picks unless marked ★.</div>
  <div class="cgrid">${d.combos.slice().sort((a,b)=>(b.kind==='value')-(a.kind==='value')||((b.pred||{}).p_clear??-1)-((a.pred||{}).p_clear??-1)).map(ccard).join('')}</div>`:''}`:''}
 </div><aside>${adv?slip(d)+singlesCard(d):budgetCard(d)}</aside></div>${slipBar()}`;}
setInterval(()=>{if(S.view==='build'&&S.build&&(S.build.board||[]).some(g=>g.started)&&!document.hidden&&!S.buying&&!$('#modal').classList.contains('on'))load('build').catch(()=>{});},30000);
function setPview(k){hap();S.pview=k;try{localStorage.setItem('cw_pview',k)}catch(e){}S.panel=cget('panel_'+k);const want=k==='all'?'mix':k;if(want!==S.lg){setLg(want);}else load('build');}
try{S.pview=localStorage.getItem('cw_pview')||'all'}catch(e){S.pview='all'}
try{const l=JSON.parse(localStorage.getItem('cw_leagues')||'null');if(Array.isArray(l)&&l.length>1&&l.every(x=>Array.isArray(x)&&x.length>=3&&/^[a-z0-9_]+$/.test(x[0])&&typeof x[1]==='string'&&typeof x[2]==='string'))S.lgs=l;
 const g=JSON.parse(localStorage.getItem('cw_gn')||'null');if(g&&typeof g==='object'&&!Array.isArray(g))S.gn=g}catch(e){}
S.lg=S.pview==='all'?'mix':S.pview;
const KIND={single:['🎯','Single game'],early:['🎢','Sell-early favorite'],line:['📏','Spread / total'],combo:['🧩','Combo']};
function pTime(ts){return ts?new Date(ts*1000).toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'}):'';}
const started=c=>!c.live&&c.kick&&c.kick*1000<Date.now()+5*60e3;
function panelItem(c,st,approved,verb){const k=KIND[c.kind]||['•',c.kind];const off=S.pOff&&S.pOff.has(c.id);
 const state=c.state||'';const chip={'':approved||off||started(c)?'':`<span class="tag pwhen">buys when you ${verb==='add'?'add it':'approve'}</span>`,scheduled:started(c)?'<span class="tag bad">Game started · won\'t buy</span>':c.buy_at&&c.buy_at*1000>Date.now()?`<span class="tag">buys ${pTime(c.buy_at)}</span>`:`<span class="tag">${{paused:'Paused · not bought yet','no key':'Can\'t trade from here',price:'Waiting for a fresh price'}[c.hold]||'Buying now'}</span>`,bought:'<span class="tag good">Bought</span>',buying:'<span class="tag">Buying…</span>',check:'<span class="tag bad">Check Kalshi</span>',paper:'<span class="tag">Paper</span>',
  skipped:'<span class="tag bad">Skipped</span>',swapped:'<span class="tag">Swapped</span>',failed:'<span class="tag bad">Didn\'t buy</span>',cancelled:'<span class="tag">Cancelled</span>','left out':'<span class="tag">Left out</span>'}[state]||'';
 const res=c.result?`<span class="tag ${c.pl>=0?'good':'bad'}">${c.pl>=0?'+':'−'}${money(Math.abs(c.pl))}</span>`:'';
 const title=c.kind==='combo'?(c.legs.every(l=>l.game)?c.legs.map(l=>esc(l.game)).join('<br>'):c.legs.map(l=>esc(short(l.pick))).join(' + ')):c.kind==='line'?esc(c.legs[0].pick.replace(/ \(.*\)$/,'')):`${esc(short(c.legs[0].pick))}${c.kind==='single'?' to win':''}`;
 const games=pGames(c);
 const nums=c.kind==='early'?`${pct(c.chance)} it reaches ${Math.round(c.exit*100)}¢ · buy ${Math.round(c.price*100)}¢`:c.kind==='combo'?`${pct(c.chance)} to hit · pays ≈${pct(c.pct)} of fair`:`${pct(c.chance)} to win · ${Math.round(c.price*100)}¢`;
 return `<div class="pitem ${off?'off':''} ${S.pJust===c.id?'tog':''}" data-pid="${esc(c.id)}"><div class="pi">${c.icon||k[0]}</div><div class="pm"><div class="pk">${k[1]}${c.slate?' · slate':''}${c.league?' · '+esc(c.league):''} · ${c.live?'<span class="pliv">Under way · priced live</span>':esc(pTime(c.kick))}</div><b>${title}</b>
  <div class="pg">${games.map(g=>`<div>${esc(g)}</div>`).join('')}</div>
  <div class="pn">${nums} · <span class="up">+${Math.round(c.ret*100)}% expected</span></div>${c.why?`<div class="pw">${esc(c.why)}</div>`:''}${c.note?`<div class="pw">${esc(c.note)}</div>`:''}</div>
  <div class="ps"><b data-num="ps:${esc(c.id)}" data-v="${(+c.stake||0).toFixed(2)}">${money(c.stake)}</b>${pxSpark(c)}${chip}${res}${!approved?`<button class="x" title="${off?'Put back':'Leave out'}" onclick="pToggle('${c.id}')">${off?'↺':'✕'}</button>`:''}</div></div>`;}
/* Which game each bet is on, in plain English ("Over 7.5" alone told Pete nothing): one line per game. Spreads and totals
   say "Flyers at Bruins"; a single or one leg of a combo says "Flyers vs Bruins" (the team picked first). Older saved
   drafts have no game text, so fall back to what they do carry. */
function pGames(c){const L=c.legs||[];
 if(c.kind==='line'){const m=/\((.*)\)$/.exec(L[0]&&L[0].pick||'');return [c.game||(L[0]&&L[0].game)||(m?m[1]:'')].filter(Boolean);}
 if(c.kind==='combo')return [];   // its title already lists each leg's game
 return [c.game||(L[0]&&L[0].game)||(c.opp&&L[0]?short(L[0].pick)+' vs '+short(c.opp):'')].filter(Boolean);}
function pToggle(id){hap();S.pOff=S.pOff||new Set();S.pOff.has(id)?S.pOff.delete(id):S.pOff.add(id);S.pJust=id;renderBuild();S.pJust=null;}
/* A tiny line on each panel card: the bet's Kalshi price (a combo's share of fair) over the times this phone has seen
   it, kept for 36 hours. It only shows once there are two or more readings, so it never makes data up. */
function pxVal(c){const v=c.kind==='combo'?c.pct:(c.price!=null?c.price:((c.legs||[])[0]||{}).p);return v==null||isNaN(v)?null:+v;}
function pxHist(){if(!S.pxh){try{S.pxh=JSON.parse(localStorage.getItem('cw_pxh')||'{}')||{}}catch(e){S.pxh={}}}return S.pxh;}
function pxNote(c){const v=pxVal(c);if(v==null||!c.id)return [];const h=pxHist(),now=Date.now()/1000;let a=(h[c.id]||[]).filter(p=>now-p[0]<36*3600);const last=a[a.length-1];
 if(!last||Math.abs(last[1]-v)>1e-4||now-last[0]>600){a=a.concat([[Math.round(now),+v.toFixed(4)]]).slice(-48);h[c.id]=a;clearTimeout(S.pxT);
  S.pxT=setTimeout(()=>{try{const hh=pxHist();for(const k in hh)if(!(hh[k]||[]).some(p=>Date.now()/1000-p[0]<36*3600))delete hh[k];localStorage.setItem('cw_pxh',JSON.stringify(hh))}catch(e){}},400);}
 return a;}
function pxSpark(c){const a=pxNote(c);if(a.length<2)return '';const vs=a.map(p=>p[1]),lo=Math.min(...vs),hi=Math.max(...vs),rg=Math.max(hi-lo,.01),t0=a[0][0],t1=a[a.length-1][0];
 const d=a.map((p,i)=>`${i?'L':'M'}${((p[0]-t0)/Math.max(1,t1-t0)*64).toFixed(1)} ${(19-(p[1]-lo)/rg*16).toFixed(1)}`).join('');const col=vs[vs.length-1]>=vs[0]?'var(--yes)':'var(--no)';
 const f=c.kind==='combo'?pct:(x=>Math.round(x*100)+'¢');
 return `<svg class="psp" viewBox="0 0 64 22" preserveAspectRatio="none" aria-label="Price ${f(vs[0])} then ${f(vs[vs.length-1])}"><title>Kalshi price since this phone first saw it: ${f(vs[0])} → ${f(vs[vs.length-1])}</title><path d="${d}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/></svg>`;}
function rbOn(r){return !!(r&&(r.state==='asked'||r.state==='running'));}
/* A requested rebuild, from the Mac's own notes: waiting to start, which sport it's on, or picking the mix. */
function rbText(r){if(r.state==='asked')return r.wait>=90?'Waiting for the Mac to start. It hasn\'t picked this up yet: is it on and awake?':'Starting…';
 if(r.step==='choosing')return 'Picking the best mix for today…';return `Looking at ${esc(SPN[r.sport]||String(r.sport||'').toUpperCase())}… ${Math.min((r.i||0)+1,r.n||1)} of ${r.n||1} sports`;}
function rbFrac(r){if(r.state==='asked')return .04;const n=(r.n||1)+1;return Math.min(.97,r.step==='choosing'?(n-.5)/n:((r.i||0)+.5)/n);}
function rbCard(r){return `<div class="card rbcard" style="text-align:center;padding:22px 18px"><div style="font-size:30px">🔎</div><b style="display:block;margin:6px 0 4px;font-size:17px">Putting together a fresh panel</b>
  <div class="m rbtxt" style="font-size:13px;line-height:1.5"><span class="spin"></span> ${rbText(r)}</div><div class="rbtrack"><i style="width:${Math.round(rbFrac(r)*100)}%"></i></div>
  <div class="m" style="font-size:12px">It appears here on its own when it's ready. Only bets priced better than their real chance make it.</div></div>`;}
function rbStrip(r){return rbOn(r)?`<div class="rbstrip rbcard"><span class="spin"></span><span class="rbtxt">${rbText(r)}</span></div>`:'';}
function panelEmpty(d){const r=d&&d.rebuild;if(rbOn(r))return rbCard(r);
 if(d&&d.view&&d.view!=='all')return `<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🧘</div><b style="display:block;margin:6px 0 4px;font-size:17px">Nothing in ${esc(SPN[d.view]||d.view)} clears the bar right now</b>
  <div class="m" style="font-size:13px;line-height:1.5">No ${esc(SPN[d.view]||d.view)} bet is priced better than its real chance at the moment. The Mac keeps checking through the day. You can still build your own below.</div></div>`;
 const look=`<button class="btn acc" style="width:100%;justify-content:center;margin-top:14px" onclick="panelLook(this)">${r&&r.state==='done'?'Look again now':'Look now'}</button>`;
 if(r&&r.state==='done'&&!r.found)return `<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🧘</div><b style="display:block;margin:6px 0 4px;font-size:17px">No bets clear the bar right now</b>
  <div class="m rbwhy" style="font-size:13px;line-height:1.5">${esc(r.why||'Nothing is priced better than its real chance at the moment.')}</div><div class="m" style="font-size:12px;margin-top:6px">Looked ${ago2(r.upd)==='now'?'just now':ago2(r.upd)+' ago'}. The Mac keeps checking through the day and the panel shows up here if bets turn up.</div>${look}</div>`;
 return `<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🗓️</div><b style="display:block;margin:6px 0 4px;font-size:17px">No panel yet today</b>
  <div class="m" style="font-size:13px;line-height:1.5">The Mac builds one on its own as prices come in, keeping only bets priced better than their real chance. Tap below to have it look at every sport right now.</div>${look}</div>`;}
function panelBlock(d){if(!d||!d.panel)return panelEmpty(d);
 const p=d.panel,st=p.stats||{},approved=d.view==='all'&&p.status!=='draft',items=p.items||[];S.pOff=S.pOff||new Set();
 const live=items.filter(c=>!S.pOff.has(c.id)&&!(p.status==='draft'&&started(c)));const total=live.reduce((a,c)=>a+c.stake,0);
 const head=`<div class="phead"><div><h2 style="margin:0">${d.view==='all'?"Today's panel":(SPN[d.view]||d.view)+(d.approved_other?' picks':' panel')}</h2>
   <div class="m" style="font-size:12.5px;margin-top:2px">${items.length} bet${items.length===1?'':'s'} · ${money(approved?items.filter(c=>['scheduled','buying','bought','check'].includes(c.state)).reduce((a,c)=>a+c.stake,0):total)} of your ${money(p.budget)} · picked together for the best chance the day ends up ahead</div></div>
   <div class="pring" style="--p:${Math.round((st.p_ahead||0)*100)}"><b>${pct(st.p_ahead||0)}</b><small>chance up</small></div></div>`;
 const addMode=d.view!=='all'&&d.approved_other;
 const btn=addMode?`<button class="btn acc" style="width:100%;justify-content:center;font-size:16px;padding:13px" onclick="panelAdd(this)">Add ${live.length} to today's panel · ${money(total)}</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">Today's panel is already approved. These are bought right after you add them, the same way, inside your daily panel budget.</div>`:approved?(p.status==='approved'?`<button class="btn ghost" style="width:100%;justify-content:center" onclick="panelCancel()">Stop buying the rest</button>`:p.status==='cancelled'?`<button class="btn acc" style="width:100%;justify-content:center" onclick="panelRestart(this)">Build a fresh panel for today</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">Bets already bought stay. The Mac looks at today's remaining games again and puts together a new panel for you to approve.</div>`:'')
  :`<button class="btn acc" style="width:100%;justify-content:center;font-size:16px;padding:13px" onclick="panelApprove(this)">Approve ${live.length} bet${live.length===1?'':'s'} · ${money(total)}</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">The Mac buys them right after you approve, checking each price again first. If one no longer qualifies, it swaps in a similar bet or skips it.</div>`;
 const longer=(p.longer||[]).length?`<h2 style="margin-top:20px">Longer plays <span class="n">${p.longer.length}</span></h2><div class="m" style="font-size:12px;margin:-4px 2px 10px">Over the next few days. Each day is a chance to cash out early. Not part of the approval above.</div><div class="plist">${p.longer.map(c=>panelItem(c,'',true)).join('')}</div>`:'';
 const other='';
 return `${d.view==='all'?rbStrip(d.rebuild):''}<div class="card panel">${head}${other}<div class="plist">${items.map(c=>panelItem(c,c.state,approved,addMode?'add':'approve')).join('')||'<div class="m">Nothing qualifies right now.</div>'}</div>
  <div class="m" style="font-size:12px;margin:10px 2px">Expected ${smoney(st.ev||0)} · range ${smoney(st.worst||0)} to ${smoney(st.best||0)}</div>${poolLine(st.pool)}${btn}</div>${extraBlock(d.extra)}${longer}`;}
function extraBlock(x){const its=((x||{}).items||[]).filter(c=>!pSentHas(c.id));if(!its.length)return '';x=Object.assign({},x,{items:its});const live=its.filter(c=>!S.pOff.has(c.id));const tot=live.reduce((a,c)=>a+c.stake,0);
 return `<div class="card panel" style="margin-top:14px;border-color:color-mix(in srgb,var(--yes) 40%,var(--line))"><div class="phead"><div><h2 style="margin:0">🆕 New since you approved</h2>
  <div class="m" style="font-size:12.5px;margin-top:2px">Good bets that turned up after you approved, on games today's panel doesn't have a bet on. Checked every few minutes as games get close.</div></div></div>
  <div class="plist">${x.items.map(c=>panelItem(c,'',false,'add')).join('')}</div>
  ${live.length?`<button class="btn acc" style="width:100%;justify-content:center;margin-top:10px" onclick="panelAdd(this,'extra')">Add ${live.length} to today's panel · ${money(tot)}</button>`:''}</div>`;}
function poolLine(pl){if(!pl)return '';const n=k=>pl[k]||0;
 const parts=[[n('combo'),'combo','combos'],[n('single'),'single game','single games'],[n('early'),'sell-early favorite','sell-early favorites'],[n('line'),'spread or total','spreads or totals']].map(([v,a,b])=>`${v} ${v===1?a:b}`);
 return `<div class="m" style="font-size:12px;margin:-4px 2px 10px">Qualifying today: ${parts.join(' · ')}.${n('combo')?'':' No combo is priced at your cut-off or better right now; Kalshi usually pays less than fair on combos.'}</div>`;}
/* Approve / Add: the first tap arms the button, the second sends it once. While it's on its way (S.pSend) every
   other Approve/Add tap does nothing, and a redraw can't bring back a live button (the arm timer stands aside). */
function pArm(b,txt){b.dataset.sure='1';b.textContent=txt;b.classList.add('arm');hap('warning');
 setTimeout(()=>{if(b.isConnected&&!S.pSend&&b.dataset.sure==='1'){b.dataset.sure='';renderBuild();}},4000);}
async function panelApprove(b){if(S.pSend||b.disabled)return;const ids=(S.panel.panel.items||[]).filter(c=>!S.pOff.has(c.id)).map(c=>c.id);
 if(!b.dataset.sure){pArm(b,'Tap again to approve');return;}
 S.pSend=true;b.disabled=true;b.dataset.sure='sent';b.classList.remove('arm');b.innerHTML='<span class="spin"></span> Sending…';let r;
 try{r=await pPost({a:'panel_approve',ids,view:S.pview||'all',at:S.panel.panel.at});}finally{S.pSend=false;}
 hap(r.ok?'success':'error');toast(r.msg,6000,r.ok?'good':'bad');S.pOff=new Set();await load('build');if(r.ok)pBuyWatch();}
/* Right after Approve / Add the Mac buys within seconds: look again a few times so "Buying now" turns into "Bought". */
function pBuyWatch(){clearTimeout(S.pbT);let i=0;const tick=()=>{if(S.view!=='build')return;
 if(document.hidden||S.buying||$('#modal').classList.contains('on')){S.pbT=setTimeout(tick,3000);return;}
 const pn=((S.panel||{}).panel||{}),its=pn.items||[];if(i&&S.pview==='all'&&pn.status==='approved'&&!its.some(c=>c.state==='scheduled'||c.state==='buying'))return;
 load('build').catch(()=>{}).finally(()=>{if(++i<8)S.pbT=setTimeout(tick,[6,10,15,20,30,60,90][i-1]*1000);});};S.pbT=setTimeout(tick,4000);}
/* Extras this phone just added stay off the New-since-you-approved card for 2 min, even if a refresh that left
   before the Mac saved the add still lists them (the Mac drops them from the card itself too). */
function pSentHas(id){const t=(S.pSent||{})[id];return !!t&&Date.now()-t<120000;}
async function panelAdd(b,view){if(S.pSend||b.disabled)return;const src=view==='extra'?(S.panel.extra||{}):S.panel.panel;
 const ids=(src.items||[]).filter(c=>!S.pOff.has(c.id)&&!(view==='extra'&&pSentHas(c.id))).map(c=>c.id);
 if(!b.dataset.sure){pArm(b,'Tap again to add');return;}
 S.pSend=true;b.disabled=true;b.dataset.sure='sent';b.classList.remove('arm');b.innerHTML='<span class="spin"></span> Adding…';let r;
 try{r=await pPost({a:'panel_add',ids,view:view||S.pview});}finally{S.pSend=false;}
 hap(r.ok?'success':'error');toast(r.msg,6000,r.ok?'good':'bad');
 if(r.ok){if(view==='extra'){S.pSent=S.pSent||{};const now=Date.now();ids.forEach(id=>S.pSent[id]=now);}
  if(b.isConnected){b.innerHTML='✓ Added';b.classList.add('done');}await new Promise(res=>setTimeout(res,700));}
 S.pOff=new Set();await load('build');
 /* keep hidden only what today's panel now really has; anything the Mac left out (budget, same game) shows again */
 if(r.ok&&view==='extra'&&S.panel&&S.panel.panel){const has=new Set((S.panel.panel.items||[]).filter(c=>['scheduled','buying','bought','check','failed'].includes(c.state)).map(c=>c.id));
  let back=false;ids.forEach(id=>{if(!has.has(id)){delete S.pSent[id];back=true;}});if(back)renderBuild();}
 if(r.ok)pBuyWatch();}
/* Approve/Add requests give up waiting after 30 s so a hung link can't leave every button dead; the Mac's side is
   safe to repeat (panel_tx), so the next tap can't buy anything twice. */
function pPost(body){return Promise.race([api('/app/api/act',body).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'})),
 new Promise(res=>setTimeout(()=>res({ok:false,msg:'The Mac is slow to answer. Pull to refresh in a moment to see whether it went through.'}),30000))]);}
async function panelRestart(b){hap();b.innerHTML='<span class="spin"></span>';
 const r=await api('/app/api/act',{a:'panel_restart'}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 hap(r.ok?'success':'error');toast(r.msg,7000,r.ok?'good':'bad');S.rbWas=!!r.ok;await load('build');}
async function panelLook(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking the Mac…';}
 const r=await api('/app/api/act',{a:'panel_look'}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 if(!r.ok){hap('error');toast(r.msg,6000,'bad');}else{S.rbWas=true;if(S.panel){S.panel.rebuild=r.rebuild||{state:'asked',wait:0};}}
 await load('build');}
/* While the Mac rebuilds, ask it every 2 s how far it's got and redraw just the panel card; when it's done, the
   new panel (or the reason there isn't one) drops in by itself. */
function rbWatch(){const on=S.view==='build'&&rbOn((S.panel||{}).rebuild);if(on){S.rbWas=true;if(!S.rbT)S.rbT=setInterval(rbPoll,2000);}else if(S.rbT){clearInterval(S.rbT);S.rbT=null;}}
async function rbPoll(){if(S.view!=='build'){rbWatch();return;}if(document.hidden||S.rbBusy)return;S.rbBusy=true;const pv=S.pview||'all';
 try{const p=await api('/app/api/panel?v='+pv);if(!p||pv!==(S.pview||'all'))return;S.panel=p;cput('panel_'+pv,p);
  if(rbOn(p.rebuild)){const el=$('#pblock');const t=el&&el.querySelector('.rbtxt'),bar=el&&el.querySelector('.rbtrack i');
   if(t&&!!bar===!p.panel){t.innerHTML=(p.panel?'':'<span class="spin"></span> ')+rbText(p.rebuild);if(bar)bar.style.width=Math.round(rbFrac(p.rebuild)*100)+'%';}else renderBuild();return;}
  const r=p.rebuild;if(S.rbWas&&r&&r.state==='done'){if(r.found){hap('success');toast(r.kind==='extra'?`Found ${r.found} new bet${r.found===1?'':'s'} since you approved.`:`Your fresh panel is ready: ${r.found} bet${r.found===1?'':'s'}.`,5000,'good');}else hap('warning');}
  S.rbWas=false;renderBuild();}catch(e){}finally{S.rbBusy=false;rbWatch();}}
async function panelCancel(){hap('warning');if(!confirm('Stop the Mac from buying the rest of today\'s panel?'))return;const r=await api('/app/api/act',{a:'panel_cancel'});toast(r.msg,5000);await load('build');}
function toggleAdv(){hap();const open=S.adv||S.slip.length>0;S.adv=!open;if(open){S.slip=[];S.custom=null;}try{localStorage.setItem('cw_adv',S.adv?'1':'')}catch(e){}renderBuild();
 if(S.adv)setTimeout(()=>{const h=document.querySelector('.board');if(h)h.scrollIntoView({behavior:'smooth',block:'start'});},60);}
function comboRet(c){const r=c.pred&&c.pred.n>=20?c.pred.pct:c.est_pct;return r==null?null:r;}
function bestBets(d){const out=[];
 (d.singles||[]).filter(x=>x.idea).forEach(x=>out.push({k:'single',score:x.ev,x}));
 (d.lines||[]).filter(x=>x.edge>=0.04).forEach(x=>out.push({k:'line',score:x.edge/Math.max(.05,x.p),x}));
 (d.combos||[]).filter(c=>c.kind==='value'&&!c.bought&&(comboRet(c)||0)>=1).forEach(c=>out.push({k:'combo',score:comboRet(c)-1,x:c}));
 return out.sort((a,b)=>b.score-a.score).slice(0,6);}
function betCard(b){const x=b.x,ret=`<span class="ret">+${Math.round(b.score*100)}%<small>expected</small></span>`;
 if(b.k==='single')return `<div class="bet"><div class="bt"><div><span class="kind">🎯 Single game</span><b>${esc(short(x.pick))} to beat ${esc(short(x.opp))}</b></div>${ret}</div>
  <div class="bnums"><div>Chance to win<b>${pct(x.fair)}</b></div><div>Kalshi price<b>${Math.round(x.p*100)}¢</b></div><div>Edge<b class="up">${(x.edge*100).toFixed(1)}¢</b></div></div>
  <div class="why">Kalshi charges ${Math.round(x.p*100)}¢ for a ${pct(x.fair)} chance, after its fee. Wins pay $1 per contract.</div>
  <button class="btn acc" style="width:100%" onclick="singleFromBoard('${x.ticker}',this)">Get a price</button></div>`;
 if(b.k==='line')return `<div class="bet"><div class="bt"><div><span class="kind">${x.kind==='spread'?'📏 Spread':'➕ Total'} · ${esc(x.game)}</span><b>${esc(x.pick.replace(/ \(.*\)$/,''))}</b></div>${ret}</div>
  <div class="bnums"><div>Chance<b>${pct(x.fair)}</b></div><div>Kalshi price<b>${Math.round(x.p*100)}¢</b></div><div>Edge<b class="up">${(x.edge*100).toFixed(1)}¢</b></div></div>
  <div class="why">From the sportsbook line (${esc(String(x.book_line))}) and how often games land within that range. A model adds its own error, so only bigger edges show here.</div>
  <button class="btn acc" style="width:100%" onclick="lineFromBoard('${x.ticker}',this)">Get a price</button></div>`;
 const c=x,o=S.quotes&&S.quotes[c.i],fresh=o&&Date.now()/1000-o.at<20;
 return `<div class="bet"><div class="bt"><div><span class="kind">★ ${c.legs.length}-team combo</span><b>${c.legs.map(l=>esc(short(l.pick))).join(' + ')}</b></div>${ret}</div>
  <div class="bnums"><div>Chance to hit<b>${pct(c.chance)}</b></div><div>Fair payout<b>${money(c.fair)}</b></div><div>Pays vs fair<b class="up">≈${pct(comboRet(c))}</b></div></div>
  <div class="why">Every leg is priced below the sharp books' chance, so the combo should pay more than it's worth. Get the real price before buying.</div>
  ${fresh?`<div class="qline ${o.clears?'good':'bad'} ${qNew(o)}">${qBar(o)}<b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · <span class="qs" data-at="${o.at}">${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}</span>s left</span></div>
   <button class="btn ${o.clears?'yes':'warn'}" style="width:100%" id="b${c.i}" onclick="buy(${c.i},false,this)">${o.clears?'Buy':'Buy anyway'} ${money(o.stake)} → ${money(o.pays)}</button>`:`<button class="btn acc" style="width:100%" id="q${c.i}" onclick="quote(${c.i})">Get a price</button>`}</div>`;}
function budgetCard(d){return d.spent!=null?`<div class="card"><h3>This week <span>${esc(d.name)}</span></h3><div class="mini">Spent<b>${money(d.spent)}</b></div><div class="mini">Your cap<b>${money(d.budget)}</b></div><div class="mini">Combo cut-off<b>${d.cut}% of fair</b></div></div>`:'';}
function slipBar(){const legs=S.slip.map(sideBy).filter(Boolean);const was=S.slipWas;S.slipWas=legs.length;if(!legs.length)return '';
 const ch=legs.reduce((a,l)=>a*(l.fair||l.p||0),1);
 return `<div class="slipbar ${was?'':'in'}"><span>${legs.length<2?`${ICON[legWhere(legs[0]).sp]||''} ${esc(short(legs[0].pick))}${legWhere(legs[0]).opp?' vs '+esc(short(legWhere(legs[0]).opp.pick)):''} picked · tap 1 more team`:`${legs.map(l=>ICON[legWhere(l).sp]||'').join('')} ${legs.length} picks · ${pct(ch)} to hit`}</span>${legs.length>=2?`<button onclick="document.querySelector('.slip').scrollIntoView({behavior:'smooth',block:'center'});if($('#slipq'))quoteSlip()">Price it ›</button>`:''}<button class="x" aria-label="Clear" onclick="S.slip=[];S.custom=null;renderBuild()">✕</button></div><div class="slipgap" style="height:64px"></div>`;}
try{S.adv=!!localStorage.getItem('cw_adv')}catch(e){}
function setLg(k){S.lg=k;S.slip=[];try{localStorage.setItem('cw_lg',k)}catch(e){};S.build=cget('build_'+k);renderBuild();load('build');}
function pick(t,ev){const d=S.build;const same=d.board.find(g=>g.event===ev).sides.map(s=>s.ticker);
 if(S.slip.includes(t))S.slip=S.slip.filter(x=>x!==t);else{S.slip=S.slip.filter(x=>!same.includes(x));S.slip.push(t);S.justPicked=t;}S.custom=null;renderBuild();S.justPicked=null;}
function sideBy(t){for(const g of S.build.board)for(const s of g.sides)if(s.ticker===t)return s;}
function slip(d){const legs=S.slip.map(sideBy).filter(Boolean);const stake=d.stake||5;
 const fairChance=legs.reduce((a,l)=>a*(l.fair||l.p||0),1),kal=legs.reduce((a,l)=>a*(l.p||0),1);const c=S.custom;
 return `<div class="card slip"><h3>Your combo <span>${legs.length} pick${legs.length==1?'':'s'}</span></h3>
  ${legs.length?legs.map(l=>`<div class="pick">${legRow(l)}<button aria-label="Remove" onclick="pick('${l.ticker}','${l.event}')">×</button></div>`).join(''):'<div class="m" style="padding:6px 0 10px">Tap teams on the board to build your own combo, or use a suggestion below.</div>'}
  ${legs.length>=2?`<div style="margin-top:10px"><div class="sum">Chance it hits<b>${pct(fairChance)}</b></div><div class="sum">Fair payout for ${money(stake)}<b>${money(stake/fairChance)}</b></div>
   <div class="sum">Kalshi's single prices imply<b>${money(stake/kal)}</b></div>
   ${c&&c.offer?`<div class="sum">Kalshi offers<b class="${c.offer.clears===false?'':'up'}" ${c.offer.clears===false?'style="color:#f5b544"':''}>${money(c.offer.pays)}</b></div>${c.offer.pct!=null?`<div class="sum">That's<b>${pct(c.offer.pct)} of fair · ${c.offer.clears===false?'below':'above'} your cut-off</b></div>`:''}`:''}
   <div style="display:flex;gap:8px;margin-top:12px">${c&&c.offer&&Date.now()/1000-c.offer.at<20?`<button class="btn qb ${c.offer.clears===false?'warn':'yes'}" style="flex:1" onclick="buy(${c.i},true)">${qBar(c.offer)}${c.offer.clears===false?'Buy anyway':'Buy'} ${money(c.offer.stake)} to win ${money(c.offer.pays)}</button>`:`<button class="btn acc" style="flex:1" id="slipq" onclick="quoteSlip()">Get Kalshi's price</button>`}</div></div>`:''}
  <div class="m" style="font-size:12px;margin-top:12px">${d.spent!=null?`Spent ${money(d.spent)} of your ${money(d.budget)} cap · cut-off ${d.cut}% of fair`:''}</div></div>`;}
async function quoteSlip(){$('#slipq').innerHTML='<span class="spin"></span> Asking Kalshi…';const r=await api('/app/api/act',{a:'custom',tickers:S.slip});
 if(!r.ok){toast(r.msg);renderBuild();return;}const q=await api('/app/api/act',{a:'quote',i:r.i,legs:S.slip.slice()});
 if(!q.ok){toast(q.error||q.msg||'No price came in.');renderBuild();return;}S.custom={i:r.i,offer:{pays:q.pays,stake:q.stake,at:Date.now()/1000,pct:q.pct,clears:q.clears}};hap(q.clears?'success':'warning');renderBuild();clearInterval(S.qT);S.qT=setInterval(qTick,1000);
 toast(`Kalshi pays ${money(q.pays)} for ${money(q.stake)} (${pct(q.pct)} of fair). Buy within 20 seconds.`,6000);}
async function rebuild(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Rebuilding…';}
 const before=JSON.stringify(((S.build||{}).combos||[]).map(c=>c.legs.map(l=>l.ticker)));S.quotes={};
 await load('build',true);const after=JSON.stringify(((S.build||{}).combos||[]).map(c=>c.legs.map(l=>l.ticker)));
 toast(before===after?'Prices refreshed. The best combos are still the same ones.':'New combos are ready.',4000,'good');}
async function swapCombo(i,b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span>';}
 const r=await api('/app/api/act',{a:'swap',i}).catch(()=>({ok:false}));if(S.quotes)delete S.quotes[i];if(S.flips)delete S.flips[i];
 if(!r.ok){hap('error');toast(r.msg||'Couldn\'t find another one.');renderBuild();return;}
 const k=S.build.combos.findIndex(x=>x.i===i);if(k>=0)S.build.combos[k]=r.combo;S.ccJust=i;renderBuild();S.ccJust=null;hap('success');}
async function flipLeg(i,t){hap();const r=await api('/app/api/act',{a:'flip',i,t}).catch(()=>({ok:false}));
 if(!r.ok){hap('error');toast(r.msg||'Couldn\'t flip that one.',6000);return;}
 const k=S.build.combos.findIndex(x=>x.i===i);if(k>=0)S.build.combos[k]=r.combo;if(S.quotes)delete S.quotes[i];
 S.flips=S.flips||{};S.flips[i]={v:r.verdict,text:r.text};hap(r.verdict==='good'?'success':r.verdict==='bad'?'warning':'light');S.ccJust=i;renderBuild();S.ccJust=null;}
/* A bet's leg, Kalshi-style: sport icon, the pick in bold, then who it plays, the league and when, with the price on the right
   (and the live score when the game is under way). Display only: it reads the Build board the page already has. */
function gameOf(l){const ev=l.event||String(l.ticker||'').replace(/-[^-]*$/,'');const b=S.build&&S.build.board;if(!b)return undefined;
 if(!S._gm||S._gm.b!==b){S._gm={b,m:new Map(b.map(x=>[x.event,x]))};}return S._gm.m.get(ev);}
function legWhere(l){const g=gameOf(l)||{};const opp=(g.sides||[]).find(s=>!s.tie&&s.ticker!==l.ticker);return {g,opp,sp:g.sport||''};}
function legRow(l,o){o=o||{};const {g,opp,sp}=legWhere(l);const meta=[opp?'vs '+opp.pick:'',SPN[sp]||'',g.started?'':(g.label||'')].filter(Boolean).join(' · ');
 const live=g.started?(legLive(l)||'<span class="legsc even">● Live</span>'):'';
 return `<div class="lrow${o.flip?' flip':''}"${o.flip?` onclick="flipLeg(${o.i},'${l.ticker}')" title="Tap to flip to the other team"`:''}>${ICON[sp]?`<span class="li">${ICON[sp]}</span>`:''}<div class="lm"><b>${esc(l.pick)}</b><small>${esc(meta)}</small>${live}</div><span class="lp">${l.fair!=null?pct(l.fair):''}${o.flip?'<i>⇄</i>':''}</span></div>`;}
function legSummary(ls){return (ls||[]).map(l=>{const {opp,sp}=legWhere(l);return `${ICON[sp]||''} ${l.pick}${opp?' vs '+opp.pick:''}`.trim();}).join(' · ');}
function legLive(l){const ev=(l.event||String(l.ticker||'').replace(/-[^-]*$/,''));const g=(S.build&&S.build.board||[]).find(x=>x.event===ev);if(!g||!g.sc)return '';
 const sc=g.sc,me=l.ticker===g.first?sc.me:sc.opp,th=l.ticker===g.first?sc.opp:sc.me;return `<span class="legsc ${me>th?'up':me<th?'down':'even'}">● ${me}–${th} · ${esc(sc.detail||'live')}</span>`;}
/* a fresh Kalshi quote: it rises in once, and a thin bar under it drains over the 20 seconds the price lasts */
function qNew(o){return o&&Date.now()/1000-o.at<1.2?'new':'';}
function qBar(o){return o?`<i class="qt" style="animation-delay:-${Math.max(0,Date.now()/1000-o.at).toFixed(2)}s"></i>`:'';}
function ccSig(c){return (c&&c.legs||[]).map(l=>l.ticker).join('|');}
function ccPhase(c){const o=S.quotes&&S.quotes[c.i],wait=v=>v&&Date.now()-v.t<60000&&v.sig===ccSig(c);   // a price or a buy still on its way (never stuck for more than a minute)
 return wait(S.bpend&&S.bpend[c.i])?'buy':wait(S.qpend&&S.qpend[c.i])?'ask':o&&Date.now()/1000-o.at<20?'quote'+o.at:'idle';}
function ccard(c){const o=S.quotes&&S.quotes[c.i];const fresh=o&&Date.now()/1000-o.at<20;const fl=S.flips&&S.flips[c.i];const ph=ccPhase(c);const busy=ph==='buy'||ph==='ask';
 if(c.bought)return `<div class="ccard" style="opacity:.62"><div class="hd"><div><div class="tier" style="color:var(--yes)">✓ You bought this</div><b>${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold">${pct(c.chance)}</span></div>
  <div class="lrows">${c.legs.map(l=>legRow(l)).join('')}</div>
  <div class="brow"><button class="btn ghost pri" onclick="go('live')">See it on Live</button><button class="btn ghost sec" onclick="swapCombo(${c.i},this)">↻ Another</button></div></div>`;
 return `<div class="ccard ${S.ccJust===c.i?'flash':''}" data-i="${c.i}" data-ph="${ph}" data-sig="${esc(ccSig(c))}"><div class="hd"><div><div class="tier" ${c.kind==='value'?'style="color:var(--yes)"':''}>${c.kind==='value'?'★ Value pick':esc(c.tier||c.kind||'')}</div><b data-num="cf:${c.i}" data-v="${(+c.fair||0).toFixed(2)}">${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold" data-num="cc:${c.i}" data-v="${c.chance}" data-f="pct">${pct(c.chance)}</span></div>
  <div class="lrows">${c.legs.map(l=>legRow(l,{flip:1,i:c.i})).join('')}</div>
  ${fl?`<div class="flipnote ${fl.v}"><b class="v">${fl.v==='good'?'Good flip':fl.v==='bad'?'Worse bet':'Trade-off'}</b>${esc(fl.text)}</div>`:`<div class="m" style="font-size:11.5px">Tap a team to flip it to the other side.</div>`}
  <div class="s" style="font-size:12.5px">${c.pred&&c.pred.n>=20?`<span class="pred ${c.pred.p_clear>=.6?'good':c.pred.p_clear<.2?'bad':''}">Likely ≈ ${pct(c.pred.pct)} of fair · ${c.pred.p_clear>=.9?'very likely':c.pred.p_clear>=.6?'likely':c.pred.p_clear>=.35?'maybe':'unlikely'} to clear your cut-off</span><div class="m" style="font-size:11.5px;margin-top:4px">Guess from ${c.pred.n} past Kalshi prices. Get price for the real one.</div>`:c.est?`Kalshi will likely pay about ${money(c.est)} (${pct(c.est_pct)} of fair)`:fresh?'':'Get a price to see what Kalshi pays.'}
   ${c.size?`<div class="m" style="margin-top:6px">Suggested bet ${money(c.size)}${c.exposure?` · smaller: you already need ${esc(short(c.exposure.team))} a lot`:''}</div>`:c.exposure?`<div class="m" style="margin-top:6px">You already need ${esc(short(c.exposure.team))} in a lot of combos</div>`:''}</div>
  ${fresh?`<div class="qline ${o.clears?'good':'bad'} ${qNew(o)}">${qBar(o)}<b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · ${o.clears?'above':'below'} your ${o.cut||''}% cut-off · <span class="qs" data-at="${o.at}">${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}</span>s left</span></div>`:''}
  <div class="brow">${ph==='buy'?`<button class="btn pri ${o&&o.clears?'yes':'warn'}" id="b${c.i}" disabled><span class="spin"></span> Buying… confirming with Kalshi</button>`:
   ph==='ask'?`<button class="btn pri" id="q${c.i}" disabled><span class="spin"></span> Asking Kalshi…</button>`:
   fresh?`<button class="btn pri ${o.clears?'yes':'warn'}" id="b${c.i}" onclick="buy(${c.i},false,this)">${o.clears?'Buy':'Buy anyway'} ${money(o.stake)} → ${money(o.pays)}</button>`:
   `<button class="btn pri" id="q${c.i}" onclick="quote(${c.i})">Get price</button>`}<button class="btn ghost sec" title="Not this one: show a different combo" ${busy?'disabled':''} onclick="swapCombo(${c.i},this)">↻ Not this one</button></div></div>`;}
async function quote(i){hap();S.qpend=S.qpend||{};const cur0=(S.build&&S.build.combos||[]).find(c=>c.i===i),sig=ccSig(cur0);
 if(S.qpend[i]&&Date.now()-S.qpend[i].t<60000&&S.qpend[i].sig===sig)return;S.qpend[i]={t:Date.now(),sig};const b=$('#q'+i);
 if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';const sc=b.parentNode.querySelector('.sec');if(sc)sc.disabled=true;const cc=b.closest('.ccard');if(cc)cc.dataset.ph='ask';}
 const shown=((S.build&&S.build.combos||[]).find(c=>c.i===i)||{}).legs;
 const r=await api('/app/api/act',{a:'quote',i,legs:shown?shown.map(l=>l.ticker):undefined}).catch(e=>({ok:false,error:'Couldn\'t reach your Mac ('+(e&&e.message||e)+').'}));
 if(S.qpend[i]&&S.qpend[i].sig===sig)delete S.qpend[i];
 if(ccSig((S.build&&S.build.combos||[]).find(c=>c.i===i))!==sig){renderBuild();return;}   // the card was swapped, flipped or rebuilt while we waited: that price isn't for what's on screen
 if(!r.ok){hap('error');toast(r.error||r.msg||'No price came in.',6000);renderBuild();return;}
 S.quotes=S.quotes||{};S.quotes[i]={pays:r.pays,stake:r.stake,pct:r.pct,clears:r.clears,cut:r.cut,at:Date.now()/1000};hap(r.clears?'success':'warning');renderBuild();
 clearInterval(S.qT);S.qT=setInterval(qTick,1000);}
/* The quote countdown: once a second only the "Ns left" numbers change, in place. A card is redrawn once, when its quote
   runs out (the button goes back to Get price), never every second (that replaced the button under your finger). */
function qTick(){if(S.view!=='build')return;const now=Date.now()/1000;
 document.querySelectorAll('#main .qs').forEach(e=>{const left=Math.max(0,Math.round(20-(now-(+e.dataset.at||0))));if(e.textContent!==String(left))e.textContent=left;});
 const old=q=>q&&!q.x&&now-q.at>=20;   // a quote that has just run out: one redraw puts Get price back (and drops the dead Buy)
 const over=Object.values(S.quotes||{}).some(old)||old(S.custom&&S.custom.offer);
 if(over&&!S.buying){Object.values(S.quotes||{}).forEach(q=>{if(old(q))q.x=1;});if(old(S.custom&&S.custom.offer))S.custom.offer.x=1;renderBuild();}
 if(!Object.values(S.quotes||{}).some(q=>q&&now-q.at<21)&&!(S.custom&&S.custom.offer&&now-S.custom.offer.at<21))clearInterval(S.qT);}
async function buy(i,custom,btn){if(S.buying)return;S.buying=true;
 if(!custom){S.bpend=S.bpend||{};S.bpend[i]={t:Date.now(),sig:ccSig((S.build&&S.build.combos||[]).find(x=>x.i===i))};const cc=btn&&btn.closest('.ccard');if(cc)cc.dataset.ph='buy';const sc=btn&&btn.parentNode&&btn.parentNode.querySelector('.sec');if(sc)sc.disabled=true;}
 hap();const named=legSummary(custom?S.slip.map(sideBy).filter(Boolean):((S.build&&S.build.combos||[]).find(x=>x.i===i)||{}).legs);if(btn){btn.disabled=true;btn.innerHTML='<span class="spin"></span> Buying… confirming with Kalshi';}
 let r;try{r=await api('/app/api/act',{a:'buy',i});}catch(e){r={ok:false,msg:'Couldn\'t reach your Mac ('+(e&&e.message||e)+'). Check Live before trying again, so you don\'t buy twice.'};}
 S.buying=false;if(S.bpend)delete S.bpend[i];if(r.ok){okSheet('Bought',`${money(r.pays||0)} if it hits`,(named?named+'. ':'')+'It shows on Live within a minute. Smart sell watches it from there.');}else{toast(r.msg||'Didn\'t go through.',7000,'bad');}
 if(custom)S.custom=null;else if(S.quotes)delete S.quotes[i];if(r.ok&&custom)S.slip=[];
 if(r.ok&&!custom&&S.build){const c=S.build.combos.find(x=>x.i===i);if(c)c.bought=true;}renderBuild();}
/* Haptics. light/selection = one tick; success = two quick ticks; warning = two slower; error = three.
   In the iPhone app: combo://haptic/<kind>. Home Screen app / Safari on iOS: toggling an <input switch> ticks the
   Taptic Engine; it has to happen synchronously inside a real tap (the global tap listener calls hap() from the click
   event), on an element that is laid out (a tiny, nearly see-through one inside the screen; iOS ignores display:none,
   visibility:hidden and, it seems, things parked off-screen). iPhones and iPads get the switch even if they report
   navigator.vibrate; everything else uses navigator.vibrate. window.__haps keeps the last 60 kinds for the page tests.
   HT holds every method the Settings > Test haptics card can try; HAPDEF is the one hap() uses (change that one letter
   once Pete reports which method he feels). The card's Haptics switch is saved on this phone (cw_hapoff). */
const HAPN={success:[0,90],warning:[0,160],error:[0,80,160]};
const APPLE=/iP(hone|ad|od)/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const HAPDEF='B';
const HAPCLICK='ABCDEFJK';   // the methods hap() can run itself (G, H, I need the finger itself; L, M aren't switches)
const HAPCSS='position:fixed;left:8px;bottom:8px;width:2px;height:2px;opacity:.01;overflow:hidden;z-index:-1';
const HAPSW='<input type="checkbox" switch tabindex="-1">';
function hapNode(id,css){let l=document.getElementById(id);if(!l){l=document.createElement('label');l.id=id;l.className='hapx';l.setAttribute('aria-hidden','true');l.style.cssText=css;l.innerHTML=HAPSW;document.body.appendChild(l);}return l;}
const HT={
 A(){hapNode('hapA','position:fixed;left:-99px;top:0;opacity:0;width:1px;height:1px;overflow:hidden').click();},   // the old way
 B(){hapNode('hapl',HAPCSS).click();},
 C(){hapNode('hapC',HAPCSS).querySelector('input').click();},
 D(){const l=document.createElement('label');l.className='hapx';l.setAttribute('aria-hidden','true');l.style.cssText=HAPCSS;l.innerHTML=HAPSW;document.body.appendChild(l);l.click();setTimeout(()=>l.remove(),400);},
 E(){const l=hapNode('hapl',HAPCSS);l.click();l.click();},
 F(){const l=hapNode('hapl',HAPCSS);l.click();setTimeout(()=>l.click(),120);},
 G(){},H(){},I(){},   // native: the user's own tap is the toggle, nothing to run
 J(){HT.B();},K(){HT.B();},
 L(){if(!navigator.vibrate)return false;navigator.vibrate([20,40,20]);},
 M(){if(!S.inapp)return false;const f=document.createElement('iframe');f.style.display='none';f.src='combo://haptic/light';document.body.appendChild(f);setTimeout(()=>f.remove(),300);}
};
const HAPM=[   // [id, event, name, what it does]
 ['A','click','Switch label click (how the app did it)','A tiny switch parked off the left edge of the screen; the label is clicked inside your tap.'],
 ['B','click','Switch label click, on screen (the app now)','The same, but the switch sits inside the screen, nearly see-through.'],
 ['C','click','Click the switch itself','Clicks the switch input directly, not its label.'],
 ['D','click','A brand-new switch each tap','Makes a fresh switch inside your tap, clicks it, removes it.'],
 ['E','click','Double tick, two clicks at once','Clicks the switch twice, right after each other.'],
 ['F','click','Double tick, second one 120 ms later','The second click is delayed, so it is outside your tap.'],
 ['G','native','The button is the switch','Your tap lands on a label wrapped around a real switch. No code involved.'],
 ['H','native','A real, visible switch','Tap the switch itself. The plain iOS baseline.'],
 ['I','native','Our toggle with the switch attribute','The same round toggle as Settings uses, with the iOS switch attribute added.'],
 ['J','pointerdown','Fires when the finger lands','The switch click runs on touch down, before you lift.'],
 ['K','pointerup','Fires when the finger lifts','The switch click runs on touch up.'],
 ['L','click','navigator.vibrate (not expected on iPhone)','The standard web vibrate call. iPhones usually have none.'],
 ['M','click','combo://haptic (the iPhone app only)','Only works inside the Pythonista app, so it says so here.']];
function hapOff(){if(S.hapOff==null){try{S.hapOff=localStorage.getItem('cw_hapoff')==='1';}catch(e){S.hapOff=false;}}return S.hapOff;}
function hapSet(on){S.hapOff=!on;try{localStorage.setItem('cw_hapoff',on?'':'1');}catch(e){}}
function hap(k){k=k||'light';const now=performance.now(),fresh=now-(S.hapAt||0)<90;
 if(!HAPN[k]&&fresh)return;S.hapAt=now;const seq=fresh?HAPN[k].slice(1):(HAPN[k]||[0]);   // the tap's own tick counts as a pattern's first
 const hs=window.__haps=window.__haps||[];hs.push(k);if(hs.length>60)hs.shift();
 if(hapOff())return;
 try{if(S.inapp){const f=document.createElement('iframe');f.style.display='none';f.src='combo://haptic/'+k;document.body.appendChild(f);setTimeout(()=>f.remove(),300);return;}
 if(!APPLE&&navigator.vibrate){navigator.vibrate(k==='success'?[10,60,10]:k==='error'?[25,60,25,60,25]:k==='warning'?[18,120,18]:8);return;}
 const f=HAPCLICK.includes(HAPDEF)?HT[HAPDEF]:HT.B;seq.forEach(d=>d?setTimeout(f,d):f());}catch(e){}}
/* Settings > Test haptics: one button per method. Each runs its method right inside its own tap, never through hap(),
   and the global tap listener leaves these buttons alone (data-hapt) so only the method under test can buzz. */
function hapTry(id,b){const t=performance.now();if(hapTry.id===id&&t-hapTry.at<60)return;hapTry.id=id;hapTry.at=t;   // a label's tap clicks twice (label, then its switch): count it once
 (window.__hapt=window.__hapt||[]).push(id);let ok=true;try{ok=HT[id]();}catch(e){ok=false;}
 const s=b&&b.closest('.hxrow')&&b.closest('.hxrow').querySelector('.hxs');if(!s)return;
 s.textContent=ok===false?'not available here':'sent ✓';s.classList.remove('on');void s.offsetWidth;s.classList.add('on');
 clearTimeout(s._t);s._t=setTimeout(()=>{s.textContent='';s.classList.remove('on');},1500);}
function hapCard(){const row=([id,ev,name,what])=>{const lab=`<span class="hxid">${id}</span> ${esc(name)}`;let btn;
  if(id==='G')btn=`<label class="btn hxbtn" data-hapt="1" onclick="hapTry('G',this)"><input type="checkbox" switch class="hxnat" tabindex="-1">${lab}</label>`;
  else if(id==='H')btn=`<label class="btn hxbtn" data-hapt="1" onclick="hapTry('H',this)">${lab}<input type="checkbox" switch data-hapt="1"></label>`;
  else if(id==='I')btn=`<label class="btn hxbtn" data-hapt="1" onclick="hapTry('I',this)">${lab}<input type="checkbox" switch class="tg" data-hapt="1"></label>`;
  else btn=`<button class="btn hxbtn" type="button" data-hapt="1" ${ev==='click'?'onclick':ev==='pointerdown'?'onpointerdown':'onpointerup'}="hapTry('${id}',this)">${lab}</button>`;
  return `<div class="srow hxrow" data-m="${id}"><div class="l">${btn}<small>${esc(what)}</small></div><span class="hxs" aria-live="polite"></span></div>`;};
 return scard('haptics','📳','Test haptics','Tap each button. Tell Claude which one you feel.',
  `<label class="srow" data-hapt="1"><div class="l"><b>Haptics</b><small>Taps buzz on this phone. Turn off to keep it quiet. Saved on this phone only.</small></div><input type="checkbox" class="tg" id="hapon" ${hapOff()?'':'checked'} onchange="hapSet(this.checked)"></label>`
  +HAPM.map(row).join('')+`<div class="srow"><div class="l"><b>Which one worked? Tell Claude</b><small>Say the letter. Nothing here changes how the app buys or sells.</small></div></div>`);}
// ---------------- RESULTS
function resultsSkel(){return `<div class="kpis">${'<div class="kpi skel" style="height:84px"></div>'.repeat(5)}</div><div class="chart"><div class="hsk" style="padding:0"><i style="height:12px;width:30%"></i><i style="height:28px;width:44%"></i><i style="height:150px"></i></div></div>`+skel(4);}
function renderResults(){const d=S.res;const m=$('#main');if(!d){m.innerHTML=(S.lerr||{}).results?errCard('results'):resultsSkel();return;}
 if(S.scrub){S.resDirty=true;return;}
 const sh=d.shadow;
 m.innerHTML=`<div class="grid"><div>${!d.settled&&!(d.history||[]).length?`<div class="card empty" data-ic="📊" style="margin-bottom:16px"><b>No results yet</b>Profit by day and week, and what's working, fill in here as your bets settle.<br><button class="btn acc" onclick="go('build')">See today's bets</button></div>`:''}<div class="kpis">
  <div class="kpi"><span>Profit / loss</span><b class="${d.pl>=0?'up':'down'}" data-num="r:pl" data-v="${Math.abs(d.pl||0).toFixed(2)}" data-pre="${(d.pl||0)>=0?'+':'−'}">${smoney(d.pl)}</b></div>
  <div class="kpi"><span>Return on stake</span><b ${d.roi==null?'':`data-num="r:roi" data-v="${d.roi}" data-f="spct"`}>${d.roi==null?'—':(d.roi>=0?'+':'')+Math.round(d.roi*100)+'%'}</b></div>
  <div class="kpi"><span>Settled</span><b><span data-num="r:n" data-v="${d.settled||0}" data-f="int">${d.settled}</span> <small>combos</small></b></div>
  <div class="kpi"><span>Won · cashed</span><b>${d.won} <small>· ${d.cashed}</small></b></div>
  <div class="kpi"><span>Best result</span><b class="up" ${d.best!=null?`data-num="r:best" data-v="${Math.abs(d.best).toFixed(2)}" data-pre="${d.best>=0?'+':'−'}"`:''}>${smoney(d.best)}</b></div></div>
  ${plChart(d)}
  ${anBlock(S.an)}${edgeBlock(d)}
  ${historyBlock(d.history||[])}
 </div><aside class="side">
  <div class="card"><h3>Shadow auto-trading <span>paper</span></h3>${sh&&sh.quotes?`<div class="mini">Settled<b>${sh.n}</b></div><div class="mini">Paper P/L<b class="${sh.back-sh.staked>=0?'up':'down'}">${smoney(sh.back-sh.staked)}</b></div>
   <div class="mini">Open<b>${sh.open}</b></div><div class="mini">Kalshi quotes, median<b>${pct(sh.median)} of fair</b></div><div class="mini">Buys at<b>${sh.min_pct}%+</b></div>${sh.same_game&&(sh.same_game.n||sh.same_game.open)?`<div class="mini">Same-game test (winner + total)<b class="${sh.same_game.pl>=0?'up':'down'}">${smoney(sh.same_game.pl)} · ${sh.same_game.n} settled, ${sh.same_game.open} open</b></div>`:''}`:'<div class="m">No quotes yet. The Mac asks within 8 hours of game time.</div>'}</div>
  <div class="card"><h3>Most accurate odds</h3><div class="m" style="font-size:13px">${esc(d.accuracy_text||'')}</div></div>
 </aside></div>`;wireScrubs(m);}
/* Profit by day or by week: bars you can drag a finger across (the readout and a haptic tick follow it) and tap to see
   that day's or week's bets in a sheet. Day = the last 14 days that had a result; Week = the last 12 weeks. */
try{S.plr=localStorage.getItem('cw_plr')==='day'?'day':'week'}catch(e){S.plr='week'}
function setPlr(k){if(S.plr===k)return;S.plr=k;try{localStorage.setItem('cw_plr',k)}catch(e){}renderResults();}
function plBars(d){const hist=d.history||[];
 if(S.plr==='day'){const by={};hist.forEach(h=>{if(!h.day)return;const b=by[h.day]||(by[h.day]={k:h.day,pl:0,n:0});b.pl+=h.pl;b.n++;});
  return Object.values(by).sort((a,b)=>a.k.localeCompare(b.k)).slice(-14).map(b=>Object.assign(b,{lab:new Date(b.k+'T12:00:00').toLocaleDateString([], {month:'short',day:'numeric'}),items:hist.filter(h=>h.day===b.k)}));}
 return (d.weeks||[]).map(w=>({k:w.week,pl:w.pl,n:w.n,lab:'Week of '+(w.week&&/^\d{4}-/.test(w.week)?new Date(w.week+'T12:00:00').toLocaleDateString([], {month:'short',day:'numeric'}):w.week),items:hist.filter(h=>h.week===w.week)}));}
function plChart(d){const bars=plBars(d),n=bars.length,tot=bars.reduce((a,b)=>a+b.pl,0),cnt=bars.reduce((a,b)=>a+b.n,0);
 const sw=`<div class="rng2">${[['day','Day'],['week','Week']].map(([k,l])=>`<button class="${S.plr===k?'on':''}" onclick="setPlr('${k}')">${l}</button>`).join('')}</div>`;
 const sum=`${S.plr==='day'?'Last '+n+' day'+(n===1?'':'s')+' with results':'Last '+n+' week'+(n===1?'':'s')} · ${cnt} bet${cnt===1?'':'s'}`;
 if(!n)return `<h2>Profit by ${S.plr}</h2><div class="chart plc"><div class="plh"><div><b>$0</b><small>Nothing settled yet</small></div>${sw}</div><div class="empty" style="padding:22px 10px">Bars show up here as your bets settle.</div></div>`;
 const W=Math.max(300,n*44),H=150,mid=H/2,mx=Math.max(1,...bars.map(b=>Math.abs(b.pl))),bw=Math.min(30,W/n*.62);
 S.scr=S.scr||{};S.scr.pl={n,at:f=>Math.min(n-1,Math.floor(f*n)),
  show:(i,el)=>{const b=bars[i];el.closest('.plc').classList.add('on');el.querySelectorAll('rect.brc').forEach((r,j)=>r.classList.toggle('sel',j===i));
   const h=el.closest('.plc').querySelector('.plh');h.querySelector('b').textContent=smoney(b.pl);h.querySelector('b').className=b.pl>=0?'up':'down';h.querySelector('small').textContent=`${b.lab} · ${b.n} bet${b.n===1?'':'s'} · tap for the bets`;},
  end:el=>{const c=el.closest('.plc');c.classList.remove('on');el.querySelectorAll('rect.brc').forEach(r=>r.classList.remove('sel'));const h=c.querySelector('.plh');
   h.querySelector('b').textContent=smoney(tot);h.querySelector('b').className=tot>=0?'up':'down';h.querySelector('small').textContent=sum;},
  tap:i=>barSheet(bars[i])};
 return `<h2>Profit by ${S.plr}</h2><div class="chart plc"><div class="plh"><div><b class="${tot>=0?'up':'down'}">${smoney(tot)}</b><small>${sum}</small></div>${sw}</div>
  <div class="scrub" data-scrub="pl"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="0" y1="${mid}" x2="${W}" y2="${mid}" stroke="var(--line)" vector-effect="non-scaling-stroke"/>
  ${bars.map((b,i)=>{const h=Math.max(2,Math.abs(b.pl)/mx*(mid-8));return `<rect class="brc" x="${(i+.5)*W/n-bw/2}" y="${b.pl>=0?mid-h:mid}" width="${bw}" height="${h}" rx="4" fill="${b.pl>=0?'var(--yes)':'var(--no)'}"/>`;}).join('')}</svg></div>
  <div class="xl"><span>${esc(bars[0].lab)}</span><span>${n>1?esc(bars[n-1].lab):''}</span></div><div class="hint">Drag across the bars, or tap one to see its bets.</div></div>`;}
function barSheet(b){if(!b)return;const xs=b.items||[];
 const sd=d=>{if(!d)return '';const x=new Date(d+'T12:00:00');return x.toLocaleDateString([], {month:'short',day:'numeric'});};
 /* Issue #91: the bars group by when the money moved. Show the buy date and the cash-out/settlement date so the grouping explains itself. */
 const when2=h=>{const cd=h.cashed?(h.status==='cashed'?'Cashed out ':'Settled ')+sd(h.cashed):'';const bd=h.bought?'Bought '+sd(h.bought):'';return bd&&cd?bd+' · '+cd:bd||cd;};
 modal(`<h3>${esc(b.lab)}</h3><p><b class="${b.pl>=0?'up':'down'}">${smoney(b.pl)}</b> on ${b.n} bet${b.n===1?'':'s'}</p>
  <div class="blist">${xs.map(h=>`<div class="hrow2"><div class="hd2"><span class="hs">${(h.sports||[]).map(s=>ICON[s]||'').join('')||'🎲'}</span><b>${esc((h.picks||[]).map(short).slice(0,3).join(' + '))}${(h.picks||[]).length>3?' +'+((h.picks||[]).length-3):''}</b><span class="verdict ${h.status}" style="margin-left:auto">${h.status==='won'?'RODE IT':h.status==='cashed'?'CASHED':'LOST'}</span></div>
   ${when2(h)?`<div class="m" style="font-size:12px;margin:2px 0 4px">${esc(when2(h))}</div>`:''}<div class="hn"><span>Paid <b>${money(h.cost)}</b></span><span>Got back <b>${money(h.back)}</b></span><span>Result <b style="color:${h.pl>=0?'var(--yes)':'var(--no)'}">${smoney(h.pl)}</b></span></div></div>`).join('')||'<div class="m">The bet-by-bet detail for this one is older than the history kept here.</div>'}</div>
  <div class="row"><button class="btn acc" onclick="closeModal()">Done</button></div>`);}
try{S.hf=Object.assign({sport:'all',res:'all',when:'all',sort:'new'},JSON.parse(localStorage.getItem('cw_hf')||'{}'))}catch(e){S.hf={sport:'all',res:'all',when:'all',sort:'new'}}
function hset(k,v){hap();S.hf[k]=v;try{localStorage.setItem('cw_hf',JSON.stringify(S.hf))}catch(e){}renderResults();}
const RESN={won:'Rode it and won',cashed:'Cashed out early',lost:'Lost'};
function historyBlock(all){const f=S.hf;const today=new Date();const iso=d=>d.toISOString().slice(0,10);
 const since=f.when==='7'?iso(new Date(Date.now()-7*864e5)):f.when==='30'?iso(new Date(Date.now()-30*864e5)):f.when==='month'?iso(new Date(today.getFullYear(),today.getMonth(),1)):'';
 const sports=[...new Set(all.flatMap(h=>h.sports||[]))].sort();
 let xs=all.filter(h=>(f.sport==='all'||(h.sports||[]).includes(f.sport))&&(!since||(h.day||'')>=since)
  &&(f.res==='all'||(f.res==='profit'?h.pl>0:f.res==='loss'?h.pl<=0:h.status===f.res)));
 xs=xs.slice().sort(f.sort==='old'?(a,b)=>(a.day||'').localeCompare(b.day||''):f.sort==='best'?(a,b)=>b.pl-a.pl:f.sort==='worst'?(a,b)=>a.pl-b.pl:(a,b)=>(b.day||'').localeCompare(a.day||''));
 const chip=(k,v,l)=>`<button class="chip ${f[k]===v?'on':''}" onclick="hset('${k}','${v}')">${l}</button>`;
 const pl=xs.reduce((a,h)=>a+h.pl,0),staked=xs.reduce((a,h)=>a+h.cost,0);
 const dlab=d=>{if(!d)return '';const x=new Date(d+'T12:00:00');return x.toLocaleDateString([], {month:'short',day:'numeric'})+(x.getFullYear()!==today.getFullYear()?' '+x.getFullYear():'');};
 return `<h2>History <span class="n">${xs.length}${xs.length!==all.length?' of '+all.length:''}</span></h2>
  <div class="hfilters"><div class="chips">${chip('sport','all','All sports')}${sports.map(s=>chip('sport',s,(ICON[s]||'')+' '+(SPN[s]||s.toUpperCase()))).join('')}</div>
   <div class="chips">${chip('res','all','Any result')}${chip('res','won','🏁 Rode it, won')}${chip('res','cashed','💸 Cashed early')}${chip('res','lost','✕ Lost')}${chip('res','profit','Made money')}${chip('res','loss','Lost money')}</div>
   <div class="chips">${chip('when','all','All time')}${chip('when','7','Last 7 days')}${chip('when','30','Last 30 days')}${chip('when','month','This month')}
    <select class="hsort" onchange="hset('sort',this.value)">${[['new','Newest first'],['old','Oldest first'],['best','Biggest win'],['worst','Biggest loss']].map(([v,l])=>`<option value="${v}" ${f.sort===v?'selected':''}>${l}</option>`).join('')}</select></div></div>
  <div class="m" style="font-size:12.5px;margin:2px 2px 10px">${xs.length} combo${xs.length===1?'':'s'} · ${money(staked)} paid · <b class="${pl>=0?'up':'down'}">${smoney(pl)}</b>${staked?` (${pl>=0?'+':''}${Math.round(pl/staked*100)}%)`:''}</div>
  <div class="tbl">${xs.map(h=>`<div class="hrow2"><div class="hd2"><span class="hs">${(h.sports||[]).map(s=>ICON[s]||'').join('')||'🎲'}</span><b>${dlab(h.day)}</b><span class="m">${(h.sports||[]).map(s=>SPN[s]||s.toUpperCase()).join(' + ')} · ${h.picks.length} pick${h.picks.length===1?'':'s'}</span><span class="verdict ${h.status}" style="margin-left:auto">${h.status==='won'?'RODE IT':h.status==='cashed'?'CASHED':'LOST'}</span></div>
   <div class="legs">${h.picks.map(p=>`<span class="leg">${esc(short(p))}</span>`).join('')}</div>
   <div class="hn"><span>Paid <b>${money(h.cost)}</b></span><span>Got back <b>${money(h.back)}</b></span><span>Result <b style="color:${h.pl>=0?'var(--yes)':'var(--no)'}">${smoney(h.pl)}</b></span></div></div>`).join('')||'<div class="empty"><b>Nothing matches</b>Try fewer filters.</div>'}</div>`;}
function proofCard(p){if(!p)return '';const row=(lab,c,fmt)=>c?`<div class="mini">${lab}<b>${fmt(c.mean)} <span class="m" style="font-weight:500">(${fmt(c.lo)} to ${fmt(c.hi)}, ${c.n})</span></b></div>`:`<div class="mini">${lab}<b class="m">not enough yet</b></div>`;
 const pc=x=>(x>=0?'+':'−')+Math.abs(x*100).toFixed(1)+'%';
 return `<div class="card" style="border-color:${p.tone==='good'?'color-mix(in srgb,var(--yes) 50%,transparent)':p.tone==='bad'?'color-mix(in srgb,var(--no) 50%,transparent)':'var(--line)'}"><h3>Is it working? <span>95% ranges</span></h3>
  <p style="margin:0 0 10px;color:var(--ink)">${esc(p.verdict)}</p>${row('Return on stake',p.roi,pc)}${row('Prices vs kickoff',p.clv,pc)}${row('Paper auto-trading',p.paper,pc)}
  <div class="m" style="font-size:12px;margin-top:8px">The $300 full-auto test waits for prices vs kickoff to be positive with confidence and the paper record to be up over 50+ bets.</div></div>`;}
function coverCard(c){if(!c)return '';const ws=c.weeks||[];
 const chk=w=>(w.checkpoints||[]).map(cp=>`<span class="m" style="font-size:11.5px">${esc(cp.label)}: ${cp.worth?money(cp.worth):'—'}${cp.replay_exit?` · sold ${money(cp.replay_exit.exit)}`:''}</span>`).join(' · ');
 const week=w=>{
  if(w.status==='done'){const surv=(w.survivor||[]).join(' + ')||'—';
   return `<div class="mini" style="align-items:flex-start;flex-direction:column;gap:3px"><div style="display:flex;width:100%;align-items:baseline"><span>${esc(w.sunday)} · ${w.k} covered · survivor ${esc(surv)}</span><b class="${w.sim_pl>=0?'up':'down'}" style="margin-left:auto">${smoney(w.sim_pl)} <span class="m" style="font-weight:500">of ${money(w.cost_both)}</span></b></div>`
    +`<div class="m" style="font-size:11.5px">${w.beat_cost?'✅ smart sell beat the doubled cost':'✕ smart sell did not beat the doubled cost'}${chk(w)?' · '+chk(w):''}</div>`
    +`<div class="m" style="font-size:11.5px">One favourite-side combo on the same early games (highest Kalshi price — a rough proxy; the real panel picks by edge and often takes the underdog): <b class="${w.one_sided_pl>=0?'up':'down'}" style="font-weight:600">${smoney(w.one_sided_pl)}</b></div></div>`;}
  if(w.status==='open')return `<div class="mini">${esc(w.sunday)} · ${w.k} games · waiting for results<b class="m">${pct(w.p_ahead)} chance to be ahead</b></div>`;
  return `<div class="mini">${esc(w.sunday)}<b class="m">${w.status==='missed'?'missed (Mac was off before kickoff)':'no result'}</b></div>`;};
 const rows=ws.slice(0,8).map(week).join('');
 return `<div class="card"><h3>Cover the early games <span>paper test · NFL week</span></h3>
  ${c.n?`<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:8px"><b style="font-size:30px;letter-spacing:-.03em" class="${c.sim_pl>=0?'up':'down'}">${smoney(c.sim_pl)}</b><span class="m">over ${c.n} week${c.n===1?'':'s'}, ${money(c.cost)} on paper · one-sided ${smoney(c.one_sided_pl)} · beat the cost ${c.beat}/${c.n}</span></div>`:''}
  ${rows||'<div class="m">Starts this NFL week: the Mac covers both sides of the earliest games (Thursday night, Saturday, or Sunday early) before kickoff, then works out what the one surviving full-slate combo would be worth at each later checkpoint and what smart sell would have sold it for.</div>'}
  <div class="m" style="font-size:12px;margin-top:8px">$5 on both sides of the earliest games — one combo is guaranteed to survive — carried through the later games, with smart sell deciding the exit. No money is spent. Covering both sides adds no expected value (the cut is paid twice); the test measures whether smart sell's exit timing beats the doubled cost.</div></div>`;}
function gateCard(r){if(!r)return '';const pp=r.paper||{},rr=r.real||{};const need=Math.max(0,50-pp.bets);
 return `<div class="card"><h3>Is it working? <span>the daily panel</span></h3>
  <div class="m" style="font-size:12.5px;margin-bottom:8px">A paper copy of each day's panel runs by itself, with no money. When it's ahead over 50+ bets and most days end up, it's ready to be handed $300.</div>
  <div class="mini">Paper panel<b class="${pp.pl>=0?'up':'down'}">${smoney(pp.pl||0)} <span class="m" style="font-weight:500">${pp.bets} bets · ${pp.days_up}/${pp.days} days up</span></b></div>
  <div class="mini">Your real panel<b class="${rr.pl>=0?'up':'down'}">${smoney(rr.pl||0)} <span class="m" style="font-weight:500">${rr.bets} bets</span></b></div>
  <div style="margin-top:10px;padding:10px 12px;border-radius:10px;background:var(--panel2);font-size:13px">${pp.ready?'✅ <b>Ready.</b> The paper record clears the bar for running it with $300 on its own.':`⏳ <b>Not yet.</b> ${need?need+' more paper bets to go':'Needs to be ahead, with most days up'}.`}</div></div>`;}
function anBlock(a){if(!a||!a.at)return `<div class="card an"><div class="anh"><h2 style="margin:0">📊 What's working</h2></div>${a?'<div class="m" style="padding:6px 0 4px">Nothing to measure yet. Results show up as bets settle.</div>':'<div class="ansk" aria-label="Loading"><i style="height:34px;border-radius:10px"></i><i style="width:84%"></i><i></i><i style="width:92%"></i><i style="width:70%"></i></div>'}</div>`;
 const tab=S.anTab||'levels';const r=x=>x==null?'—':`<b class="${x>=0?'up':'down'}">${x>=0?'+':'−'}${Math.abs(Math.round(x*100))}%</b>`;
 const tabs=[['levels','Combo price levels'],['types','Bet types'],['sports','Sports'],['exits','Selling']];
 const tb=`<div class="seg ant">${tabs.map(([k,l])=>`<button class="${tab===k?'on':''}" onclick="anTab('${k}')">${l}</button>`).join('')}</div>`;
 const table=(head,rows)=>`<div class="antbl"><div class="anrow h">${head.map(h=>`<div>${h}</div>`).join('')}</div>${rows.map(cs=>`<div class="anrow">${cs.map((c,i)=>`<div data-l="${i?esc(head[i]):''}">${c}</div>`).join('')}</div>`).join('')||'<div class="m" style="padding:10px 0">No settled bets here yet.</div>'}</div>`;
 const mode=m=>m==='real'?'<span class="tag good">Real</span>':'<span class="tag">Paper</span>';
 let body='',expl='';
 if(tab==='levels'){expl='Every combo Kalshi has quoted (last 90 days), as if bought at that price. "% of fair" is what Kalshi pays compared to the fair payout. The lab paper-buys 3 a day in each band from 80% up, and replays smart sell on their game prices.';
  body=table(['% of fair','Quotes','Hit vs expected','Riding to end','Worth at game time','Lab: ride · smart sell'],(a.levels||[]).map(x=>[`<b>${esc(x.band)}</b>`,x.n,x.hit==null?'—':pct(x.hit)+' <span class="m">vs '+pct(x.exp)+'</span>',r(x.ride),r(x.gt)+(x.gt_n?` <span class="m">(${x.gt_n})</span>`:''),x.lab_n?`${r(x.lab_ride)} · ${r(x.lab_smart)} <span class="m">(${x.lab_n})</span>`:'<span class="m">—</span>']));}
 else if(tab==='types'||tab==='sports'){expl=tab==='types'?'Every settled panel bet, real and paper (the paper panel and the combo lab). Return is profit over what was staked. Smart sell is the replay on recorded game prices, where there are enough of them. CLV: how the price you got compares with Kalshi\'s price right before the game. Positive means the market moved your way.':'The same bets, by sport.';
  body=table([tab==='types'?'Bet type':'Sport','Bets','Won','Return','Smart sell','CLV'],(a[tab]||[]).map(x=>[`<b>${esc(x.what)}</b> ${mode(x.mode)}`,x.n,x.n?Math.round(x.won/x.n*100)+'%':'—',r(x.roi),x.sim_n?r(x.smart):'<span class="m">—</span>',x.clv==null?'—':r(x.clv)]));
  if(tab==='types')body+=`<h3 class="an-live" style="margin:18px 0 4px;font-size:15px">Bought during the game, by league</h3><div class="m" style="font-size:12.5px;margin-bottom:6px">Panel bets on games already under way, priced live from a fresh score and clock. Kept apart so each league's record can show whether they pay. ${esc(a.live_excluded||'')}</div>`
   +table(['League','Bets','Won','Return','Smart sell'],(a.live||[]).map(x=>[`<b>${esc(x.what)}</b> ${mode(x.mode)}`,x.n,x.n?Math.round(x.won/x.n*100)+'%':'—',r(x.roi),x.sim_n?r(x.smart):'<span class="m">—</span>']));}
 else{expl='Your real combos in the last 90 days: ridden to the end vs cashed out early, and what automatic selling did in the last 30 days.';
  const au=a.auto||{};const an=Object.keys(au);const ch=a.cut_held||{};const cn=Object.keys(ch);const hh=a.hedge_held||{};const hn=Object.keys(hh);
  body=table(['How it ended','Combos','Profit','Return'],(a.exits||[]).map(x=>[`<b>${esc(x.what)}</b>`,x.n,smoney(x.pl),r(x.roi)]))
   +`<div class="m" style="margin-top:10px;font-size:13px">${an.length?'Automatic sales, last 30 days: '+an.map(k=>`<b>${au[k]}</b> ${esc(k)}`).join(' · '):'No automatic sales in the last 30 days.'}</div>`
   +`<div class="m cut-held" style="margin-top:6px;font-size:13px">${cn.length?'Loss cuts the guards held back, last 30 days: '+cn.map(k=>`<b>${ch[k]}</b> ${esc(k)}`).join(' · '):'No loss cut has been held back by the guards in the last 30 days.'}</div>`
   +`<div class="m hedge-held" style="margin-top:6px;font-size:13px">${hn.length?'Auto-hedges the guards held back, last 30 days: <b>'+hn.reduce((s,k)=>s+hh[k],0)+'</b> ('+hn.map(k=>`${hh[k]} ${esc(k)}`).join(' · ')+')':'No auto-hedge has been held back by the guards in the last 30 days.'} <span style="opacity:.8">Auto-hedge only buys on a fresh live score, never at a break, when it locks in at least what you paid, after 3+ minutes, at a re-checked price.</span></div>`
   +`<h3 style="margin:18px 0 4px;font-size:15px">Smart sell, tuned by league</h3><div class="m" style="font-size:12.5px;margin-bottom:6px">Every week the Mac replays settled bets on their recorded game prices with slightly different settings and keeps whatever did clearly better: small steps, 30+ results a league, never below what you paid unless a league's own record says cutting a loss pays, and even then only late in a game, on a fresh score, not at a break, after a big fall that held 3+ minutes. Leagues without enough results use their sport's settings, then everyone's (but never borrow a loss cut).</div>`
   +table(['League','Profit floor','Risk weight','Cut losses','Bets'],(a.tuning||[]).map(x=>[`<b>${esc(x.name)}</b>${x.own?'':' <span class="m">(learning)</span>'}${x.why?`<div class="m" style="font-size:11.5px;font-weight:500;margin-top:2px">${esc(x.why)}</div>`:''}<div class="m sl-row" style="font-size:11.5px;margin-top:2px">Selling at a loss (a learned cut, or the stop-loss switch if on): only after ${pct(x.sl_prog==null?0.5:x.sl_prog)} of the game, a ${Math.round((x.sl_drop==null?0.2:x.sl_drop)*100)}-point fall from before the game, held 3+ min, on a fresh score, never at a break${x.sl_own?'':' (starting point)'}</div>${x.sl_why?`<div class="m" style="font-size:11.5px;font-weight:500;margin-top:2px">${esc(x.sl_why)}</div>`:''}`,x.floor+'×',x.lam===1?'standard':x.lam<1?'holds longer':'sells sooner',x.loss?'under '+pct(x.loss)+'<div class="m" style="font-size:11px">late, confirmed</div>':'never',x.n]));}
 const notes=(a.notes||[]).map(n=>`<li>${esc(n)}</li>`).join('');
 return `<div class="card an"><div class="anh"><h2 style="margin:0">📊 What's working</h2><span class="m" style="font-size:12px">updated ${ago2(a.at)==='now'?'just now':ago2(a.at)+' ago'}</span></div>${tb}
  ${notes?`<ul class="annotes">${notes}</ul>`:''}<div class="${S.anJust?'antab':''}"><div class="m" style="font-size:12.5px;margin:4px 0 10px;line-height:1.45">${expl}</div>${body}</div></div>`;}
function anTab(k){if(S.anTab===k)return;S.anTab=k;S.anJust=true;renderResults();S.anJust=false;
 if(!matchMedia('(prefers-reduced-motion: reduce)').matches)document.querySelectorAll('.an .antbl .anrow').forEach((r,i)=>{r.style.animation=`rise .34s var(--ease) ${Math.min(i,12)*30}ms both`;});}
function edgeBlock(d){const e=d.edge||{};const out=[];out.push(gateCard(d.panel));if(d.proof)out.push(proofCard(d.proof));out.push(coverCard(d.cover));
 const clv=e.clv||[0,0,0];
 if(clv[2]){const g=clv[1]/clv[0]-1;out.push(`<div class="card"><h3>Your prices vs kickoff <span>${clv[2]} combos</span></h3>
  <div style="display:flex;align-items:baseline;gap:12px"><b style="font-size:30px;letter-spacing:-.03em" class="${g>=0?'up':'down'}">${g>=0?'+':'−'}${Math.abs(g*100).toFixed(1)}%</b>
  <span class="m">You paid ${money(clv[0])} for combos the market valued at ${money(clv[1])} at kickoff.</span></div>
  <div class="m" style="font-size:12.5px;margin-top:6px">Above 0% means you buy better than the market's final price: the earliest reliable sign of a real edge, long before wins and losses settle it.</div></div>`);}
 const cal=Object.entries(e.cal||{}).filter(([k,v])=>v[0]);
 if(cal.length)out.push(`<div class="card"><h3>Did combos hit as often as priced? <span>settled</span></h3><div class="bars2">${cal.map(([k,[n,ps,h]])=>{const ex=ps/n,hit=h/n,mx=Math.max(.05,...cal.map(([,v])=>Math.max(v[1]/v[0],v[2]/v[0])));
  return `<div class="br"><span>${esc(k)} <span class="m">· ${n}</span></span><div style="display:grid;gap:3px"><div class="tr2"><i style="left:0;width:${ex/mx*100}%;background:var(--mute);opacity:.6"></i></div><div class="tr2"><i style="left:0;width:${hit/mx*100}%;background:${hit>=ex?'var(--yes)':'var(--no)'}"></i></div></div><span class="num">${pct(ex)} → <b>${pct(hit)}</b></span></div>`;}).join('')}</div>
  <div class="key" style="margin-top:8px"><span><i style="background:var(--mute)"></i>Priced</span><span><i style="background:var(--yes)"></i>Actually hit</span></div></div>`);
 const bt=(d.by_tier||[]);
 if(bt.length){const mx=Math.max(1,...bt.map(r=>Math.abs(r.back-r.cost)));out.push(`<div class="card"><h3>Returns by number of picks <span>settled</span></h3><div class="bars2">${bt.map(r=>{const pl=r.back-r.cost;
  return `<div class="br"><span>${esc(r.k)} <span class="m">· ${r.n}</span></span><div class="tr2"><i style="${pl>=0?'left:50%':'right:50%'};width:${Math.abs(pl)/mx*50}%;background:${pl>=0?'var(--yes)':'var(--no)'}"></i></div><span class="num ${pl>=0?'up':'down'}">${smoney(pl)}</span></div>`;}).join('')}</div></div>`);}
 const md=d.model;
 if(md){out.push(`<div class="card"><h3>How Kalshi prices combos <span>${md.n} quotes</span></h3>
  <div class="m" style="font-size:12.5px;margin-bottom:8px">Kalshi's combo quote as a share of what its own single-game prices multiply out to. Learned from every quote the Mac sees; Build uses it to predict prices before asking.</div>
  <div class="bars2">${Object.entries(md.by_picks||{}).sort((a,b)=>parseInt(a[0])-parseInt(b[0])).map(([k,v])=>`<div class="br"><span>${esc(k)} pick${k==='1'?'':'s'}</span><div class="tr2"><i style="left:0;width:${Math.min(100,v*100)}%;background:var(--acc)"></i></div><span class="num">${pct(v)}</span></div>`).join('')}
  ${Object.entries(md.by_time||{}).map(([k,v])=>`<div class="br"><span>${esc(k)} to game</span><div class="tr2"><i style="left:0;width:${Math.min(100,v*100)}%;background:var(--live)"></i></div><span class="num">${pct(v)}</span></div>`).join('')}</div></div>`);}
 const b=d.backtest;
 if(b&&b.quotes){const rows=b.rows.filter(r=>r.n);const mx=Math.max(1,...rows.map(r=>Math.abs(r.pl)));const cut=(S.set&&S.set.values&&S.set.values.accept_pct)||null;
  out.push(`<div class="card"><h3>What each cut-off would have earned <span>${b.quotes} settled quotes</span></h3>
  <div class="m" style="font-size:12.5px;margin-bottom:8px">Every quote Kalshi gave (yours and the Mac's paper trades), bought only if it cleared that share of fair, settled with the real results.</div>
  <div class="bars2">${rows.map(r=>`<div class="br"><span>${r.cut}%+ <span class="m">· ${r.n}</span></span><div class="tr2"><i style="${r.pl>=0?'left:50%':'right:50%'};width:${Math.abs(r.pl)/mx*50}%;background:${r.pl>=0?'var(--yes)':'var(--no)'}"></i></div><span class="num ${r.pl>=0?'up':'down'}">${smoney(r.pl)}</span></div>`).join('')}</div></div>`);}
 if(out.length<=1&&!(d.proof&&(d.proof.roi||d.proof.clv)))return (out[0]||'')+`<div class="card"><h3>Your edge</h3><div class="m">Fills in as combos settle and the Mac records Kalshi's quotes: prices vs kickoff, how often combos hit vs their price, returns by number of picks, and a back-test of your fair-price cut-off.</div></div>`;
 return `<h2>Your edge</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,380px),1fr));gap:14px;align-items:start">${out.join('')}</div>`;}
function blockRow(b){if(!b||!b.length)return '';return b.map(x=>{const until=new Date(x.until*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});return `<div class="srow"><div class="l"><b>Order block: ${esc(x.ticker)} · ${x.sell?'sell ':''}${esc(x.side)}</b><small>An order here had no clear answer, so the app sends none on it until ${esc(until)}. Check Kalshi first; the unclear order itself is never resent.</small></div><button class="btn ghost" data-k="${esc(x.key)}" onclick="clearBlock(this)">Clear order block</button></div>`}).join('');}
function clearBlock(b){hap('warning');if(!confirm('Clear this order block? Only do this after checking Kalshi: new orders on this market can go again.'))return;btnBusy(b);api('/app/api/act',{a:'clear_block',key:b.dataset.k}).then(r=>{toast(r.msg,5000);btnState(b,!!r.ok);setTimeout(()=>load('settings'),1200)}).catch(()=>btnState(b,false));}
function skimRow(k){if(!k||!k.reserved)return '';return `<div class="srow"><div class="l"><b>Profit set aside</b><small>${money(k.reserved)} isn't bet with. Move it out of Kalshi, then tap here.</small></div><button class="btn ghost" onclick="const b=this;btnBusy(b);api('/app/api/act',{a:'skim_moved'}).then(r=>{toast(r.msg,5000);btnState(b,!!r.ok);setTimeout(()=>load('settings'),1200)}).catch(()=>btnState(b,false))">I moved it</button></div>`;}
function cutCard(cs){if(!cs||!cs.length)return `<div class="srow"><div class="l"><b>Panel combo cut-off</b><small>Starts at 95% of fair for every sport and size, and adjusts itself weekly from results (never below 85%).</small></div><b>95%</b></div>`;
 return `<div class="srow" style="display:block"><div class="l"><b>Panel combo cut-off</b><small>Adjusts itself weekly from results; never below 85%.</small></div>${cs.map(c=>`<div class="mini" style="margin-top:6px">${esc(c.group.replace(':',' · ')+' picks')}<b>${c.level}%</b></div>${c.why?`<div class="m" style="font-size:11.5px">${esc(c.why)}</div>`:''}`).join('')}</div>`;}
function fidRow(){const f=S.fid||{};const here=(f.keys||[]).filter(k=>k.rp===location.hostname);
 if(LOCAL&&!/\.ts\.net$/.test(location.hostname))return (f.keys||[]).length?`<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${f.keys.map(k=>esc(k.name)).join(', ')}</small></div><button class="btn ghost" onclick="fidRemoveAll()">Remove all</button></div>`:'';
 if(location.protocol!=='https:'||!window.PublicKeyCredential)return `<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${(S.pk||{}).https?`Works on the secure address. Open <a href="${esc(S.pk.https)}">${esc(S.pk.https.replace('https://',''))}</a> and turn it on there.`:'Needs the Mac\'s secure address first (Settings › This Mac on the Mac).'}</small></div></div>`;
 return `<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${here.length?`On for ${here.map(k=>esc(k.name)).join(', ')}. Unlock Combo Hub with your face instead of the passcode.`:((f.keys||[]).length?`Face ID was set up for another address (${esc((f.keys[0]||{}).rp||'')}). Turn it on again here to use it on this one.`:'Unlock Combo Hub with Face ID instead of typing the passcode.')}</small></div>
  ${here.length?`<button class="btn ghost" onclick="fidRemoveAll()">Turn off</button>`:`<button class="btn acc" onclick="fidOn(this)">Turn on</button>`}</div>`;}
const fb64=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
const fe64=a=>btoa(String.fromCharCode(...new Uint8Array(a))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
async function fidOn(btn){hap();try{if(btn)btn.innerHTML='<span class="spin"></span>';
  const o=await api('/auth/reg-begin',{});const name=/iPhone/.test(navigator.userAgent)?'iPhone':/iPad/.test(navigator.userAgent)?'iPad':/Mac/.test(navigator.userAgent)?'Mac':'This device';
  const c=await navigator.credentials.create({publicKey:{challenge:fb64(o.challenge),rp:{id:o.rp,name:'Combo Hub'},user:{id:fb64(o.user),name:'Combo Hub',displayName:'Combo Hub'},
   pubKeyCredParams:[{type:'public-key',alg:-7}],authenticatorSelection:{authenticatorAttachment:'platform',residentKey:'preferred',userVerification:'required'},
   excludeCredentials:o.exclude.map(id=>({type:'public-key',id:fb64(id)})),attestation:'none',timeout:60000}});
  const r=await api('/auth/reg-finish',{clientDataJSON:fe64(c.response.clientDataJSON),attestationObject:fe64(c.response.attestationObject),name});
  hap(r.ok?'success':'error');toast(r.ok?'Face ID is on. Next time, just look at your phone to unlock.':(r.msg||'Couldn\'t turn it on.'),5000,r.ok?'good':'bad');
 }catch(e){toast(e&&e.name==='NotAllowedError'?'Cancelled.':e&&e.name==='InvalidStateError'?'Face ID is already on for this device.':'Couldn\'t turn it on: '+(e&&e.message||e),5000);}
 await fidLoad();if(S.view==='settings')renderSettings();}
async function fidLoad(){S.fid=await api('/auth/list',{}).catch(()=>({keys:[]}));}
async function fidRemoveAll(){const here=(S.fid.keys||[]).filter(k=>LOCAL&&!/\.ts\.net$/.test(location.hostname)||k.rp===location.hostname);
 for(const k of here)await api('/auth/remove',{id:k.id});toast('Face ID sign-in turned off.');await fidLoad();renderSettings();}
function pushRow(){const pk=S.pk||{};const can='serviceWorker' in navigator&&'PushManager' in window;
 if(location.protocol!=='https:'&&location.hostname!=='localhost')return `<div class="srow"><div class="l"><b>Notifications on this device</b><small>${pk.https?`Needs the secure address. Open <a href="${esc(pk.https)}">${esc(pk.https.replace('https://',''))}</a>, add that to your Home Screen, and turn them on there.`:'Needs the Mac\'s secure address first (Settings › This Mac on the Mac).'}</small></div></div>`;
 if(!can)return `<div class="srow"><div class="l"><b>Notifications on this device</b><small>On iPhone: open Combo Hub from its Home Screen icon (Share › Add to Home Screen), then turn them on here.</small></div></div>`;
 return `<div class="srow"><div class="l"><b>Notifications on this device</b><small>${S.pushOn?'On. Alerts from the Mac open the right screen when tapped.':'Get the Mac\'s alerts here, straight from Combo Hub.'}${pk.n?` · ${pk.n} device${pk.n>1?'s':''} signed up`:''}</small></div>
  ${S.pushOn?`<button class="btn" onclick="pushTest(this)">Send test</button><button class="btn ghost" onclick="pushOff()">Turn off</button>`:`<button class="btn acc" onclick="pushOn(this)">Turn on</button>`}</div>`;}
function urlB64(s){const p='='.repeat((4-s.length%4)%4);const b=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...b].map(c=>c.charCodeAt(0)));}
async function pushOn(btn){try{const perm=await Notification.requestPermission();
  if(perm!=='granted'){toast('Notifications are blocked. Allow them in Settings › Notifications › Combo Hub.',6000);return;}
  if(btn)btn.innerHTML='<span class="spin"></span>';
  const k=await api('/app/push',{a:'key'});if(!k.ok){toast('The Mac is still updating. Try again in a few minutes.');return;}
  const reg=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;
  const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlB64(k.key)});
  await api('/app/push',{a:'sub',sub:sub.toJSON(),label:/iPhone/.test(navigator.userAgent)?'iPhone':'Browser'});
  const t=await api('/app/push',{a:'test'});S.pushOn=true;toast(t.sent?'Notifications are on. A test is on its way.':'Signed up. The test didn\'t go through yet.',5000);load('settings');
 }catch(e){toast('Couldn\'t turn them on: '+(e&&e.message||e),6000);load('settings');}}
async function pushTest(b){btnBusy(b,'Sending…');const t=await api('/app/push',{a:'test'}).catch(()=>({}));btnState(b,!!t.sent,t.sent?'Sent':'Not sent');toast(t.sent?'Sent. It should arrive in a few seconds.':'Nothing sent. Try turning it off and on.');}
async function pushOff(){try{const reg=await navigator.serviceWorker.getRegistration();const sub=reg&&await reg.pushManager.getSubscription();if(sub){await api('/app/push',{a:'off',sub:sub.toJSON()});await sub.unsubscribe();}}catch(e){}S.pushOn=false;toast('Notifications off on this device.');load('settings');}
function httpsRow(mac){const h=mac.https||{};
 if(h.state==='on')return `<div class="srow"><div class="l"><b>Secure address</b><small><a href="${esc(h.url)}" target="_blank">${esc(h.url.replace('https://',''))}</a> · use this on your iPhone for notifications</small></div><button class="btn ghost" onclick="navigator.clipboard.writeText('${esc(h.url)}').then(()=>toast('Copied'))">Copy</button></div>`;
 if(h.state==='need-enable'&&h.link)return `<div class="srow"><div class="l"><b>Secure address: one step</b><small>HTTPS certificates are not enabled in Tailscale admin yet. Tap Allow https, approve in the Tailscale page, then tap Check (it also checks itself every few minutes).</small></div><a class="btn acc" href="${esc(h.link)}" target="_blank">Allow https</a><button class="btn" onclick="macDo('https',this)">Check</button></div>`;
 if(h.state==='need-enable')return `<div class="srow"><div class="l"><b>Secure address: one step</b><small>HTTPS certificates are not enabled in Tailscale admin. Open the page, sign in, scroll to <b>HTTPS Certificates</b>, tap <b>Enable HTTPS...</b> and confirm. Then tap Check (it also checks itself every few minutes).</small></div><a class="btn acc" href="${esc(h.admin||'https://login.tailscale.com/admin/dns')}" target="_blank">Open Tailscale admin</a><button class="btn" onclick="macDo('https',this)">Check</button></div>`;
 const why={'no-cli':'Tailscale\'s command line isn\'t available on this Mac. Install the Tailscale app, then Try again.',
  'no-status':'Couldn\'t read Tailscale\'s status. Open the Tailscale app on this Mac, then Try again.',
  'no-daemon':'Couldn\'t read Tailscale\'s status: the command line can\'t talk to the Tailscale app. Open Tailscale on this Mac, check it says Connected, then Try again.',
  'cli-broken':'Couldn\'t read Tailscale\'s status: its command line wouldn\'t start from the watcher. Install the command line from Tailscale\'s settings, then Try again.',
  'signed-out':'Tailscale says this Mac is signed out. Open Tailscale, sign in, then Try again.',
  'needs-approval':'This Mac waits for approval in Tailscale admin (login.tailscale.com/admin/machines). Approve it, then Try again.',
  'ts-off':'Tailscale is switched off on this Mac. Open Tailscale, turn it on, then Try again.',
  'starting':'Tailscale is still starting on this Mac. It checks again by itself in a few minutes.',
  'no-name':'Tailscale is running but gave this Mac no name. Turn MagicDNS on at login.tailscale.com/admin/dns, then Try again.',
  'issuing':'Tailscale is still making the certificate. This can take a few minutes; it keeps checking.'};
 if(h.detail&&['no-cli','no-status','no-daemon','cli-broken','signed-out','needs-approval','ts-off','starting'].includes(h.state))why[h.state]=esc(h.detail.slice(0,300));
 return `<div class="srow"><div class="l"><b>Secure address</b><small>${why[h.state]||(h.state?'Not on yet ('+esc(h.state)+')'+(h.detail?': '+esc(h.detail.slice(-140)):''):'Checking…')}</small></div><button class="btn" onclick="macDo('https',this)">Try again</button></div>`;}
function killerCard(k){if(!k)return '';const r=k.rules||{};const M={off:'Off',watch:'Watch only',on:'Buy automatically'};
 const rows=(k.rows||[]).slice(0,6).map(x=>`<div class="moment"><span class="k">${x.status==='bought'?'🔥':x.status==='watched'?'👀':'⏭'}</span><span><b>${esc(x.picks)}</b> <span class="m">${pct(x.pct)} of fair · ${money(x.stake)} → ${money(x.pays)} · ${esc(x.status)}${x.outcome?' · '+x.outcome:''}</span></span><time>${ago2(x.ts)}</time></div>`).join('');
 return `<div class="srow"><div class="l"><b>Killer deals</b><small>The Mac buys only deals that pass every check below, at most ${r.per_day||2} a day and ${money(r.day_dollars||20)} a day, inside your cap. Watch only records what it would have bought.</small></div>
  <div class="seg">${['off','watch','on'].map(m=>`<button class="${k.mode===m?'on':''}" onclick="killerMode('${m}')">${M[m]}</button>`).join('')}</div></div>
  <div class="srow" style="display:block"><div class="m" style="font-size:12.5px;line-height:1.6">
   Single game: ${Math.round((r.single_edge||.08)*100)}¢+ a contract and ${Math.round((r.single_rel||.15)*100)}%+ under fair, after the fee · Combo: Kalshi quote ${Math.round((r.combo_pct||1.15)*100)}%+ of fair, ${r.combo_legs||4} picks or fewer ·
   two odds sources agree within ${Math.round((r.agree||.02)*100)} points · line steady ${r.steady_mins||30} minutes · no injury news in ${r.news_hours||3} hours · enough for sale on Kalshi · games not started · up to ${money(r.per_buy||10)} each.</div>
   ${k.settled?`<div class="mini" style="margin-top:6px">Record so far<b class="${k.pl>=0?'up':'down'}">${smoney(k.pl)} on ${money(k.staked)} (${k.settled})</b></div>`:''}${rows?`<div style="margin-top:6px">${rows}</div>`:''}</div>`;}
function killerMode(m,sure){if(m==='on'&&!sure){modal(`<h3>Let the Mac buy killer deals?</h3><p>Only deals that pass every check, up to 2 a day and $20 a day, inside your cap. Every buy sends an alert with a Pause button.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();killerMode('on',true)">Turn on</button></div>`);return;}
 S.set.killer.mode=m;setv('killer_mode',m);renderSettings();toast(m==='on'?'Killer deals: the Mac buys them now. Pause from any alert.':m==='watch'?'Killer deals: watch only.':'Killer deals off.',5000);}
function singlesCard(d){const ss=d.singles||[];if(!ss.length)return '';
 if(S.sgView==='odds')return singlesOdds(ss);
 return `<div class="card"><h3>Single games <span>best prices</span></h3><div class="m" style="font-size:12px;margin:-4px 0 8px">Kalshi's price vs the sharp books' chance to win, after Kalshi's fee. No combo maker taking a cut.</div>
  ${ss.map(x=>`<div class="moment"><span class="k" style="color:${x.edge>=0.025?'var(--yes)':x.edge>0?'var(--sub)':'var(--mute)'}">${x.edge>=0.025?'🎯':'·'}</span><span><b>${esc(short(x.pick))}</b> <span class="m">vs ${esc(short(x.opp))} · ${Math.round(x.p*100)}¢ · fair ${pct(x.fair)}</span></span>
   ${x.idea?`<button class="btn acc" style="padding:6px 10px" onclick="singleFromBoard('${x.ticker}',this)">${(x.edge*100).toFixed(1)}¢ edge</button>`:`<b class="m" style="font-size:12px">${x.edge>=0?'+':'−'}${Math.abs(x.edge*100).toFixed(1)}¢</b>`}</div>`).join('')}
  ${ss.some(x=>x.idea)?'':'<div class="m" style="font-size:12px;margin-top:8px">Nothing at least 2.5¢ under fair right now: Kalshi is pricing these games in line with the sharp books. The Mac keeps checking every 10 minutes and alerts you when one opens up.</div>'}
  <button class="btn ghost" style="margin-top:10px;width:100%" onclick="S.sgView='odds';renderBuild()">Win and sell-early chances</button></div>`;}
function singlesOdds(ss){const rows=ss.slice().sort((a,b)=>b.win-a.win);
 return `<div class="card"><h3>Single games <span>win and sell-early</span></h3>
  <div class="m" style="font-size:12px;margin:-4px 0 8px">Per $1 contract: chance to win, what it profits if it wins, the chance its price is up 10¢ at some point (a chance to sell early at a profit), and the expected profit after Kalshi's fee.</div>
  <div class="sgt"><span></span><span>Win</span><span>Up 10¢</span><span>Expected</span>${rows.map(x=>`<b>${esc(short(x.pick))}<small class="m" style="display:block">${Math.round(x.p*100)}¢, wins +${Math.round(x.profit*100)}¢</small></b><span>${pct(x.win)}</span><span>${pct(x.touch)}</span><span class="${x.ev>=0?'up':'down'}">${x.ev>=0?'+':'−'}${Math.abs(x.ev*100).toFixed(1)}%</span>`).join('')}</div>
  <div class="m" style="font-size:12px;margin-top:8px">Read honestly: a likely winner pays little, and a price that's up 10¢ often comes back down. Selling early doesn't create profit on its own; the expected column is what you make on average, and it's only positive when Kalshi's price is below fair.</div>
  <button class="btn ghost" style="margin-top:10px;width:100%" onclick="S.sgView='';renderBuild()">Back to best prices</button></div>`;}
async function singleFromBoard(t,b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span>';}const r=await api('/app/api/act',{a:'singleidea',t}).catch(()=>({ok:false}));
 if(!r.ok){toast(r.msg||'Couldn\'t set that up.');renderBuild();return;}S.view='live';chrome();await load('live',true);S.hl=r.id;renderLive();await priceIdea(r.id);
 const e=document.getElementById('idea-'+r.id);if(e)e.scrollIntoView({behavior:'smooth',block:'center'});}
function makerCard(k){if(!k)return '';const r=k.rules||{};const M={off:'Off',watch:'Watch only',on:'Place orders'};
 const rows=(k.recent||[]).slice(0,6).map(x=>`<div class="moment"><span class="k">${x.status==='filled'?'✅':x.status==='posted'?'📌':x.status==='watching'?'👀':'⏹'}</span><span><b>${esc(short(x.pick))}</b> <span class="m">${x.n} at ${Math.round(x.price*100)}¢ · fair ${pct(x.fair)} · ${esc(x.status)}${x.outcome?' · '+x.outcome:''}${x.why?' · '+esc(x.why):''}</span></span><time>${ago2(x.ts)}</time></div>`).join('');
 return `<div class="srow"><div class="l"><b>Standing orders</b><small>The Mac keeps buy orders ${Math.round((r.discount||.03)*100)}¢ under the sharp books' chance, so you only buy when someone sells to you cheap. Watch only records what would have filled.</small></div>
  <div class="seg">${['off','watch','on'].map(m=>`<button class="${k.mode===m?'on':''}" onclick="makerMode('${m}')">${M[m]}</button>`).join('')}</div></div>
  <div class="srow" style="display:block"><div class="m" style="font-size:12.5px;line-height:1.6">Teams with a ${pct(r.min_fair||.2)}–${pct(r.max_fair||.85)} chance · two odds sources agree · games within ${r.horizon_hours||30} hours · one order per game · up to ${money(r.per_order||10)} each, ${r.max_orders||6} orders and ${money(r.max_dollars||40)} out at once, inside your cap ·
   re-priced when the fair chance moves ${Math.round((r.reprice||.01)*100)}¢ · cancelled ${r.cancel_mins||20} minutes before the game and on injury news (Kalshi also expires them by itself).</div>
   ${k.settled?`<div class="mini" style="margin-top:6px">Record so far<b class="${k.pl>=0?'up':'down'}">${smoney(k.pl)} (${k.settled} settled, ${k.filled} filled)</b></div>`:''}${rows?`<div style="margin-top:6px">${rows}</div>`:''}</div>`;}
function makerMode(m,sure){if(m==='on'&&!sure){modal(`<h3>Let the Mac place standing orders?</h3><p>Real buy orders on Kalshi, a few cents under fair, up to ${money(40)} out at once and inside your cap. They're cancelled before games start, on news, and when you tap Pause on any alert.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();makerMode('on',true)">Turn on</button></div>`);return;}
 S.set.maker.mode=m;setv('maker_mode',m);renderSettings();toast(m==='on'?'Standing orders: on. They appear on Live.':m==='watch'?'Standing orders: watch only.':'Standing orders off. Any open ones are cancelled on the next pass.',5000);}
function ordersCard(d){const os=d.orders||[];if(!os.length)return '';
 return `<div class="card"><h3>Standing orders <span>${os[0].mode==='on'?'on Kalshi':'watching'}</span></h3>${os.map(x=>`<div class="moment"><span class="k">${x.mode==='on'?'📌':'👀'}</span><span><b>${esc(short(x.pick))}</b> <span class="m">${x.n} at ${Math.round(x.price*100)}¢ · fair ${pct(x.fair)}</span></span><time>${ago2(x.ts)}</time></div>`).join('')}</div>`;}
function dayBar(d){const v=d.days;if(!v)return '';const b=(on,lab,js)=>`<button class="${on?'on':''}" onclick="${js}">${lab}</button>`;
 if(v.mode==='day')return `<div class="seg daybar">${b(!v.next_day,'Today',"setDays({next_day:false})")}${b(v.next_day,'Tomorrow',"setDays({next_day:true})")}</div>`;
 if(v.mode==='mix')return `<div class="seg daybar">${v.windows.map((w,i)=>b(v.mix_window===i,esc(w),`setDays({mix_window:${i}})`)).join('')}</div>`;
 return `<div class="seg daybar">${b(v.thursday,v.wed?'+ Wed & Thu':'+ Thursday',`setDays({thursday:${!v.thursday}})`)}${b(true,'Sunday','')}${b(v.saturday,'+ Saturday',`setDays({saturday:${!v.saturday}})`)}${b(v.monday,'+ Monday',`setDays({monday:${!v.monday}})`)}</div>`;}
async function setDays(vals){hap();Object.assign(S.build.days,vals);renderBuild();
 const r=await api('/app/api/settings',{lg:S.lg,values:vals}).catch(()=>({ok:false}));if(!r.ok){toast('Couldn\'t change the days.');return;}
 S.build=null;renderBuild();load('build',true);}
try{S.bsec=JSON.parse(localStorage.getItem('cw_bsec')||'null')||{}}catch(e){S.bsec={}}
function secOpen(k){return S.bsec[k]!==false;}
/* folding a Build section: the chevron turns and the section rises in, instead of jumping */
function secTog(k){hap('selection');S.bsec[k]=!secOpen(k);try{localStorage.setItem('cw_bsec',JSON.stringify(S.bsec))}catch(e){}S.secJust=k;renderBuild();S.secJust=null;
 const h=document.querySelector(`.sech[data-k="${k}"]`);if(!h)return;const c=h.querySelector('.chev');
 requestAnimationFrame(()=>requestAnimationFrame(()=>{if(c)c.classList.remove('from-open','from-shut');}));
 if(secOpen(k)){let n=h.nextElementSibling;for(let i=0;i<2&&n&&!n.classList.contains('sech');i++,n=n.nextElementSibling)n.classList.add('unfold');}}
function secHead(k,title,n,sub,extra){const o=secOpen(k);return `<h2 class="sech ${o?'open':''}" data-k="${k}" onclick="secTog('${k}')"><span class="chev ${S.secJust===k?(o?'from-shut':'from-open'):''}">▾</span>${title} <span class="n">${n}</span>${o&&sub?`<span class="r m" style="font-size:12px">${sub}</span>`:''}${extra?`<span class="r">${extra}</span>`:''}</h2>${o?'':`<div class="m secfold" onclick="secTog('${k}')">Folded · tap to show</div>`}`;}
function linesBlock(d){const ls=d.lines||[];if(!ls.length)return '';const games={};ls.forEach(x=>{(games[x.game]=games[x.game]||[]).push(x);});
 return secHead('lines','Spreads &amp; totals',ls.length,'Kalshi price · model chance from the sportsbook line')+(!secOpen('lines')?'':`
  <div class="tbl lines"><div class="lrow2 m" style="font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding-top:10px"><span></span><span class="num">Kalshi</span><span class="num">Chance</span><span class="num" style="text-align:center">Edge</span></div>${Object.entries(games).map(([g,xs])=>`<div class="lhd">${esc(g)} <span class="m">· book ${xs.find(x=>x.kind==='spread')?'spread '+xs.find(x=>x.kind==='spread').book_line:''}${xs.find(x=>x.kind==='total')?' · total '+xs.find(x=>x.kind==='total').book_line:''}</span></div>
   ${xs.sort((a,b)=>a.kind.localeCompare(b.kind)||a.line-b.line).map(x=>`<div class="lrow2"><span>${x.kind==='spread'?'📏':'➕'} ${esc(x.pick.replace(/ \(.*\)$/,''))}</span><span class="num">${Math.round(x.p*100)}¢</span><span class="num m">${pct(x.fair)}</span>
    <button class="btn ${x.edge>=0.04?'acc':'ghost'}" onclick="lineFromBoard('${x.ticker}',this)">${x.edge>=0?'+':'−'}${Math.abs(x.edge*100).toFixed(1)}¢</button></div>`).join('')}`).join('')}</div>
  <div class="m" style="font-size:12px;margin:6px 2px 0">Edge after Kalshi's fee. Blue = at least 4¢ in your favour. A score model adds its own error, so treat small edges as zero.</div>`);}
async function lineFromBoard(t,b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span>';}const r=await api('/app/api/act',{a:'lineidea',t}).catch(()=>({ok:false}));
 if(!r.ok){toast(r.msg||'Couldn\'t set that up.');renderBuild();return;}S.view='live';chrome();await load('live',true);S.hl=r.id;renderLive();await priceIdea(r.id);
 const e=document.getElementById('idea-'+r.id);if(e)e.scrollIntoView({behavior:'smooth',block:'center'});}
// ---------------- charts
function sparkPath(pts,w,h,lo,hi){if(!pts||pts.length<2)return '';const t0=pts[0][0],t1=pts[pts.length-1][0]||t0+1;lo=lo??0;hi=hi??1;
 return pts.map((p,i)=>`${i?'L':'M'}${((p[0]-t0)/Math.max(1,t1-t0)*w).toFixed(1)} ${(h-(Math.min(hi,Math.max(lo,p[1]))-lo)/Math.max(1e-9,hi-lo)*h).toFixed(1)}`).join('');}
function spark(pts,w,h,col){if(!pts||pts.length<2)return `<svg viewBox="0 0 ${w} ${h}"><line x1="0" x2="${w}" y1="${h/2}" y2="${h/2}" stroke="var(--line)" stroke-dasharray="3 4"/></svg>`;
 const last=pts[pts.length-1][1];col=col||(last>=.5?'var(--yes)':'var(--no)');const p=sparkPath(pts,w,h-4,0,1);
 return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><line x1="0" x2="${w}" y1="${(h-4)/2}" y2="${(h-4)/2}" stroke="var(--line)" stroke-dasharray="3 4"/>
  <path d="${p} L${w} ${h} L0 ${h}Z" fill="${col}" opacity=".10"/><path d="${p}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;}
function valueChart(off,cost,pays){if(!off||off.length<2)return '<div class="m" style="padding:18px 4px">The value chart fills in as the Mac watches this combo.</div>';
 const W=Math.round(Math.max(340,Math.min(820,window.innerWidth-70))),H=W<600?190:200,pl=44,pb=22,iw=W-pl-8,ih=H-pb-10;const t0=off[0].ts,t1=off[off.length-1].ts;
 const vals=off.flatMap(o=>[o.hold,o.offer]).filter(v=>v!=null).concat([cost]);const hi=Math.max(...vals)*1.08,lo=0;
 const X=t=>pl+(t-t0)/Math.max(1,t1-t0)*iw,Y=v=>10+ih-(v-lo)/(hi-lo)*ih;
 const line=k=>off.filter(o=>o[k]!=null).map((o,i)=>`${i?'L':'M'}${X(o.ts).toFixed(1)} ${Y(o[k]).toFixed(1)}`).join('');
 const ticks=[0,.25,.5,.75,1].map(f=>lo+(hi-lo)*f);const tl=t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
 return `<div class="key"><span><i style="background:var(--acc)"></i>Worth holding</span><span><i style="background:var(--yes)"></i>Kalshi offer</span><span><i style="background:var(--mute)"></i>You paid</span></div>
 <svg viewBox="0 0 ${W} ${H}">${ticks.map(v=>`<line x1="${pl}" x2="${W-8}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${pl-6}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="var(--mute)">${money(v)}</text>`).join('')}
  <line x1="${pl}" x2="${W-8}" y1="${Y(cost)}" y2="${Y(cost)}" stroke="var(--mute)" stroke-dasharray="4 4"/>
  <path d="${line('hold')}" fill="none" stroke="var(--acc)" stroke-width="2.2" stroke-linejoin="round"/>
  <path d="${line('offer')}" fill="none" stroke="var(--yes)" stroke-width="2" stroke-linejoin="round" opacity=".9"/>
  ${off.filter(o=>o.real_offer&&o.offer!=null).map(o=>`<circle cx="${X(o.ts)}" cy="${Y(o.offer)}" r="3.5" fill="var(--yes)"/>`).join('')}
  <text x="${pl}" y="${H-4}" font-size="11" fill="var(--mute)">${tl(t0)}</text><text x="${W-8}" y="${H-4}" font-size="11" fill="var(--mute)" text-anchor="end">${tl(t1)}</text></svg>`;}
// ---------------- combo detail
async function openCombo(t){S.gameOpen=null;S.comboOpen=t;pushOpen('Combo');
 const [r]=await Promise.all([api('/app/api/combo?t='+encodeURIComponent(t)).catch(()=>null),pushWait()]);if(S.comboOpen!==t)return;const c=r&&r.combo;
 if(!c){pushFill('<h3>Not found</h3><p>That combo isn\'t live any more.</p>','Combo');return;}
 const h=r.history||{offers:[],ticks:{}};const [vc,vt]=verdictOf(c);
 pushFill(`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${(c.sports||[]).map(s=>SPN[s]||s).join(' · ')}</div><h3 style="font-size:22px">${esc(c.label)}</h3><div class="m">${esc(nextLine(c))}</div></div>
  <div style="display:flex;gap:8px;align-items:center"><span class="verdict ${vc}">${vt}</span></div></div>
  <div class="dkpis"><div><span>Paid</span><b>${money(c.cost)}</b></div><div><span>Pays</span><b>${money(c.pays)}</b></div><div><span>Chance</span><b>${c.group==='pending'?`<span data-num="dp:${c.t}" data-v="${c.p}" data-f="pct">${pct(c.p)}</span>`:'—'}</b></div><div><span>${c.offer_real?'Offer':'Likely offer'}</span><b>${c.offer!=null?`<span data-num="do:${c.t}" data-v="${c.offer}" data-pre="${c.offer_real?'':'≈ '}">${(c.offer_real?'':'≈ ')+money(c.offer)}</span>`:'—'}</b></div></div>
  ${c.why?`<p style="margin:-4px 0 14px">${esc(c.why)}</p>`:''}
  <div class="chartbox">${valueChart(h.offers,c.cost,c.pays)}</div>
  <h2 style="margin:4px 0 6px">Picks <span class="n">${c.legs.length}</span></h2><div class="dlegs">${c.legs.map(l=>{const tk=(h.ticks||{})[l.ticker]||[];const pts=tk.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
   return `<div class="lg"><div><b>${ICON[l.sport]||''} ${esc(l.name)}</b><div class="m" style="font-size:12.5px">${l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||(!l.res&&l.note)||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</div></div>
    ${l.res?`<span class="m" style="text-align:center">${l.res==='yes'?'✓ won':'✕ lost'}</span>`:spark(pts,120,28)}<b style="text-align:right">${l.res?'':pct(l.live!=null?l.live:l.chance)}</b></div>`;}).join('')}</div>
  ${c.group==='pending'?`<div class="row" style="margin-top:16px;flex-wrap:wrap">${c.hedge&&!c.hedge.done?`<button class="btn" onclick="closeModal();hedge('${c.t}')">Hedge · ${money(c.hedge.cost)}</button>`:''}
   <button class="btn" onclick="closeModal();ask('${c.t}')">${c.offer_real?'New offer':'Get cash-out offer'}</button>${c.offer_real?`<button class="btn yes" onclick="closeModal();sell('${c.t}')">Cash out ${money(c.offer)}</button>`:''}</div>`:''}`,c.label);}
// ---------------- games
/* Games: one live card per game you have money on (combos, single bets, spreads and totals). Team rows with the score,
   the clock, the chance line over the game with a glowing end dot, and the bets riding on it. When someone scores the
   card pulses (green when it's your side, red when it's theirs), the number bumps and the phone ticks. Tap to push
   into the game page. */
function gamesSkel(){return `<div class="games">${Array.from({length:4},()=>`<div class="gsk"><i style="height:11px;width:38%"></i><i style="height:20px;width:70%"></i><i style="height:20px;width:55%"></i><i style="height:46px"></i><i style="height:22px;width:60%"></i></div>`).join('')}</div>`;}
function miniLine(pts,col){if(!pts||pts.length<2)return `<div class="mline"><svg viewBox="0 0 300 46" preserveAspectRatio="none"><line x1="0" x2="300" y1="23" y2="23" stroke="var(--line)" stroke-width="2" stroke-dasharray="3 5" vector-effect="non-scaling-stroke"/></svg></div>`;
 const t0=pts[0][0],t1=pts[pts.length-1][0],X=t=>(t-t0)/Math.max(1,t1-t0)*300,Y=v=>42-Math.max(0,Math.min(1,v))*38;
 const d=pts.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');const ly=Y(pts[pts.length-1][1]);const id='mg'+Math.random().toString(36).slice(2,7);
 return `<div class="mline"><svg viewBox="0 0 300 46" preserveAspectRatio="none"><defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".28"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
  <line x1="0" x2="300" y1="${Y(.5)}" y2="${Y(.5)}" stroke="var(--line)" stroke-dasharray="3 5" vector-effect="non-scaling-stroke"/><path d="${d} L300 46 L0 46Z" fill="url(#${id})"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg>
  <i class="sdot" style="left:100%;top:${(ly/46*100).toFixed(1)}%;background:${col};color:${col}"></i></div>`;}
function gameLine(g){S.gh=S.gh||{};const k=g.ticker||g.name;let h=S.gh[k]||[];const now=Date.now()/1000;   // the page keeps its own line too, for bets the Mac hasn't charted yet
 if(g.chance!=null&&(!h.length||h[h.length-1][1]!==g.chance))h=h.concat([[now,g.chance]]).slice(-240);S.gh[k]=h;
 const sp=(g.spark||[]).filter(p=>p[1]!=null);return sp.length>=2?sp.concat(h.filter(p=>p[0]>sp[sp.length-1][0])):h;}
const GLIVE=g=>g.state==='live'&&!['probably_over','waiting','over'].includes(g.phase);
function gameCard(g){const live=GLIVE(g),fin=g.phase==='over',sc=g.sc,ch=g.chance,lc=live?legCls({state:'live',sc,live:ch}):'';
 const col=ch==null?'var(--acc)':ch>=.5?'var(--yes)':'var(--no)';const sg=S.gscore&&S.gscore[g.ticker||g.name];
 const what=g.kind==='spread'?'to cover':g.kind==='total'?'to hit':live?'to win now':'to win';
 // both teams and both scores on every card: the full opponent name, else the short code from the score; no score (tennis/UFC) = no number, never a fake 0
 const shown=sc&&(live||fin),myPts=shown&&sc.me!=null?sc.me:null,oppPts=shown&&sc.opp!=null?sc.opp:null,oppNm=g.opp||(sc&&sc.opp_abbr)||'';
 const bets=[g.combos?`<span class="bt">🎯 ${g.combos} combo${g.combos>1?'s':''}</span>`:'',...(g.singles||[]).map(x=>`<span class="bt s">${x.kind==='spread'?'📏':x.kind==='total'?'Σ':'✓'} ${esc(x.label||'')}</span>`)].join('');
 const head=live?`<span class="lv"><i></i>${esc((sc&&sc.detail)||'Live')}</span>`:fin?`<span>Final${sc&&sc.detail?' · '+esc(sc.detail):''}</span>`:g.state==='over'||g.phase==='probably_over'?'<span>Probably finished</span>':g.phase==='waiting'?'<span>Not started yet</span>':`<span>${esc(g.short||g.starts||'Upcoming')}</span>`;
 return `<div class="gc ${live?'live l'+lc:''} ${sg?'scored '+sg:''}" data-gk="${esc(g.ticker||g.name)}" onclick="openGame('${esc(g.ticker||'')}')">
  <div class="gh"><span>${ICON[g.sport]||''} ${esc(SPN[g.sport]||g.sport||'')}</span>${head}</div>
  <div class="tms"><div class="gtr me"><span class="nm">${esc(g.name)}</span><span class="mine">YOURS</span>${myPts!=null?`<b class="pts ${sg?'bump':''}">${esc(String(myPts))}</b>`:''}</div>
   ${oppNm||oppPts!=null?`<div class="gtr them"><span class="nm">${esc(oppNm||'Opponent')}</span>${oppPts!=null?`<b class="pts">${esc(String(oppPts))}</b>`:''}</div>`:''}</div>
  <div class="gl"><div class="ch"><b class="${ch==null?'':ch>=.5?'up':'down'}" ${ch!=null?`data-num="gch:${esc(g.ticker||g.name)}" data-v="${ch}" data-f="pct"`:''}>${ch==null?'—':pct(ch)}</b><small>${what}</small>
   <div class="gbar"><i data-bar="gb:${esc(g.ticker||g.name)}" style="width:${ch==null?0:Math.max(2,Math.min(100,ch*100))}%;background:${col}"></i></div></div>${miniLine(gameLine(g),col)}</div>
  <div class="bets">${bets}<span class="rd">${money(g.pays)} riding</span></div></div>`;}
function scoreWatch(gs){/* who scored since the last paint: your side, or theirs */
 S.gsc=S.gsc||{};S.gscore={};let any=null;
 gs.forEach(g=>{const k=g.ticker||g.name,sc=g.sc;if(!sc||g.state!=='live')return;const o=S.gsc[k];S.gsc[k]=[sc.me,sc.opp];
  if(o&&(o[0]!==sc.me||o[1]!==sc.opp)){const good=sc.me>o[0];S.gscore[k]=good?'good':'bad';any=any||S.gscore[k];}});
 if(any&&S.view==='games')hap(any==='good'?'success':'warning');
 clearTimeout(S.gscT);S.gscT=setTimeout(()=>{S.gscore={};document.querySelectorAll('.gc.scored').forEach(e=>e.classList.remove('scored','good','bad'));},1700);}
function renderGames(){const d=S.games;const m=$('#main');if(!d){m.innerHTML=(S.lerr||{}).games?errCard('games'):gamesSkel();return;}
 const gs=d.games||[];if(!gs.length){m.innerHTML='<div class="card empty" data-ic="🏟️"><b>No games to watch</b>Games you have money on, in combos or as single bets and spreads, show up here with live scores and chance lines.<br><button class="btn acc" onclick="go(\'build\')">See today\'s bets</button></div>';return;}
 scoreWatch(gs);
 const on=GLIVE,live=gs.filter(on),fin=gs.filter(g=>g.phase==='over'),idle=gs.filter(g=>!on(g)&&!fin.includes(g)&&(g.phase==='probably_over'||g.state==='over')),rest=gs.filter(g=>!on(g)&&!fin.includes(g)&&!idle.includes(g));
 m.innerHTML=(d.fresh?`<div class="fresh" data-fr="N" style="text-align:right;margin:-6px 2px 4px">${frTxt('N')}</div>`:'')+(live.length?`<h2><span class="live-dot"></span>Playing now <span class="n">${live.length}</span></h2><div class="games">${live.map(gameCard).join('')}</div>`:'')
  +(rest.length?`<h2>Coming up <span class="n">${rest.length}</span></h2><div class="games">${rest.map(gameCard).join('')}</div>`:'')
  +(fin.length?`<h2>Finished <span class="n">${fin.length}</span></h2><div class="m" style="font-size:12.5px;margin:-6px 2px 10px">Over. Kalshi settles them when the result is in.</div><div class="games">${fin.map(g=>gameCard(g).replace('class="gc ','class="gc done ')).join('')}</div>`:'')
  +(idle.length?`<h2>Probably finished <span class="n">${idle.length}</span></h2><div class="m" style="font-size:12.5px;margin:-6px 2px 10px">No live score for these. Kalshi settles them when the result is in.</div><div class="games">${idle.map(g=>gameCard(g).replace('class="gc ','class="gc done ')).join('')}</div>`:'');}
// ---------------- one game, live
async function openGame(t){if(!t)return;S.comboOpen=null;S.gameOpen=t;S.gameSig=null;S.gtab=null;S.gtabPos=null;S.gtabScroll=null;S.pbpStep=null;S.pbpOpen={};S.pbpSeen=null;S.pbpBall=null;pushOpen('Game');await drawGame();}
// The open game sheet redraws on its own: on every Mac tick, on a score event for this game, and on a slow timer if the
// live link is down. It only repaints when something changed (and keeps its scroll place), and the clock below it counts
// down between updates while it is running. Only the first draw waits for the slide-in to finish.
async function drawGame(){const t=S.gameOpen;if(!t||!$('#modal').classList.contains('on')||S.gameBusy||S.scrub)return;   // a finger on the chart holds the page still
 const sh=$('#sheet');S.gameBusy=true;S.gameAt=Date.now();
 try{const [r]=await Promise.all([api('/app/api/game?t='+encodeURIComponent(t)).catch(()=>null),S.gameSig?null:pushWait()]);if(S.gameOpen!==t)return;
  if(!r||!r.leg){if(!S.gameSig)pushFill('<h3>Game not found</h3><p>It may have finished and settled.</p>','Game');return;}
  frSet('G',r.fresh);clkNote(t,r.leg);
  const sig=JSON.stringify([r.leg,r.combos,r.story,r.whatif,r.detail]);
  if(sig===S.gameSig&&sh.querySelector('.board2')){frTick();return;}
  S.gameSig=sig;const top=sh.scrollTop;paintGame(r);sh.scrollTop=top;frTick();
 }finally{S.gameBusy=false;}}
const CLK_SPORTS=['nba','ncaamb','ncaawb','nhl','ahl','euroleague'];
function clkNote(t,l){S.clk=S.clk||{};const sc=l.sc,m=sc&&l.state==='live'&&CLK_SPORTS.includes(l.sport)?/^(.*?)\s*(\d{1,2}):(\d{2})$/.exec(sc.detail||''):null;
 if(!m){delete S.clk[t];return;}
 const lab=m[1].trim(),secs=+m[2]*60+ +m[3],p=S.clk[t],now=Date.now();
 if(p&&p.lab===lab&&secs===p.srv){if(p.run&&now-p.recv<25000)return;S.clk[t]={lab,srv:secs,secs,recv:now,run:false};return;}
 S.clk[t]={lab,srv:secs,secs,recv:now,run:!!(p&&p.lab===lab&&secs<p.srv)};}
function clkTick(){document.querySelectorAll('[data-clk]').forEach(e=>{const c=(S.clk||{})[e.dataset.clk];if(!c)return;const v=c.run?Math.max(0,c.secs-Math.floor((Date.now()-c.recv)/1000)):c.secs;
 const t=c.lab+' '+Math.floor(v/60)+':'+String(v%60).padStart(2,'0');if(e.textContent!==t)e.textContent=t;});}
function paintGame(r){const t=S.gameOpen;S.gameR=r;{const gb=document.querySelector('#sheet .gtabs');if(gb)S.gtabScroll=gb.scrollLeft;}
 const l=r.leg,sc=l.sc,st=r.story||{ticks:[],plays:[]};const ch=l.live!=null?l.live:l.chance;const lc=legCls(l);
 const pts=st.ticks.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
 const plays=st.plays.slice().reverse();
 const ov=`<div class="dkpis"><div><span>${l.kind==='spread'?'Chance it covers':l.kind==='total'?'Chance it hits':esc(short(l.name))+' to win'}</span><b class="${ch>=.5?'up':'down'}" data-num="gc:${t}" data-v="${ch}" data-f="pct">${pct(ch)}</b></div><div><span>Your bets on it</span><b>${r.combos.length}</b></div><div><span>Riding on it</span><b>${money(r.combos.reduce((a,c)=>a+c.pays,0))}</b></div><div><span>Score changes</span><b>${Math.max(0,st.plays.length-1)}</b></div></div>
  <div class="chartbox">${winChart(pts,st.plays)}</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px">
   <div><h2 style="margin:0 0 6px">Scoring</h2>${plays.length>1?plays.slice(0,-1).map((p,i)=>{const prev=plays[i+1];const mine=p.me>prev.me;return `<div class="moment"><span class="k" style="color:${mine?'var(--yes)':'var(--no)'}">${mine?'▲':'▼'}</span><span>${mine?esc(short(l.name)):esc(short(l.opp||'Them'))} score · <b>${p.me}–${p.opp}</b> <span class="m">${esc(p.detail||'')}</span></span><time>${ago2(p.ts)}</time></div>`;}).join(''):'<div class="m">No score changes recorded yet.</div>'}</div>
   <div><h2 style="margin:0 0 6px">Your bets on this game</h2>${r.combos.map(c=>`<div class="moment" ${c.single?'':`style="cursor:pointer" onclick="openCombo('${c.t}')"`}><span class="k">${c.single?'📏':'🎯'}</span><span><b>${esc(c.label)}</b> <span class="m">${c.single?(c.how?esc(c.how)+' · ':'')+pct(c.p)+' chance':c.legs+' picks · '+pct(c.p)+' to hit'}</span></span><b>${money(c.pays)}</b></div>`).join('')||'<div class="m">None pending.</div>'}
   ${r.whatif?`<h2 style="margin:16px 0 6px">What if…</h2><div class="whatif"><div class="wi up"><span>${esc(short(l.name))} get the next ${esc(r.whatif.unit)}</span><b>${pct(r.whatif.up)}</b><small>to win${r.combos[0]&&r.combos[0].if_up!=null?` · ${esc(r.combos[0].label)} worth ≈${money(r.combos[0].if_up)}`:''}</small></div>
    <div class="wi down"><span>${esc(short(l.opp||'They'))} get it</span><b>${pct(r.whatif.down)}</b><small>to win${r.combos[0]&&r.combos[0].if_down!=null?` · ≈${money(r.combos[0].if_down)}`:''}</small></div></div>
    ${r.combos[0]&&r.combos[0].now!=null?`<div class="m" style="font-size:12px;margin-top:6px">Worth ≈${money(r.combos[0].now)} now. Estimates use Kalshi's usual cash-out discount.</div>`:''}`:''}</div></div>
  ${l.url?`<div class="row" style="margin-top:14px"><a class="btn" href="${esc(l.url)}" target="_blank">Kalshi game page ↗</a></div>`:''}`;
 pushFill(`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${esc(SPN[l.sport]||l.sport)}${(l.state==='live'||l.on)&&l.phase!=='probably_over'&&l.phase!=='waiting'?' · <span style="color:var(--live)">LIVE</span>':''} <span class="fresh" data-fr="G" style="margin-left:8px">${frTxt('G')}</span></div>
   <h3 style="font-size:20px">${ICON[l.sport]||''} ${esc(l.name)}${l.opp?` <span class="m" style="font-weight:500">vs ${esc(l.opp)}</span>`:''}</h3></div></div>
  <div class="board2 ${lc}">${sc?`<div class="tm2"><div><span>${esc(sc.abbr)}${scbPoss(r.detail,sc.abbr)}</span>${scbTimeouts(r.detail,sc.abbr)}</div><b data-num="sm:${t}" data-v="${sc.me}" data-f="int">${sc.me}</b></div><div class="mid2"><div class="clk"${(S.clk||{})[t]?` data-clk="${esc(t)}"`:''}>${(l.state==='live'||l.on)&&l.phase!=='probably_over'&&l.phase!=='waiting'?'<span class="live-dot"></span>':''}${esc(sc.detail||'')}</div><div class="m">${(l.state==='live'||l.on)&&l.phase!=='probably_over'&&l.phase!=='waiting'?'in progress':''}${l.src==='kalshi'?'<div style="font-size:10.5px;opacity:.75">score from Kalshi</div>':''}</div></div><div class="tm2 r"><b data-num="so:${t}" data-v="${sc.opp}" data-f="int">${sc.opp}</b><div><span>${scbPoss(r.detail,sc.opp_abbr)}${esc(sc.opp_abbr)}</span>${scbTimeouts(r.detail,sc.opp_abbr)}</div></div>`:
   `<div class="mid2" style="grid-column:1/-1"><div class="clk">${esc(l.note||l.starts||'Not started')}</div></div>`}</div>
  ${fieldStrip(gameStepDetail(r),l)}
  ${gameTabsHtml(r,ov)}`,l.opp?short(l.name)+' vs '+short(l.opp):l.name);gameAfterPaint(r);}
/* The live field strip (football only, display only): our own art from ESPN's team colours. A 100-yard field with the
   two end zones tinted, a yard ruler (G 10 20 30 40 50 40 30 20 10 G), a ball at the line of scrimmage, a possession
   arrow pointing the way the offence is driving, a yellow first-down line and red-zone shading inside the 20. The ball
   slides to the new spot when the play changes (CSS transition; prefers-reduced-motion respected). Nothing here is read
   by any buy/sell path, and a bad or missing feed just returns '' so the page still works. */
/* A team colour, safe to drop into an inline style: a 6-hex-digit colour (with or without a leading #) becomes
   #rrggbb; anything else (empty, a name, something odd in the feed) falls back to the given CSS variable. The rest
   of the strip escapes its text with esc(); colours are the one place a raw feed value reaches a style attribute. */
function fcolor(c,fb){c=(c||'').replace(/^#/,'');return /^[0-9a-f]{6}$/i.test(c)?'#'+c:fb;}
function fieldStrip(d,l){if(!d)return '';const b=d.board||{},sit=d.situation||{},dr=d.drive||{};
 const home=b.home||{},away=b.away||{};const hc=fcolor(home.color,'var(--no)'),ac=fcolor(away.color,'var(--yes)');
 // Where is the ball? Prefer the drive's yards-to-end-zone; fall back to the situation's yardLine (0 own goal → 100 foe).
 let ytz=dr.ballYardsToEndzone;if(ytz==null&&sit.yardLine!=null)ytz=100-sit.yardLine;
 // Who has it, and which way do they drive? Away attacks right (home's zone), home attacks left (away's zone).
 const offAbbr=dr.teamAbbr||(sit.possessionText||'').split(' ')[0]||'';
 const homeHas=offAbbr&&home.abbr&&offAbbr.toUpperCase()===home.abbr.toUpperCase();
 const haveBall=ytz!=null;
 // Field goes 0..100 left→right in the 100-yard playing area. Everything inside .grass (ball, arrow, ticks, first-down line,
 // red zone) is positioned in % of the GRASS box, which already sits between the two end zones, so a spot at N yards from the
 // left goal line is simply left:N%. The ruler lives in .fld (the whole strip), so it keeps its own end-zone inset below.
 const EZ=100/12,play=100-2*EZ;
 // Line of scrimmage as a % of the whole strip. For the away offence (driving right) distance from left goal = 100-ytz.
 let losYd=homeHas?ytz:(100-ytz);                 // yards from the LEFT goal line (0..100)
 let losPct=haveBall?Math.max(0,Math.min(100,losYd)):50;
 // First-down line: `distance` yards further toward the offence's target end zone.
 const dist=(sit.distance!=null)?sit.distance:null;
 let fdYd=dist!=null?(homeHas?losYd-dist:losYd+dist):null;
 let fdPct=fdYd!=null?Math.max(0,Math.min(100,fdYd)):null;
 const rz=!!sit.isRedZone;const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const rulerN=['G','10','20','30','40','50','40','30','20','10','G'];
 const ruler=rulerN.map((n,i)=>`<span style="left:${(EZ+i*play/10).toFixed(2)}%">${n}</span>`).join('');
 const ticks=Array.from({length:11},(_,i)=>`<i style="left:${i*10}%"></i>`).join('');
 // The ball marker + possession arrow point the direction of the drive.
 const dir=homeHas?-1:1;                           // home drives left (−), away drives right (+)
 const ball=haveBall?`<i class="fball" style="left:${losPct.toFixed(2)}%"><svg viewBox="0 0 24 14" aria-hidden="true"><ellipse cx="12" cy="7" rx="11" ry="6"/><line x1="7" y1="7" x2="17" y2="7"/></svg></i>
   <i class="fdir" style="left:${losPct.toFixed(2)}%;transform:translate(${dir>0?'6px':'-110%'},-50%) scaleX(${dir})">▶</i>`:'';
 // Only draw the first-down line when a ball marker is shown, so a partial feed can't leave a floating line with no ball.
 const fdLine=(haveBall&&fdPct!=null)?`<i class="fdline" style="left:${fdPct.toFixed(2)}%"></i>`:'';
 // The red zone is 20 yards deep in front of the defending end zone: left end zone (home attacking) covers 0..20,
 // right end zone (away attacking) covers 80..100.
 const rzShade=rz?`<i class="frz" style="left:${dir>0?80:0}%;width:20%"></i>`:'';
 // The situation line: down & distance, ball spot, who has it; and the last play + its type.
 const dd=sit.downDistanceText||dr.downDistanceText||'';
 const spot=sit.possessionText||'';                 // ESPN's "IND 27"; no synthetic number if the feed lacks it
 const offName=homeHas?short(home.name||home.abbr):short(away.name||away.abbr);
 const lastPlay=(sit.lastPlayText||'').trim();const lastType=(sit.lastPlayType||'').trim();
 return `<div class="fstrip${reduce?' noanim':''}">
  <div class="fld" role="img" aria-label="Field position">
   <i class="ez l" style="background:${ac}"><span>${esc(away.abbr||'')}</span></i>
   <i class="ez r" style="background:${hc}"><span>${esc(home.abbr||'')}</span></i>
   <div class="grass">${ticks}${rzShade}${fdLine}${ball}</div>
   <div class="ruler">${ruler}</div>
  </div>
  ${haveBall||dd?`<div class="situ"><span class="dd">${esc(dd||(sit.down?ordinal(sit.down)+' & '+(sit.distance??''):''))||(sit.replay?'Replay':'Live')}</span>
   ${spot?`<span class="m">· ball on ${esc(spot)}</span>`:''}${offName?`<span class="m">· ${esc(offName)} ball</span>`:''}${rz?'<span class="rzt">RED ZONE</span>':''}${sit.replay?'<span class="rzt rpl">REPLAY</span>':''}</div>`:''}
  ${lastPlay?`<div class="lastplay">${lastType?`<span class="lpt">${esc(lastType)}</span>`:''}<span>${esc(lastPlay)}</span></div>`:''}
 </div>`;}
function ordinal(n){n=+n;const s=['th','st','nd','rd'],v=n%100;return n+(s[(v-20)%10]||s[v]||s[0]);}
// Timeout dots under a team's code on the scoreboard (3 = full). Possession football next to the code with the ball.
function _teamSide(d,abbr){if(!d||!d.board||!abbr)return null;const a=(abbr||'').toUpperCase();
 const b=d.board;if((b.home||{}).abbr&&b.home.abbr.toUpperCase()===a)return 'home';if((b.away||{}).abbr&&b.away.abbr.toUpperCase()===a)return 'away';return null;}
function scbTimeouts(d,abbr){const side=_teamSide(d,abbr);const sit=(d||{}).situation||{};if(!side)return '';
 const to=side==='home'?sit.homeTimeouts:sit.awayTimeouts;if(to==null)return '';
 return `<div class="tdots">${[0,1,2].map(i=>`<i class="${i<to?'on':''}"></i>`).join('')}</div>`;}
function scbPoss(d,abbr){const sit=(d||{}).situation||{},dr=(d||{}).drive||{};if(!abbr||!_teamSide(d,abbr))return '';
 const a=(abbr||'').toUpperCase();const has=((dr.teamAbbr||'').toUpperCase()===a)||((sit.possessionText||'').toUpperCase().startsWith(a+' '));
 return has?'<span class="poss" title="has the ball">🏈</span>':'';}
/* ---- The game page's tab framework (display only). One spec per sport says which tabs its page has; a sport with no spec
   (or a spec with only one visible tab) gets no tab row and the page is exactly as before. A tab is {k, l, has(r), html(r, ov)}:
   `has` hides it when its data is missing (a bad or absent feed shows nothing), `html` draws its panel (`ov` is the overview
   markup). The chosen tab lives in S.gtab and survives the page's periodic redraws; only the open tab's panel is drawn. */
const FOOTBALL_TABS=[{k:'overview',l:'Overview',html:(r,ov)=>ov},{k:'pbp',l:'Play-by-play',has:pbpHas,html:pbpHtml}];
const GAME_TABS={nfl:FOOTBALL_TABS,ncaaf:FOOTBALL_TABS};
function gameTabList(r){const spec=GAME_TABS[((r||{}).leg||{}).sport];if(!spec)return [];const a=spec.filter(t=>!t.has||t.has(r));return a.length>1?a:[];}
function gameTabCur(tabs){return tabs.some(t=>t.k===S.gtab)?S.gtab:(tabs[0]||{}).k;}
function gameTabsHtml(r,ov){const tabs=gameTabList(r);S.gtabCur=null;if(!tabs.length)return ov;const cur=gameTabCur(tabs);S.gtabCur=cur;
 return `<div class="gtabs" role="tablist">${tabs.map(t=>`<button type="button" role="tab" class="gtab${t.k===cur?' on':''}" aria-selected="${t.k===cur}" data-tab="${esc(t.k)}" onclick="gameTab('${esc(t.k)}')">${esc(t.l)}</button>`).join('')}<i class="gtabind"></i></div>
 ${tabs.map(t=>`<div class="gpanel" role="tabpanel" data-tab="${esc(t.k)}"${t.k===cur?'':' hidden'}>${t.k===cur||t===tabs[0]?t.html(r,ov):''}</div>`).join('')}`;}
/* switch tab without a full repaint: only the visible panel is (re)drawn, and leaving the play-by-play puts the strip back to live */
function gameTab(k){const r=S.gameR,tabs=gameTabList(r),t=tabs.find(x=>x.k===k);if(!t)return;const was=S.gtabCur;S.gtab=k;S.gtabCur=k;
 document.querySelectorAll('#sheet .gtab').forEach(b=>{const on=b.dataset.tab===k;b.classList.toggle('on',on);b.setAttribute('aria-selected',on);});
 document.querySelectorAll('#sheet .gpanel').forEach(p=>{const on=p.dataset.tab===k;p.hidden=!on;if(on&&p.dataset.tab!==tabs[0].k)p.innerHTML=t.html(r,'');else if(!on&&p.dataset.tab!==tabs[0].k)p.innerHTML='';});
 gameTabInd();if(was==='pbp'&&k!=='pbp'&&S.pbpStep!=null){S.pbpStep=null;pbpRefresh('slide');}}
/* The sliding underline. It is a child of the scrolling row, so it scrolls with the tabs and offsetLeft is already right. */
function gameTabInd(){const bar=document.querySelector('#sheet .gtabs');if(!bar)return;const on=bar.querySelector('.gtab.on'),ind=bar.querySelector('.gtabind');if(!on||!ind)return;
 const to={left:on.offsetLeft,width:on.offsetWidth},prev=S.gtabPos;
 /* paintGame rebuilds the row, so a fresh underline starts at left:0/width:0: always seed it where the old one was (or where it is going), no transition, then glide only if the tab changed */
 const from=prev||to;ind.style.transition='none';ind.style.left=from.left+'px';ind.style.width=from.width+'px';void ind.offsetWidth;ind.style.transition='';
 ind.style.left=to.left+'px';ind.style.width=to.width+'px';S.gtabPos=to;
 if(S.gtabScroll!=null){bar.scrollLeft=S.gtabScroll;S.gtabScroll=null;}
 const vis=on.offsetLeft-bar.scrollLeft;if(vis<0||vis+on.offsetWidth>bar.clientWidth)bar.scrollTo({left:on.offsetLeft-(bar.clientWidth-on.offsetWidth)/2,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
addEventListener('resize',()=>{if(document.querySelector('#sheet .gtabs'))gameTabInd();});
/* after every repaint: the underline, the row's own sideways scroll, and (live) the newest play's animation */
function gameAfterPaint(r){gameTabInd();pbpAfterPaint(r);}
/* ---- Play-by-play (football; ESPN drives and plays, display only). Stepping shows the strip as it stood after the chosen play
   (S.pbpStep = that play's id, null = live) and replays an illustration of the play from its type and yardage. The animations
   are illustrations only: ESPN has no player tracking, and the tab says so. Under prefers-reduced-motion nothing moves: the
   text and the ball spot still update. Nothing here is read by any buy/sell path. */
function pbpData(r){const p=((r||{}).detail||{}).pbp;return p&&Array.isArray(p.drives)?p:null;}
function pbpHas(r){const p=pbpData(r);return !!(p&&p.drives.some(d=>d&&Array.isArray(d.plays)&&d.plays.length));}
function pbpPlays(r){const out=[];let n=0;((pbpData(r)||{}).drives||[]).forEach(d=>((d&&d.plays)||[]).forEach(p=>{out.push({p,d,k:String(p.id||('#'+n)),n});n++;}));return out.slice(-250);}
function pbpIdx(list){if(S.pbpStep==null)return list.length-1;const i=list.findIndex(x=>x.k===S.pbpStep);return i<0?list.length-1:i;}
function pbpLiveNow(list){return S.pbpStep==null||!list.some(x=>x.k===S.pbpStep);}
const Q_LBL=['','1st','2nd','3rd','4th'];
function qShort(q){q=+q;return q>4?(q===5?'OT':(q-4)+'OT'):(Q_LBL[q]||'Q'+q);}
function qFull(q){q=+q;return q>4?'Overtime':(Q_LBL[q]||'Q'+q)+' Quarter';}
function pbpHtml(r){const pb=pbpData(r),list=pbpPlays(r);if(!pb||!list.length)return '';S.pbpOpen=S.pbpOpen||{};
 const i=pbpIdx(list),cur=list[i],live=pbpLiveNow(list),p=cur.p,b=(r.detail||{}).board||{};const open=(k,def)=>k in S.pbpOpen?S.pbpOpen[k]:def;
 const tint=x=>x.sc?' sc':x.to?' to':'';const keyOf=new Map(list.map(x=>[x.p,x.k]));
 const meta=[qShort(p.q)+(p.clk?' · '+p.clk:''),p.dn].filter(Boolean).join(' · ');
 const card=`<div class="pcard${tint(p)}" id="pbp-card"><div class="pch"><button type="button" class="pstep" data-step="prev" aria-label="Previous play" onclick="pbpStepBy(-1)"${i<=0?' disabled':''}>‹</button>
   <div class="pcm"><div class="pct">${esc(p.ty||'Play')}</div><div class="pcs">${live?'Latest play':'Replay · play '+(i+1)+' of '+list.length}${meta?' · '+esc(meta):''}</div></div>
   <button type="button" class="pstep" data-step="next" aria-label="Next play" onclick="pbpStepBy(1)"${i>=list.length-1?' disabled':''}>›</button></div>
  <div class="pctx">${esc(p.txt)}</div>
  <div class="pcf"><span>${list.length} play${list.length===1?'':'s'}${pb.cut>0?' (latest shown)':''}</span><button type="button" class="plive" onclick="pbpLive()"${live?' hidden':''}>Back to live</button></div></div>
  <div class="pnote">Illustrations only, no player tracking</div>`;
 const qs=[];pb.drives.forEach(d=>{let g=qs.find(x=>x.q===d.q);if(!g){g={q:d.q,ds:[]};qs.push(g);}g.ds.push(d);});
 qs.reverse().forEach(g=>g.ds.reverse());
 const chev='<svg class="chev" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 const secs=qs.map(g=>{const qk='q'+g.q,qo=open(qk,g.ds.some(d=>d.plays.includes(p)));
  return `<div class="pqs"><button type="button" class="pq" data-k="${esc(qk)}" aria-expanded="${qo}" onclick="pbpTog(this)"><span>${esc(qFull(g.q))}</span>${chev}</button>
   ${qo?g.ds.map(d=>{const dk='d'+d.id,dop=open(dk,d.plays.includes(p));const tm=(b[d.side]||{});
    return `<button type="button" class="pdr${tint(d)}" data-k="${esc(dk)}" aria-expanded="${dop}" onclick="pbpTog(this)"><i class="pdot" style="background:${fcolor(tm.color,'var(--sub)')}"></i><b>${esc(d.team)}</b><span class="pres">${esc(d.res)}</span><span class="m psum">${esc(d.sum)}</span>${chev}</button>
     ${dop?`<div class="pps">${d.plays.slice().reverse().map(x=>{const k=keyOf.get(x)||'';return `<div class="pp${tint(x)}${x===p&&!live?' cur':''}" data-pid="${esc(k)}" onclick="pbpGo(this.dataset.pid)"><div class="ppm"><b>${esc(x.dn||'')}</b><span class="m">${esc(qShort(x.q))}${x.clk?' · '+esc(x.clk):''}</span></div><div class="ppt">${esc(x.txt)}</div></div>`;}).join('')}</div>`:''}`;}).join(''):''}</div>`;}).join('');
 return `<div class="pbp">${card}${secs}</div>`;}
function pbpTog(el){S.pbpOpen=S.pbpOpen||{};S.pbpOpen[el.dataset.k]=el.getAttribute('aria-expanded')!=='true';pbpRefresh('');}
function pbpStepBy(dl){const r=S.gameR,list=pbpPlays(r);if(!list.length)return;const i=pbpIdx(list),j=Math.max(0,Math.min(list.length-1,i+dl));if(j===i)return;S.pbpStep=j===list.length-1?null:list[j].k;pbpRefresh('play');}
function pbpGo(k){const list=pbpPlays(S.gameR),j=list.findIndex(x=>x.k===k);if(j<0||j===pbpIdx(list))return;S.pbpStep=j===list.length-1?null:list[j].k;pbpRefresh('play');}
function pbpLive(){S.pbpStep=null;pbpRefresh('slide');}
/* The strip as it stood after the stepped play (the ball spot, who has it, first-down line, red zone), as a detail block for fieldStrip().
   A play with no ball movement (timeout, end of quarter) keeps the spot of the nearest earlier play that had one. */
function gameStepDetail(r){const d=r.detail;if(!d||S.pbpStep==null)return d;const list=pbpPlays(r);let i=list.findIndex(x=>x.k===S.pbpStep);if(i<0)return d;const p=list[i].p;
 let j=i;while(j>=0&&(list[j].p.b==null||!pbpSide(list[j].p.bs)))j--;if(j<0)return d;const pb=list[j].p,side=pb.bs==='home'||pb.bs==='away'?pb.bs:'',abbr=(((d.board||{})[side])||{}).abbr||'';
 return Object.assign({},d,{drive:{teamAbbr:abbr,ballYardsToEndzone:pb.b,downDistanceText:pb.edd||''},
  situation:{distance:pb.edd?pb.ed:null,downDistanceText:pb.edd||'',possessionText:pb.ep||'',isRedZone:pb.b>0&&pb.b<=20,lastPlayText:p.txt,lastPlayType:p.ty,replay:true}});}
function pbpRefresh(mode){const r=S.gameR;if(!r)return;const st=document.querySelector('#sheet .fstrip');
 if(mode&&st){const tmp=document.createElement('div');tmp.innerHTML=fieldStrip(gameStepDetail(r),r.leg);const ns=tmp.firstElementChild;if(ns)st.replaceWith(ns);}
 const pan=document.querySelector('#sheet .gpanel[data-tab="pbp"]');if(pan&&!pan.hidden)pan.innerHTML=pbpHtml(r);
 let delay=0;if(mode==='play'){const list=pbpPlays(r);const x=list[pbpIdx(list)];if(x)delay=pbpFx(x.p);}
 if(mode)pbpSlide(delay);}
function pbpAfterPaint(r){const list=pbpPlays(r);
 if(S.gtabCur==='pbp'&&S.pbpStep==null&&list.length){const last=list[list.length-1];if(S.pbpSeen!=null&&S.pbpSeen!==last.k){pbpSlide(pbpFx(last.p));}else pbpSyncBall();S.pbpSeen=last.k;}
 else pbpSyncBall();}
function pbpSyncBall(){const b=document.querySelector('#sheet .fstrip .fball');S.pbpBall=b?parseFloat(b.style.left):null;}
/* slide the ball marker (and the possession arrow) from where it was to its new spot; a pass or kick waits for the flight */
function pbpSlide(delay){const st=document.querySelector('#sheet .fstrip'),ball=st&&st.querySelector('.fball');if(!ball){S.pbpBall=null;return;}const to=ball.style.left,from=S.pbpBall;S.pbpBall=parseFloat(to);
 if(matchMedia('(prefers-reduced-motion: reduce)').matches||from==null||isNaN(from)||Math.abs(from-parseFloat(to))<.05)return;
 const els=[ball,st.querySelector('.fdir')].filter(Boolean);els.forEach(e=>{e.style.transition='none';e.style.left=from+'%';});void st.offsetWidth;
 els.forEach(e=>{e.style.transition='';e.style.transitionDelay=(delay||0)+'ms';e.style.left=to;});}
/* ---- illustrations: what kind of play was it, and a small effect on the field for it */
function fabs(side,ytz){return side==='home'?ytz:100-ytz;}      // yards from the LEFT goal line = % across .grass (home attacks left, away right), the same as fieldStrip
function pbpSide(x){return x==='home'||x==='away';}      // a ball move is only drawn when the server knew whose end zone it is
function pbpKind(p){const t=(p.ty||'').toLowerCase(),turn=!!p.to&&!/penalty/.test(t);
 const k={mv:'dflt',td:/touchdown/.test(t)||(p.sc&&p.b===0&&!/field goal|safety|extra point/.test(t)),turn,fg:null,safety:/safety/.test(t)};
 if(p.a==null||p.b==null||!pbpSide(p.as)||!pbpSide(p.bs))k.mv='none';
 else if(p.pen||/penalty/.test(t))k.mv='pen';
 else if(/field goal/.test(t)){k.mv='kick';k.fg=p.sc?'good':'no';}
 else if(/kickoff|punt|extra point/.test(t))k.mv='kick';
 else if(/sack/.test(t))k.mv='sack';
 else if(/pass|interception/.test(t))k.mv='pass';
 else if(/rush|run/.test(t)||/scramble/.test((p.txt||'').toLowerCase()))k.mv='run';
 return k;}
function pbpFx(p){if(matchMedia('(prefers-reduced-motion: reduce)').matches)return 0;const grass=document.querySelector('#sheet .fstrip .grass');if(!grass)return 0;
 const k=pbpKind(p);if(k.mv==='none')return 0;
 const a=fabs(p.as,p.a),b=fabs(p.bs,p.b),off=p.as==='home'?-1:1;
 const add=(cls,css,txt)=>{const e=document.createElement('div');e.className=cls;Object.assign(e.style,css||{});if(txt)e.textContent=txt;grass.appendChild(e);setTimeout(()=>e.remove(),2000);return e;};
 const tag=(txt,tone)=>add('ftag '+(tone||''),{},txt);
 const fly=(from,to,ah,dur)=>{const e=add('fproj',{left:from+'%'});e.style.setProperty('--ah',ah+'px');e.style.setProperty('--dur',dur+'ms');e.innerHTML='<b></b>';void e.offsetWidth;e.style.left=to+'%';return dur;};
 const trail=(from,to,red)=>{add('ftrail'+(red?' red':''),{left:Math.min(from,to)+'%',width:Math.abs(to-from)+'%',transformOrigin:to>=from?'left center':'right center'});};
 const goal=off>0?100:0;let delay=0;
 if(k.mv==='pass'){const inc=/incomplet/.test((p.ty||'').toLowerCase())||Math.abs(b-a)<.1;const to=k.turn?a+off*15:(inc?a+off*11:b);
  delay=fly(a,to,Math.min(26,9+Math.abs(to-a)*.5),460+Math.min(320,Math.abs(to-a)*6));}
 else if(k.mv==='kick'){const to=k.fg?goal:b;delay=fly(a,to,Math.min(36,16+Math.abs(to-a)*.3),720+Math.min(520,Math.abs(to-a)*8));}
 else if(k.mv==='run')trail(a,b,false);
 else if(k.mv==='sack'){trail(a,b,true);tag('SACK','bad');}
 else if(k.mv==='pen'){add('fflag',{left:a+'%'},'🚩');}
 if(k.td){const ez=document.querySelector('#sheet .fstrip .ez.'+(off>0?'r':'l'));if(ez){ez.classList.add('tdflash');setTimeout(()=>ez.classList.remove('tdflash'),1400);}tag('TOUCHDOWN','good');}
 else if(k.fg==='good'){tag('FIELD GOAL','good');}
 else if(k.fg==='no'){tag('NO GOOD','bad');}
 else if(k.safety){tag('SAFETY','bad');}
 if(k.turn){const bl=document.querySelector('#sheet .fstrip .fball');if(bl){bl.classList.add('turn');setTimeout(()=>bl.classList.remove('turn'),1700);}tag('TURNOVER','bad');}
 return delay;}
function winChart(pts,plays){if(!pts||pts.length<2)return '<div class="m" style="padding:18px 4px">The win-chance line fills in as the Mac watches this game.</div>';
 const W=Math.round(Math.max(340,Math.min(820,window.innerWidth-70))),H=170,pl=36,iw=W-pl-8,ih=H-30;const t0=pts[0][0],t1=pts[pts.length-1][0];
 const X=t=>pl+(t-t0)/Math.max(1,t1-t0)*iw,Y=v=>8+ih-v*ih;const d=pts.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');
 const last=pts[pts.length-1][1];const col=last>=.5?'var(--yes)':'var(--no)';const tl=t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
 S.scr=S.scr||{};S.scr.win={n:pts.length,at:f=>{const t=t0+(f*W-pl)/iw*(t1-t0);let i=0,b=Infinity;pts.forEach((p,j)=>{const dd=Math.abs(p[0]-t);if(dd<b){b=dd;i=j;}});return i;},
  x:i=>X(pts[i][0])/W*100,y:i=>Y(pts[i][1])/H*100,lab:i=>tl(pts[i][0])+' · '+pct(pts[i][1])};
 return `<div class="key"><span><i style="background:${col}"></i>Chance to win</span><span><i style="background:var(--sub);height:8px;width:2px"></i>Score change</span><span class="m">Drag to look back</span></div><div class="scrub" data-scrub="win"><span class="sread"></span><i class="scrl"></i><i class="scrd" style="background:${col}"></i><svg viewBox="0 0 ${W} ${H}">
  ${[0,.25,.5,.75,1].map(v=>`<line x1="${pl}" x2="${W-8}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" ${v===.5?'stroke-dasharray="4 4"':''}/><text x="${pl-6}" y="${Y(v)+4}" font-size="11" text-anchor="end" fill="var(--mute)">${v*100}%</text>`).join('')}
  ${(plays||[]).slice(1).filter(p=>p.ts>=t0).map(p=>`<line x1="${X(p.ts)}" x2="${X(p.ts)}" y1="8" y2="${8+ih}" stroke="var(--sub)" stroke-width="1" opacity=".35"/>`).join('')}
  <path d="${d} L${X(t1)} ${8+ih} L${pl} ${8+ih}Z" fill="${col}" opacity=".08"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round"/>
  <text x="${pl}" y="${H-4}" font-size="11" fill="var(--mute)">${tl(t0)}</text><text x="${W-8}" y="${H-4}" font-size="11" fill="var(--mute)" text-anchor="end">${tl(t1)}</text></svg></div>`;}
/* Any chart you can drag a finger along (the game's chance line, the Results profit bars): same feel as the Live hero
   chart. A spec in S.scr[name] says how many points there are, which one is under the finger, and where to draw the
   line, dot and readout; every new point ticks a haptic. A short tap (no drag) can open the point (o.tap). Refreshes
   wait while a finger is down (S.scrub). */
function wireScrubs(root){(root||document).querySelectorAll('[data-scrub]').forEach(el=>{if(el._wired)return;el._wired=1;let idx=-1,on=false,x0=0,moved=false;
 const spec=()=>(S.scr||{})[el.dataset.scrub];
 const pick=e=>{const o=spec(),r=el.getBoundingClientRect();return o?o.at(Math.max(0,Math.min(.9999,(e.clientX-r.left)/Math.max(1,r.width)))):-1;};
 const show=i=>{const o=spec();if(!o||i===idx||i<0||i>=o.n)return;idx=i;
  if(o.x){const fx=o.x(i),l=el.querySelector('.scrl'),d=el.querySelector('.scrd'),rd=el.querySelector('.sread');if(l)l.style.left=fx+'%';if(d){d.style.left=fx+'%';d.style.top=o.y(i)+'%';}
   if(rd){rd.textContent=o.lab(i);rd.style.left=Math.max(14,Math.min(86,fx))+'%';}}
  if(o.show)o.show(i,el);hap('selection');};
 el.addEventListener('pointerdown',e=>{if(e.button)return;on=true;moved=false;x0=e.clientX;S.scrub=true;el.classList.add('on');idx=-1;show(pick(e));try{el.setPointerCapture(e.pointerId)}catch(x){}});
 el.addEventListener('pointermove',e=>{if(!on)return;if(Math.abs(e.clientX-x0)>6)moved=true;show(pick(e));});
 const end=e=>{if(!on)return;on=false;S.scrub=false;el.classList.remove('on');const i=idx,o=spec();idx=-1;if(o&&o.end)o.end(el);
  if(e.type==='pointerup'&&!moved&&o&&o.tap&&i>=0)o.tap(i);if(S.liveDirty){S.liveDirty=false;if(S.view==='live')renderLive();}if(S.resDirty){S.resDirty=false;if(S.view==='results')renderResults();}};
 ['pointerup','pointercancel','lostpointercapture'].forEach(k=>el.addEventListener(k,end));});}
// ---------------- the Sold moment, wins and the big hit
/* Cashing out gets the same drawn-check sheet as buying: what came back, the profit and a ticket stub. A loss gets a
   calm grey version (no alarm), like Kalshi's "Position closed" card. Shown for your own taps and, while the page is
   open, for sales smart sell or auto cash-out made by themselves. */
function soldSheet(o){const back=+o.back||0,cost=+o.cost||0,pl=back-cost,up=pl>=-0.004;hap(up?'success':'light');
 const id='sold:'+Date.now();S.nums[id]=0;
 modal(`<div class="okcard sold ${up?'':'okloss'}"><svg viewBox="0 0 84 84"><circle cx="42" cy="42" r="38"/>${up?'<path d="M27 43 L37 53 L58 32"/>':'<path d="M28 42 L56 42"/>'}</svg>
  <div class="stamp">${o.auto?'SOLD BY SMART SELL':'POSITION CLOSED'}</div><h3>${up?'Sold':'Closed'} · ${esc(o.label||'')}</h3>
  <div class="amt" data-num="${id}" data-v="${back.toFixed(2)}">${money(back)}</div>
  <div class="plp">${pl>=0?'+':'−'}${money(Math.abs(pl))} ${pl>=0?'profit':'loss'}${cost?` · ${pl>=0?'+':'−'}${Math.abs(Math.round(pl/cost*100))}%`:''}</div>
  <div class="tkt"><div>You paid<b>${money(cost)}</b></div><div>Got back<b>${money(back)}</b></div></div>
  <p>${up?(o.auto?'Smart sell took the offer because it beat holding.':'Locked in. The money is back in your balance.'):(o.auto?'Smart sell cut this one before it slid further.':'Some of it came back. On to the next one.')}</p>
  <div class="row" style="justify-content:center"><button class="btn acc" onclick="closeModal()">Done</button></div></div>`);
 rollNums($('#sheet'));clearTimeout(S.okT);S.okT=setTimeout(()=>{if($('#sheet .okcard.sold'))closeModal();},7000);}
function bigWin(c){const pays=+c.pays||0,cost=+c.cost||0,reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 document.querySelectorAll('.bigwin').forEach(e=>e.remove());const box=document.createElement('div');box.className='bigwin';
 box.innerHTML=`<i class="ring2"></i><i class="ring2 b"></i><div class="bw"><div class="ey">Big hit</div><div class="amt">${money(reduce?pays:0)}</div><div class="lb">${esc(c.label||'')}</div>
  <div class="mx">+${money(pays-cost)}${cost?` · ${(pays/cost).toFixed(1)}× your money`:''}</div><br><button class="btn acc">Nice</button></div>`;
 const close=()=>{box.classList.add('out');setTimeout(()=>box.remove(),380);};box.addEventListener('click',close);document.body.appendChild(box);
 hap('success');setTimeout(()=>hap('success'),650);if(!reduce){celebrate();setTimeout(celebrate,700);
  const a=box.querySelector('.amt'),t0=performance.now();const step=t=>{const k=Math.min(1,(t-t0)/1400),e=1-Math.pow(1-k,4);a.textContent=money(pays*e);if(k<1)requestAnimationFrame(step);};requestAnimationFrame(step);}
 setTimeout(()=>{if(box.isConnected)close();},9000);}
function isBig(c){const p=(+c.pays||0)-(+c.cost||0);return p>=50||(p>=15&&c.cost>0&&c.pays/c.cost>=5);}
function winMoment(c){S.momSeen=S.momSeen||{};if(S.momSeen['w:'+c.t])return;S.momSeen['w:'+c.t]=1;
 if(isBig(c))bigWin(c);else{celebrate();toast(`${c.label} won · +${money((c.pays||0)-(c.cost||0))}`,5000,'good');}}
/* What changed between two loads of Live while the page was open: a combo that won, one that was cashed out, and
   any sale smart sell made by itself (singles included, from its log). */
function liveMoments(prev,d){if(!d||d.error)return;S.momSeen=S.momSeen||{};const was={};((prev&&prev.combos)||[]).forEach(c=>was[c.t]=c.group);
 if(prev&&!prev.error)(d.combos||[]).forEach(c=>{if(was[c.t]!=='pending')return;
  if(c.group==='won')winMoment(c);
  else if(c.group==='cashed'&&!S.momSeen['s:'+c.t]){S.momSeen['s:'+c.t]=1;const auto=(d.sales||[]).some(x=>x.ticker===c.t);soldShow({label:c.label,back:c.back,cost:c.cost,auto});}});
 (d.sales||[]).forEach(x=>{if((x.at||0)<S.t0||S.momSeen['s:'+x.ticker])return;S.momSeen['s:'+x.ticker]=1;soldShow({label:x.combo,back:x.offer,cost:x.cost,auto:true});});}
function soldShow(o){if($('#modal').classList.contains('on')){const pl=(+o.back||0)-(+o.cost||0);toast(`Sold ${o.label} for ${money(o.back)} (${pl>=0?'+':'−'}${money(Math.abs(pl))})`,6000,pl>=0?'good':null);return;}soldSheet(o);}
S.t0=Date.now()/1000;
// ---------------- live events from the Mac
async function loadRecap(){const h=new Date().getHours();const day=new Date().toDateString();
 let seen='';try{seen=localStorage.getItem('cw_recap')||''}catch(e){}
 if(h<5||h>=14||seen===day){S.recap=null;return;}S.recap=await api('/app/api/recap').catch(()=>null);if(S.view==='live')renderLive();}
function recapCard(){const r=S.recap;if(!r||!r.bets||!r.bets.length)return '';
 return `<div class="card recap"><div class="rh"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">Yesterday</div>
  <b style="font-size:26px" class="${r.pl>=0?'up':'down'}" data-num="rc:pl" data-v="${Math.abs(r.pl||0).toFixed(2)}" data-pre="${(r.pl||0)>=0?'+':'−'}">${smoney(r.pl)}</b> <span class="m">${r.won} up · ${r.lost} down</span></div>
  <button class="x" onclick="try{localStorage.setItem('cw_recap',new Date().toDateString())}catch(e){};S.recap=null;renderLive()">✕</button></div>
  ${r.best&&r.best.pl>0?`<div class="mini">Best<b class="up">${esc(r.best.what)} ${smoney(r.best.pl)}</b></div>`:''}${r.worst&&r.worst.pl<0?`<div class="mini">Worst<b class="down">${esc(r.worst.what)} ${smoney(r.worst.pl)}</b></div>`:''}
  ${r.note?`<div class="m" style="font-size:12.5px;margin-top:6px">${esc(r.note)}</div>`:''}${streakNote(r)}</div>`;}
/* The streak note in the morning recap: days in a row the panel finished up, a flame and a dot per day (up to a week).
   One good day says what starts a streak; a down day says nothing (no guilt trip). */
function streakNote(r){const s=+r.streak||0;if(s<1)return '';
 if(s===1)return `<div class="streak"><span class="fl">🔥</span><span><b>1 day up.</b> Another good day today starts a streak.</span></div>`;
 return `<div class="streak hot"><span class="fl">🔥</span><span><b>${s} days up</b> in a row${s>=7?'. A whole week.':s>=3?'. Keep it going.':''}</span><span class="dots">${Array.from({length:Math.min(s,7)},(_,i)=>`<i style="--i:${i}"></i>`).join('')}</span></div>`;}
function okSheet(title,amt,sub,bad){hap(bad?'error':'success');modal(`<div class="okcard ${bad?'bad':''}"><svg viewBox="0 0 84 84"><circle cx="42" cy="42" r="38"/>${bad?'<path d="M30 30 L54 54 M54 30 L30 54"/>':'<path d="M27 43 L37 53 L58 32"/>'}</svg>
 <h3>${esc(title)}</h3>${amt!=null?`<div class="amt">${esc(amt)}</div>`:''}<p>${esc(sub||'')}</p><div class="row" style="justify-content:center"><button class="btn acc" onclick="closeModal()">Done</button></div></div>`);
 clearTimeout(S.okT);S.okT=setTimeout(()=>{if($('#sheet .okcard'))closeModal();},5200);}
function celebrate(){hap('success');const box=document.createElement('div');box.className='confetti';const cols=['#4f8cff','#3ecf8e','#ffb020','#ff6b9a','#b48cff'];
 for(let i=0;i<70;i++){const s=document.createElement('i');s.style.left=Math.random()*100+'vw';s.style.background=cols[i%cols.length];s.style.animationDelay=Math.random()*.4+'s';s.style.transform=`rotate(${Math.random()*360}deg)`;box.appendChild(s);}
 document.body.appendChild(box);setTimeout(()=>box.remove(),2600);}
function connect(){if(!window.EventSource)return;try{const es=new EventSource('/app/events');S.es=es;
 es.onopen=()=>{S.live_ok=true;S.esEver=true;stat();};
 es.onerror=()=>{S.live_ok=false;stat();};
 es.onmessage=e=>{let ev;try{ev=JSON.parse(e.data)}catch(x){return}
  if(ev.kind==='tick'){if(S.gameOpen&&$('#modal').classList.contains('on')){if(Date.now()-(S.gameAt||0)>4000)drawGame();return;}if(['live','games'].includes(S.view)&&Date.now()-(S.lastLoad||0)>4000&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}return;}
  S.events=(S.events||[]).concat([ev]).slice(-30);
  if(ev.kind==='settled'&&/ won$/.test(ev.text||'')){const c=((S.live&&S.live.combos)||[]).find(x=>x.t===ev.combo);if(c)winMoment(c);else celebrate();}
  if(['score','advice','alert','settled','idea'].includes(ev.kind)){const k=ev.kind+'|'+ev.text;S.seen=S.seen||{};if(Date.now()-(S.seen[k]||0)>90000){S.seen[k]=Date.now();toast(ev.text,ev.kind==='score'?6000:4500,ev.kind==='score'?(ev.good?'good':'bad'):null);}}
  if(S.gameOpen&&ev.ticker===S.gameOpen)drawGame();
  if(S.view==='live'||S.view==='games'){S.lastLoad=Date.now();load(S.view,ev.kind==='advice'||ev.kind==='settled'||ev.kind==='idea');}};
 }catch(x){}}
function stat(){netBanner();const el=$('#st');if(!el)return;el.innerHTML=`<span class="dot ${S.live_ok===false?'off':''}"></span>${S.live_ok===false?'Reconnecting…':'Mac · live'}`;}
// ---------------- settings
const UNITS={panel_budget:['$',''],take_profit:['','% of payout'],stake:['$',''],budget:['$',''],accept_pct:['','%'],live_min:['','%'],max_share:['','%'],bankroll:['$',''],refresh_secs:['','s'],cash_every:['',' min'],auto_cap:['',''],hedge_cap:['$','']};
const RANGES={panel_budget:[10,200,5],take_profit:[0,95,5],stake:[1,20,1],budget:[10,200,10],accept_pct:[50,100,5],live_min:[10,50,5],max_share:[20,100,10],bankroll:[100,5000,100],refresh_secs:[10,120,5],cash_every:[1,10,1],auto_cap:[1,10,1],hedge_cap:[25,500,25]};
function fmtv(k,v){if(k==='take_profit'&&+v===0)return 'Off';const u=UNITS[k]||['',''];return u[0]+(+v).toLocaleString()+u[1];}
function rng(k,label,sub,dis){const v=S.set.values[k],[lo,hi,st]=RANGES[k];const p=Math.round((Math.min(Math.max(v,lo),hi)-lo)/(hi-lo)*100);
 return `<div class="srow ${dis?'dim':''}"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><div class="rng"><input type="range" min="${lo}" max="${hi}" step="${st}" value="${v}" style="--p:${p}%"
  oninput="this.style.setProperty('--p',Math.round((this.value-${lo})/${hi-lo}*100)+'%');const o=this.nextElementSibling;o.textContent=fmtv('${k}',this.value);o.classList.remove('bump');void o.offsetWidth;o.classList.add('bump')" onchange="setv('${k}',+this.value)"><output>${fmtv(k,v)}</output></div></div>`;}
function tgl(k,label,sub,dis){return `<label class="srow ${dis?'dim':''}"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><input type="checkbox" class="tg" ${S.set.values[k]?'checked':''} onchange="setv('${k}',this.checked)"></label>`;}
function seg(k,label,sub,names){const v=S.set.values[k];return `<div class="srow"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><div class="seg">${names.map((n,i)=>`<button class="${v===i?'on':''}" onclick="setv('${k}',${i});renderSettings()">${esc(n)}</button>`).join('')}</div></div>`;}
/* Let it ride as a slider with five detents: each step ticks the phone, the name pops, the dots under it fill. */
function rideRow(names){names=names||[];const n=Math.max(2,names.length),v=Math.max(0,Math.min(n-1,+S.set.values.ride||0));
 return `<div class="srow"><div class="l"><b>Let it ride</b><small>How long to hold before cashing out. Cautious sells sooner, Bold later, Ride it out turns smart sell off.</small></div>
  <div class="rng rdet"><input type="range" id="ride" aria-label="Let it ride" min="0" max="${n-1}" step="1" value="${v}" style="--p:${Math.round(v/(n-1)*100)}%" oninput="rideIn(this)" onchange="setv('ride',+this.value);renderSettings()"><output>${esc(names[v]||'')}</output>
  <div class="tks">${names.map((_,i)=>`<i class="${i<=v?'on':''} ${i===v?'at':''}"></i>`).join('')}</div></div></div>`;}
function rideIn(el){const names=(S.set&&S.set.ride)||[],n=Math.max(2,names.length),v=+el.value;el.style.setProperty('--p',Math.round(v/(n-1)*100)+'%');
 const o=el.parentNode.querySelector('output');if(o){o.textContent=names[v]||'';o.classList.remove('bump');void o.offsetWidth;o.classList.add('bump');}
 el.parentNode.querySelectorAll('.tks i').forEach((t,i)=>{t.classList.toggle('on',i<=v);t.classList.toggle('at',i===v);});}
function stp(k,lo,hi){const v=S.set.values[k];return `<div class="stp"><button onclick="bump('${k}',-1,${lo},${hi})">−</button><span>${v}</span><button onclick="bump('${k}',1,${lo},${hi})">＋</button></div>`;}
function bump(k,d,lo,hi){const v=Math.min(hi,Math.max(lo,(S.set.values[k]||0)+d));if(v===S.set.values[k])return;setv(k,v);
 const t=k.split('_')[0];const mn=t+'_min',mx=t+'_max';if(S.set.values[mn]>S.set.values[mx]){const o=k===mn?mx:mn;setv(o,S.set.values[k]);}renderSettings();}
function scard(id,ic,title,sub,inner){return `<section class="scard" id="s-${id}"><header><span class="ic">${ic}</span><div><h3>${title}</h3>${sub?`<p>${sub}</p>`:''}</div></header>${inner}</section>`;}
const PEND={};let saveT=null;
function setv(k,v){hap('selection');S.set.values[k]=v;PEND[k]=v;saved('Saving…');clearTimeout(saveT);saveT=setTimeout(flush,450);
 if(['auto_sell','auto_hedge','include_live','auto_cash','size_auto'].includes(k))renderSettings();}
async function flush(){const vals=Object.assign({},PEND);for(const k in PEND)delete PEND[k];
 const r=await api('/app/api/settings',{lg:S.set.lg,values:vals}).catch(()=>({ok:false}));
 if(r.ok){S.build=null;saved('Saved','ok');if(r.synced===true)toast('Saved · the Mac watcher has it now.');else if(r.synced===false)toast('Saved here, but the Mac watcher didn\'t get it. Try again.');}
 else{saved('Not saved');toast(r.msg||'Couldn\'t save. Check the connection.');}}
function saved(t,c){const e=$('#saved');if(e){e.className='saved '+(c||'')+(c==='ok'?' bump':'');e.innerHTML=(t==='Saving…'?'<span class="spin"></span>':c==='ok'?'✓':'')+' '+t;}}
function sport(lg){S.slg=lg;S.set=null;renderSettings();load('settings');}
function settingsSkel(){const row='<div style="display:grid;grid-template-columns:1fr 46px;gap:14px;align-items:center"><div style="display:grid;gap:6px"><i style="height:13px;width:52%"></i><i style="height:10px;width:78%"></i></div><i style="height:26px;border-radius:99px"></i></div>';
 return `<div class="set"><div></div><div><div class="hsk" style="padding:2px 0 18px"><i style="height:24px;width:34%"></i><i style="height:12px;width:60%"></i></div><div class="setsk">${[3,4,2].map(n=>`<div><i style="height:15px;width:40%"></i>${row.repeat(n)}</div>`).join('')}</div></div></div>`;}
function renderSettings(){const m=$('#main');const d=S.set;if(!d){m.innerHTML=(S.lerr||{}).settings?`<div class="set"><div></div><div>${errCard('settings')}</div></div>`:settingsSkel();return;}
 const v=d.values,mode=d.mode,mac=S.mac;
 const cap=mode==='mix'?'Mix cap':mode==='day'?'Daily cap':'Weekend cap';
 const days=mode==='mix'?seg('mix_window','Games from','Which games Mixed sports can combine',d.windows)+tgl('next_day','Same day means tomorrow'):
  mode==='day'?tgl('next_day','Use tomorrow\'s games','Instead of today\'s'):
  tgl('thursday','Thursday games')+tgl('saturday','Saturday games')+tgl('monday','Monday games')+`<div class="srow"><div class="l"><small>Sunday is always in.</small></div></div>`;
 const tiers=(d.full?[['full','Full slate','Every game on the slate in one bet. You choose how many underdogs it picks.','upsets',0,8,'underdogs']]:[]).concat([['safer','Safer','Short combos, more likely to hit.',null,2,8,'games each'],['middle','Middle','The core of the mix.',null,2,12,'games each'],['moonshot','Moonshot','Long shots, big payouts.',null,2,16,'games each']]);
 const mix=`<div class="mixl">${tiers.map(([t,n,s,alt,lo,hi,unit])=>{const b=alt||t;
  return `<div class="mixr"><div><b>${n}</b><small>${s}</small></div><div class="mixs"><div><span>How many</span>${stp(t+'_count',0,10)}</div><div><span>${alt?'Underdogs':'Games each'}</span>${stp(b+'_min',alt?0:lo,hi)}<span>to</span>${stp(b+'_max',alt?0:lo,hi)}</div></div></div>`;}).join('')}</div>`;
 const secs=[['money','💵','Money'],['mix','🧩','Combo mix'],['games','🗓️','Games & picks'],['killer','🔥','Killer deals'],['maker','📌','Standing orders'],['cash','💸','Cash out & hedging'],['alerts','🔔','Notifications'],['haptics','📳','Haptics'],['mac','💻',LOCAL?'This Mac':'The Mac'],['keys','🔑','Accounts & keys']];
 const ago=s=>s<3600?Math.round(s/60)+' min':s<86400?Math.round(s/3600)+' hr':Math.round(s/86400)+' days';
 const macCard=LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Tailscale</span><b>${mac.ts?esc(mac.ts):'<span class="down">Not signed in</span>'}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · auto cash-out paused':''}</b></div>
   <div><span>Combo Hub passcode</span><b>${esc(mac.pass)}</b></div><div><span>Updates</span><b>${mac.auto_update?'Automatic':'Phone-approved · '+esc(mac.approved||'—')}</b></div></div>
   <div class="sact"><button class="btn acc" onclick="macUpdate(this)">Update now</button><button class="btn" onclick="macCode()">Phone pairing code</button><button class="btn" onclick="macPass()">Change passcode</button><button class="btn" onclick="S.showlog=!S.showlog;renderSettings()">${S.showlog?'Hide':'Show'} activity</button><button class="btn ghost" onclick="macDo('advanced',this)">Kalshi key & removal…</button><button class="btn ghost" onclick="hap('light');location.reload()">Reload the page</button></div>
   <label class="srow"><div class="l"><b>Install updates automatically</b><small>${mac.auto_update?'New versions install within about 10 minutes, no tap needed.':'Waits until your phone runs the new version and approves it.'}</small></div><input type="checkbox" class="tg" ${mac.auto_update?'checked':''} onchange="api('/app/mac',{a:'autoupdate',on:this.checked}).then(r=>{toast(r.msg);load('settings')})"></label>
   <div class="srow"><div class="l"><b>Alerts</b><small>${mac.last_push&&mac.last_push.at?`Last sent ${ago2(mac.last_push.at)} ago${mac.last_push.ok===false?' · <span class="down">ntfy refused it ('+mac.last_push.code+')</span>':''}: ${esc(mac.last_push.title)}`:'None sent since the Mac last restarted.'}${mac.quiet?' · Quiet hours now (10 PM–7 AM): only urgent ones go out.':''}</small></div><button class="btn" onclick="macDo('testpush',this)">Send test</button></div>
   ${httpsRow(mac)}${mac.history?`<div class="srow"><div class="l"><b>History on this Mac</b><small>${(mac.history.q||0).toLocaleString()} Kalshi quotes · ${(mac.history.t||0).toLocaleString()} live ticks · ${(mac.history.b||0).toLocaleString()} combos tracked</small></div></div>`:''}
   ${S.showlog?`<div class="logbox">${esc((mac.log||[]).join('\n'))}</div>`:''}`
  :!LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Newest</span><b style="display:block;word-break:normal">${mac.latest?(mac.latest===mac.engine?'<i style="font-style:normal;color:var(--yes)">Up to date</i>':esc(mac.latest)+(mac.waiting?' · waiting':' · installing soon')):'—'}${mac.checked?`<i class="m" style="display:block;font-style:normal;font-size:12px;font-weight:500;margin-top:2px">${Date.now()/1000-mac.checked<60?'checked just now':'checked '+ago(Math.round(Date.now()/1000-mac.checked))+' ago'}</i>`:''}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · paused':''}</b></div></div>
   <div class="srow"><div class="l"><small>Updates install ${mac.auto_update?'automatically within about 10 minutes':'after your phone approves them'}. The pairing code and passcode are on the Mac itself.</small></div><div class="sact" style="margin:0"><button class="btn" onclick="macCheck(this)">Check for an update now</button><button class="btn ghost" onclick="hap('light');location.reload()">Reload the page</button></div></div>`
  :`<div class="srow"><div class="l"><b>${LOCAL?'Couldn\'t read the Mac\'s status':'Couldn\'t reach the Mac'}</b><small>${LOCAL?'Reload in a moment.':'It may be asleep or restarting. Pull to refresh in a minute.'}</small></div><button class="btn ghost" onclick="hap('light');location.reload()">Reload the page</button></div>`;
 m.innerHTML=`<div class="set"><nav class="sidx">${secs.map(([id,ic,t])=>`<a href="#s-${id}" onclick="event.preventDefault();document.getElementById('s-${id}').scrollIntoView({behavior:'smooth'})">${ic} ${t}</a>`).join('')}<div class="sv">Planner ${esc(d.version)}</div></nav><div>
 <div class="shead"><div><h1>Settings</h1><p>Planner settings are per sport. Changes save as you go.</p></div><div class="saved" id="saved"></div></div>
 <div class="chips" style="margin-bottom:18px">${d.leagues.map(([k,n,ic])=>`<button class="chip ${k===d.lg?'on':''}" onclick="sport('${k}')">${ic} ${esc(n)}</button>`).join('')}</div>
 ${scard('money','💵','Money','What each combo costs and the price you\'ll accept from Kalshi.',
   rng('panel_budget',"Today's panel",'The most the daily panel spends in one day')+tgl('panel_live','Include games already under way','The panel may pick a game in progress when its live price beats its chance right now, worked out from a fresh score and clock (never the pre-game price), and checked again just before buying. Not EuroLeague, UFC or tennis: no live score we trust there.')+cutCard(S.panelCuts)+blockRow(d.blocks)+skimRow(S.skim)+rng('stake','Per combo')+rng('budget',cap,'The most the planner spends in one '+(mode==='day'?'day':mode==='mix'?'mix':'weekend'))+rng('accept_pct','Cut-off for your own combos','Kalshi prices paying less than this share of fair get marked')+tgl('size_auto','Bet more when the price is good','$3 near the cut-off, up to $10 well above fair'))}
 ${scard('mix','🧩','Combo mix','How many of each kind to build each day, and how big each one is.',mix)}
 ${scard('games','🗓️','Games & picks','Which games go in, and how picks are spread.',days+tgl('include_live','Include games already in progress','With extra safety checks')+rng('live_min','Live picks need at least','Chance to win right now',!v.include_live)
   +rng('max_share','One pick in at most','Share of combos for any single team')+tgl('hedge_close','Split coin-flip games','Put both sides of close games across combos')+tgl('dogs_late','Underdogs late','Favourites in the early games')+tgl('skip_news','Skip games with breaking news','When Kalshi and the sportsbooks disagree a lot'))}
 ${d.killer?scard('killer','🔥','Killer deals','Rare deals so good the Mac may buy them on its own.',killerCard(d.killer)):''}
 ${d.maker?scard('maker','📌','Standing orders','Buy orders resting under fair, managed by the Mac.',makerCard(d.maker)):''}
 ${scard('cash','💸','Cash out & hedging','When to take money off the table. The Mac watches these all day.',
   rng('bankroll','Betting bankroll','Bigger sure amounts against this get favoured')+rideRow(d.ride)
   +tgl('auto_cash','Keep a cash-out offer ready','On every live combo')+rng('cash_every','Fresh offers every','',!v.auto_cash)+rng('refresh_secs','Live updates every')
   +tgl('auto_sell','Auto cash-out','The Mac sells by itself, logged and capped')
   +tgl('smart_sell','Smart profit-taking','Sells when locking in beats the risk of holding, by sport: a one-goal hockey lead is fragile, an early NBA lead isn\'t',!v.auto_sell)
   +rng('take_profit','Take profit at','Sell once Kalshi offers this much of the payout, if it\'s at least 25% more than you paid',!v.auto_sell)
   +tgl('lock_trail','Lock in a run-up','After the offer reaches 60% of the payout, sell if it drops 20% from its high, while still a profit',!v.auto_sell)
   +tgl('stop_loss','Manual override: sell at a loss when a game turns','Off by default. When on, auto cash-out may sell a combo for less than you paid, but only late in a game (from about halfway), when a pick has fallen well below its chance before the game, and only after that has held for 3+ minutes. It never does it at halftime or a break, early in a game, or when the live score is missing or out of date. How late and how big a fall are learned league by league (see Results › Selling). Separately, the app learns when cutting a loss beats holding.',!v.auto_sell)
   +rng('auto_cap','Auto cash-outs a day, at most','',!v.auto_sell)
   +tgl('auto_hedge','Hedge instead when it locks in more','When a combo is down to its last game and a cash-out is due, buys the other side instead if that locks in more. It only does so while that game is in play on an up-to-date live score, never at halftime or a break, only if it locks in at least what you paid, only after that has held for 3+ minutes, and only after re-checking the price right before buying. Otherwise it waits or cashes out as usual.',!v.auto_sell)+tgl('prefer_hedge','Prefer hedging','Even at up to 5% less than the cash-out',!v.auto_sell)+rng('hedge_cap','Most to spend on one hedge','',!v.auto_sell))}
 ${scard('alerts','🔔','Notifications','From the Mac. Bundled to one every 30 minutes, quiet 10 PM–7 AM. Urgent ones come right away.',
   fidRow()+pushRow()+tgl('notify_value','Combos quoting at a fair price')+tgl('notify_price','A better price on a combo')+tgl('notify_cash','Cash-outs and hedges')+tgl('notify_news','Big line moves and news'))}
 ${hapCard()}
 ${scard('mac','💻',LOCAL?'This Mac':'The Mac',LOCAL?'The watcher and Combo Hub run here, and keep themselves up to date.':'',macCard)}
 ${scard('keys','🔑','Accounts & keys','Keys never leave the device they\'re on.',`<div class="kv"><div><span>Kalshi</span><b style="display:flex;align-items:center;gap:7px;word-break:normal">${d.keys.kalshi?'<span class="dot" style="flex:none"></span><span>Connected through the Mac</span>':'<span class="down">Not connected</span>'}</b></div><div><span>Sportsbook odds</span><b>${d.keys.odds?'Key saved':'Free sources only'}</b></div></div>
   <div class="srow"><div class="l"><small>Change the Mac's Kalshi key under This Mac › Kalshi key. The phone's keys are in the planner on the iPhone.</small></div>${S.inapp?'<a class="btn ghost" href="combo://phone">Phone screens</a>':''}</div>`)}
 </div></div>`;}
async function macCheck(b){btnBusy(b,'Checking…');const was=S.mac&&S.mac.engine;
 const r=await api('/app/mac-check',{}).catch(()=>({ok:false}));toast(r.msg||'Couldn\'t reach the Mac.',6000);if(!r.ok){btnState(b,false,'Couldn\'t reach the Mac');return;}
 for(const w of [20,25,25,30]){await new Promise(z=>setTimeout(z,w*1000));const m=await api('/app/mac-info',{}).catch(()=>null);
  if(m&&m.ok){S.mac=m;if(S.view==='settings')renderSettings();if(m.engine!==was&&was){toast('The Mac is now on '+m.engine+'.',5000);return;}if(m.latest===m.engine&&m.checked*1000>Date.now()-60e3){toast('Already on the newest version.',4000);return;}}}}
async function httpsCheck(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Checking Tailscale…';}
 const was=JSON.stringify((S.mac||{}).https||{});const r=await api('/app/mac',{a:'https'}).catch(()=>({ok:false}));
 if(!r.ok){toast(r.msg||'Couldn\'t reach the Mac.',5000,'bad');load('settings');return;}
 for(let k=0;k<20;k++){await new Promise(z=>setTimeout(z,3000));const m=await api('/app/mac',{a:'status'}).catch(()=>null);
  if(m&&m.ok){const h=m.https||{};if(JSON.stringify(h)!==was||k===19){S.mac=m;renderSettings();
   toast(h.state==='on'?'Secure address is on.':h.state==='need-enable'?(h.link?'One step left: tap Allow https, approve in Tailscale, then Check.':'One step left: enable HTTPS Certificates in Tailscale admin, then Check.'):h.state==='no-cli'?'Tailscale isn\'t installed on this Mac.':h.state==='issuing'?'Almost there: Tailscale is making the certificate.':'Not on yet: '+(h.detail||h.state||'no answer from Tailscale'),7000,h.state==='on'?'good':h.state==='need-enable'?null:'bad');return;}}}
 load('settings');}
/* Mac buttons: spin while working, then a check (or a cross) on the button itself before the card refreshes. */
async function macDo(a,b){if(a==='https')return httpsCheck(b);btnBusy(b);const r=await api('/app/mac',{a}).catch(()=>({ok:false}));
 toast(r.msg||(r.ok?'Done.':'That didn\'t work.'),5000);
 if(a==='update'&&r.ok){btnState(b,true,'Updating · back in about a minute',0);setTimeout(()=>location.reload(),70000);return;}
 btnState(b,!!r.ok,r.ok?(a==='testpush'?'Sent':'Done'):'Didn\'t work');setTimeout(()=>{if(S.view==='settings')load('settings');},1500);}
/* updating restarts the watcher, so it asks first */
function macUpdate(b){S.updBtn=b;modal(`<h3>Update the Mac now?</h3><p>It installs the newest version and restarts the watcher. Bets and settings stay as they are, and this page reloads by itself in about a minute.</p>
 <div class="row"><button class="btn" onclick="closeModal()">Not now</button><button class="btn acc" onclick="closeModal();macDo('update',S.updBtn)">Update now</button></div>`);}
async function macCode(){const r=await api('/app/mac',{a:'code'});modal(`<h3>Phone pairing code</h3><p>On the iPhone: planner › Settings › Watcher, paste this and Save. Only needed for a new phone or a reinstall.</p>
 <div class="code" id="pc">${esc(r.code||'')}</div><p class="m" style="font-size:12.5px">Hub: ${esc(r.hub||'Tailscale not signed in: the phone can only use the Mac at home.')}</p>
 <div class="row"><button class="btn" onclick="closeModal()">Close</button><button class="btn acc" onclick="navigator.clipboard.writeText($('#pc').textContent).then(()=>toast('Copied'))">Copy</button></div>`);}
function macPass(){modal(`<h3>Combo Hub passcode</h3><p>Needed on devices other than this Mac. Your phone's Open Combo Hub link signs in by itself.</p>
 <input class="txt" id="np" placeholder="At least 6 characters" autocomplete="new-password"><p class="m" id="perr" style="color:var(--no);min-height:18px"></p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="savePass()">Save passcode</button></div>`);setTimeout(()=>$('#np').focus(),50);}
async function savePass(){const r=await api('/app/mac',{a:'passcode',pass:$('#np').value});if(!r.ok){$('#perr').textContent=r.msg;return;}closeModal();toast(r.msg,5000);load('settings');}
// ---------------- refresh loop
window.__inapp=function(){S.inapp=true;if(S.view==='settings')renderSettings();};
if(location.hash.startsWith('#s=')){S.hl=location.hash.slice(3);S.view='live';history.replaceState(null,'',location.pathname);setTimeout(()=>{const e=document.getElementById('idea-'+S.hl);if(e)e.scrollIntoView({behavior:'smooth',block:'center'});},2500);}
chrome();render();load(S.view);connect();loadRecap();
setTimeout(async()=>{try{if(location.protocol!=='https:'||!window.PublicKeyCredential||S.inapp||localStorage.getItem('cw_fid_asked'))return;
 if(!(await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()))return;await fidLoad();
 if((S.fid.keys||[]).some(k=>k.rp===location.hostname))return;localStorage.setItem('cw_fid_asked','1');
 modal(`<h3>Unlock with Face ID?</h3><p>Skip the passcode next time. Your face never leaves your phone; the Mac only keeps a key that can't be used anywhere else.</p>
  <div class="row"><button class="btn" onclick="closeModal()">Not now</button><button class="btn acc" onclick="closeModal();fidOn()">Turn on Face ID</button></div>`);}catch(e){}},2500);
setInterval(()=>{if(document.hidden)return;if(S.live_ok&&Date.now()-(S.lastLoad||0)<30000)return;if(['live','games'].includes(S.view)&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}},12000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.view==='live')load('live');});
</script></body></html>
"""


def webapp_main():
    """Run the planner app for the browser (started by the watcher as its own process)."""
    import threading, types
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    # ---- stand-ins for Pythonista's modules, so the planner runs its phone code here
    ui = types.ModuleType("ui")

    class View:
        def __init__(self, **kw):
            self.subviews, self.hidden, self.on_screen = [], False, False
            self.frame = self.bounds = (0, 0, 390, 844)
            self.left_button_items = self.right_button_items = []
            for k, v in kw.items():
                setattr(self, k, v)

        def add_subview(self, v):
            self.subviews.append(v)

        def present(self, *a, **k):
            self.on_screen = True

        def close(self):
            pass

        def layout(self):
            pass

        def wait_modal(self):
            pass

    class WebView(View):
        delegate = None

        def load_html(self, h):
            pass

        def evaluate_javascript(self, js):
            return ""

    class ButtonItem:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    for name in ("Label", "Button", "ScrollView", "Slider", "Switch", "TextField", "TextView", "SegmentedControl"):
        setattr(ui, name, type(name, (View,), {}))
    ui.View, ui.WebView, ui.ButtonItem = View, WebView, ButtonItem
    ui.AUTOCAPITALIZE_NONE = 0
    ui.delay = lambda fn, t: threading.Timer(t, fn).start()
    ui.in_background = lambda fn: (lambda *a, **k: threading.Thread(target=fn, args=a, kwargs=k, daemon=True).start())
    ui.get_screen_size = lambda: (390, 844)

    console = types.ModuleType("console")

    def alert(title, message="", button1="OK", *a, **k):
        raise KeyboardInterrupt                     # no phone screen to ask: treat it as Cancel, never as a yes
    console.alert = alert
    console.set_idle_timer_disabled = lambda on: None
    console.hud_alert = lambda *a, **k: None
    notification = types.ModuleType("notification")
    notification.schedule = notification.remove_all_scheduled = lambda *a, **k: None
    clipboard = types.ModuleType("clipboard")
    _clip = {"t": ""}
    clipboard.set = lambda t: _clip.update(t=t)
    clipboard.get = lambda: _clip["t"]
    appex = types.ModuleType("appex")
    appex.is_running_extension = lambda: False
    sys.modules.update(ui=ui, console=console, notification=notification, clipboard=clipboard, appex=appex)

    A = load_engine()
    try:
        A.store_open(os.path.join(HOME, "combo_history.db"))
    except Exception as err:
        print("history off:", err, flush=True)
    A.latest_version = lambda: A.VERSION            # the watcher installs updates (phone-approved); not this copy
    A.install_update = lambda *a, **k: None
    A.write_helpers = lambda *a, **k: None
    A.schedule_buy_nudge = lambda *a, **k: None
    A.watcher_alive = lambda *a, **k: True          # the watcher does the automatic cash-outs, never this copy
    A.start_autosell_keeper = lambda *a, **k: None
    A.window_open = lambda: False                   # there is no phone window in this copy
    A.open_outside = lambda url: None
    A.tap_haptic = lambda *a, **k: None
    try:                                            # get data, odds and trades through the hub like the phone
        c = json.load(open(CONF))                   # does: one shared cache, one set of odds credits
        hub = {"topic": c["topic"], "secret": c["secret"], "hub": f"http://127.0.0.1:{c.get('hub_port', 8765)}"}
        A.hub_conf = lambda: hub                    # in memory only; never saved to the settings file
    except (OSError, ValueError, KeyError):
        pass
    _set_league = A.set_league

    def set_league(code):                           # settings reload with each sport: keep these
        _set_league(code)
        A.CFG["tour_pending"] = False
        A.CFG["built_once"] = True                  # you're not new: no first-time tips
    A.set_league = set_league
    set_league(A.LEAGUE["code"])

    # ---- Combo Hub's own screens: plain data in, actions out (same engine, same rules as the phone)
    alock = threading.RLock()
    LIVE = {"at": 0.0, "data": None}
    ACT = TapLock(alock)                     # taps take the lock through this: capped wait, rebuilds stand aside
    act_lock = ACT.hold
    BUILD = {"lg": None}

    def jsonable(x):
        return json.loads(json.dumps(x, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)))

    # How fresh the page's numbers are kept (display only: the watcher's own loop, smart sell, auto cash-out and
    # every buy/sell decision read their own data and are untouched by any of this).
    LIVE_FAST, LIVE_SLOW = 8, 30             # seconds a Live snapshot is served before a new one is built
    SCORES_FAST, SCORES_SLOW = 8, 30         # seconds this app keeps a league's scores (default was 45)
    A.SCORES_MAX_AGE = SCORES_FAST

    def games_live():
        """Is any game under way in the scores this app last read?"""
        now = time.time()
        for got in list(A.SCORES_BY.values()):
            if now - (got.get("at") or 0) > 300:
                continue
            for infos in list((got.get("by") or {}).values()):
                for i in infos if isinstance(infos, list) else [infos]:
                    if isinstance(i, dict) and str(i.get("state") or "") in ("in", "live"):
                        return True
        try:                                     # tennis, EuroLeague, UFC (Kalshi's live data, display only)
            return bool(A.kalshi_live_on())
        except Exception:
            return False

    def live_limit():
        return LIVE_FAST if LIVE.get("fast") else LIVE_SLOW

    def set_pace():
        """Quick score and snapshot refreshes only while a game is live; relaxed otherwise."""
        fast = games_live()
        LIVE["fast"] = fast
        A.SCORES_MAX_AGE = SCORES_FAST if fast else SCORES_SLOW

    def live_refresh():
        try:
            if ACT.waiting:                      # a tap is waiting for the lock: it goes first
                return
            api_live(warm=True)
        finally:
            LIVE["busy"] = False

    def api_live(fresh=False, warm=False):
        """The Live numbers. A snapshot younger than the limit is served as is; an older one is rebuilt first and
        the fresh one is served (waiting a few seconds at most), so the page isn't one refresh behind. If the
        build is stuck behind another job or fails, the last good copy is served."""
        if not fresh and not warm:
            LIVE["asked"] = time.time()
        limit = live_limit() - (2 if warm else 0)
        if not fresh and LIVE["data"] and time.time() - LIVE["at"] < limit:
            return live_extras(LIVE["data"])
        patient = not fresh and LIVE["data"] is not None and time.time() - LIVE["at"] < 600
        if not alock.acquire(timeout=6 if patient else -1):
            return live_extras(LIVE["data"])                    # busy elsewhere (e.g. pricing a combo): last good copy
        try:
            if fresh or not LIVE["data"] or time.time() - LIVE["at"] > limit:
                try:
                    if not A.MINE.get("all_games"):
                        games, days, sunday = A.week_games(A.fetch_markets())
                        A.MINE.update(all_games=games, days=days, sunday=sunday, notes=[], book={}, live=True)
                        try:
                            book, _ = A.fetch_book_odds(A.CFG.get("odds_key", ""))
                            A.MINE["book"] = book
                        except Exception:
                            pass
                    A.MINE["live"] = True
                    A.mine_page(live=True)
                    LIVE.update(at=time.time(), built=time.time(), data=jsonable(A.MINE.get("view") or {}))
                    set_pace()
                except Exception as err:
                    if not LIVE["data"]:
                        raise
                    log("live refresh failed, serving the last good copy:", type(err).__name__, err)
                    LIVE["at"] = time.time() - max(0, live_limit() - 5)       # try again in ~5s
            out = LIVE["data"]
        finally:
            alock.release()
        return live_extras(out)

    def freshness():
        """How old each stage of the numbers on screen is, so the page can say so and we can see where time goes."""
        now = time.time()
        ages, on = [], []                  # the age of each league's scores; leagues with a game under way are the ones that matter
        for got in list(A.SCORES_BY.values()):
            if not got.get("at") or now - got["at"] > 600:
                continue
            ages.append(now - got["at"])
            if any(isinstance(i, dict) and str(i.get("state") or "") in ("in", "live")
                   for infos in list((got.get("by") or {}).values()) for i in (infos if isinstance(infos, list) else [infos])):
                on.append(now - got["at"])
        scores = max(on) if on else (min(ages) if ages else None)
        # "live" is the real signal that a game is under way; "scores" alone is just the newest cache age when nothing is on
        return {"now": now, "built": LIVE.get("built") or LIVE["at"] or None, "scores": scores,
                "live": bool(on), "fast": bool(LIVE.get("fast"))}

    def live_extras(out):
        try:
            ideas = jsonable(A.live_suggestions()) if A.STORE.get("db") else []
        except Exception:
            ideas = []
        try:
            orders = jsonable(A.maker_summary()["open"]) if A.STORE.get("db") else []
        except Exception:
            orders = []
        try:
            pulse = A.pulse_series() if A.STORE.get("db") else []
        except Exception:
            pulse = []
        return dict(out, ideas=ideas, orders=orders, pulse=pulse, sales=recent_sales(),
                    auto_sell=bool(A.CFG.get("auto_sell")), fresh=freshness()) if isinstance(out, dict) else out

    def recent_sales(hours=3):
        """Read-only: what auto cash-out / smart sell sold lately (from its own log), so an open page can show the
        "Sold" moment for a sale it didn't make itself."""
        try:
            with open(A.SELL_LOG, encoding="utf-8") as f:
                tail = f.readlines()[-60:]
        except (OSError, AttributeError):
            return []
        out, cut = [], time.time() - hours * 3600
        for line in tail:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("result") == "sold" and (r.get("at") or 0) >= cut:
                out.append({k: r.get(k) for k in ("at", "combo", "ticker", "offer", "cost", "pays", "kind", "why")})
        return out[-10:]

    def side_view(s):
        return {"ticker": s["ticker"], "pick": s["pick"], "abbr": s.get("abbr", ""), "p": s.get("p"),
                "bid": s.get("bid"), "fair": s.get("fair"), "edge": s.get("edge"), "src": s.get("src"),
                "tie": bool(s.get("tie")), "event": s["event"]}

    def legset(c):
        return frozenset(l["ticker"] for l in c.get("legs") or [] if l.get("ticker"))

    def owned_sets():
        """Combos you already hold: bought here this session, plus pending ones on your Kalshi account."""
        out = set(BUILD.setdefault("bought", set()))
        try:
            v = A.ACCT_CACHE.get("value")
            for b in (v[0] if v else None) or []:
                if b.get("status") == "pending":
                    out.add(frozenset(l["ticker"] for l in b.get("legs") or [] if l.get("ticker")))
        except Exception:
            pass
        return out

    def combo_view(i, c, owned=None):
        est = A.est_offer(c)
        try:
            pred = A.predict_quote(c)
        except Exception:
            pred = None
        fx, heavy = A.exposure_factor(c["legs"])
        size = A.stake_for(pred["pct"], c["legs"]) if pred and A.CFG.get("size_auto") else None
        return {"i": i, "kind": c.get("kind"), "tier": c.get("tier"), "fair": c.get("fair"), "min": c.get("min"),
                "bought": legset(c) in (owned if owned is not None else owned_sets()),
                "kalshi": c.get("kalshi"), "est": est[0], "est_pct": est[1], "pred": pred, "size": size,
                "value_pct": c.get("value_pct"),
                "exposure": {"factor": fx, "team": heavy} if heavy else None,
                "chance": 1.0 / (c["fair"] / A.CTX.get("stake", A.CFG["stake"])) if c.get("fair") else None,
                "legs": [side_view(l) for l in c["legs"]],
                "offer": {k: v for k, v in (A.CTX.get("offers", {}).get(i) or {}).items() if k in ("pays", "stake", "at")} or None}

    def singles_view(games):
        """Every team's Kalshi price vs the sharp books' chance, after Kalshi's fee: best first."""
        out = []
        for e, sd in games.items():
            for x in sd:
                if x.get("tie") or not x.get("fair") or not x.get("p") or x.get("src") is None or A.started(x):
                    continue
                fee = A.single_fee(x["p"])
                edge = x["fair"] - x["p"] - fee
                up = min(0.99, x["p"] + 0.10)
                # A fair price drifts like a fair coin's running odds: the chance it ever trades up to `up`
                # before the game ends is fair / up (and it must, if the team wins).
                touch = min(1.0, x["fair"] / up)
                out.append({"ticker": x["ticker"], "pick": x["pick"], "p": x["p"], "fair": x["fair"],
                            "edge": round(edge, 4), "opp": A.opp_of(games, x), "idea": edge >= A.SINGLE_MIN_EDGE,
                            "ev": round(edge / (x["p"] + fee), 4), "touch": round(touch, 3), "win": x["fair"],
                            "profit": round(1 - x["p"] - fee, 4)})
        out.sort(key=lambda r: -r["edge"])
        return out[:8]

    SNAP = {}                                           # sport -> its last Build, ready to switch to

    def use_snap(lg):
        s = SNAP.get(lg)
        if not s or time.time() - s["at"] > 600:
            return False
        A.set_league(lg)
        A.CTX.clear()
        A.CTX.update(s["ctx"])
        BUILD.update(lg=lg, last=lg, note=s["note"], at=s["at"], days=s["days"], lines=s["lines"])
        return True

    def api_build(lg, rebuild=True, warming=False):
        import random
        BUILD.setdefault("seen", {})[lg] = time.time()
        if not warming:
            BUILD["touched"] = time.time()
        with alock:
            gone = not A.CTX.get("all_games")              # Settings for another sport clears the build's games
            if not rebuild and (BUILD["lg"] != lg or gone) and use_snap(lg):
                rebuild = False
            elif rebuild or BUILD["lg"] != lg or gone:
                A.set_league(lg)
                games, days, slate = A.week_games(A.fetch_markets())
                try:
                    book, note = A.fetch_book_odds(A.CFG.get("odds_key", ""))
                except Exception as err:
                    book, note = {}, f"No sportsbook lines ({type(err).__name__})."
                A.attach_fair(games, book)
                live_ok = set()
                try:                                    # games under way: live prices, same checks as the phone
                    bf = {e: [x["fair"] for x in sd] for e, sd in games.items() if sd[0].get("src")}
                    skipped, live = A.screen_live(games, bf)
                    live_ok = set(live) - set(skipped)
                except Exception:
                    pass
                combos, _ = A.build_combos(games, A.CFG.get("picks") or {}, random.Random()) if games else ([], None)
                try:                                    # the value search's best few go first
                    vals = A.value_combos(games, A.CFG["stake"], k=4, live_ok=live_ok) if games else []
                    have = {frozenset(l["ticker"] for l in c["legs"]) for c in combos}
                    combos = [c for c in vals if frozenset(l["ticker"] for l in c["legs"]) not in have] + combos
                except Exception as err:
                    print("value search:", err, flush=True)
                skip = owned_sets() | BUILD.setdefault("nope", set())      # yours already, or swapped away
                combos = [c for c in combos if legset(c) not in skip] or combos
                A.CTX.clear()
                A.CTX.update(combos=combos, all_games=games, games=dict(games), stake=A.CFG["stake"], offers={},
                             build_id=None)
                BUILD.update(lg=lg, last=lg, note=note, at=time.time(), days=days)
                try:                                    # spreads and totals, priced with the score model
                    codes = [c for c in A.MIX_SPORTS] if lg == "mix" else [lg]
                    BUILD["lines"] = [x for c in codes for x in A.line_candidates(c, everything=True)][:40]
                except Exception as err:
                    print("lines:", err, flush=True)
                    BUILD["lines"] = []
                SNAP[lg] = {"at": time.time(), "ctx": dict(A.CTX), "note": note, "days": days, "lines": BUILD["lines"]}
            games = A.CTX.get("all_games") or {}
            board = []
            on = {e for e, sides in games.items() if any(A.started(x) for x in sides)}
            for code in {A.ticker_sport(games[e][0]["ticker"]) for e in on if games[e]}:
                try:                                    # live scores for the games under way (cached ~45 s)
                    A.fetch_scores(code=code)
                except Exception:
                    pass
            try:                                        # tennis, EuroLeague, UFC: Kalshi's live data (display only)
                A.kalshi_live_refresh({e for e in on if A.ticker_sport(e) in A.KLIVE_SPORTS})
            except Exception:
                pass
            for e, sides in games.items():
                teams = [x for x in sides if not x.get("tie")]
                sc = None
                if e in on and teams:
                    try:
                        x = A.display_score({"ticker": teams[0]["ticker"], "side": "yes"}, pre=True)
                        sc = {k: x.get(k) for k in ("me", "opp", "abbr", "opp_abbr", "detail", "state")} if x else None
                        if sc and x.get("src") == "kalshi" and x.get("state") == "pre":   # due, but not begun yet
                            sc.update(me=None, opp=None, detail="Not started yet")
                    except Exception:
                        sc = None
                board.append({"event": e, "start": A.KICKOFF.get(e), "label": A.start_label(e), "sc": sc,
                              "sport": (A.ticker_sport(teams[0]["ticker"]) if teams else "") or "",
                              "first": teams[0]["ticker"] if teams else None,
                              "started": e in on,
                              "sides": [side_view(x) for x in sides], "tie": any(x.get("tie") for x in sides),
                              "value": max((x.get("edge") or -1) for x in teams) if teams else None})
            board.sort(key=lambda g: (g["started"], str(g["start"])))
            return jsonable({"lg": lg, "name": A.LG()["name"], "icon": A.LG().get("icon", ""), "note": BUILD.get("note", ""),
                             "stake": A.CTX.get("stake"), "budget": A.CFG.get("budget"), "cut": A.CFG.get("accept_pct"),
                             "spent": A.week_spend() if A.can_trade() else 0,
                             "board": board, "combos": [combo_view(i, c, own) for own in [owned_sets()] for i, c in enumerate(A.CTX.get("combos") or [], 1)],
                             "singles": singles_view(games), "lines": BUILD.get("lines") or [],
                             "days": {"mode": "mix" if A.is_mix() else "day" if A.by_day() else "week",
                                      **{k: A.CFG.get(k) for k in ("next_day", "thursday", "saturday", "monday", "mix_window")},
                                      "wed": sum(1 for x in (BUILD.get("days") or {}).values() if x == "Wednesday"),
                                      "windows": A.MIX_WINDOWS},
                             "leagues": [["mix", "Mix sports", A.LEAGUES.get("mix", {}).get("icon", "🎲")]]
                                        + [[k, A.SPORTS.get(k, {}).get("name", k.upper()), A.SPORTS.get(k, {}).get("icon", "")]
                                           for k in ("nfl", "nba", "nhl", "ahl", "ncaaf", "ncaamb", "ncaawb", "soccer", "ufc", "tennis", "euroleague")
                                           if k in A.SPORTS]})

    def api_results():
        with alock:
            bets, balance, note = A.fetch_account(max_age=30, every_league=True)
            bets = bets or []
            done = [a for a in bets if a["status"] in ("won", "lost", "cashed")]
            back = lambda a: a["back"] if a["status"] == "cashed" else a["pays"] if a["status"] == "won" else 0.0
            when = {}
            if A.STORE.get("db"):                       # the day each combo finished, from the Mac's record
                for r in A.store_rows("select combo, settled, first_seen from bets"):
                    when[r["combo"]] = (r["settled"], r["first_seen"])
            # Issue #91: date each bet by when the money actually moved (the cash-out sell, else Kalshi's
            # settlement, else the Mac's detection time st), not the game/slate date. Day and week come from
            # the one realized date in the Mac's local tz, so a bet can't land in different buckets.
            realized = {a["ticker"]: A.realized_buckets(a, when.get(a["ticker"], (None, None))[0]) for a in done}
            weeks = {}
            for a in done:
                wk = realized[a["ticker"]][1] or "?"
                w = weeks.setdefault(wk, {"week": wk, "pl": 0.0, "n": 0, "won": 0})
                w["pl"] += back(a) - a["cost"]
                w["n"] += 1
                w["won"] += a["status"] == "won"
            hist = []
            for a in sorted(done, key=lambda a: (realized[a["ticker"]][0] or "", when.get(a["ticker"], (0, 0))[0] or 0), reverse=True)[:400]:
                names = []
                for l in a.get("legs") or []:
                    t = l.get("ticker") or ""
                    nm = A.PICK_NAME.get(t) or A.sport_teams(A.ticker_sport(t) or "nfl").get(t.rsplit("-", 1)[-1]) or t.rsplit("-", 1)[-1]
                    names.append(("not " if l.get("side") == "no" else "") + nm)
                st, fs = when.get(a["ticker"], (None, None))
                day, week = realized[a["ticker"]]    # money-moved day and its week, one local-tz date (issue #91)
                cashed = A.realized_ts(a, st)         # the moment the money moved, for the detail sheet
                sports = sorted({A.ticker_sport(l.get("ticker") or "") or "" for l in a.get("legs") or []} - {""}) or (a.get("lgs") or [])
                hist.append({"t": a["ticker"], "status": a["status"], "cost": a["cost"], "back": round(back(a), 2),
                             "pl": round(back(a) - a["cost"], 2), "pays": a["pays"], "week": week, "day": day,
                             "bought": time.strftime("%Y-%m-%d", time.localtime(fs)) if fs else None,
                             "cashed": time.strftime("%Y-%m-%d", time.localtime(cashed)) if cashed else None,
                             "picks": names, "sports": sports})
            staked = sum(a["cost"] for a in done)
            ret = sum(back(a) for a in done)
            shadow = A.hub_call("shadow", timeout=10) if A.hub_conf() else None
            try:
                edge = A.edge_stats(bets)
            except Exception:
                edge = None
            return jsonable({"balance": balance, "settled": len(done), "won": sum(a["status"] == "won" for a in done),
                             "cashed": sum(a["status"] == "cashed" for a in done), "staked": staked,
                             "returned": ret, "pl": ret - staked, "roi": (ret - staked) / staked if staked else None,
                             "best": max((back(a) - a["cost"] for a in done), default=0),
                             "weeks": sorted(weeks.values(), key=lambda w: w["week"])[-12:], "history": hist,
                             "shadow": (shadow or {}).get("summary"), "accuracy": (shadow or {}).get("accuracy"),
                             "accuracy_text": A.accuracy_text((shadow or {}).get("accuracy") or {}),
                             "edge": edge, "backtest": A.backtest() if A.STORE.get("db") else None,
                             "model": model_summary(), "by_tier": by_tier(done), "proof": proof(bets, done),
                             "killer": A.killer_summary() if A.STORE.get("db") else None,
                             "cover": A.cover_summary() if A.STORE.get("db") else None,
                             "panel": A.panel_record() if A.STORE.get("db") else None})

    def proof(bets, done):
        """Is it working? Returns with a 95% range, prices vs kickoff, the paper record, and a verdict."""
        import math as _m, statistics as _st

        def ci(xs, weights=None):
            n = len(xs)
            if n < 2:
                return None
            if weights:
                tot = sum(weights)
                mean = sum(xs) / tot
                se = _st.pstdev(xs) * _m.sqrt(n) / tot
            else:
                mean = _st.mean(xs)
                se = _st.stdev(xs) / _m.sqrt(n)
            return {"n": n, "mean": round(mean, 4), "lo": round(mean - 1.96 * se, 4), "hi": round(mean + 1.96 * se, 4)}
        back = lambda a: a["back"] if a["status"] == "cashed" else a["pays"] if a["status"] == "won" else 0.0
        roi = ci([back(a) - a["cost"] for a in done], [a["cost"] for a in done]) if done else None
        close = A.load_json(A.CLOSING, {})
        clv = []
        for a in bets:
            probs = []
            for l in a.get("legs") or []:
                v = close.get(l.get("ticker") or "")
                if v is None:
                    probs = None
                    break
                probs.append(v if l.get("side", "yes") == "yes" else 1 - v)
            if probs and a["cost"] > 0:
                clv.append((a.get("full_pays") or a["pays"]) * _m.prod(probs) / a["cost"] - 1)
        clv_ci = ci(clv)
        sh = [b for b in A.shadow_state().get("bets", []) if b["status"] != "open"]
        paper = ci([b.get("payout", 0) - b["stake"] for b in sh], [b["stake"] for b in sh]) if sh else None
        n = len(done)
        if n < 30 and not (paper and paper["n"] >= 30):
            verdict, tone = f"Too early to tell: {n} settled combo{'s' * (n != 1)}. Results are mostly luck until about 50.", "wait"
        elif clv_ci and clv_ci["lo"] > 0 and paper and paper["mean"] > 0 and paper["n"] >= 50:
            verdict, tone = "The edge looks real: you beat the kickoff price with confidence and the paper record is up. Ready for the $300 test.", "good"
        elif roi and roi["hi"] < 0 and n >= 50:
            verdict, tone = "Losing money with confidence. Raise the fair-price cut-off or bet less until prices vs kickoff turn positive.", "bad"
        elif clv_ci and clv_ci["hi"] < 0 and clv_ci["n"] >= 40:
            verdict, tone = "Your prices are worse than kickoff prices on average. That's the clearest sign of no edge: lean on Value picks and buy ideas only.", "bad"
        else:
            verdict, tone = "Not proven either way yet. Keep sizes small; this updates as combos settle.", "wait"
        return {"roi": roi, "clv": clv_ci, "paper": paper, "verdict": verdict, "tone": tone}

    def model_summary():
        m = A.quote_model() if A.STORE.get("db") else None
        if not m:
            return None
        import math as _m
        groups = {k: round(_m.exp(m["mu"] + v), 3) for k, v in m["eff"].items()}
        return {"n": m["n"], "typical": round(_m.exp(m["mu"]), 3), "spread": round(m["sd"], 3),
                "by_picks": {k[2:]: v for k, v in groups.items() if k.startswith("n:")},
                "by_time": {k[2:]: v for k, v in groups.items() if k.startswith("h:")}}

    def by_tier(done):
        out = {}
        for a in done:
            n = len(a.get("legs") or [])
            k = "2 picks" if n <= 2 else "3 picks" if n == 3 else "4 picks" if n == 4 else "5–6 picks" if n <= 6 else "7+ picks"
            back = a["back"] if a["status"] == "cashed" else a["pays"] if a["status"] == "won" else 0.0
            r = out.setdefault(k, {"k": k, "n": 0, "cost": 0.0, "back": 0.0, "won": 0})
            r["n"] += 1
            r["cost"] += a["cost"]
            r["back"] += back
            r["won"] += a["status"] == "won"
        order = ["2 picks", "3 picks", "4 picks", "5–6 picks", "7+ picks"]
        return [out[k] for k in order if k in out]

    def api_panel(view="all"):
        """Today's panel (or one sport's), its record and the cut-offs."""
        if not A.STORE.get("db"):
            return {"panel": None}
        real = A.panel_get("real")
        p = real if view in ("all", "") else A.panel_get(f"view:{view}")
        sk = A.load_json(A.SIZING_FILE, {})
        return jsonable({"panel": p, "view": view, "record": A.panel_record(), "cutoffs": A.cutoff_summary(),
                         "rebuild": A.rebuild_status(),
                         "games": (real or {}).get("games") or (p or {}).get("games"),
                         "reserved": sk.get("reserved", 0), "skim_note": sk.get("skim_note"),
                         "approved_other": bool(real and real["status"] != "draft" and view not in ("all", "")),
                         "extra": A.panel_extras(real) if (real and real["status"] == "approved" and view in ("all", "")) else None})

    def api_orders():
        return jsonable(A.maker_summary() if A.STORE.get("db") else {})

    def api_combo(t):
        view = (api_live() or {}).get("combos") or []
        v = next((x for x in view if x["t"] == t), None)
        h = A.combo_history(t) if A.STORE.get("db") else {"offers": [], "ticks": {}}
        return jsonable({"combo": v, "history": h})

    def api_game(t):
        d = api_live() or {}
        leg, combos = None, []
        game = (t.split("-") + ["", ""])[1]                # the game's date+teams code, shared by its spread/total/winner
        for x in d.get("singles") or []:
            if x.get("t") == t:
                leg = x
        for v in d.get("combos") or []:
            for lg in v.get("legs") or []:
                if lg["ticker"] == t or (game and (lg["ticker"].split("-") + ["", ""])[1] == game):
                    leg = leg or lg
                    if v["group"] == "pending" and not any(c["t"] == v["t"] for c in combos):
                        combos.append({"t": v["t"], "label": v["label"], "p": v.get("p"), "pays": v["pays"],
                                       "cost": v["cost"], "legs": len(v["legs"])})
        for x in d.get("singles") or []:                    # your single bets and spreads on this game
            if game and (x["t"].split("-") + ["", ""])[1] == game and x.get("state") in ("live", "pre"):
                combos.append({"t": x["t"], "label": x["label"], "p": x.get("chance"), "pays": x["pays"],
                               "cost": x["cost"], "legs": 1, "single": True, "worth": x.get("worth"), "how": x.get("how")})
        story = A.game_story(t) if A.STORE.get("db") else {"ticks": [], "plays": []}
        wi = None
        if leg and leg.get("state") == "live" and leg.get("kind") in (None, "win"):
            ch = leg.get("live") if leg.get("live") is not None else leg.get("chance")
            try:
                wi = A.what_if(t, ch, leg.get("side", "yes"))
            except Exception:
                wi = None
            if wi and ch:
                disc = A.kalshi_discount(True)
                for c in combos:
                    if c.get("p") and not c.get("single"):
                        c["if_up"] = round(c["pays"] * c["p"] * wi["up"] / ch * disc, 2)
                        c["if_down"] = round(c["pays"] * c["p"] * wi["down"] / ch * disc, 2)
                        c["now"] = round(c["pays"] * c["p"] * disc, 2)
        # Live game strip (display only, football only): situation off the scoreboard + a richer ESPN summary.
        # Wrapped so a bad/missing feed shows nothing and never affects the rest of the page or the trading loop.
        detail = None
        try:
            if leg and leg.get("state") == "live" and A.ticker_sport(t) in ("nfl", "ncaaf"):
                full = A.leg_score(leg)                 # the full score row (has the ESPN event id and situation)
                if full and full.get("game"):
                    summ = A.game_detail(full["game"], A.ticker_sport(t)) or {}
                    sit = full.get("situation") or {}
                    if summ or sit:
                        detail = {"situation": sit, **summ}
        except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError) as err:
            # Narrowed so a genuine programming bug (NameError etc.) surfaces instead of being hidden; a bad/missing
            # feed just drops the strip. Logged once per game like the engine's live-score paths.
            A.klive_log_once("gamedetail", t, err)
            detail = None
        return jsonable({"leg": leg, "combos": combos, "story": story, "whatif": wi,
                         "detail": detail, "fresh": freshness()})

    def api_games():
        d = api_live() or {}
        games = d.get("games") or []
        out = []
        tick_of = {}
        for v in d.get("combos") or []:
            for lg in v.get("legs") or []:
                tick_of[(lg["name"], lg.get("opp"))] = lg["ticker"]
        def code(t):                                     # the game's date+teams code, shared by its winner/spread/total
            return (str(t or "").split("-") + ["", ""])[1]
        for g in games:
            tk = g.get("ticker") or tick_of.get((g["name"], g.get("opp")))
            out.append(dict(g, ticker=tk, singles=[]))
        # single bets, spreads and totals ride on a game card too: on the game they belong to, or a card of their own
        for x in d.get("singles") or []:
            if x.get("state") not in ("live", "pre", "over"):
                continue
            bet = {"t": x["t"], "label": x.get("label"), "kind": x.get("kind"), "cost": x.get("cost"),
                   "pays": x.get("pays"), "worth": x.get("worth"), "chance": x.get("chance"), "how": x.get("how")}
            g = next((g for g in out if code(x["t"]) and code(g.get("ticker")) == code(x["t"])), None)
            if g:
                g["singles"].append(bet)
                g["pays"] = round((g.get("pays") or 0) + (x.get("pays") or 0), 2)
                continue
            ch = x["live"] if x.get("live") is not None else x.get("chance")
            out.append({"name": x.get("name") or x.get("label"), "opp": x.get("opp") or "", "sport": x.get("sport"),
                        "combos": 0, "pays": x.get("pays") or 0, "ticker": x["t"], "kind": x.get("kind"),
                        "state": x["state"], "score": x.get("score"), "sc": x.get("sc"), "starts": x.get("starts"),
                        "phase": x.get("phase", ""), "note": x.get("note", ""), "short": x.get("short", ""),
                        "chance": ch, "singles": [bet]})
        for g in out:                                    # the chance line: what the Mac recorded for this pick lately
            tk = g.get("ticker")
            hist = A.store_rows("select ts, chance from ticks where ticker=? and ts > ? order by ts",
                                (tk, time.time() - 8 * 3600)) if tk and A.STORE.get("db") else []
            g["spark"] = [[round(r["ts"]), r["chance"]] for r in hist if r["chance"] is not None][-240:]
        out.sort(key=lambda g: (g.get("state") != "live", -(g.get("combos") or 0) - len(g.get("singles") or [])))
        return jsonable({"games": out, "at": d.get("at"), "fresh": freshness()})

    SET_KEYS = ("stake", "budget", "accept_pct", "size_auto", "full_count", "upsets_min", "upsets_max",
                "safer_count", "safer_min", "safer_max", "middle_count", "middle_min", "middle_max",
                "moonshot_count", "moonshot_min", "moonshot_max", "thursday", "saturday", "monday", "next_day",
                "mix_window", "max_share", "hedge_close", "include_live", "live_min", "dogs_late", "skip_news",
                "bankroll", "auto_cash", "refresh_secs", "cash_every", "ride", "auto_sell", "auto_cap", "auto_hedge",
                "prefer_hedge", "hedge_cap", "notify_value", "notify_price", "notify_cash", "notify_news", "killer_mode",
                "maker_mode", "take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "panel_live")

    def send_synced():
        """Settings the Mac's watcher uses go to it signed, exactly like a save on the phone."""
        try:
            c = json.load(open(CONF))
            body = json.dumps({"at": int(time.time()), "cfg": {k: A.CFG.get(k) for k in A.WATCHER_SYNCED}},
                              separators=(",", ":"))
            requests.post(f"{NTFY}/{c['topic']}-cfg", timeout=8, headers={"Cache": "yes"},
                          data=json.dumps({"body": body, "sig": sign(c["secret"], body)}).encode())
            return True
        except (OSError, ValueError, KeyError, requests.RequestException):
            return False

    def api_settings(lg, vals=None):
        with alock:
            if lg in A.LEAGUES and A.LEAGUE["code"] != lg:
                A.set_league(lg)
                BUILD["lg"] = None
            else:                                       # pick up changes the watcher or phone saved since
                A.CFG.update({k: v for k, v in A.load_json(A.SAVED, {}).items() if k in A.CFG and k not in A.KEY_FIELDS})
                if A.SAVED != A.MAIN_SAVED:
                    main = A.load_json(A.MAIN_SAVED, {})
                    A.CFG.update({k: main[k] for k in A.SHARED_KEYS if k in main and k not in A.KEY_FIELDS})
            synced = None
            if vals:
                before = {k: A.CFG.get(k) for k in A.WATCHER_SYNCED}
                for k, v in vals.items():
                    if k not in SET_KEYS or k not in A.CFG:
                        continue
                    cur = A.CFG[k]
                    if k in ("killer_mode", "maker_mode"):
                        if v in ("off", "watch", "on"):
                            A.CFG[k] = v
                        continue
                    try:
                        v = bool(v) if isinstance(cur, bool) else int(round(float(v))) if isinstance(cur, int) \
                            else float(v) if isinstance(cur, float) else None
                    except (TypeError, ValueError):
                        continue
                    if v is not None:
                        A.CFG[k] = v
                for t in ("upsets", "safer", "middle", "moonshot"):
                    if A.CFG.get(f"{t}_min", 0) > A.CFG.get(f"{t}_max", 99):
                        A.CFG[f"{t}_max"] = A.CFG[f"{t}_min"]
                A.save_cfg()
                BUILD["lg"] = None                      # the next Build uses the new settings
                SNAP.clear()
                LIVE["at"] = 0
                if before != {k: A.CFG.get(k) for k in A.WATCHER_SYNCED}:
                    synced = send_synced()
            mode = "mix" if A.is_mix() else "day" if A.by_day() else "week"
            return jsonable({"ok": True, "lg": A.LEAGUE["code"], "name": A.LG()["name"], "mode": mode,
                             "full": bool(A.LG().get("full")), "synced": synced,
                             "values": {k: A.CFG.get(k) for k in SET_KEYS if k in A.CFG},
                             "keys": {"kalshi": bool(A.CFG.get("kalshi_key_id")) or bool(A.hub_conf()),
                                      "odds": bool(A.CFG.get("odds_key"))},
                             "ride": [n for n, _ in A.RIDE], "windows": A.MIX_WINDOWS, "version": A.VERSION,
                             "killer": A.killer_summary() if A.STORE.get("db") else None,
                             "maker": A.maker_summary() if A.STORE.get("db") else None,
                             "blocks": A.order_blocks(),
                             "leagues": [[k, v.get("short") or v.get("name") or k.upper(), v.get("icon", "")]
                                         for k, v in A.LEAGUES.items()]})

    def api_act(d):
        try:
            return _api_act(d)
        except ActBusy:
            msg = "The app is busy updating. Nothing was done; try again in a moment."
            log("tap waited too long for the app lock:", str(d.get("a", ""))[:20])
            return {"ok": False, "msg": msg, "error": msg, "busy": True}

    def _api_act(d):
        a, t = str(d.get("a", "")), str(d.get("t", ""))
        was = BUILD.get("lg") or BUILD.get("last")
        if a in ("custom", "quote", "buy", "swap", "flip") and not A.CTX.get("all_games") and was:
            with act_lock():                                # the build's games were cleared (e.g. by Settings for another sport)
                if not use_snap(was):                       # the exact board you were looking at, if it's recent
                    if a != "custom":                       # never price or buy a different combo than the one shown
                        return {"ok": False, "msg": "The board was refreshed. Pull down to reload Build, then try again."}
                    try:
                        api_build(was, rebuild=False)             # your own picks are named by team, so a fresh board is fine
                    except Exception as err:
                        return {"ok": False, "msg": f"Couldn't load the games: {type(err).__name__}"}
        if a == "selfsell":
            if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t):
                return {"ok": False, "msg": "That bet isn't recognized."}
            A.set_self_sell(t, bool(d.get("on")))
            LIVE["at"] = 0
            return {"ok": True, "msg": "Got it. This one waits for you to sell it." if d.get("on") else
                    "Smart sell is watching this one now."}
        with act_lock():
            if a in ("ask", "askhalf", "go", "keep", "hedgego"):
                if t not in (A.MINE.get("hold") or {}):
                    return {"ok": False, "msg": "That combo isn't live any more."}
                A.cash_action("drop" if a == "keep" else a, t)
                LIVE["at"] = 0
                o = A.MINE["cash"].get(t) or {}
                flash = A.MINE.pop("flash", None)
                msg = A.re.sub("<[^>]+>", "", flash or "") or (o.get("error") or "")
                return {"ok": not o.get("error"), "msg": msg, "offer": o.get("offer"), "frac": o.get("frac", 1.0)}
            if a == "quote":
                i = int(d.get("i", 0))
                shown = d.get("legs")
                cur = (A.CTX.get("combos") or [])[i - 1] if 1 <= i <= len(A.CTX.get("combos") or []) else None
                if shown is not None and (not cur or sorted(map(str, shown)) != sorted(l["ticker"] for l in cur["legs"])):
                    return {"ok": False, "error": "The board was refreshed with new combos. Pull down to reload Build, then try again."}
                try:
                    r = A.get_offer(i, amount=d.get("stake"))
                    c = A.CTX["combos"][i - 1]
                    if not r.get("error") and r.get("pct") and A.CFG.get("size_auto") and not d.get("stake"):
                        want = A.stake_for(r["pct"], c["legs"])  # the price sets the size, less if you're heavy on a team
                        if want and abs(want - r["stake"]) > 0.01:
                            r2 = A.get_offer(i, amount=want)
                            if not r2.get("error"):
                                r = r2
                except (RuntimeError, PermissionError) as err:
                    return {"ok": False, "error": str(err).replace(" Try Swap.", "")}
                return jsonable({"ok": not r.get("error"), "clears": r.get("ok"), "cut": A.CFG["accept_pct"],
                                 **{k: r.get(k) for k in ("pays", "stake", "pct", "error")}})
            if a == "idea":                             # a buy idea from the Mac: rebuild it, get your own price
                rows = A.store_rows("select * from suggestions where id=?", (str(d.get("id", "")),))
                if not rows:
                    return {"ok": False, "gone": True, "msg": "That idea has expired."}
                row = rows[0]
                if row["n"] == 1:                           # a single game: today's price, straight from the book
                    tk = json.loads(row["legs"])[0]
                    if BUILD.get("lg") != row["lg"]:
                        api_build(row["lg"], rebuild=True)
                    side = next((x for sd in (A.CTX.get("all_games") or {}).values() for x in sd if x["ticker"] == tk), None)
                    dpt = A.book_depth(tk, max_age=0)
                    fair = (side or {}).get("fair") or row.get("pfair") or 0   # spreads/totals: the model's chance
                    if not fair or not dpt or dpt.get("ask") is None:
                        return {"ok": False, "gone": True, "msg": "Kalshi isn't listing that game right now."}
                    ask = dpt["ask"]
                    fee = A.single_fee(ask)
                    edge = fair - ask - fee
                    pct = fair / (ask + fee) if ask else 0
                    stake = A.edge_stake(pct, A.CFG.get("size_min", 3), A.CFG.get("size_max", 10), fair)
                    n = max(1, int(stake / (ask + fee)))
                    if dpt.get("ask_size"):             # Kalshi's sizes can be fractional now ("0.40")
                        n = min(n, int(dpt["ask_size"]))
                    if n < 1:
                        return {"ok": False, "msg": "Kalshi has under one contract for sale at that price right now."}
                    spent = A.week_spend() if A.can_trade() else 0
                    if spent + n * (ask + fee) > A.CFG["budget"] + 0.01:
                        return {"ok": False, "msg": A.cap_msg(spent, n * (ask + fee))}
                    return jsonable({"ok": True, "single": True, "price": ask, "n": n, "stake": round(n * (ask + fee), 2),
                                     "pays": float(n), "pct": pct, "edge": round(edge, 4), "fair": fair,
                                     "clears": edge >= A.SINGLE_MIN_EDGE * 0.6})
                if row["kick"] and row["kick"] < time.time() + 60:
                    return {"ok": False, "gone": True, "msg": "A game in it is starting, so this one's off the table."}
                if row.get("live") and row["ts"] < time.time() - 600:
                    return {"ok": False, "gone": True, "msg": "That idea had a game in progress and is more than 10 minutes old."}
                if BUILD.get("lg") != row["lg"]:
                    api_build(row["lg"], rebuild=True)
                k, why = A.add_own_combo(json.loads(row["legs"]))
                if not k:
                    return {"ok": False, "gone": True, "msg": why or "Kalshi isn't listing those games any more."}
                try:
                    r = A.get_offer(k)
                    c = A.CTX["combos"][k - 1]
                    if not r.get("error") and r.get("pct") and A.CFG.get("size_auto"):
                        want = A.stake_for(r["pct"], c["legs"])
                        if want and abs(want - r["stake"]) > 0.01:
                            r2 = A.get_offer(k, amount=want)
                            if not r2.get("error"):
                                r = r2
                except (RuntimeError, PermissionError) as err:
                    return {"ok": False, "msg": str(err).replace(" Try Swap.", "")}
                if r.get("error"):
                    return {"ok": False, "msg": r["error"]}
                return jsonable({"ok": True, "i": k, "pays": r["pays"], "stake": r["stake"], "pct": r.get("pct"),
                                 "clears": r.get("ok")})
            if a == "lineidea":                         # a spread or total from the Build board, as a buy idea
                x = next((x for x in BUILD.get("lines") or [] if x["ticker"] == str(d.get("t", ""))), None)
                if not x:
                    return {"ok": False, "msg": "That line isn't on the board any more."}
                pct = x["fair"] / (x["p"] + A.single_fee(x["p"]))
                stake = A.edge_stake(1 + (pct - 1) * 0.7, A.CFG.get("size_min", 3), A.CFG.get("size_max", 10), x["fair"])
                n = max(1, int(stake / (x["p"] + A.single_fee(x["p"]))))
                sid = A.store_suggestion({"legs": [dict(x, event=x.get("event") or "")], "fair": stake / x["fair"]},
                                         {"pays": float(n), "stake": round(n * (x["p"] + A.single_fee(x["p"])), 2)}, pct)
                if sid:
                    A.store_x("update suggestions set note=? where id=?",
                              (f"Priced from the sportsbook {x['kind']} of {x['book_line']:g} with a score model", sid))
                return {"ok": bool(sid), "id": sid}
            if a == "singleidea":                       # a single game from the Build board, as a buy idea
                tk = str(d.get("t", ""))
                x = next((x for sd in (A.CTX.get("all_games") or {}).values() for x in sd if x["ticker"] == tk), None)
                if not x or not x.get("fair") or not x.get("p"):
                    return {"ok": False, "msg": "That team isn't on the board any more."}
                pct = x["fair"] / (x["p"] + A.single_fee(x["p"]))
                stake = A.edge_stake(pct, A.CFG.get("size_min", 3), A.CFG.get("size_max", 10), x["fair"])
                n = max(1, int(stake / (x["p"] + A.single_fee(x["p"]))))
                sid = A.store_suggestion({"legs": [x], "fair": stake / x["fair"]},
                                         {"pays": float(n), "stake": round(n * (x["p"] + A.single_fee(x["p"])), 2)}, pct)
                return {"ok": bool(sid), "id": sid}
            if a == "singlebuy":
                rows = A.store_rows("select legs from suggestions where id=? and n=1", (str(d.get("id", "")),))
                if not rows:
                    return {"ok": False, "msg": "That idea has expired."}
                n, price = int(d.get("n") or 0), float(d.get("price") or 0)
                if not 1 <= n <= 1000 or not 0.01 <= price <= 0.97 or n * price > A.CFG.get("size_max", 10) * 1.6:
                    return {"ok": False, "msg": "That size or price isn't allowed."}
                try:
                    filled, err = A.buy_single(json.loads(rows[0]["legs"])[0], n, price)
                except Exception as e:                  # no clear answer: it may have gone through, never resent
                    LIVE["at"] = 0
                    log("single buy: outcome unknown:", type(e).__name__, str(e)[:160])
                    return {"ok": False, "check": True,
                            "msg": "Kalshi didn't answer clearly, so this may or may not have been bought. Check "
                                   "Kalshi before trying again; the app won't send it again."}
                LIVE["at"] = 0
                if err:
                    return {"ok": False, "msg": err}
                if filled <= 0:
                    return {"ok": False, "msg": f"Nobody was selling at {price * 100:.0f}¢ any more. Nothing was bought."}
                log_line = f"single bought: {filled:g} at {price:.2f}"
                print(log_line, flush=True)
                return {"ok": True, "msg": f"Bought {filled:g} contract{'s' * (filled != 1)} at {price * 100:.0f}¢: "
                                           f"pays {A.money(filled)} if it wins.", "pays": filled}
            if a == "buy":
                i = int(d.get("i", 0))
                print(f"buy combo {i}: accepting Kalshi's quote", flush=True)
                try:
                    r = A.accept_offer(i)
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    if A.order_outcome(err) == "refused":       # a definite refusal: nothing was bought
                        r = {"error": A.order_words(err)}
                    else:                                       # may have gone through (e.g. after the accept)
                        w = A.order_words(err) if isinstance(err, RuntimeError) else \
                            f"Something went wrong ({type(err).__name__})"
                        r = {"error": w if "may or may not" in w else
                             w.rstrip(".") + ". It may or may not have been bought: check Kalshi before trying again."}
                print(f"buy combo {i}:", r, flush=True)
                LIVE["at"] = 0
                if not r.get("error") and 1 <= i <= len(A.CTX.get("combos") or []):
                    BUILD.setdefault("bought", set()).add(legset(A.CTX["combos"][i - 1]))
                return jsonable({"ok": not r.get("error"), "msg": r.get("error") or "Bought.", "pays": r.get("pays")})
            if a == "panel_approve":
                ok, msg = A.panel_approve(d.get("ids"), d.get("view") or "all", d.get("at"))
                return {"ok": ok, "msg": msg}
            if a == "clear_block":                  # Pete lifts an "unknown outcome" block after checking Kalshi
                key = str(d.get("key", ""))[:200]
                if not A.clear_order_block(key):
                    return {"ok": False, "msg": "That block has already ended."}
                log("order block cleared from Settings:", key)
                return {"ok": True, "msg": "Cleared. New orders on that market can go again; the unclear one is never resent."}
            if a == "skim_moved":
                amt = A.skim_moved()
                return {"ok": True, "msg": f"Got it. The app counts your whole Kalshi balance again ({A.money(amt)} was set aside)."}
            if a == "panel_add":
                ok, msg = A.panel_add(d.get("ids") or [], d.get("view") or "")
                return {"ok": ok, "msg": msg}
            if a == "panel_look":
                ok, msg = A.panel_look_now()
                return {"ok": ok, "msg": msg, "rebuild": A.rebuild_status()}
            if a == "panel_restart":
                ok, msg = A.panel_restart()
                return {"ok": ok, "msg": msg}
            if a == "panel_cancel":
                ok, msg = A.panel_cancel()
                return {"ok": ok, "msg": msg}
            if a == "flip":                         # switch one pick to the other team, with a verdict
                i, tk = int(d.get("i", 0)), str(d.get("t") or "")
                if not 1 <= i <= len(A.CTX.get("combos") or []):
                    return {"ok": False, "msg": "That combo is gone. Tap Rebuild."}
                ok, note = A.flip_pick(i, tk)
                import html as _html
                text = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", note or ""))).strip()
                if not ok:
                    return {"ok": False, "msg": text}
                verdict = "good" if "Good flip" in note else "bad" if "Worse bet" in note else "mid"
                text = re.sub(r"^(Good flip|Worse bet|Trade-off)\s*", "", text).replace(" Tap Flip again to undo.", " Tap it again to undo.")
                A.CTX.get("offers", {}).pop(i, None)
                return jsonable({"ok": True, "verdict": verdict, "text": text, "combo": combo_view(i, A.CTX["combos"][i - 1])})
            if a == "swap":                         # "not that one": a different combo in its place
                import random
                i = int(d.get("i", 0))
                combos = A.CTX.get("combos") or []
                if not 1 <= i <= len(combos):
                    return {"ok": False, "msg": "That combo is gone. Tap Rebuild."}
                old = combos[i - 1]
                BUILD.setdefault("nope", set()).add(legset(old))
                have = {legset(c) for c in combos} | owned_sets() | BUILD["nope"]
                games = A.CTX.get("all_games") or {}
                pick = None
                for _ in range(8):
                    cands, _x = A.build_combos(games, A.CFG.get("picks") or {}, random.Random()) if games else ([], None)
                    new = [c for c in cands if legset(c) not in have]
                    if new:
                        pick = (next((c for c in new if c.get("tier") == old.get("tier") and len(c["legs"]) == len(old["legs"])), None)
                                or next((c for c in new if c.get("tier") == old.get("tier")), None) or new[0])
                        break
                if not pick:
                    return {"ok": False, "msg": "No other combo to offer from these games."}
                combos[i - 1] = pick
                A.CTX.get("offers", {}).pop(i, None)
                return jsonable({"ok": True, "combo": combo_view(i, pick)})
            if a == "custom":
                k, why = A.add_own_combo([str(x) for x in d.get("tickers") or []])
                if not k:
                    return {"ok": False, "msg": why}
                return {"ok": True, "i": k, "combo": jsonable(combo_view(k, A.CTX["combos"][k - 1]))}
            if a == "stake":
                v = max(1, min(100, float(d.get("stake") or A.CFG["stake"])))
                A.CTX["stake"] = v
                return {"ok": True}
        return {"ok": False, "msg": "Unknown action."}


    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", extra=None):
            body = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}") if 0 < n < 100_000 else {}
            except ValueError:
                return {}

        def do_GET(self):
            path, _, query = self.path.partition("?")
            local = self.headers.get("X-CW-Local") == "1"
            if path in ("/app", "/app/"):
                return self._send(200, SPA.replace("__CWLOCAL__", "true" if local else "false"), "text/html; charset=utf-8")
            if path.startswith("/app/api/"):
                from urllib.parse import parse_qs
                q = {k: v[0] for k, v in parse_qs(query).items()}
                try:
                    if path == "/app/api/live":
                        out = api_live(fresh=q.get("fresh") == "1")
                    elif path == "/app/api/build":
                        lg = q.get("lg") or "nba"
                        out = api_build(lg if lg in A.LEAGUES else "nba", rebuild=q.get("fresh") == "1")
                    elif path == "/app/api/results":
                        out = api_results()
                    elif path == "/app/api/analytics":
                        out = jsonable(A.analytics()) if A.STORE.get("db") else {}
                    elif path == "/app/api/recap":
                        out = jsonable(A.recap()) if A.STORE.get("db") else {}
                    elif path == "/app/api/panel":
                        out = api_panel(q.get("v") or "all")
                    elif path == "/app/api/orders":
                        out = api_orders()
                    elif path == "/app/api/combo":
                        out = api_combo(q.get("t") or "")
                    elif path == "/app/api/game":
                        out = api_game(q.get("t") or "")
                    elif path == "/app/api/games":
                        out = api_games()
                    elif path == "/app/api/pulse":          # read-only: the hero chart's Week range (pulse keeps 30 days)
                        try:
                            h = max(1, min(720, int(q.get("h") or 16)))
                        except ValueError:
                            h = 16
                        out = {"h": h, "pulse": A.pulse_series(hours=h, points=200) if A.STORE.get("db") else []}
                    elif path == "/app/api/settings":
                        out = api_settings(q.get("lg") or "")
                    else:
                        return self._send(404, "{}")
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    out = {"error": f"{type(err).__name__}: {err}"}
                return self._send(200, json.dumps(out))
            self._send(404, "{}")

        def do_POST(self):
            d = self._json()
            if self.path == "/app/api/settings":
                try:
                    out = api_settings(str(d.get("lg", "")), d.get("values") or {})
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    out = {"ok": False, "msg": f"Couldn't save: {type(err).__name__}: {err}"}
                return self._send(200, json.dumps(out, default=str))
            if self.path == "/app/api/act":
                try:
                    out = api_act(d)
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    out = {"ok": False, "msg": f"That didn't work: {type(err).__name__}: {err}"}
                return self._send(200, json.dumps(out, default=str))
            self._send(404, "{}")

    parent = os.getppid()

    def orphan_check():                             # the watcher restarted (e.g. an update): go too
        while True:
            time.sleep(5)
            if os.getppid() != parent:
                os._exit(0)
    threading.Thread(target=orphan_check, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", WEBAPP_PORT), H)
    srv.daemon_threads = True
    log(f"planner app for the browser ready (engine {A.VERSION})")
    threading.Thread(target=lambda: (time.sleep(3), api_live()), daemon=True).start()   # warm up the Live numbers

    def warmer():
        """Keeps pages ready: Live rebuilt a little ahead of its limit while a page is open and a game is on (every
        ~6s), every 20s otherwise, and the Build for the sports you've looked at in the last day rebuilt every 5
        minutes, only while nobody is tapping, so a page opens from what's already there."""
        def live_beat():
            asked = time.time() - LIVE.get("asked", 0) < 90          # a page has asked for Live lately
            pace = live_limit() - 2 if asked else 20
            if not LIVE.get("busy") and time.time() - LIVE["at"] > pace:
                LIVE["busy"] = True
                live_refresh()
        time.sleep(20)
        while True:
            try:
                live_beat()
                idle = time.time() - BUILD.get("touched", 0) > 30
                seen = BUILD.get("seen") or {"nba": 0, "nhl": 0}
                for lg, at in sorted(seen.items(), key=lambda x: -x[1]):
                    if not idle or time.time() - at > 86400 and at:
                        continue
                    if time.time() - SNAP.get(lg, {}).get("at", 0) < 300:
                        continue
                    if lg == BUILD.get("lg") and A.CTX.get("offers"):
                        continue                                # a price you asked for is still open
                    with alock:
                        cur, saved = BUILD.get("lg"), dict(A.CTX)
                        try:
                            api_build(lg, rebuild=True, warming=True)
                        finally:
                            if cur and cur != lg:              # put back what you were looking at
                                A.set_league(cur)
                                A.CTX.clear()
                                A.CTX.update(saved)
                                s = SNAP.get(cur)
                                if s:
                                    BUILD.update(lg=cur, note=s["note"], days=s["days"], lines=s["lines"])
                    break                                       # one sport per round
            except Exception as err:
                print("warm-up:", type(err).__name__, err, flush=True)
            for _ in range(5):                                  # 15s between Build rounds, Live checked every 3s
                time.sleep(3)
                try:
                    live_beat()
                except Exception as err:
                    print("warm-up (live):", type(err).__name__, err, flush=True)
    threading.Thread(target=warmer, daemon=True, name="warmer").start()
    srv.serve_forever()


def start_webapp():
    """Keep the browser copy of the planner running in its own process."""
    import subprocess

    def keep():
        while True:
            p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--webapp"],
                                 env=dict(os.environ, COMBOWATCH_HOME=HOME))
            p.wait()
            log("browser app stopped (code %s); restarting" % p.returncode)
            time.sleep(10)
    threading.Thread(target=keep, daemon=True, name="webapp").start()


STARTED = time.time()


def mac_tailscale_ip():
    import subprocess
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for ip, b in re.findall(r"inet (100\.(\d+)\.\d+\.\d+)", out):
        if 64 <= int(b) <= 127:
            return ip
    return ""


LATEST_SEEN = {}


def mac_settings(conf, web, d, tok):
    """Combo Hub's This Mac section: status, pairing code, passcode, update. Only from the Mac itself."""
    import subprocess
    a = str(d.get("a", ""))
    E = WATCHER.get("E")
    if a == "status":
        try:
            with open(os.path.join(HOME, "watcher.log"), encoding="utf-8", errors="replace") as fh:
                tail = [l.rstrip()[:200] for l in fh.readlines()[-12:]]
        except OSError:
            tail = []
        return {"ok": True, "watcher": WATCHER_VERSION, "engine": getattr(E, "VERSION", ""), "up": int(time.time() - STARTED),
                "ts": mac_tailscale_ip(), "pass": conf.get("web_pass", ""), "role": conf.get("role") or "main",
                "paused": bool(conf.get("paused")), "approved": (conf.get("approve") or {}).get("version", ""),
                "https": conf.get("https") or {}, "push_devices": len(PUSH.subs()), "push_ok": PUSH.ok(),
                "auto_update": auto_updates(conf), "last_push": dict(PUSHLOG),
                "quiet": not (7 <= time.localtime().tm_hour < 22),
                "history": E.store_rows("select (select count(*) from quotes) q, (select count(*) from ticks) t, "
                                        "(select count(*) from bets) b")[0] if getattr(E, "STORE", {}).get("db") else None,
                "log": tail}
    if a == "code":
        ip = mac_tailscale_ip()
        out = {"topic": conf["topic"], "secret": conf["secret"]}
        if ip:
            out["hub"] = f"http://{ip}:{conf.get('hub_port', 8765)}"
        return {"ok": True, "code": base64.urlsafe_b64encode(json.dumps(out).encode()).decode().rstrip("="),
                "hub": out.get("hub", "")}
    if a == "passcode":
        p = str(d.get("pass", "")).strip()
        if len(p) < 6 or len(p) > 64:
            return {"ok": False, "msg": "Use 6 to 64 characters."}
        conf["web_pass"] = p
        save = getattr(E, "save_json", None)
        if save:
            save(CONF, conf)
        else:
            with open(CONF, "w") as fh:
                json.dump(conf, fh)
        web.keep_only(tok)                                                     # everyone else signs in again
        return {"ok": True, "msg": "Passcode changed. Other devices sign in again with the new one."}
    if a == "update":
        d2 = os.path.join(HOME, "setup")
        os.makedirs(d2, exist_ok=True)
        r = requests.get(REPO + "watcher/install_mac.sh", params={"t": int(time.time())}, timeout=20)
        if not r.ok:
            return {"ok": False, "msg": "Couldn't download the update. Check this Mac's internet."}
        path = os.path.join(d2, "install_mac.sh")
        with open(path, "wb") as out:
            out.write(r.content)
        with open(os.path.join(HOME, "setup.log"), "a") as lg:
            subprocess.Popen(["bash", path, "--auto"], stdout=lg, stderr=lg, start_new_session=True)
        log("update started from Combo Hub")
        return {"ok": True, "msg": "Updating. Combo Hub reconnects in about a minute."}
    if a == "advanced":
        return {"ok": open_admin(), "msg": "Opening the Mac setup window…"}
    if a == "testpush":
        push(conf, "✅ Test from your Mac. If you see this, ntfy alerts are working.", title="Combo Hub test", priority="high",
             click="/app", web=False)
        sent = PUSH.send("Combo Hub test", "If you see this, Combo Hub notifications are working.", tag="test")
        return {"ok": True, "msg": f"Sent a test to ntfy ({'ok' if PUSHLOG.get('ok') else 'failed'})"
                                   + (f" and to {sent} Combo Hub device{'s' * (sent != 1)}." if sent else
                                      ". No devices are signed up for Combo Hub notifications yet.")}
    if a == "autoupdate":
        conf["auto_update"] = bool(d.get("on"))
        (E.save_json if E else (lambda p, c: json.dump(c, open(p, "w"))))(CONF, conf)
        log("automatic updates", "on" if conf["auto_update"] else "off (waits for the phone)")
        return {"ok": True, "msg": "Updates install automatically." if conf["auto_update"] else
                "Updates now wait until your phone approves them."}
    if a == "https":
        threading.Thread(target=tailscale_https, args=(conf, conf.get("hub_port", 8765)), daemon=True).start()
        return {"ok": True, "msg": "Checking Tailscale's https address…"}
    return {"ok": False, "msg": "Unknown action."}


def open_admin():
    """Open the Mac settings page (status, update, pairing code, passcode, Kalshi key, remove)."""
    import subprocess
    d = os.path.join(HOME, "setup")
    os.makedirs(d, exist_ok=True)
    try:
        for f in ("setup_wizard.py", "install_mac.sh"):
            r = requests.get(REPO + "watcher/" + f, params={"t": int(time.time())}, timeout=20)
            if r.ok:
                with open(os.path.join(d, f), "wb") as out:
                    out.write(r.content)
        subprocess.Popen([sys.executable, os.path.join(d, "setup_wizard.py"), "--installer", os.path.join(d, "install_mac.sh")],
                         env=dict(os.environ, CW_ADMIN="1"), start_new_session=True)
        return True
    except (OSError, requests.RequestException) as err:
        log("Mac settings didn't open:", err)
        return False


def webapp_proxy(handler, tok, method, path, body=b""):
    """Pass a signed-in request through to the browser copy of the planner on this Mac."""
    import urllib.request, urllib.error
    req = urllib.request.Request(f"http://127.0.0.1:{WEBAPP_PORT}{path}", data=body if method == "POST" else None,
                                 method=method, headers={"Content-Type": handler.headers.get("Content-Type") or "application/json",
                                                         "X-CW-Local": "1" if is_local(handler) else "0"})
    where = ""
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            code, ctype, data = r.status, r.headers.get("Content-Type", "application/json"), r.read()
            where = r.headers.get("X-CW-Where") or ""
    except urllib.error.HTTPError as err:
        code, ctype, data = err.code, "application/json", b"{}"
    except (urllib.error.URLError, OSError):
        code, ctype = 503, "text/html; charset=utf-8"
        data = (b"<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'>"
                b"<body style='font:17px -apple-system;padding:40px'>The planner is starting on your Mac. "
                b"<script>setTimeout(function(){location.reload()},3000)</script>")
    if ctype.startswith("text/html"):
        data = data.replace(b"__CWTOK__", tok.encode())
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Frame-Options", "DENY")
    if where:
        handler.send_header("X-CW-Where", where)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def accuracy_loop(odds, every=300):
    """Before each game: record every source's price (sportsbooks, Polymarket, Kalshi, the planner's
    blend); after it: score them. Over a season this says which source to trust, and the free blend
    re-weights itself from it once there are 150+ games of each."""
    time.sleep(90)
    last_resolve = 0
    while True:
        for code in SHADOW_LEAGUES:
            try:
                with odds.lock:
                    snap = odds.get(code, "")
                    soon = odds.soonest(snap)
                    if soon and soon - time.time() < 1500:          # a game starts within 25 minutes
                        H = odds.engine()
                        games, _, _ = H.week_games(H.fetch_markets())
                        H.attach_fair(games, H.load_book_state(snap))
                        n = H.accuracy_record(games, snap)
                        if n:
                            log(f"accuracy: recorded {n} {code} game(s) at kickoff")
            except Exception as err:
                log(f"accuracy {code} skipped:", type(err).__name__, err)
        if time.time() - last_resolve > 1800:
            last_resolve = time.time()
            try:
                with odds.lock:
                    n = odds.engine().accuracy_resolve()
                if n:
                    log(f"accuracy: scored {n} finished game(s)")
            except Exception as err:
                log("accuracy scoring skipped:", type(err).__name__, err)
        time.sleep(every)


def start_hub(conf, E, odds=None):
    """Serve the phone over Tailscale (or your home network). Every request must be sealed with the
    pairing secret, recent, and not a replay; anything else gets a bare 403."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    secret, cache, seen = conf["secret"], HubCache(E), {}
    web = Web(conf, E) if conf.get("web", True) else None
    odds = odds or HubOdds()
    builder = WebBuild(odds)
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
        if op == "weblink":
            return {"path": web.issue_once(), "base": (conf.get("https") or {}).get("url") or ""} if web else \
                {"err": "kalshi", "msg": "Web view is off."}
        if op == "shadow":
            return {"summary": E.shadow_summary(), "accuracy": E.accuracy_summary()}
        if op == "odds":
            return {"snap": odds.get(str(req.get("league") or "nfl"), str(req.get("key") or ""))}
        if op == "kalshi":
            method, path = str(req.get("method", "GET")).upper(), str(req.get("path", ""))
            if method not in ("GET", "POST", "PUT", "DELETE") or not HUB_PATHS.match(path):
                return {"err": "kalshi", "msg": "That request isn't allowed through the Mac."}
            if method != "GET":
                log("phone order:" if "/accept" in path or path.endswith("/orders") else "phone request:", method, path)
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

        def _form(self, n):
            from urllib.parse import parse_qs
            raw = self.rfile.read(n).decode("utf-8", "replace") if 0 < n < 10_000 else ""
            return {k: v[0] for k, v in parse_qs(raw).items()}

        def _html(self, code, page, cookie=None, location=None):
            body = page.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if cookie:
                self.send_header("Set-Cookie", f"cw={cookie}; Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict"
                                 + ("; Secure" if is_https(self) else ""))
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if web and self.path == "/app/admin":           # Mac settings: only from the Mac itself
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok or not is_local(self):
                    return self._send(403, b"")
                ok = open_admin()
                return self._send(200, json.dumps({"ok": ok}).encode())
            if web and self.path == "/app/push":            # iPhone notifications: this device's subscription
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok or not 0 <= n < 10_000:
                    return self._send(403, b"")
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    d = {}
                a = d.get("a")
                if a == "key":
                    out = {"ok": PUSH.ok(), "key": PUSH.public_b64() if PUSH.ok() else "", "n": len(PUSH.subs()),
                           "https": (conf.get("https") or {}).get("url") or ""}
                elif a == "sub":
                    out = {"ok": PUSH.add(d.get("sub"), d.get("label", ""))}
                elif a == "off":
                    PUSH.remove(str((d.get("sub") or {}).get("endpoint", "")))
                    out = {"ok": True}
                elif a == "test":
                    out = {"ok": True, "sent": PUSH.send("Combo Hub", "Notifications are on. Tap to open Combo Hub.", tag="test")}
                else:
                    out = {"ok": False}
                return self._send(200, json.dumps(out).encode())
            if web and self.path == "/app/mac-info":        # read-only status for any signed-in device
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok:
                    return self._send(403, b"")
                eng = WATCHER.get("E")
                info = {"ok": True, "watcher": WATCHER_VERSION, "engine": getattr(eng, "VERSION", ""),
                        "up": int(time.time() - STARTED), "role": conf.get("role") or "main",
                        "paused": bool(conf.get("paused")), "auto_update": auto_updates(conf),
                        "waiting": conf.get("waiting") or "", "latest": LATEST_SEEN.get("v", ""),
                        "checked": LATEST_SEEN.get("at") or 0}
                return self._send(200, json.dumps(info).encode())
            if web and self.path == "/app/mac-check":       # any signed-in device: look for an update right now
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok:
                    return self._send(403, b"")
                conf["update_now"] = True
                log("update check asked for from Combo Hub")
                return self._send(200, json.dumps({"ok": True, "msg": "The Mac is checking now. If there's a newer version, "
                                                   "it installs and restarts within about a minute."}).encode())
            if web and self.path == "/app/mac":             # This Mac (Settings): only from the Mac itself
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok or not is_local(self) or not 0 <= n < 10_000:
                    return self._send(403, b"")
                try:
                    out = mac_settings(conf, web, json.loads(self.rfile.read(n) or b"{}"), tok)
                except Exception as err:
                    log("Mac settings failed:", type(err).__name__, err)
                    out = {"ok": False, "msg": f"That didn't work: {type(err).__name__}"}
                return self._send(200, json.dumps(out).encode())
            if web and self.path.startswith("/app/"):
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok or not 0 <= n < 200_000:
                    return self._send(403, b"")
                return webapp_proxy(self, tok, "POST", self.path, self.rfile.read(n) if n else b"")
            if web and self.path == "/login":
                tok, msg = web.login(self._form(n))
                return self._html(303, "", cookie=tok, location="/") if tok else self._html(200, web.login_page(msg, web.rp_of(self)))
            if web and self.path.startswith("/auth/") and 0 <= n < 20_000:    # Face ID (passkeys)
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    d = {}
                rp = web.rp_of(self)
                if self.path == "/auth/begin":
                    keys = web.passkeys(rp)
                    out = {"ok": bool(keys), "challenge": web.challenge("get"), "rp": rp, "ids": [p["id"] for p in keys]}
                    return self._send(200, json.dumps(out).encode())
                if self.path == "/auth/finish":
                    tok, msg = web.passkey_login(d, rp)
                    body = json.dumps({"ok": bool(tok), "msg": msg}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    if tok:
                        self.send_header("Set-Cookie", f"cw={tok}; Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict; Secure")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    return self.wfile.write(body)
                tok = web.session(self)                      # adding and removing need a signed-in device
                if not tok or self.headers.get("X-CW") != tok:
                    return self._send(403, b"")
                if self.path == "/auth/list":
                    out = {"ok": True, "rp": rp, "keys": [{k: p.get(k) for k in ("id", "name", "added", "used", "rp")}
                                                           for p in web.passkeys()]}
                elif self.path == "/auth/reg-begin":
                    import secrets
                    out = {"ok": True, "challenge": web.challenge("reg"), "rp": rp,
                           "user": web.conf.setdefault("passkey_user", secrets.token_urlsafe(16)),
                           "exclude": [p["id"] for p in web.passkeys(rp)]}
                    E.save_json(CONF, web.conf)
                elif self.path == "/auth/reg-finish":
                    try:
                        pk = web.passkey_register(d, rp, str(d.get("name") or "Device"))
                        out = {"ok": True, "name": pk["name"]}
                    except Exception as err:
                        log("Face ID setup refused:", type(err).__name__, str(err)[:80])
                        out = {"ok": False, "msg": str(err) if "supported" in str(err) else "Couldn't add Face ID. Try again."}
                elif self.path == "/auth/remove":
                    web.conf["passkeys"] = [p for p in web.passkeys() if p["id"] != d.get("id")]
                    E.save_json(CONF, web.conf)
                    out = {"ok": True}
                else:
                    out = {"ok": False}
                return self._send(200, json.dumps(out).encode())
            if web and self.path == "/act":
                tok, form = web.session(self), self._form(n)
                if not tok or form.get("tok") != tok:      # signed in, and the button came from our own page
                    return self._html(403, web.login_page("Please sign in again."))
                if form.get("do") in ("bquote", "bbuy"):
                    try:
                        i = int(form.get("i", "0"))
                        msg = builder.quote(i) if form["do"] == "bquote" else builder.buy(i)
                    except Exception as err:
                        log("web build action failed:", type(err).__name__, err)
                        msg = f"That didn't work: {type(err).__name__}. Nothing was bought."
                    return self._html(200, web.page(tok, msg, builder.html(tok)))
                return self._html(200, web.page(tok, web.act(form), builder.html(tok)))
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
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path)
            if web and u.path in ("/sw.js", "/manifest.webmanifest", "/icon.png", "/apple-touch-icon.png"):
                import base64
                body, ctype = ((SW_JS.encode(), "text/javascript") if u.path == "/sw.js" else
                               (MANIFEST.encode(), "application/manifest+json") if u.path.endswith("webmanifest") else
                               (base64.b64decode(ICON_PNG), "image/png"))
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-cache" if u.path == "/sw.js" else "max-age=86400")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if web and u.path == "/app/events":           # live events, pushed as they happen
                if not web.session(self):
                    return self._send(403, b"")
                q = BUS.sub()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    self.wfile.write(b"retry: 3000\n\n")
                    self.wfile.flush()
                    end = time.time() + 600                 # the browser reconnects by itself
                    while time.time() < end:
                        try:
                            ev = q.get(timeout=15)
                            self.wfile.write(f"data: {json.dumps(ev, default=str)}\n\n".encode())
                        except Exception as err:
                            if type(err).__name__ != "Empty":
                                raise
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    BUS.unsub(q)
                return None
            if web and u.path == "/once":
                tok = web.use_once((parse_qs(u.query).get("t") or [""])[0])
                return self._html(303, "", cookie=tok, location="/") if tok else \
                    self._html(200, web.login_page("That link was already used or expired. Tap Open Combo Hub again."))
            if web and (u.path.startswith("/app/") or (u.path == "/app" and "frag=1" in u.query)):
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok:
                    return self._send(403, b"")
                return webapp_proxy(self, tok, "GET", self.path)
            if web and u.path in ("/", "/index.html", "/simple"):
                tok = web.session(self)
                if not tok and is_local(self):                  # on the Mac itself: no passcode
                    tok = web.new_session()
                    return self._html(303, "", cookie=tok, location=self.path)
                if not tok:
                    return self._html(200, web.login_page("", web.rp_of(self)))
                lg = (parse_qs(u.query).get("build") or [""])[0]
                note = ""
                if lg in dict(WEB_LEAGUES):
                    try:
                        builder.build(lg)
                    except Exception as err:
                        log("web build failed:", type(err).__name__, err)
                        note = f"Couldn't build just now ({type(err).__name__}). Try again in a minute."
                if u.path != "/simple" and not lg and conf.get("webapp", True):
                    return webapp_proxy(self, tok, "GET", "/app")
                return self._html(200, web.page(tok, note, builder.html(tok)))
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
    if web and conf.get("https_auto", True) and sys.platform == "darwin":
        threading.Thread(target=https_loop, args=(conf, port), daemon=True, name="https").start()
    ip = hub_address()
    log(f"hub serving the phone on port {port}" + (f" at http://{ip}:{port}" if ip else " (no Tailscale address found)")
        + (" · web view on the same address" if web else ""))
    return srv


def main():
    conf = load_conf()
    DEP["conf"] = conf
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
        if E.CFG.get("killer_mode") == "on":
            E.CFG["killer_mode"] = "watch"
        if E.CFG.get("maker_mode") == "on":
            E.CFG["maker_mode"] = "watch"
        save_settings(E, ("auto_sell", "killer_mode", "maker_mode"))
    if not E.can_trade():
        push(conf, "The watcher can't reach your Kalshi account: check the Key ID and key file on the watcher.",
             priority="high")
        log("no Kalshi access; waiting 10 minutes")
        time.sleep(600)
        return 1
    note, tries = None, 0
    while True:                                          # a real call, not just "the key file exists"
        bets, balance, note = E.fetch_account(max_age=0, every_league=True)
        if bets is not None:
            break
        tries += 1
        log(f"Kalshi check failed (try {tries}):", note)
        if tries == 4:                                   # about 2 minutes: worth telling you
            push(conf, f"The watcher couldn't read your Kalshi account: {note or 'no answer'}. It keeps "
                       "trying; if this lasts, check its key (run its installer with --new-key).", priority="high")
        time.sleep(min(30 * tries, 300))                 # usually just the network settling after a restart
    log(f"Kalshi OK: {sum(1 for b in bets if b['status'] == 'pending')} live combos, balance ${balance or 0:.2f}")
    import threading
    lock = threading.Lock()
    listen_for_settings(conf, E, lock)
    E.SCORES_MAX_AGE = 8                    # live scores every few seconds while games are on
    notifier = Notifier(conf, E)
    E.notify = notifier.add
    backup = conf.get("role") == "backup"            # a Pi kept as alerts-only backup for the Mac
    if backup:
        log("backup mode: alerts only, and only while the Mac is quiet; never trades")
    WATCHER["E"] = E
    try:
        E.store_open(os.path.join(HOME, "combo_history.db"))
        threading.Thread(target=history_loop, args=(E,), daemon=True, name="history").start()
        threading.Thread(target=ensure_crypto, daemon=True, name="crypto").start()
    except Exception as err:
        log("history off:", type(err).__name__, err)
    if conf.get("hub", sys.platform == "darwin"):      # the Mac hub; a Pi only if asked
        odds = HubOdds()
        start_hub(conf, E, odds)
        if conf.get("shadow", True):
            threading.Thread(target=shadow_loop, args=(odds, notifier), daemon=True, name="shadow").start()
            if not backup:
                threading.Thread(target=panel_loop, args=(odds, conf), daemon=True, name="panel").start()
                threading.Thread(target=rebuild_loop, args=(odds, notifier), daemon=True, name="rebuild").start()
        threading.Thread(target=accuracy_loop, args=(odds,), daemon=True, name="accuracy").start()
        if conf.get("webapp", True):
            start_webapp()
    threading.Thread(target=update_loop, args=(E, conf), daemon=True, name="updates").start()
    log("watcher", WATCHER_VERSION, "engine", E.VERSION, "started")
    push(conf, f"Watcher started (planner {E.VERSION}). It's keeping an eye on your combos.", priority="low", web=False)
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
            try:                                   # history + live events for open screens
                for ev in E.record_view(E.MINE.get("view")):
                    BUS.publish(ev)
                BUS.publish({"kind": "tick"})
            except Exception as err:
                log("record failed:", type(err).__name__, err)
            if t0 - last["sell"] > 60:
                last["sell"] = t0
                done = E.autosell_pass()
                if done:
                    log("auto-sell placed or moved:", done)
            if backup:
                E.CFG["auto_sell"] = False
                E.CFG["killer_mode"] = "off"
                E.CFG["maker_mode"] = "off"
                if t0 - last.get("mac", 0) > 60:
                    last["mac"] = t0
                    quiet = not mac_alive(conf)
                    if quiet != last.get("quiet", False):
                        push(conf, "🛟 Your Mac has gone quiet, so the Pi is sending alerts until it's back." if quiet
                             else "✅ Your Mac is back; the Pi is quiet again.", priority="high" if quiet else "low")
                    last["quiet"] = quiet
                if not last.get("quiet"):
                    notifier.q.clear()
                    E.notify = lambda msg: None
                else:
                    E.notify = notifier.add
            notifier.flush()
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
                    text = E.weekly_text(st)
                    try:
                        text += "\n" + E.shadow_text(E.shadow_summary())
                        text += "\n🎯 " + E.accuracy_text(E.accuracy_summary())
                    except Exception:
                        pass
                    push(conf, text, title="Weekly report", priority="low")
            if UPDATED.get("now"):
                return 0                          # launchd/systemd starts the new version
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
        if UPDATED.get("now"):
            return 0
        playing = any(lv for h in (E.MINE.get("hold") or {}).values() for _, lv, _ in h.get("legs_left") or [])
        every = 5 if playing else int(E.CFG.get("refresh_secs", 15))   # quicker while your games are on
        time.sleep(max(3, every - (time.time() - t0)))


if __name__ == "__main__":
    if "--webapp" in sys.argv:
        sys.exit(webapp_main() or 0)
    sys.exit(main() or 0)
