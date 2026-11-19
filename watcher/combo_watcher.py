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
WATCHER_VERSION = "2026.11.18.109"

# Settings the phone may change on the watcher. Keys and anything else are never accepted.
SYNCED = ("take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap",
          "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news",
          "killer_mode", "maker_mode", "accept_pct", "size_min", "size_max", "budget", "include_live", "live_min")


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


def push(conf, msg, title="Combo planner", priority="default", topic=None, pause_button=False, click=None):
    """A notification on your phone (ntfy app subscribed to your topic). With pause_button, it
    carries a "Pause auto cash-out" button that stops automatic sales until you resume. With click,
    tapping it opens that Combo Hub page."""
    headers = {"Title": title, "Priority": priority, "Tags": "moneybag"}
    if click and hub_base(conf):
        headers["Click"] = hub_base(conf) + click
    if pause_button:
        headers["Actions"] = f"http, Pause auto cash-out, {NTFY}/{conf['topic']}-pause, method=POST, body=pause, clear=true"
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
    return E


def auto_updates(conf):
    """Install new versions as soon as they're out, no approval needed. On by default on the Mac
    (you chose this); a Pi keeps waiting for the phone unless turned on."""
    return bool(conf.get("auto_update", sys.platform == "darwin"))


def update_if_newer(E, conf):
    """Install a newer engine and watcher from GitHub. With automatic updates on, any new version
    whose two files agree on it; otherwise only the exact files your phone installed (it sends
    their SHA-256, signed). Returns True if the watcher should restart."""
    try:
        latest = requests.get(REPO + "version.txt", params={"t": int(time.time())}, timeout=15,
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
        sb = requests.get(REPO + "nfl_combo_planner.py", params={"t": int(time.time())}, timeout=30).content
        wb = requests.get(REPO + "watcher/combo_watcher.py", params={"t": int(time.time())}, timeout=30).content
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


class HubCache:
    """Recent public reads, kept fresh in the background for whatever the phone asked for lately."""
    def __init__(self, E):
        self.E, self.lock = E, threading.Lock()
        self.data, self.wanted = {}, {}

    @staticmethod
    def ttl(url):
        if "espn.com" in url:
            return 8
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
                push(self.conf, msg, title="Buy idea", priority="default", click=url)
                threading.Thread(target=PUSH.send, args=("Buy idea", msg), kwargs={"url": url, "tag": "idea"},
                                 daemon=True).start()
                return True
            return True                                  # it's waiting in Combo Hub's Do now list
        kind = kind or ("cash" if ("cash" in low or "hedge" in low) else "info")
        auto_done = "auto" in low and ("cashed" in low or "hedged" in low or "sold" in low)
        if kind in self.SWITCH and not self.E.CFG.get(self.SWITCH[kind], True) and not auto_done:
            return False                              # switched off (actions it took are always reported)
        if kind in ("cash", "info") and any(w in low for w in self.URGENT):
            push(self.conf, msg.replace("Open the planner to confirm.", "Open the planner to cash out."),
                 pause_button=bool(self.E.CFG.get("auto_sell")))
            threading.Thread(target=PUSH.send, args=("Combo Hub", msg.replace("Open the planner to confirm.", "Tap to decide.")),
                             kwargs={"urgent": True, "tag": "urgent"}, daemon=True).start()
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
        push(self.conf, body, title=f"{len(msgs)} update{'s' * (len(msgs) != 1)}", priority="low")
        threading.Thread(target=PUSH.send, args=(f"{len(msgs)} update{'s' * (len(msgs) != 1)}", body),
                         kwargs={"tag": "digest"}, daemon=True).start()
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


# ---- https through Tailscale (a private address with a real certificate; needed for iPhone notifications)
def tailscale_cli():
    import shutil
    for p in (shutil.which("tailscale"), "/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/usr/local/bin/tailscale",
              "/opt/homebrew/bin/tailscale", "/usr/bin/tailscale"):
        if p and os.path.exists(p):
            return p
    return None


def tailscale_https(conf, port):
    """Ask Tailscale to serve Combo Hub at https://<this-mac>.<tailnet>.ts.net. If the tailnet hasn't
    allowed https yet, keep the one-time link that turns it on, for Settings > This Mac."""
    import subprocess
    cli = tailscale_cli()
    if not cli:
        conf["https"] = {"state": "no-cli"}
        return None
    try:
        st = json.loads(subprocess.run([cli, "status", "--json"], capture_output=True, text=True, timeout=15).stdout or "{}")
        name = ((st.get("Self") or {}).get("DNSName") or "").rstrip(".")
    except (OSError, ValueError, subprocess.SubprocessError):
        name = ""
    if not name:
        conf["https"] = {"state": "no-name"}
        return None
    url = f"https://{name}"
    try:
        r = requests.get(url + "/sw.js", timeout=8)
        if r.ok and b"Combo Hub" in r.content:
            conf["https"] = {"state": "on", "url": url}
            return url
    except requests.RequestException:
        pass
    try:
        p = subprocess.run([cli, "serve", "--bg", str(port)], capture_output=True, text=True, timeout=25)
        out = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as err:
        out = ((err.stdout or b"").decode() if isinstance(err.stdout, bytes) else (err.stdout or "")) + \
              ((err.stderr or b"").decode() if isinstance(err.stderr, bytes) else (err.stderr or ""))
    except (OSError, subprocess.SubprocessError) as err:
        out = str(err)
    link = re.search(r"https://login\.tailscale\.com/\S+", out)
    for _ in range(6):
        try:
            r = requests.get(url + "/sw.js", timeout=8)
            if r.ok and b"Combo Hub" in r.content:
                conf["https"] = {"state": "on", "url": url}
                log("https on:", url)
                return url
        except requests.RequestException:
            pass
        time.sleep(3)
    conf["https"] = {"state": "need-enable" if link else "failed", "link": link.group(0) if link else "",
                     "detail": out.strip()[-300:]}
    log("https not on yet:", conf["https"]["state"], conf["https"].get("link") or out.strip()[-160:])
    return None


# ---- iPhone notifications (Web Push from the home screen app; needs the https address)
def _b64u(b):
    import base64
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64u_dec(s):
    import base64
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
  const url = (e.notification.data && e.notification.data.url) || '/app';
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


def panel_loop(odds, conf, every=60):
    """Buys approved panel bets when they're due (rechecked, swapped if needed) and runs the paper panel."""
    time.sleep(180)
    n = 0
    while True:
        try:
            with odds.lock:
                H = odds.engine()
                out = H.panel_exec(log=log, paused=bool(conf.get("paused")), may_trade=H.can_trade())
                n += 1
                if n % 5 == 0:                            # results, exits and game-time prices
                    H.panel_settle()
                if H.rebuild_asked():                     # "Build a fresh panel" was tapped: do it now
                    H.panel_pass(log=log)
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
        time.sleep(every)


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


SHADOW_LEAGUES = ("nfl", "nba", "nhl", "ncaaf", "ncaamb")


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
                did = H.panel_pass(log=log) + H.panel_settle() + [f"cut-off {m}" for m in H.adjust_cutoffs()]
            if did:
                log("panel:", "; ".join(did))
            for m in did if notifier else []:
                if m.startswith("🆕"):
                    notifier.add(m, "idea")
        except Exception as err:
            log("panel skipped:", type(err).__name__, err)
        try:                                              # Sunday "cover the early games" paper test
            with odds.lock:
                did = odds.engine().cover_pass(log=log, alert=notifier.add if notifier else None)
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
</style></head><body><div class="box" id="box">
<img class="logo" src="data:image/png;base64,__ICON__" alt="">
<h1>Combo Hub</h1><p class="sub" id="sub">Your Mac's betting desk</p>
<div id="fidwrap" style="display:none"><button class="fid" id="fid" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2M9 9v1.5M15 9v1.5M12 9v4.5h-1M9.5 16c1.5 1.2 3.5 1.2 5 0"/></svg><span>Unlock with Face ID</span></button>
<div class="or">or use your passcode</div></div>
<form method="post" action="/login" id="f"><div class="field"><input name="pass" id="p" type="password" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="Passcode" required>
<button class="eye" type="button" aria-label="Show passcode" onclick="var p=document.getElementById('p');p.type=p.type==='password'?'text':'password'"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button></div>
<button class="go" id="go">Unlock</button></form>
<div class="msg" id="msg">__MSG__</div>
<div class="hint" id="hint">The passcode is in Settings › This Mac, on the Mac.</div>
</div><script>
const FID="__FID__",HTTPS="__HTTPS__",box=document.getElementById('box'),msg=document.getElementById('msg');
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
  if(r.ok){location.replace('/');return;}msg.textContent=r.msg||'Face ID didn\'t work.';box.classList.remove('shake');void box.offsetWidth;box.classList.add('shake');
 }catch(e){if(!auto)msg.textContent=(e&&e.name==='NotAllowedError')?'Face ID was cancelled. Use the passcode or try again.':'Face ID isn\'t available here. Use the passcode.';}
 btn.innerHTML=old;}
document.getElementById('fid').onclick=()=>unlock(false);
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
    import base64
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
        import base64
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
        import secrets, hmac as _h
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
# The Mac runs a separate copy of the planner (its own process) that believes it is on the phone:
# a stand-in "ui" module turns its window into a bridge. Pages it shows go to your browser; taps in
# the browser go back to it, exactly as on the phone. The hub (port 8765) signs you in and passes
# requests through to it on this Mac only (port 8766).
WEBAPP_PORT = 8766

BRIDGE_JS = r"""<script>
(function(){
var TOK="__CWTOK__", V=__CWV__, wrap=document.getElementById('cwwrap');
function post(p,b){return fetch(p,{method:'POST',credentials:'same-origin',
  headers:{'Content-Type':'application/json','X-CW':TOK},body:JSON.stringify(b)});}
function go(u){u=String(u);if(u.indexOf('combo://')===0){post('/app/nav',{u:u});}else{location.href=u;}}
window.__cwgo=go;
window.__cw={set href(u){go(u);},get href(){return location.href;}};
window.__cwadmin=function(b){b.textContent='Opening…';post('/app/admin',{}).then(function(){setTimeout(function(){b.textContent='⚙︎ Mac settings';},3000);});};
window.__cwtab=function(t){if(t!=='refresh')mark(t);else{var r=document.getElementById('cwref');if(r){r.classList.add('spin');setTimeout(function(){r.classList.remove('spin')},400);}}post('/app/tab',{t:t});};
function mark(t){if(!t)return;document.querySelectorAll('#cwbar button,#cwside nav button').forEach(function(b){b.classList.toggle('on',b.dataset.t===t);});}
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href]');if(!a)return;
  var h=a.getAttribute('href');if(h&&h.indexOf('combo://')===0){e.preventDefault();go(h);}},true);
async function newPage(v){              /* swap the page in place: no white flash, no reload */
  var r=await fetch('/app/classic?frag=1',{credentials:'same-origin',headers:{'X-CW':TOK}});
  var h=await r.text();V=v;
  if(window.__load){window.__load(h);}else{document.open();document.write(h);document.close();}
  if(!wrap.isConnected)document.body.appendChild(wrap);
  mark(r.headers.get('X-CW-Where')||'');}
async function poll(){for(;;){try{
  var r=await fetch('/app/poll?v='+V,{credentials:'same-origin',headers:{'X-CW':TOK}});
  if(r.status==403){location.href='/';return;}
  var d=await r.json();
  if(d.v!==V){await newPage(d.v);}
  if(d.where)mark(d.where);
  for(const j of d.js){var out='';try{out=(0,eval)(j.code);}catch(err){out='';}
    if(!wrap.isConnected)document.body.appendChild(wrap);
    if(j.w)post('/app/result',{id:j.id,value:(out===undefined||out===null)?'':String(out)});}
}catch(err){await new Promise(function(r){setTimeout(r,1500);});}}}
poll();
})();
</script>"""

ICONS = {
    "mine": "<svg viewBox='0 0 24 24'><circle cx='12' cy='12' r='5' fill='currentColor'/><circle cx='12' cy='12' r='9.5' fill='none' stroke='currentColor' stroke-width='1.6' opacity='.45'/></svg>",
    "build": "<svg viewBox='0 0 24 24'><path d='M12 4.5v15M4.5 12h15' stroke='currentColor' stroke-width='2.2' stroke-linecap='round'/></svg>",
    "results": "<svg viewBox='0 0 24 24'><path d='M5 19V11M12 19V5M19 19v-6' stroke='currentColor' stroke-width='2.4' stroke-linecap='round'/></svg>",
    "settings": "<svg viewBox='0 0 24 24'><circle cx='12' cy='12' r='3.2' fill='none' stroke='currentColor' stroke-width='1.9'/><path d='M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8' stroke='currentColor' stroke-width='1.9' stroke-linecap='round'/></svg>",
}

SHELL_CSS = """<style>
/* ---------- Combo Hub: the planner's screens, dressed for the browser ---------- */
html{-webkit-text-size-adjust:100%}
body{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;font-feature-settings:"tnum" 1,"ss01" 1;
 padding-bottom:calc(76px + env(safe-area-inset-bottom))!important;-webkit-tap-highlight-color:transparent}
@media (display-mode:standalone){body{padding-top:env(safe-area-inset-top)!important}}
h1{letter-spacing:-.025em}
.card,.game,.stat,details.lostbox,.quote{transition:transform .18s cubic-bezier(.2,.7,.3,1),box-shadow .18s,background-color .18s}
.stat b{font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.btn,button,.tabs button,summary,label.row,.pickrow .seg button{transition:background-color .15s,color .15s,transform .1s,opacity .15s}
.btn:active,.tabs button:active{transform:scale(.97)}
:focus-visible{outline:2px solid var(--accent,#0a84ff);outline-offset:2px;border-radius:10px}

/* bottom tab bar (phone) */
#cwbar{position:fixed;left:0;right:0;bottom:0;z-index:9999;display:flex;justify-content:space-around;
 padding:7px 6px calc(5px + env(safe-area-inset-bottom));
 background:color-mix(in srgb,var(--bg,#000) 72%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);
 backdrop-filter:saturate(180%) blur(24px);border-top:.5px solid var(--line,rgba(84,84,88,.6))}
#cwbar button{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;background:none;border:0;
 color:var(--muted,#98989f);font:600 10.5px -apple-system,system-ui;letter-spacing:.01em;padding:3px 0;cursor:pointer}
#cwbar button svg{width:26px;height:26px;transition:transform .2s cubic-bezier(.2,.7,.3,1.4)}
#cwbar button.on{color:var(--accent,#0a84ff)}
#cwbar button.on svg{transform:scale(1.06)}
#cwref{position:fixed;top:calc(12px + env(safe-area-inset-top));right:14px;z-index:9999;width:38px;height:38px;border-radius:50%;
 display:flex;align-items:center;justify-content:center;border:.5px solid var(--line,rgba(84,84,88,.6));
 background:color-mix(in srgb,var(--card,#1c1c1e) 82%,transparent);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);
 color:var(--accent,#0a84ff);cursor:pointer;transition:transform .35s cubic-bezier(.2,.7,.3,1)}
#cwref:active,#cwref.spin{transform:rotate(200deg)}
#cwside{display:none}

/* ---------- laptop & desktop: sidebar, centred content, cards in a grid ---------- */
@media (min-width:900px){
 body{padding:0 40px 56px 292px!important;font-size:16px}
 #cwbar{display:none}
 #cwside{display:flex;flex-direction:column;position:fixed;inset:0 auto 0 0;width:252px;z-index:9999;padding:26px 14px 18px;
  background:color-mix(in srgb,var(--card,#1c1c1e) 55%,var(--bg,#000));border-right:.5px solid var(--line,rgba(84,84,88,.6));
  -webkit-backdrop-filter:blur(30px);backdrop-filter:blur(30px)}
 #cwside .brand{display:flex;align-items:center;gap:11px;padding:0 10px 26px;font:700 19px -apple-system,system-ui;
  letter-spacing:-.02em;color:var(--ink,#fff)}
 #cwside .mark{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;
  background:linear-gradient(145deg,#2f8cff,#7a5cff 60%,#c84bff);box-shadow:0 4px 14px rgba(80,90,255,.35)}
 #cwside .mark svg{width:20px;height:20px}
 #cwside nav{display:flex;flex-direction:column;gap:3px}
 #cwside nav button{display:flex;align-items:center;gap:12px;width:100%;padding:10px 12px;border:0;border-radius:10px;
  background:none;color:var(--ink,#fff);font:500 15px -apple-system,system-ui;cursor:pointer;text-align:left;opacity:.82}
 #cwside nav button svg{width:21px;height:21px;color:var(--muted,#98989f)}
 #cwside nav button:hover{background:var(--card2,#2c2c2e);opacity:1}
 #cwside nav button.on{background:var(--accentbg,rgba(10,132,255,.18));color:var(--accent,#0a84ff);opacity:1;font-weight:600}
 #cwside nav button.on svg{color:var(--accent,#0a84ff)}
 #cwside .foot{margin-top:auto;padding:12px 12px 0;border-top:.5px solid var(--line,rgba(84,84,88,.6));
  font:500 12px -apple-system,system-ui;color:var(--muted,#98989f);line-height:1.5}
 #cwside .foot button{margin-top:10px;display:flex;align-items:center;gap:8px;border:0;background:var(--card2,#2c2c2e);
  color:var(--ink,#fff);font:600 13px -apple-system;padding:8px 12px;border-radius:9px;cursor:pointer}
 #cwside .foot button:hover{background:var(--press,#3a3a3c)}
 #cwref{display:none}
 body>*:not(#cwwrap):not(script):not(.ptr){max-width:1040px;margin-left:auto!important;margin-right:auto!important}
 body:has(#budgetline)>*:not(#cwwrap):not(script):not(.ptr){max-width:760px}
 header{padding-top:38px!important}
 h1{font-size:40px!important}
 .tabs,.seg{max-width:560px}
 .stats{gap:16px!important}
 .stat{padding:20px 22px!important;border-radius:18px!important}
 .stat b{font-size:30px!important}
 section#combos:has(>.card~.card),section:has(>.card~.card~.card){display:grid!important;
  grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px;align-items:start}
 section:has(>.card~.card)>:not(.card){grid-column:1/-1}
 section:has(>.card~.card)>.card{margin:0!important}
 .card,.game,.stat{border:.5px solid var(--line,rgba(84,84,88,.45))}
 .card:hover{transform:translateY(-2px);box-shadow:0 10px 30px rgba(0,0,0,.28)}
 .row:hover,label.row:hover,summary:hover{background:color-mix(in srgb,var(--card2,#2c2c2e) 60%,transparent)}
 a,button,summary,label,.btn{cursor:pointer}
 ::-webkit-scrollbar{width:10px}::-webkit-scrollbar-thumb{background:var(--track,#444);border-radius:10px;border:3px solid var(--bg,#000)}
}
@media (min-width:1500px){body>*:not(#cwwrap):not(script):not(.ptr){max-width:1240px}}
</style>"""

MARK = ("<svg viewBox='0 0 24 24'><path d='M4 15.5l4.2-4.2 3.3 3.3L20 6' fill='none' stroke='#fff' stroke-width='2.6' "
        "stroke-linecap='round' stroke-linejoin='round'/><circle cx='20' cy='6' r='1.6' fill='#fff'/></svg>")


PWA_HEAD = ("<meta name='apple-mobile-web-app-capable' content='yes'><meta name='mobile-web-app-capable' content='yes'>"
            "<meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'>"
            "<meta name='apple-mobile-web-app-title' content='Combos'><meta name='theme-color' content='#000000'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>")


SPA = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="Combo Hub"><link rel="apple-touch-icon" href="/icon.png"><link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0b0d12"><title>Combo Hub</title>
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
.menu{position:relative}.menu>button{border:1px solid var(--line);background:var(--panel);border-radius:10px;width:38px;height:38px;color:var(--sub)}
.dd{position:absolute;right:0;top:46px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:6px;min-width:200px;box-shadow:0 12px 40px rgba(0,0,0,.35);display:none}
.dd.open{display:block}.dd button,.dd a{display:block;width:100%;text-align:left;border:0;background:none;padding:9px 12px;border-radius:8px;color:var(--ink);font-weight:500}
.dd button:hover,.dd a:hover{background:var(--hover)}
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
.slip .pick{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid var(--line)}
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
.toast.on{opacity:1;transform:translateX(-50%)}
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
.mid2{text-align:center}.mid2 .clk{font-weight:800;font-size:15px}
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
.kv>div{padding:13px 22px;box-shadow:1px 1px 0 var(--line)}.kv span{display:block;color:var(--mute);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
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
  background:color-mix(in srgb,var(--bg) 80%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);border-top:1px solid var(--line)}
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
.panel{padding:16px}.phead{display:flex;gap:14px;align-items:center;justify-content:space-between;margin-bottom:10px}
.pring{--p:0;flex:none;width:74px;height:74px;border-radius:50%;display:grid;place-content:center;text-align:center;
 background:radial-gradient(closest-side,var(--panel) 79%,transparent 80% 100%),conic-gradient(var(--yes) calc(var(--p)*1%),var(--panel2) 0)}
.pring b{font-size:18px;line-height:1}.pring small{font-size:9.5px;color:var(--mute);font-weight:600}
.plist{display:flex;flex-direction:column;gap:8px}.pitem{display:flex;gap:10px;align-items:flex-start;padding:11px 12px;border-radius:12px;background:var(--panel2)}
.pitem.off{opacity:.4}.pitem .pi{font-size:20px;line-height:1.2}.pitem .pm{flex:1;min-width:0}.pitem .pk{font-size:11px;font-weight:700;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}
.pitem .pm b{display:block;font-size:15px;line-height:1.3;margin:2px 0}.pitem .pn{font-size:12.5px;color:var(--sub)}.pitem .pw{font-size:12px;color:var(--mute);margin-top:4px;line-height:1.4}
.pitem .ps{display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex:none}.pitem .ps b{font-size:15px}.pitem .x{border:0;background:none;color:var(--mute);font-size:15px;cursor:pointer;padding:2px 4px}
.bets{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:12px}
.bet{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:12px}
.bet .bt{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}.bet .bt b{display:block;font-size:17px;line-height:1.3;margin-top:3px}
.bet .kind{font-size:11.5px;font-weight:700;color:var(--sub);text-transform:uppercase;letter-spacing:.05em}
.bet .ret{flex:none;text-align:right;color:var(--yes);font-weight:800;font-size:22px;line-height:1}.bet .ret small{display:block;font-size:10.5px;font-weight:600;color:var(--mute);margin-top:3px}
.bnums{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.bnums div{background:var(--panel2);border-radius:10px;padding:8px 10px;font-size:11.5px;color:var(--mute)}
.bnums b{display:block;font-size:15px;color:var(--ink);margin-top:2px}.bet .why{font-size:12.5px;color:var(--sub);line-height:1.45}
.slipbar{display:none}.leg.flip{cursor:pointer;border:1px dashed transparent}.leg.flip:hover{border-color:var(--acc)}
.flipnote{font-size:12.5px;line-height:1.4;padding:9px 11px;border-radius:9px;background:var(--panel2);margin:2px 0 4px}.flipnote b.v{display:inline-block;margin-right:6px}
.flipnote.good b.v{color:var(--yes)}.flipnote.bad b.v{color:var(--no)}.flipnote.mid b.v{color:var(--warn,#e0a040)}
@media (max-width:900px){.slipbar{display:flex;position:fixed;left:12px;right:12px;bottom:calc(74px + env(safe-area-inset-bottom));z-index:29;align-items:center;gap:10px;
 padding:10px 12px 10px 14px;border-radius:14px;background:var(--acc);color:#fff;box-shadow:0 8px 28px rgba(0,0,0,.35);font-weight:700;font-size:14px}
 .slipbar span{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.slipbar button{border:0;border-radius:9px;padding:8px 12px;font-weight:800;background:#fff;color:var(--acc)}
 .slipbar .x{background:transparent;color:#fff;padding:8px 6px}}
@media (min-width:1361px){.numwrap{display:contents}}
</style></head><body>
<header class="top">
 <div class="brand"><div class="mk"><svg width="16" height="16" viewBox="0 0 24 24"><path d="M4 15.5l4.2-4.2 3.3 3.3L20 6" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>Combo Hub</div>
 <nav class="nav" id="nav"></nav>
 <div class="tr">
  <div class="ts"><span>Balance</span><b id="bal">—</b></div>
  <div class="ts wk"><span>Last 7 days</span><b id="wk">—</b></div>
  <div class="status" id="st"><span class="dot"></span>Mac · live</div>
  <button class="cta" onclick="go('build')">＋ Build combos</button>
  <div class="menu"><button onclick="menu()" aria-label="More">⋯</button><div class="dd" id="dd">
   <button onclick="go('settings')">Settings</button><a href="/app/classic">Classic screens</a>
   <button onclick="location.reload()">Reload</button></div></div>
 </div>
</header>
<main id="main"></main>
<nav class="tabbar" id="tabbar"></nav>
<div class="toast" id="toast"></div>
<div class="modal" id="modal"><div class="sheet" id="sheet"></div></div>
<script>
const TOK="__CWTOK__",LOCAL=__CWLOCAL__;
const $=s=>document.querySelector(s);
const api=(p,b)=>fetch(p,b===undefined?{credentials:'same-origin',headers:{'X-CW':TOK}}:{method:'POST',credentials:'same-origin',headers:{'X-CW':TOK,'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>{if(r.status==403){location.href='/';throw 0;}return r.json();});
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':(Math.abs(x)>=1000?'$'+Math.round(x).toLocaleString():Math.abs(x)>=10?'$'+Math.round(x):'$'+(+x).toFixed(2).replace(/\.00$/,''));
const smoney=x=>x==null?'—':(x>=0?'+':'−')+money(Math.abs(x));
const pct=x=>x==null?'—':x>=.1?Math.round(x*100)+'%':x>=.001?(x*100).toFixed(1)+'%':'<0.1%';
const SPN={mix:'Mix',nfl:'NFL',nba:'NBA',nhl:'NHL',ncaaf:'CFB',ncaamb:'CBB',ncaawb:'WCBB',soccer:'Soccer',ufc:'UFC',tennis:'Tennis',euroleague:'Euro'};
const ICON={nfl:'🏈',nba:'🏀',nhl:'🏒',ncaaf:'🎓',ncaamb:'🏀',ncaawb:'🏀',soccer:'⚽',ufc:'🥊',tennis:'🎾',euroleague:'🏀',other:'🎯'};
const SVG={live:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7" opacity=".45"/></svg>',
 build:'<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
 results:'<svg viewBox="0 0 24 24"><path d="M5 19v-7M12 19V6M19 19v-10" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
 games:'<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="3" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M12 5v14M3.5 12h17" stroke="currentColor" stroke-width="1.5" opacity=".7"/></svg>',
 settings:'<svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="7" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="17" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
 more:'<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg>'};
const S={view:(localStorage.getItem('cw_view')||'live'),live:null,build:null,res:null,open:{},filter:'all',lg:localStorage.getItem('cw_lg')||'nba',slip:[],busy:{}};
function toast(m,ms,tone){const t=$('#toast');t.textContent=(tone==='good'?'✅ ':tone==='bad'?'⚠️ ':'')+m;t.classList.remove('good','bad');if(tone)t.classList.add(tone);t.classList.add('on');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('on'),ms||3200);}
function menu(){$('#dd').classList.toggle('open');}
document.addEventListener('click',e=>{if(!e.target.closest('.menu'))$('#dd').classList.remove('open');});
function admin(){api('/app/admin',{}).then(()=>toast('Opening Mac settings…'));}
function modal(h){$('#sheet').innerHTML=h;$('#modal').classList.add('on');}
function closeModal(){$('#modal').classList.remove('on');$('#sheet').classList.remove('wide');S.gameOpen=null;}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal();});
function chrome(){const tabs=[['live','Live'],['games','Games'],['build','Build'],['results','Results'],['settings','Settings']];
 $('#nav').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${l}</button>`).join('');
 $('#tabbar').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${SVG[k]}${l}</button>`).join('');
}
function menuSheet(){modal(`<h3>More</h3><p>Planner settings and the classic screens open in the same window.</p>
 <div style="display:grid;gap:8px"><a class="btn" href="/app/classic">Planner settings</a>${LOCAL?'<button class="btn" onclick="admin();closeModal()">Mac settings</button>':''}<button class="btn" onclick="closeModal()">Close</button></div>`);}
function go(v){hap();S.view=v;try{localStorage.setItem('cw_view',v)}catch(e){};chrome();render();load(v);window.scrollTo(0,0);}
function render(){({live:renderLive,games:renderGames,build:renderBuild,results:renderResults,settings:renderSettings}[S.view]||renderLive)();}
function cget(k){try{const x=JSON.parse(localStorage.getItem('cw_c_'+k)||'null');return x&&Date.now()-x.t<6*3600e3?x.d:null}catch(e){return null}}
function cput(k,d){try{if(d)localStorage.setItem('cw_c_'+k,JSON.stringify({t:Date.now(),d}))}catch(e){}}
function warm(v){/* show the last copy straight away while the fresh one loads */
 if(v==='live'&&!S.live){S.live=cget('live');if(S.live)head(S.live);}
 if(v==='build'&&(!S.build||S.build.lg!==S.lg)){S.build=cget('build_'+S.lg);S.panel=cget('panel_'+(S.pview||'all'))||S.panel;}
 if(v==='results'&&!S.res)S.res=cget('results');
 if(v==='games'&&!S.games)S.games=cget('games');
 if(S.view===v&&(v!=='build'||S.build))render();}
async function load(v,fresh){try{warm(v);
 if(v==='live'){S.live=await api('/app/api/live'+(fresh?'?fresh=1':''));head(S.live);cput('live',S.live);}
 if(v==='build'){const lg=S.lg,pv=S.pview||'all';const [b,p]=await Promise.all([api('/app/api/build?lg='+lg+(fresh?'&fresh=1':'')),api('/app/api/panel?v='+pv).catch(()=>null)]);
  if(lg!==S.lg)return;S.build=b;S.panel=p;cput('build_'+lg,b);cput('panel_'+pv,p);}
 if(v==='results'){S.res=await api('/app/api/results');head(S.res);cput('results',S.res);}
 if(v==='games'){S.games=await api('/app/api/games');cput('games',S.games);}
 if(v==='settings'){const [st,mac,pk]=await Promise.all([api('/app/api/settings?lg='+(S.slg||S.lg)),LOCAL?api('/app/mac',{a:'status'}).catch(()=>null):api('/app/mac-info',{}).catch(()=>null),api('/app/push',{a:'key'}).catch(()=>null)]);S.set=st;S.mac=mac;S.pk=pk;await fidLoad();try{const pp=await api('/app/api/panel?v=all');S.panelCuts=pp.cutoffs;S.skim={reserved:pp.reserved}}catch(e){}
  try{const reg=navigator.serviceWorker&&await navigator.serviceWorker.getRegistration();const sub=reg&&reg.pushManager&&await reg.pushManager.getSubscription();S.pushOn=!!sub;}catch(e){S.pushOn=false;}}
 if(S.view===v)render();}catch(e){if(e)console.log(e);}}
function head(d){if(!d)return;if(d.balance!=null)$('#bal').textContent=money(d.balance);
 if(d.week_pl!=null){const w=$('#wk');w.textContent=smoney(d.week_pl);w.className=d.week_pl>=0?'up':'down';}}
function skel(n){return Array.from({length:n},()=>'<div class="skel" style="height:66px;margin-bottom:10px"></div>').join('');}
// ---------------- LIVE
function legCls(l){if(l.res==='yes')return 'won';if(l.res==='no')return 'lost';if(l.state!=='live')return '';
 const lead=l.sc?(l.sc.me-l.sc.opp):0;const ch=l.live!=null?l.live:l.chance;
 if(lead>0||(!lead&&ch!=null&&ch>=.6))return 'up';if(lead<0||(!lead&&ch!=null&&ch<=.4))return 'down';return 'live';}
function legTag(l){const c=legCls(l);const sc=l.state==='live'&&l.sc?` ${l.sc.me}–${l.sc.opp}`:'';
 const pre=c==='won'?'✓ ':c==='lost'?'✕ ':['up','down','live'].includes(c)?'<i class="pd"></i>':'';
 const tip=c==='up'?'Winning right now':c==='down'?'Losing right now':c==='live'?'Tied or close':c==='won'?'Won':c==='lost'?'Lost':'Not started';
 return `<span class="leg ${c}" title="${tip}">${pre}${esc(short(l.name))}${sc}</span>`;}
function legTags(ls){const o=[...ls].sort((a,b)=>(b.state==='live')-(a.state==='live')||(b.res==='yes')-(a.res==='yes'));
 const max=7;return o.slice(0,max).map(legTag).join('')+(o.length>max?`<span class="leg">+${o.length-max}</span>`:'');}
const PLACE_END=new Set(['City','Orleans','York','Bay','Angeles','Vegas','Francisco','Diego','Jersey','England','Louis','Antonio','Lake','Jose','Carolina','Florida','Dakota','Mexico','Virginia','Kentucky','Michigan','Illinois','Texas','Tech','State','Coast']);
function short(n){n=String(n||'');const p=n.split(' ');if(p.length<2||n.length<=14)return n;const last=p[p.length-1];
 if(PLACE_END.has(last))return p.slice(0,-1).map(w=>w[0]+'.').join('')+' '+last;   // "San Francisco" -> "S. Francisco", never just "City"
 return last;}
function verdictOf(c){if(c.group==='won')return['won','WON'];if(c.group==='lost')return['lost','OUT'];if(c.group==='cashed')return['cashed','CASHED'];
 if(c.verdict==='sell')return['sell','SELL'];if(c.verdict==='half')return['sell','SELL ½'];return['hold','HOLD'];}
function nextLine(c){if(c.group!=='pending')return c.preview||'';const lv=c.legs.find(l=>l.state==='live'&&l.score);if(lv)return '● '+lv.score;
 const up=c.legs.find(l=>!l.res&&l.starts);return up?('Next: '+short(up.name)+' · '+up.starts):(c.when||'');}
function renderLive(){const d=S.live;const m=$('#main');
 if(!d){m.innerHTML=`<div class="kpis">${'<div class="kpi skel" style="height:84px"></div>'.repeat(5)}</div>`+skel(6);return;}
 if(d.error){m.innerHTML=`<div class="card empty"><b>Couldn't load your combos</b>${esc(d.error)}</div>`;return;}
 const cs=(d.combos||[]);const pend=cs.filter(c=>c.group==='pending');
 const sports=[...new Set(cs.flatMap(c=>c.sports))];
 const shown=cs.filter(c=>S.filter==='all'?c.group==='pending':S.filter==='live'?c.group==='pending'&&c.live:S.filter==='done'?c.group!=='pending':c.group==='pending'&&c.sports.includes(S.filter))
   .sort((a,b)=>(b.verdict==='sell')-(a.verdict==='sell')||(b.live-a.live)||a.sort-b.sort);
 const todo=cs.filter(c=>(d.todo||[]).includes(c.t));
 m.innerHTML=`<div class="grid"><div>
 <div class="kpis">
  <div class="kpi"><span>Riding</span><b>${d.riding} <small>combos</small></b></div>
  <div class="kpi"><span>Staked</span><b>${money(d.staked)}</b></div>
  <div class="kpi"><span>Chance one hits</span><b>${pct(d.chance_one)}</b></div>
  <div class="kpi"><span>Cash-out value now</span><b>${(d.combos||[]).some(c=>c.group==='pending'&&!c.offer_real)?'≈ ':''}${money(d.cash_now)}</b></div>
  <div class="kpi"><span>Biggest payout</span><b class="up">${money(d.best)}</b></div></div>
 ${recapCard()}${momentBar(cs)}${doNow(d,cs)}
 <h2>Your combos <span class="n">${pend.length}</span><span class="r chips">${[['all','Riding'],['live','Live now'],...sports.filter(s=>SPN[s]).map(s=>[s,(ICON[s]||'')+' '+SPN[s]]),['done','Settled']].map(([k,l])=>`<button class="chip ${S.filter===k?'on':''}" onclick="S.filter='${k}';renderLive()">${l}</button>`).join('')}</span></h2>
 <div class="tbl"><div class="thead"><div>Combo</div><div>Picks</div><div class="num">Paid</div><div class="num">Pays</div><div class="num">To hit</div><div class="num">Kalshi offer</div><div></div></div>
 ${shown.map(rowLive).join('')||'<div class="empty"><b>Nothing here</b>Combos you place on Kalshi show up here with live scores and cash-out offers.</div>'}</div>
 ${pend.some(c=>c.legs.some(l=>l.state==='live'&&!l.res))?`<div class="legend"><span class="leg up"><i class="pd"></i>Winning now</span><span class="leg down"><i class="pd"></i>Losing now</span><span class="leg live"><i class="pd"></i>Tied</span><span class="leg won">✓ Won</span><span class="leg lost">✕ Lost</span></div>`:''}
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
 if(!items.length)return pend.length?`<div class="calm"><i></i><span><b>Nothing to do right now.</b> ${pend.length} combo${pend.length>1?'s':''} riding · the Mac tells you the moment one is worth selling.</span></div>`:'';
 return `<h2>Do now <span class="n">${items.length}</span></h2><div class="doit">${items.slice(0,4).map(({c,kind})=>{
  const nums=`<div class="dnums"><div>${c.offer_real?'Offer now':'Likely offer'}<b>${c.offer_real?'':'≈ '}${money(c.offer)}</b></div><div>Holding is worth<b>${money(c.hold_ce!=null?c.hold_ce:c.hold_value)}</b></div>${c.threshold?`<div>Sell after next game at<b>${money(c.threshold)}+</b></div>`:''}<div>You paid<b>${money(c.cost)}</b></div></div>`;
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
  if(x.n===1)return `<div class="dcard idea ${S.hl===x.id?'flash':''}" id="idea-${x.id}"><div><h4>🎯 ${esc(x.picks)} <span class="tag" style="background:var(--panel2);color:var(--sub)">SINGLE GAME</span>${x.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">IN PROGRESS</span>':''}</h4>
   <p>${esc(x.sport)} · found ${ago2(x.ts)} ago · Kalshi's price is below the sharp books' chance of winning, after Kalshi's fee. No combo maker taking a cut.</p>
   ${x.note?`<p style="margin-top:6px">🩹 ${esc(x.note)}</p>`:''}
   <div class="dnums">${fresh?`<div>Price now<b>${Math.round(q.price*100)}¢</b></div><div>Fair chance<b>${pct(q.fair)}</b></div><div>Edge after fee<b class="${q.edge>0?'up':'down'}">${(q.edge*100).toFixed(1)}¢</b></div><div>Buy<b>${q.n} for ${money(q.stake)} → ${money(q.pays)}</b></div>`:`<div>Value<b>${pct(x.pct)} of fair</b></div>`}</div></div>
   <div class="dbtns">${fresh?`<button class="btn ghost" onclick="S.ideaq['${x.id}']=null;renderLive()">Pass</button><button class="btn yes" ${q.edge>0?'':'disabled'} onclick="buySingle('${x.id}')">Buy · ${left}s</button>`:
    `<button class="btn ghost" onclick="hideIdea('${x.id}')">Not now</button><button class="btn acc" id="ib-${x.id}" onclick="priceIdea('${x.id}')">Get today's price</button>`}</div></div>`;
  return `<div class="dcard idea ${S.hl===x.id?'flash':''}" id="idea-${x.id}"><div><h4>💡 ${esc(x.picks)}${x.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">IN PROGRESS</span>':''}</h4><p>${esc(x.sport)} · ${x.n} picks · priced at <b>${pct(x.pct)}</b> of fair ${ago2(x.ts)} ago${x.kick?' · starts '+new Date(x.kick*1000).toLocaleTimeString([],{weekday:'short',hour:'numeric',minute:'2-digit'}):''}</p>
   ${x.note?`<p style="margin-top:6px">🩹 ${esc(x.note)}</p>`:''}
   <div class="dnums"><div>Last price<b>${money(x.stake)} → ${money(x.pays)}</b></div><div>Fair payout<b>${money(x.fair)}</b></div>${fresh?`<div>Your price now<b class="${q.clears?'up':''}">${money(q.stake)} → ${money(q.pays)}</b></div><div>Share of fair<b>${pct(q.pct)}</b></div>`:''}</div></div>
   <div class="dbtns">${fresh?`<button class="btn ghost" onclick="S.ideaq['${x.id}']=null;renderLive()">Pass</button><button class="btn yes" onclick="buyIdea('${x.id}')">Buy · ${left}s</button>`:
    `<button class="btn ghost" onclick="hideIdea('${x.id}')">Not now</button><button class="btn acc" id="ib-${x.id}" onclick="priceIdea('${x.id}')">Get my price</button>`}</div></div>`;}).join('')}</div>`;}
async function priceIdea(id){const b=$('#ib-'+id);if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';}
 const r=await api('/app/api/act',{a:'idea',id}).catch(()=>({ok:false}));
 if(!r.ok){toast(r.msg||'No price came in. Try again in a minute.',5000);renderLive();return;}
 S.ideaq[id]={i:r.i,pays:r.pays,stake:r.stake,pct:r.pct,clears:r.clears,at:Date.now()/1000,price:r.price,n:r.n,edge:r.edge,fair:r.fair,single:r.single};renderLive();
 clearInterval(S.ideaT);S.ideaT=setInterval(()=>{if(S.view==='live'&&!$('#modal').classList.contains('on'))renderLive();const q=S.ideaq[id];if(!q||Date.now()/1000-q.at>21){clearInterval(S.ideaT);renderLive();}},1000);}
async function buyIdea(id){const q=S.ideaq[id];if(!q)return;const r=await api('/app/api/act',{a:'buy',i:q.i});S.ideaq[id]=null;
 toast(r.ok?`Bought: ${money(q.stake)} to win ${money(r.pays||q.pays)}. It shows in your combos within a minute.`:(r.msg||'Didn\'t go through.'),6000);if(r.ok)hideIdea(id);else renderLive();load('live',true);}
async function buySingle(id){const q=S.ideaq[id];if(!q)return;const r=await api('/app/api/act',{a:'singlebuy',id,n:q.n,price:q.price});S.ideaq[id]=null;
 toast(r.msg||(r.ok?'Bought.':'Didn\'t go through.'),6000,r.ok?'good':null);if(r.ok)hideIdea(id);else renderLive();load('live',true);}
function hideIdea(id){try{const h=JSON.parse(localStorage.getItem('cw_hide')||'[]');h.push(id);localStorage.setItem('cw_hide',JSON.stringify(h.slice(-60)))}catch(e){}renderLive();}
function sweat(c){if(c.group!=='pending'||c.legs.length<2)return '';const w=c.legs.filter(l=>l.res==='yes').length;
 const seg=c.legs.map(l=>l.res==='yes'?'w':l.res==='no'?'x':(!l.res&&l.state==='live'&&(l.live??l.chance)>=.5)?'u':'').sort((a,b)=>'wux'.indexOf(a)>-1&&'wux'.indexOf(b)>-1?'wux'.indexOf(a)-'wux'.indexOf(b):a?-1:b?1:0);
 return `<span class="sweat" title="${w} of ${c.legs.length} picks won">${seg.map(s=>`<i class="${s}"></i>`).join('')}</span>`;}
function momentBar(cs){const m=cs.filter(c=>c.group==='pending'&&c.moment&&c.offer).sort((a,b)=>(b.offer-b.cost)-(a.offer-a.cost));if(!m.length)return '';
 const auto=S.live&&S.live.auto_sell;const more=m.length>1?`<div class="m" style="font-size:12px;margin:-6px 4px 12px">${m.length-1} more combo${m.length>2?'s are':' is'} at a good point too. They're marked with a green edge below.</div>`:'';
 return m.slice(0,1).map(c=>`<div class="moment-bar"><div><b>💸 ${auto?'Cashing out':'Good time to cash out'}: ${esc(c.label)}</b><span>Kalshi offers ${money(c.offer)} on ${money(c.cost)} paid (${smoney(c.offer-c.cost)}). ${c.moment.why==='take profit'?'It reached your take-profit level.':c.moment.why==='lock in'?'It\'s slipping from its high.':c.moment.why==='checkpoint'?'The early games came through.':'Locking in beats the risk of holding.'}</span></div>
  ${auto?'<span class="tag good">Auto</span>':`<button class="btn yes" onclick="sell('${c.t}')">Cash out</button>`}</div>`).join('')+more;}
function rowLive(c){const [vc,vt]=verdictOf(c);const open=S.open[c.t];
 const offer=c.group!=='pending'?(c.group==='cashed'?`<b>${money(c.back)}</b><small>cashed out</small>`:'—'):c.offer!=null?`<b>${c.offer_real?'':'≈ '}${money(c.offer)}</b><small>${c.offer_real?'vs '+money(c.hold_value)+' holding':'estimate'}</small>`:'<small>—</small>';
 return `<div class="trow ${c.moment?'hot':''}" onclick="tog('${c.t}')"><div class="name"><b>${ICON[c.sports[0]]||''} ${esc(c.label)}${sweat(c)}</b><span>${esc(nextLine(c))}</span></div>
  <div class="legs">${legTags(c.legs)}</div>
  <div class="numwrap"><div class="num" data-l="Paid">${money(c.cost)}</div><div class="num" data-l="Pays">${money(c.pays)}</div>
  <div class="num" data-l="To hit">${c.group==='pending'?pct(c.p):'—'}${c.group==='pending'?`<div class="bar"><i style="width:${Math.max(1,Math.min(100,c.p*100))}%"></i></div>`:''}</div>
  <div class="num offer" data-l="Offer">${offer}</div></div><div class="verdict ${vc}">${vt}</div></div>
  ${open?`<div class="exp">${c.legs.map(l=>`<div class="lrow" style="cursor:pointer" onclick="event.stopPropagation();openGame('${l.ticker}')"><span class="mark ${legCls(l)}">${l.res==='yes'?'✓':l.res==='no'?'✕':''}</span>
   <div class="who"><b>${ICON[l.sport]||''} ${esc(l.name)}</b> <span>${l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</span>${l.url?` <a href="${esc(l.url)}" target="_blank" onclick="event.stopPropagation()">game ↗</a>`:''}</div>
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
 return moments()+ordersCard(d)+`<div class="card"><h3>Games you need <span>${gs.length}</span></h3>${gs.slice(0,8).map(g=>`<div class="g" style="cursor:pointer" onclick="openGame('${g.ticker||''}')"><div class="t">${ICON[g.sport]||''} ${esc(g.name)}${g.state==='live'?'<span class="tag">LIVE</span>':''}</div>
  <div class="e">${g.state==='live'&&g.sc?`<b>${g.sc.me}–${g.sc.opp}</b>${esc(g.sc.detail||'')}`:`<b>${pct(g.chance)}</b>${esc(g.starts||'')}`}</div>
  <div class="x">In ${g.combos} combo${g.combos>1?'s':''} · ${money(g.pays)} riding</div></div>`).join('')||'<div class="m">Nothing pending.</div>'}</div>
 ${r?`<div class="card"><h3>If ${esc(short(r.name))} lose <span>biggest risk</span></h3><div class="mini">Combos out<b>${r.combos} of ${d.riding}</b></div><div class="mini">Payout riding<b>${money(r.pays)}</b></div><div class="mini">${esc(short(r.name))} to win<b>${pct(r.chance)}</b></div></div>`:''}
 ${todayCard(d)}`;}
function todayCard(d){const t=d.today;if(!t)return `<div class="card"><h3>Finished <span>recently</span></h3><div class="mini">Won or cashed<b class="up">${money(d.locked)}</b></div><div class="mini">Holding is worth<b>${money(d.hold_value)}</b></div></div>`;
 const n=t.won+t.cashed+t.lost;const bits=[t.won?`${t.won} won`:'',t.cashed?`${t.cashed} cashed`:'',t.lost?`${t.lost} lost`:''].filter(Boolean).join(' · ');
 return `<div class="card"><h3>Today <span>${n?bits:'nothing finished yet'}</span></h3>${n?`<div class="mini">Paid back<b>${money(t.back)}</b></div><div class="mini">They cost<b>${money(t.cost)}</b></div><div class="mini">Profit today<b class="${t.pl>=0?'up':'down'}">${smoney(t.pl)}</b></div>`:''}${d.week_pl!=null?`<div class="mini">Last 7 days<b class="${d.week_pl>=0?'up':'down'}">${smoney(d.week_pl)}</b></div>`:''}<div class="mini">Still riding is worth<b>${money(d.hold_value)}</b></div></div>`;}
async function ask(t){S.busy[t]=true;S.open[t]=true;renderLive();const r=await api('/app/api/act',{a:'ask',t});S.busy[t]=false;
 if(!r.ok)toast(r.msg||'No offer came in.');await load('live',true);}
function sell(t){const c=(S.live.combos||[]).find(x=>x.t===t);if(!c)return;
 modal(`<h3>Cash out ${esc(c.label)} for ${money(c.offer)}?</h3><p>You paid ${money(c.cost)} (${smoney(c.offer-c.cost)}). If you hold instead: ${pct(c.p)} chance of ${money(c.pays)}. Kalshi's offer only lasts a few seconds.</p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn yes" id="sellgo" onclick="doSell('${t}')">Cash out</button></div>`);}
async function doSell(t){hap();$('#sellgo').innerHTML='<span class="spin"></span>';const r=await api('/app/api/act',{a:'go',t});closeModal();hap(r.ok?'success':'error');toast(r.msg||(r.ok?'Done.':'Didn\'t go through.'),5000);load('live',true);}
async function hedge(t){const c=(S.live.combos||[]).find(x=>x.t===t);modal(`<h3>Hedge ${esc(c.label)}?</h3><p>Buys the other side of its last game for about ${money(c.hedge.cost)}, so you collect about ${money(c.hedge.locked)} whichever team wins.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();api('/app/api/act',{a:'hedgego',t:'${t}'}).then(r=>{toast(r.msg||'Done.',5000);load('live',true)})">Place hedge</button></div>`);}
async function act(a,t){const r=await api('/app/api/act',{a,t});if(r.msg)toast(r.msg);load('live',true);}
// ---------------- BUILD
function renderBuild(){const d=S.build;const m=$('#main');
 const lgs=(d&&d.leagues)||[['mix','Mix sports','🎲'],['nfl','NFL','🏈'],['nba','NBA','🏀'],['nhl','NHL','🏒'],['ncaaf','CFB','🎓']];
 const pv=S.pview||'all';const gameN=S.panel&&S.panel.games;const chipRow=`<div class="chips" style="margin-bottom:14px"><button class="chip ${pv==='all'?'on':''}" onclick="setPview('all')">⭐ All</button>${lgs.filter(([k])=>k!=='mix'&&(k===pv||k===S.lg||!gameN||gameN[k]==null||gameN[k]>0)).map(([k,n,i])=>`<button class="chip ${pv===k?'on':''}" onclick="setPview('${k}')">${i} ${esc(SPN[k]||n)}</button>`).join('')}</div>`;
 if(!d||d.lg!==S.lg){m.innerHTML=chipRow+'<div class="grid"><div>'+skel(7)+'</div><div class="skel" style="height:300px"></div></div>';return;}
 const best=bestBets(d);const adv=S.adv||S.slip.length>0;
 m.innerHTML=chipRow+`<div class="grid"><div>
  ${panelBlock(S.panel)}
  <button class="btn ghost" style="width:100%;margin:18px 0 6px;justify-content:center" onclick="toggleAdv()">${adv?'Hide the full board ▴':`Build your own · all ${d.board.length} games${(d.lines||[]).length?', spreads & totals':''} ▾`}</button>
  ${adv?`<h2>${esc(d.icon)} ${esc(d.name)} games <span class="n">${d.board.length}</span><span class="r m" style="font-size:12px">Kalshi price · fair chance from the sportsbooks</span></h2>
  <div class="board">${d.board.map(g=>`<div class="mrow"><div class="when">${g.started?'<span class="tag">LIVE</span>':esc(g.label||'')}</div>
   ${g.sides.filter(s=>!s.tie).map(s=>{const on=S.slip.includes(s.ticker);return `<button class="pickbtn ${on?'on':''}" onclick="pick('${s.ticker}','${g.event}')"><span class="nm"><span class="full">${esc(s.pick)}</span><span class="short">${esc(short(s.pick))}</span>${s.edge!=null&&s.edge>=.01?'<span class="val">VALUE</span>':''}</span>
    <span class="pr"><b>${s.p!=null?Math.round(s.p*100)+'¢':'—'}</b><span>${s.fair!=null?'fair '+pct(s.fair):''}</span></span></button>`}).join('')}</div>`).join('')||'<div class="empty"><b>No games right now</b>Try another sport.</div>'}</div>
  ${linesBlock(d)}
  <h2>More combo ideas <span class="n">${d.combos.length}</span><span class="r"><button class="btn" id="rebuildb" onclick="rebuild(this)">Rebuild</button></span></h2>
  <div class="m" style="font-size:12px;margin:-4px 2px 10px">Fairly priced combos built to your mix. They aren't value picks unless marked ★.</div>
  <div class="cgrid">${d.combos.slice().sort((a,b)=>(b.kind==='value')-(a.kind==='value')||((b.pred||{}).p_clear??-1)-((a.pred||{}).p_clear??-1)).map(ccard).join('')}</div>`:''}
 </div><aside>${adv?slip(d)+singlesCard(d):budgetCard(d)}</aside></div>${slipBar()}`;}
function setPview(k){hap();S.pview=k;try{localStorage.setItem('cw_pview',k)}catch(e){}if(k!=='all'&&k!==S.lg){setLg(k);}else load('build');}
try{S.pview=localStorage.getItem('cw_pview')||'all'}catch(e){S.pview='all'}
const KIND={single:['🎯','Single game'],early:['🎢','Sell-early favorite'],line:['📏','Spread / total'],combo:['🧩','Combo']};
function pTime(ts){return ts?new Date(ts*1000).toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'}):'';}
function panelItem(c,st,approved){const k=KIND[c.kind]||['•',c.kind];const off=S.pOff&&S.pOff.has(c.id);
 const state=c.state||'';const chip={scheduled:`<span class="tag">buys ${pTime(c.buy_at)}</span>`,bought:'<span class="tag good">Bought</span>',buying:'<span class="tag">Buying…</span>',check:'<span class="tag bad">Check Kalshi</span>',paper:'<span class="tag">Paper</span>',
  skipped:'<span class="tag bad">Skipped</span>',swapped:'<span class="tag">Swapped</span>',failed:'<span class="tag bad">Didn\'t buy</span>',cancelled:'<span class="tag">Cancelled</span>','left out':'<span class="tag">Left out</span>'}[state]||'';
 const res=c.result?`<span class="tag ${c.pl>=0?'good':'bad'}">${c.pl>=0?'+':'−'}${money(Math.abs(c.pl))}</span>`:'';
 const title=c.kind==='combo'?c.legs.map(l=>esc(short(l.pick))).join(' + '):c.kind==='line'?esc(c.legs[0].pick.replace(/ \(.*\)$/,'')):`${esc(short(c.legs[0].pick))}${c.opp?` <span class="m" style="font-weight:500">vs ${esc(short(c.opp))}</span>`:''}`;
 const nums=c.kind==='early'?`${pct(c.chance)} it reaches ${Math.round(c.exit*100)}¢ · buy ${Math.round(c.price*100)}¢`:c.kind==='combo'?`${pct(c.chance)} to hit · pays ≈${pct(c.pct)} of fair`:`${pct(c.chance)} to win · ${Math.round(c.price*100)}¢`;
 return `<div class="pitem ${off?'off':''}"><div class="pi">${c.icon||k[0]}</div><div class="pm"><div class="pk">${k[1]}${c.slate?' · slate':''} · ${esc(pTime(c.kick))}</div><b>${title}</b>
  <div class="pn">${nums} · <span class="up">+${Math.round(c.ret*100)}% expected</span></div>${c.why?`<div class="pw">${esc(c.why)}</div>`:''}${c.note?`<div class="pw">${esc(c.note)}</div>`:''}</div>
  <div class="ps"><b>${money(c.stake)}</b>${chip}${res}${!approved?`<button class="x" title="${off?'Put back':'Leave out'}" onclick="pToggle('${c.id}')">${off?'↺':'✕'}</button>`:''}</div></div>`;}
function pToggle(id){hap();S.pOff=S.pOff||new Set();S.pOff.has(id)?S.pOff.delete(id):S.pOff.add(id);renderBuild();}
function panelBlock(d){if(!d||!d.panel)return d&&d.view&&d.view!=='all'?`<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🧘</div><b style="display:block;margin:6px 0 4px;font-size:17px">Nothing in ${esc(SPN[d.view]||d.view)} clears the bar right now</b>
  <div class="m" style="font-size:13px;line-height:1.5">No ${esc(SPN[d.view]||d.view)} bet is priced better than its real chance at the moment. The Mac checks every 10 minutes. You can still build your own below.</div></div>`:`<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🗓️</div><b style="display:block;margin:6px 0 4px;font-size:17px">Today's panel is being put together</b>
  <div class="m" style="font-size:13px;line-height:1.5">The Mac looks at every sport every 10 minutes and keeps only bets priced better than their real chance. Check back shortly.</div></div>`;
 const p=d.panel,st=p.stats||{},approved=d.view==='all'&&p.status!=='draft',items=p.items||[];S.pOff=S.pOff||new Set();
 const live=items.filter(c=>!S.pOff.has(c.id));const total=live.reduce((a,c)=>a+c.stake,0);
 const head=`<div class="phead"><div><h2 style="margin:0">${d.view==='all'?"Today's panel":(SPN[d.view]||d.view)+(d.approved_other?' picks':' panel')}</h2>
   <div class="m" style="font-size:12.5px;margin-top:2px">${items.length} bet${items.length===1?'':'s'} · ${money(approved?items.filter(c=>['scheduled','bought'].includes(c.state)).reduce((a,c)=>a+c.stake,0):total)} of your ${money(p.budget)} · picked together for the best chance the day ends up ahead</div></div>
   <div class="pring" style="--p:${Math.round((st.p_ahead||0)*100)}"><b>${pct(st.p_ahead||0)}</b><small>chance up</small></div></div>`;
 const addMode=d.view!=='all'&&d.approved_other;
 const btn=addMode?`<button class="btn acc" style="width:100%;justify-content:center;font-size:16px;padding:13px" onclick="panelAdd(this)">Add ${live.length} to today's panel · ${money(total)}</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">Today's panel is already approved. These are bought the same way, inside your daily panel budget.</div>`:approved?(p.status==='approved'?`<button class="btn ghost" style="width:100%;justify-content:center" onclick="panelCancel()">Stop buying the rest</button>`:p.status==='cancelled'?`<button class="btn acc" style="width:100%;justify-content:center" onclick="panelRestart(this)">Build a fresh panel for today</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">Bets already bought stay. The Mac looks at today's remaining games again and puts together a new panel for you to approve.</div>`:'')
  :`<button class="btn acc" style="width:100%;justify-content:center;font-size:16px;padding:13px" onclick="panelApprove(this)">Approve ${live.length} bet${live.length===1?'':'s'} · ${money(total)}</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">The Mac buys each one shortly before its game (the time is on each bet), after checking the price again. If one no longer qualifies, it swaps in a similar bet or skips it.</div>`;
 const longer=(p.longer||[]).length?`<h2 style="margin-top:20px">Longer plays <span class="n">${p.longer.length}</span></h2><div class="m" style="font-size:12px;margin:-4px 2px 10px">Over the next few days. Each day is a chance to cash out early. Not part of the approval above.</div><div class="plist">${p.longer.map(c=>panelItem(c,'',true)).join('')}</div>`:'';
 const other='';
 return `<div class="card panel">${head}${other}<div class="plist">${items.map(c=>panelItem(c,c.state,approved)).join('')||'<div class="m">Nothing qualifies right now.</div>'}</div>
  <div class="m" style="font-size:12px;margin:10px 2px">Expected ${smoney(st.ev||0)} · range ${smoney(st.worst||0)} to ${smoney(st.best||0)}</div>${poolLine(st.pool)}${btn}</div>${extraBlock(d.extra)}${longer}`;}
function extraBlock(x){if(!x||!(x.items||[]).length)return '';const live=x.items.filter(c=>!S.pOff.has(c.id));const tot=live.reduce((a,c)=>a+c.stake,0);
 return `<div class="card panel" style="margin-top:14px;border-color:color-mix(in srgb,var(--yes) 40%,var(--line))"><div class="phead"><div><h2 style="margin:0">🆕 New since you approved</h2>
  <div class="m" style="font-size:12.5px;margin-top:2px">Good bets that turned up after you approved, on games today's panel doesn't have a bet on. Checked every few minutes as games get close.</div></div></div>
  <div class="plist">${x.items.map(c=>panelItem(c,'',false)).join('')}</div>
  ${live.length?`<button class="btn acc" style="width:100%;justify-content:center;margin-top:10px" onclick="panelAdd(this,'extra')">Add ${live.length} to today's panel · ${money(tot)}</button>`:''}</div>`;}
function poolLine(pl){if(!pl)return '';const n=k=>pl[k]||0;
 const parts=[[n('combo'),'combo','combos'],[n('single'),'single game','single games'],[n('early'),'sell-early favorite','sell-early favorites'],[n('line'),'spread or total','spreads or totals']].map(([v,a,b])=>`${v} ${v===1?a:b}`);
 return `<div class="m" style="font-size:12px;margin:-4px 2px 10px">Qualifying today: ${parts.join(' · ')}.${n('combo')?'':' No combo is priced at your cut-off or better right now; Kalshi usually pays less than fair on combos.'}</div>`;}
async function panelApprove(b){const ids=(S.panel.panel.items||[]).filter(c=>!S.pOff.has(c.id)).map(c=>c.id);
 if(!b.dataset.sure){b.dataset.sure='1';b.textContent='Tap again to approve';hap('warning');setTimeout(()=>{if(b.isConnected){b.dataset.sure='';renderBuild();}},4000);return;}
 b.innerHTML='<span class="spin"></span>';const r=await api('/app/api/act',{a:'panel_approve',ids,view:S.pview||'all',at:S.panel.panel.at}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 hap(r.ok?'success':'error');toast(r.msg,6000,r.ok?'good':'bad');S.pOff=new Set();await load('build');}
async function panelAdd(b,view){const src=view==='extra'?(S.panel.extra||{}):S.panel.panel;const ids=(src.items||[]).filter(c=>!S.pOff.has(c.id)).map(c=>c.id);
 if(!b.dataset.sure){b.dataset.sure='1';b.textContent='Tap again to add';hap('warning');setTimeout(()=>{if(b.isConnected){b.dataset.sure='';renderBuild();}},4000);return;}
 b.innerHTML='<span class="spin"></span>';const r=await api('/app/api/act',{a:'panel_add',ids,view:view||S.pview}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 hap(r.ok?'success':'error');toast(r.msg,6000,r.ok?'good':'bad');S.pOff=new Set();await load('build');}
async function panelRestart(b){hap();b.innerHTML='<span class="spin"></span>';
 const r=await api('/app/api/act',{a:'panel_restart'}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 hap(r.ok?'success':'error');toast(r.msg,7000,r.ok?'good':'bad');await load('build');}
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
  ${fresh?`<div class="qline ${o.clears?'good':'bad'}"><b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · ${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}s left</span></div>
   <button class="btn yes" style="width:100%" id="b${c.i}" onclick="buy(${c.i},false,this)">Buy ${money(o.stake)} → ${money(o.pays)}</button>`:`<button class="btn acc" style="width:100%" id="q${c.i}" onclick="quote(${c.i})">Get a price</button>`}</div>`;}
function budgetCard(d){return d.spent!=null?`<div class="card"><h3>This week <span>${esc(d.name)}</span></h3><div class="mini">Spent<b>${money(d.spent)}</b></div><div class="mini">Your cap<b>${money(d.budget)}</b></div><div class="mini">Combo cut-off<b>${d.cut}% of fair</b></div></div>`:'';}
function slipBar(){const legs=S.slip.map(sideBy).filter(Boolean);if(!legs.length)return '';
 const ch=legs.reduce((a,l)=>a*(l.fair||l.p||0),1);
 return `<div class="slipbar"><span>${legs.length<2?`${esc(short(legs[0].pick))} picked · tap 1 more team`:`Your combo · ${legs.length} picks · ${pct(ch)} to hit`}</span>${legs.length>=2?`<button onclick="document.querySelector('.slip').scrollIntoView({behavior:'smooth',block:'center'});if($('#slipq'))quoteSlip()">Price it ›</button>`:''}<button class="x" aria-label="Clear" onclick="S.slip=[];S.custom=null;renderBuild()">✕</button></div><div class="slipgap" style="height:64px"></div>`;}
try{S.adv=!!localStorage.getItem('cw_adv')}catch(e){}
function setLg(k){S.lg=k;S.slip=[];try{localStorage.setItem('cw_lg',k)}catch(e){};S.build=cget('build_'+k);renderBuild();load('build');}
function pick(t,ev){const d=S.build;const same=d.board.find(g=>g.event===ev).sides.map(s=>s.ticker);
 if(S.slip.includes(t))S.slip=S.slip.filter(x=>x!==t);else{S.slip=S.slip.filter(x=>!same.includes(x));S.slip.push(t);}S.custom=null;renderBuild();}
function sideBy(t){for(const g of S.build.board)for(const s of g.sides)if(s.ticker===t)return s;}
function slip(d){const legs=S.slip.map(sideBy).filter(Boolean);const stake=d.stake||5;
 const fairChance=legs.reduce((a,l)=>a*(l.fair||l.p||0),1),kal=legs.reduce((a,l)=>a*(l.p||0),1);const c=S.custom;
 return `<div class="card slip"><h3>Your combo <span>${legs.length} pick${legs.length==1?'':'s'}</span></h3>
  ${legs.length?legs.map(l=>`<div class="pick"><span>${esc(l.pick)} <span class="m">${l.fair!=null?pct(l.fair):''}</span></span><button onclick="pick('${l.ticker}','${l.event}')">×</button></div>`).join(''):'<div class="m" style="padding:6px 0 10px">Tap teams on the board to build your own combo, or use a suggestion below.</div>'}
  ${legs.length>=2?`<div style="margin-top:10px"><div class="sum">Chance it hits<b>${pct(fairChance)}</b></div><div class="sum">Fair payout for ${money(stake)}<b>${money(stake/fairChance)}</b></div>
   <div class="sum">Kalshi's single prices imply<b>${money(stake/kal)}</b></div>
   ${c&&c.offer?`<div class="sum">Kalshi offers<b class="up">${money(c.offer.pays)}</b></div>`:''}
   <div style="display:flex;gap:8px;margin-top:12px">${c&&c.offer&&Date.now()/1000-c.offer.at<20?`<button class="btn yes" style="flex:1" onclick="buy(${c.i},true)">Buy ${money(c.offer.stake)} to win ${money(c.offer.pays)}</button>`:`<button class="btn acc" style="flex:1" id="slipq" onclick="quoteSlip()">Get Kalshi's price</button>`}</div></div>`:''}
  <div class="m" style="font-size:12px;margin-top:12px">${d.spent!=null?`Spent ${money(d.spent)} of your ${money(d.budget)} cap · cut-off ${d.cut}% of fair`:''}</div></div>`;}
async function quoteSlip(){$('#slipq').innerHTML='<span class="spin"></span> Asking Kalshi…';const r=await api('/app/api/act',{a:'custom',tickers:S.slip});
 if(!r.ok){toast(r.msg);renderBuild();return;}const q=await api('/app/api/act',{a:'quote',i:r.i});
 if(!q.ok){toast(q.error||q.msg||'No price came in.');renderBuild();return;}S.custom={i:r.i,offer:{pays:q.pays,stake:q.stake,at:Date.now()/1000,pct:q.pct}};renderBuild();
 toast(`Kalshi pays ${money(q.pays)} for ${money(q.stake)} (${pct(q.pct)} of fair). Buy within 20 seconds.`,6000);}
async function rebuild(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Rebuilding…';}
 const before=JSON.stringify(((S.build||{}).combos||[]).map(c=>c.legs.map(l=>l.ticker)));S.quotes={};
 await load('build',true);const after=JSON.stringify(((S.build||{}).combos||[]).map(c=>c.legs.map(l=>l.ticker)));
 toast(before===after?'Prices refreshed. The best combos are still the same ones.':'New combos are ready.',4000,'good');}
async function swapCombo(i,b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span>';}
 const r=await api('/app/api/act',{a:'swap',i}).catch(()=>({ok:false}));if(S.quotes)delete S.quotes[i];if(S.flips)delete S.flips[i];
 if(!r.ok){hap('error');toast(r.msg||'Couldn\'t find another one.');renderBuild();return;}
 const k=S.build.combos.findIndex(x=>x.i===i);if(k>=0)S.build.combos[k]=r.combo;renderBuild();hap('success');}
async function flipLeg(i,t){hap();const r=await api('/app/api/act',{a:'flip',i,t}).catch(()=>({ok:false}));
 if(!r.ok){hap('error');toast(r.msg||'Couldn\'t flip that one.',6000);return;}
 const k=S.build.combos.findIndex(x=>x.i===i);if(k>=0)S.build.combos[k]=r.combo;if(S.quotes)delete S.quotes[i];
 S.flips=S.flips||{};S.flips[i]={v:r.verdict,text:r.text};hap(r.verdict==='good'?'success':r.verdict==='bad'?'warning':'light');renderBuild();}
function ccard(c){const o=S.quotes&&S.quotes[c.i];const fresh=o&&Date.now()/1000-o.at<20;const fl=S.flips&&S.flips[c.i];
 if(c.bought)return `<div class="ccard" style="opacity:.62"><div class="hd"><div><div class="tier" style="color:var(--yes)">✓ You bought this</div><b>${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold">${pct(c.chance)}</span></div>
  <div class="legs">${c.legs.map(l=>`<span class="leg">${esc(short(l.pick))} ${pct(l.fair)}</span>`).join('')}</div>
  <div style="display:flex;gap:8px"><button class="btn ghost" style="flex:1" onclick="go('live')">See it on Live</button><button class="btn ghost" onclick="swapCombo(${c.i},this)">↻ Another</button></div></div>`;
 return `<div class="ccard"><div class="hd"><div><div class="tier" ${c.kind==='value'?'style="color:var(--yes)"':''}>${c.kind==='value'?'★ Value pick':esc(c.tier||c.kind||'')}</div><b>${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold">${pct(c.chance)}</span></div>
  <div class="legs">${c.legs.map(l=>`<span class="leg flip" title="Tap to flip to the other team" onclick="flipLeg(${c.i},'${l.ticker}')">${esc(short(l.pick))} ${pct(l.fair)} ⇄</span>`).join('')}</div>
  ${fl?`<div class="flipnote ${fl.v}"><b class="v">${fl.v==='good'?'Good flip':fl.v==='bad'?'Worse bet':'Trade-off'}</b>${esc(fl.text)}</div>`:`<div class="m" style="font-size:11.5px">Tap a team to flip it to the other side.</div>`}
  <div class="s" style="font-size:12.5px">${c.pred&&c.pred.n>=20?`<span class="pred ${c.pred.p_clear>=.6?'good':c.pred.p_clear<.2?'bad':''}">Likely ≈ ${pct(c.pred.pct)} of fair · ${c.pred.p_clear>=.9?'very likely':c.pred.p_clear>=.6?'likely':c.pred.p_clear>=.35?'maybe':'unlikely'} to clear your cut-off</span><div class="m" style="font-size:11.5px;margin-top:4px">Guess from ${c.pred.n} past Kalshi prices. Get price for the real one.</div>`:c.est?`Kalshi will likely pay about ${money(c.est)} (${pct(c.est_pct)} of fair)`:fresh?'':'Get a price to see what Kalshi pays.'}
   ${c.size?`<div class="m" style="margin-top:6px">Suggested bet ${money(c.size)}${c.exposure?` · smaller: you already need ${esc(short(c.exposure.team))} a lot`:''}</div>`:c.exposure?`<div class="m" style="margin-top:6px">You already need ${esc(short(c.exposure.team))} in a lot of combos</div>`:''}</div>
  ${fresh?`<div class="qline ${o.clears?'good':'bad'}"><b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · ${o.clears?'above':'below'} your ${o.cut||''}% cut-off · ${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}s left</span></div>`:''}
  <div style="display:flex;gap:8px">${fresh?`<button class="btn yes" style="flex:1" id="b${c.i}" onclick="buy(${c.i},false,this)">Buy ${money(o.stake)} → ${money(o.pays)}</button>`:
   `<button class="btn" style="flex:1" id="q${c.i}" onclick="quote(${c.i})">Get price</button>`}<button class="btn ghost" title="Not this one: show a different combo" onclick="swapCombo(${c.i},this)">↻ Not this one</button></div></div>`;}
async function quote(i){hap();const b=$('#q'+i);if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';}
 const r=await api('/app/api/act',{a:'quote',i}).catch(e=>({ok:false,error:'Couldn\'t reach your Mac ('+(e&&e.message||e)+').'}));
 if(!r.ok){hap('error');toast(r.error||r.msg||'No price came in.',6000);renderBuild();return;}
 S.quotes=S.quotes||{};S.quotes[i]={pays:r.pays,stake:r.stake,pct:r.pct,clears:r.clears,cut:r.cut,at:Date.now()/1000};hap(r.clears?'success':'warning');renderBuild();
 clearInterval(S.qT);S.qT=setInterval(()=>{if(S.view!=='build'||S.buying)return;const any=Object.values(S.quotes||{}).some(q=>q&&Date.now()/1000-q.at<21);renderBuild();if(!any)clearInterval(S.qT);},1000);}
async function buy(i,custom,btn){if(S.buying)return;S.buying=true;hap();if(btn){btn.disabled=true;btn.innerHTML='<span class="spin"></span> Buying… confirming with Kalshi';}
 let r;try{r=await api('/app/api/act',{a:'buy',i});}catch(e){r={ok:false,msg:'Couldn\'t reach your Mac ('+(e&&e.message||e)+'). Check Live before trying again, so you don\'t buy twice.'};}
 S.buying=false;hap(r.ok?'success':'error');toast(r.ok?`Bought: ${money(r.pays||0)} if it hits. It shows on Live within a minute.`:(r.msg||'Didn\'t go through.'),7000,r.ok?'good':'bad');
 if(custom)S.custom=null;else if(S.quotes)delete S.quotes[i];if(r.ok&&custom)S.slip=[];
 if(r.ok&&!custom&&S.build){const c=S.build.combos.find(x=>x.i===i);if(c)c.bought=true;}renderBuild();}
function hap(k){try{if(S.inapp){const f=document.createElement('iframe');f.style.display='none';f.src='combo://haptic/'+(k||'light');document.body.appendChild(f);setTimeout(()=>f.remove(),300);return;}
 if(navigator.vibrate){navigator.vibrate(k==='success'?[10,50,10]:k==='error'?[30,50,30]:k==='warning'?[20]:8);return;}
 let l=document.getElementById('hapl');if(!l){l=document.createElement('label');l.id='hapl';l.style.cssText='position:fixed;left:-99px;top:0;opacity:0;width:1px;height:1px;overflow:hidden';l.innerHTML='<input type="checkbox" switch>';document.body.appendChild(l);}
 l.click();if(k==='success'||k==='error')setTimeout(()=>l.click(),90);}catch(e){}}
// ---------------- RESULTS
function renderResults(){const d=S.res;const m=$('#main');if(!d){m.innerHTML=`<div class="kpis">${'<div class="kpi skel" style="height:84px"></div>'.repeat(5)}</div>`+skel(6);return;}
 const w=d.weeks||[];const mx=Math.max(1,...w.map(x=>Math.abs(x.pl)));const sh=d.shadow;
 m.innerHTML=`<div class="grid"><div><div class="kpis">
  <div class="kpi"><span>Profit / loss</span><b class="${d.pl>=0?'up':'down'}">${smoney(d.pl)}</b></div>
  <div class="kpi"><span>Return on stake</span><b>${d.roi==null?'—':(d.roi>=0?'+':'')+Math.round(d.roi*100)+'%'}</b></div>
  <div class="kpi"><span>Settled</span><b>${d.settled} <small>combos</small></b></div>
  <div class="kpi"><span>Won · cashed</span><b>${d.won} <small>· ${d.cashed}</small></b></div>
  <div class="kpi"><span>Best result</span><b class="up">${smoney(d.best)}</b></div></div>
  <h2>By week</h2><div class="chart"><svg viewBox="0 0 ${Math.max(1,w.length)*60} 160" width="100%" height="170" preserveAspectRatio="none">
   <line x1="0" y1="80" x2="${w.length*60}" y2="80" stroke="var(--line)"/>${w.map((x,i)=>{const h=Math.abs(x.pl)/mx*70;return `<rect x="${i*60+14}" y="${x.pl>=0?80-h:80}" width="32" height="${Math.max(2,h)}" rx="4" fill="${x.pl>=0?'var(--yes)':'var(--no)'}"><title>${x.week}: ${smoney(x.pl)} on ${x.n}</title></rect>`}).join('')}</svg>
   <div style="display:flex">${w.map(x=>`<div style="width:${100/Math.max(1,w.length)}%;text-align:center;font-size:11px" class="m">${(x.week||'').slice(5)}</div>`).join('')}</div></div>
  ${edgeBlock(d)}
  ${historyBlock(d.history||[])}
 </div><aside class="side">
  <div class="card"><h3>Shadow auto-trading <span>paper</span></h3>${sh&&sh.quotes?`<div class="mini">Settled<b>${sh.n}</b></div><div class="mini">Paper P/L<b class="${sh.back-sh.staked>=0?'up':'down'}">${smoney(sh.back-sh.staked)}</b></div>
   <div class="mini">Open<b>${sh.open}</b></div><div class="mini">Kalshi quotes, median<b>${pct(sh.median)} of fair</b></div><div class="mini">Buys at<b>${sh.min_pct}%+</b></div>${sh.same_game&&(sh.same_game.n||sh.same_game.open)?`<div class="mini">Same-game test (winner + total)<b class="${sh.same_game.pl>=0?'up':'down'}">${smoney(sh.same_game.pl)} · ${sh.same_game.n} settled, ${sh.same_game.open} open</b></div>`:''}`:'<div class="m">No quotes yet. The Mac asks within 8 hours of game time.</div>'}</div>
  <div class="card"><h3>Most accurate odds</h3><div class="m" style="font-size:13px">${esc(d.accuracy_text||'')}</div></div>
 </aside></div>`;}
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
 const rows=ws.slice(0,8).map(w=>w.status==='done'?`<div class="mini">${esc(w.sunday)} · ${w.k} games · ${w.upsets} upset${w.upsets===1?'':'s'}<b class="${w.pl>=0?'up':'down'}">${smoney(w.pl)} <span class="m" style="font-weight:500">of ${money(w.cost)}</span></b></div>`:
  w.status==='open'?`<div class="mini">${esc(w.sunday)} · ${w.k} games · waiting for results<b class="m">${pct(w.p_ahead)} chance to be ahead</b></div>`:
  `<div class="mini">${esc(w.sunday)}<b class="m">${w.status==='missed'?'missed (Mac was off before kickoff)':'no result'}</b></div>`).join('');
 return `<div class="card"><h3>Cover the early games <span>paper test · NFL Sundays</span></h3>
  ${c.n?`<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:8px"><b style="font-size:30px;letter-spacing:-.03em" class="${c.pl>=0?'up':'down'}">${smoney(c.pl)}</b><span class="m">over ${c.n} Sunday${c.n===1?'':'s'}, ${money(c.cost)} on paper</span></div>`:''}
  ${rows||'<div class="m">Starts this Sunday: the Mac snapshots the early games before kickoff, then works out what the one surviving combo would be worth at midday.</div>'}
  <div class="m" style="font-size:12px;margin-top:8px">$5 on every possible result of the early games, cashed out at midday. No money is spent. Uses Kalshi's prices and the cut Kalshi usually takes on combos and cash-outs.</div></div>`;}
function gateCard(r){if(!r)return '';const pp=r.paper||{},rr=r.real||{};const need=Math.max(0,50-pp.bets);
 return `<div class="card"><h3>Is it working? <span>the daily panel</span></h3>
  <div class="m" style="font-size:12.5px;margin-bottom:8px">A paper copy of each day's panel runs by itself, with no money. When it's ahead over 50+ bets and most days end up, it's ready to be handed $300.</div>
  <div class="mini">Paper panel<b class="${pp.pl>=0?'up':'down'}">${smoney(pp.pl||0)} <span class="m" style="font-weight:500">${pp.bets} bets · ${pp.days_up}/${pp.days} days up</span></b></div>
  <div class="mini">Your real panel<b class="${rr.pl>=0?'up':'down'}">${smoney(rr.pl||0)} <span class="m" style="font-weight:500">${rr.bets} bets</span></b></div>
  <div style="margin-top:10px;padding:10px 12px;border-radius:10px;background:var(--panel2);font-size:13px">${pp.ready?'✅ <b>Ready.</b> The paper record clears the bar for running it with $300 on its own.':`⏳ <b>Not yet.</b> ${need?need+' more paper bets to go':'Needs to be ahead, with most days up'}.`}</div></div>`;}
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
function skimRow(k){if(!k||!k.reserved)return '';return `<div class="srow"><div class="l"><b>Profit set aside</b><small>${money(k.reserved)} isn't bet with. Move it out of Kalshi, then tap here.</small></div><button class="btn ghost" onclick="api('/app/api/act',{a:'skim_moved'}).then(r=>{toast(r.msg,5000);load('settings')})">I moved it</button></div>`;}
function cutCard(cs){if(!cs||!cs.length)return `<div class="srow"><div class="l"><b>Panel combo cut-off</b><small>Starts at 95% of fair for every sport and size, and adjusts itself weekly from results (never below 85%).</small></div><b>95%</b></div>`;
 return `<div class="srow" style="display:block"><div class="l"><b>Panel combo cut-off</b><small>Adjusts itself weekly from results; never below 85%.</small></div>${cs.map(c=>`<div class="mini" style="margin-top:6px">${esc(c.group.replace(':',' · ')+' picks')}<b>${c.level}%</b></div>${c.why?`<div class="m" style="font-size:11.5px">${esc(c.why)}</div>`:''}`).join('')}</div>`;}
function fidRow(){const f=S.fid||{};const here=(f.keys||[]).filter(k=>k.rp===location.hostname);
 if(LOCAL&&!/\.ts\.net$/.test(location.hostname))return (f.keys||[]).length?`<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${f.keys.map(k=>esc(k.name)).join(', ')}</small></div><button class="btn ghost" onclick="fidRemoveAll()">Remove all</button></div>`:'';
 if(location.protocol!=='https:'||!window.PublicKeyCredential)return `<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${(S.pk||{}).https?`Works on the secure address. Open <a href="${esc(S.pk.https)}">${esc(S.pk.https.replace('https://',''))}</a> and turn it on there.`:'Needs the Mac\'s secure address first (Settings › This Mac on the Mac).'}</small></div></div>`;
 return `<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${here.length?`On for ${here.map(k=>esc(k.name)).join(', ')}. Unlock Combo Hub with your face instead of the passcode.`:'Unlock Combo Hub with Face ID instead of typing the passcode.'}</small></div>
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
  ${S.pushOn?`<button class="btn" onclick="pushTest()">Send test</button><button class="btn ghost" onclick="pushOff()">Turn off</button>`:`<button class="btn acc" onclick="pushOn(this)">Turn on</button>`}</div>`;}
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
async function pushTest(){const t=await api('/app/push',{a:'test'});toast(t.sent?'Sent. It should arrive in a few seconds.':'Nothing sent. Try turning it off and on.');}
async function pushOff(){try{const reg=await navigator.serviceWorker.getRegistration();const sub=reg&&await reg.pushManager.getSubscription();if(sub){await api('/app/push',{a:'off',sub:sub.toJSON()});await sub.unsubscribe();}}catch(e){}S.pushOn=false;toast('Notifications off on this device.');load('settings');}
function httpsRow(mac){const h=mac.https||{};
 if(h.state==='on')return `<div class="srow"><div class="l"><b>Secure address</b><small><a href="${esc(h.url)}" target="_blank">${esc(h.url.replace('https://',''))}</a> · use this on your iPhone for notifications</small></div><button class="btn ghost" onclick="navigator.clipboard.writeText('${esc(h.url)}').then(()=>toast('Copied'))">Copy</button></div>`;
 if(h.state==='need-enable')return `<div class="srow"><div class="l"><b>Secure address: one step</b><small>Tailscale needs you to allow https for your network once. Open the link, approve, then tap Check.</small></div><a class="btn acc" href="${esc(h.link)}" target="_blank">Allow https</a><button class="btn" onclick="macDo('https',this)">Check</button></div>`;
 return `<div class="srow"><div class="l"><b>Secure address</b><small>${h.state==='no-cli'?'Tailscale\'s command line isn\'t available on this Mac.':h.state?'Not on yet ('+esc(h.state)+').':'Checking…'}</small></div><button class="btn" onclick="macDo('https',this)">Try again</button></div>`;}
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
function linesBlock(d){const ls=d.lines||[];if(!ls.length)return '';const games={};ls.forEach(x=>{(games[x.game]=games[x.game]||[]).push(x);});
 return `<h2>Spreads &amp; totals <span class="n">${ls.length}</span><span class="r m" style="font-size:12px">Kalshi price · model chance from the sportsbook line</span></h2>
  <div class="tbl lines"><div class="lrow2 m" style="font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding-top:10px"><span></span><span class="num">Kalshi</span><span class="num">Chance</span><span class="num" style="text-align:center">Edge</span></div>${Object.entries(games).map(([g,xs])=>`<div class="lhd">${esc(g)} <span class="m">· book ${xs.find(x=>x.kind==='spread')?'spread '+xs.find(x=>x.kind==='spread').book_line:''}${xs.find(x=>x.kind==='total')?' · total '+xs.find(x=>x.kind==='total').book_line:''}</span></div>
   ${xs.sort((a,b)=>a.kind.localeCompare(b.kind)||a.line-b.line).map(x=>`<div class="lrow2"><span>${x.kind==='spread'?'📏':'➕'} ${esc(x.pick.replace(/ \(.*\)$/,''))}</span><span class="num">${Math.round(x.p*100)}¢</span><span class="num m">${pct(x.fair)}</span>
    <button class="btn ${x.edge>=0.04?'acc':'ghost'}" onclick="lineFromBoard('${x.ticker}',this)">${x.edge>=0?'+':'−'}${Math.abs(x.edge*100).toFixed(1)}¢</button></div>`).join('')}`).join('')}</div>
  <div class="m" style="font-size:12px;margin:6px 2px 0">Edge after Kalshi's fee. Blue = at least 4¢ in your favour. A score model adds its own error, so treat small edges as zero.</div>`;}
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
async function openCombo(t){modal(`<div class="m" style="padding:30px;text-align:center"><span class="spin"></span></div>`);$('#sheet').classList.add('wide');
 const r=await api('/app/api/combo?t='+encodeURIComponent(t)).catch(()=>null);const c=r&&r.combo;
 if(!c){$('#sheet').innerHTML='<h3>Not found</h3><p>That combo isn\'t live any more.</p><div class="row"><button class="btn" onclick="closeModal()">Close</button></div>';return;}
 const h=r.history||{offers:[],ticks:{}};const [vc,vt]=verdictOf(c);
 $('#sheet').innerHTML=`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${(c.sports||[]).map(s=>SPN[s]||s).join(' · ')}</div><h3 style="font-size:22px">${esc(c.label)}</h3><div class="m">${esc(nextLine(c))}</div></div>
  <div style="display:flex;gap:8px;align-items:center"><span class="verdict ${vc}">${vt}</span><button class="btn ghost" onclick="closeModal()">Close</button></div></div>
  <div class="dkpis"><div><span>Paid</span><b>${money(c.cost)}</b></div><div><span>Pays</span><b>${money(c.pays)}</b></div><div><span>Chance</span><b>${c.group==='pending'?pct(c.p):'—'}</b></div><div><span>${c.offer_real?'Offer':'Likely offer'}</span><b>${c.offer!=null?(c.offer_real?'':'≈ ')+money(c.offer):'—'}</b></div></div>
  ${c.why?`<p style="margin:-4px 0 14px">${esc(c.why)}</p>`:''}
  <div class="chartbox">${valueChart(h.offers,c.cost,c.pays)}</div>
  <h2 style="margin:4px 0 6px">Picks <span class="n">${c.legs.length}</span></h2><div class="dlegs">${c.legs.map(l=>{const tk=(h.ticks||{})[l.ticker]||[];const pts=tk.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
   return `<div class="lg"><div><b>${ICON[l.sport]||''} ${esc(l.name)}</b><div class="m" style="font-size:12.5px">${l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</div></div>
    ${l.res?`<span class="m" style="text-align:center">${l.res==='yes'?'✓ won':'✕ lost'}</span>`:spark(pts,120,28)}<b style="text-align:right">${l.res?'':pct(l.live!=null?l.live:l.chance)}</b></div>`;}).join('')}</div>
  ${c.group==='pending'?`<div class="row" style="margin-top:16px;flex-wrap:wrap">${c.hedge&&!c.hedge.done?`<button class="btn" onclick="closeModal();hedge('${c.t}')">Hedge · ${money(c.hedge.cost)}</button>`:''}
   <button class="btn" onclick="closeModal();ask('${c.t}')">${c.offer_real?'New offer':'Get cash-out offer'}</button>${c.offer_real?`<button class="btn yes" onclick="closeModal();sell('${c.t}')">Cash out ${money(c.offer)}</button>`:''}</div>`:''}`;}
// ---------------- games
function renderGames(){const d=S.games;const m=$('#main');if(!d){m.innerHTML=`<div class="games">${'<div class="gt skel" style="height:190px"></div>'.repeat(6)}</div>`;return;}
 const gs=d.games||[];if(!gs.length){m.innerHTML='<div class="card empty"><b>No games to watch</b>Games you need show up here with live scores and win chances.</div>';return;}
 const live=gs.filter(g=>g.state==='live'),rest=gs.filter(g=>g.state!=='live');
 const tile=g=>{const ch=g.chance;const sc=g.sc;const lc=g.state==='live'?legCls({state:'live',sc,live:ch}):'';return `<div class="gt ${g.state==='live'?'live '+lc:''}" style="cursor:pointer" onclick="openGame('${g.ticker||''}')"><div class="top2"><div><div class="tm">${ICON[g.sport]||''} ${esc(g.name)}</div><div class="vs">${g.opp?'vs '+esc(g.opp):''}${g.state!=='live'&&g.starts?' · '+esc(g.starts):''}</div></div>
   ${g.state==='live'&&sc?`<div class="sc">${sc.me}–${sc.opp}<small>${esc(sc.detail||'')}</small></div>`:'<span class="tag" style="background:var(--panel2);color:var(--sub)">'+(g.state==='live'?'LIVE':'UPCOMING')+'</span>'}</div>
   <div class="ch"><b class="${ch>=.5?'up':'down'}">${pct(ch)}</b><span>${g.state==='live'?'to win right now':'to win'}</span></div>${spark(g.spark,300,56)}
   <div class="ft"><span>In ${g.combos} combo${g.combos>1?'s':''}</span><b>${money(g.pays)} riding</b></div></div>`;};
 m.innerHTML=(live.length?`<h2><span class="live-dot"></span>Playing now <span class="n">${live.length}</span></h2><div class="games">${live.map(tile).join('')}</div>`:'')
  +(rest.length?`<h2>Coming up <span class="n">${rest.length}</span></h2><div class="games">${rest.map(tile).join('')}</div>`:'');}
// ---------------- one game, live
async function openGame(t){if(!t)return;S.gameOpen=t;modal(`<div class="m" style="padding:30px;text-align:center"><span class="spin"></span></div>`);$('#sheet').classList.add('wide');await drawGame();}
async function drawGame(){const t=S.gameOpen;if(!t||!$('#modal').classList.contains('on'))return;
 const r=await api('/app/api/game?t='+encodeURIComponent(t)).catch(()=>null);if(!r||!r.leg){$('#sheet').innerHTML='<h3>Game not found</h3><p>It may have finished and settled.</p><div class="row"><button class="btn" onclick="closeModal()">Close</button></div>';return;}
 const l=r.leg,sc=l.sc,st=r.story||{ticks:[],plays:[]};const ch=l.live!=null?l.live:l.chance;const lc=legCls(l);
 const pts=st.ticks.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
 const plays=st.plays.slice().reverse();
 $('#sheet').innerHTML=`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${esc(SPN[l.sport]||l.sport)}${l.state==='live'?' · <span style="color:var(--live)">LIVE</span>':''}</div>
   <h3 style="font-size:20px">${ICON[l.sport]||''} ${esc(l.name)}${l.opp?` <span class="m" style="font-weight:500">vs ${esc(l.opp)}</span>`:''}</h3></div><button class="btn ghost" onclick="closeModal()">Close</button></div>
  <div class="board2 ${lc}">${sc?`<div class="tm2"><span>${esc(sc.abbr)}</span><b>${sc.me}</b></div><div class="mid2"><div class="clk">${esc(sc.detail||'')}</div><div class="m">${l.state==='live'?'in progress':''}</div></div><div class="tm2 r"><b>${sc.opp}</b><span>${esc(sc.opp_abbr)}</span></div>`:
   `<div class="mid2" style="grid-column:1/-1"><div class="clk">${esc(l.starts||'Not started')}</div></div>`}</div>
  <div class="dkpis"><div><span>${esc(short(l.name))} to win</span><b class="${ch>=.5?'up':'down'}">${pct(ch)}</b></div><div><span>Your combos on it</span><b>${r.combos.length}</b></div><div><span>Riding on it</span><b>${money(r.combos.reduce((a,c)=>a+c.pays,0))}</b></div><div><span>Score changes</span><b>${Math.max(0,st.plays.length-1)}</b></div></div>
  <div class="chartbox">${winChart(pts,st.plays)}</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px">
   <div><h2 style="margin:0 0 6px">Scoring</h2>${plays.length>1?plays.slice(0,-1).map((p,i)=>{const prev=plays[i+1];const mine=p.me>prev.me;return `<div class="moment"><span class="k" style="color:${mine?'var(--yes)':'var(--no)'}">${mine?'▲':'▼'}</span><span>${mine?esc(short(l.name)):esc(short(l.opp||'Them'))} score · <b>${p.me}–${p.opp}</b> <span class="m">${esc(p.detail||'')}</span></span><time>${ago2(p.ts)}</time></div>`;}).join(''):'<div class="m">No score changes recorded yet.</div>'}</div>
   <div><h2 style="margin:0 0 6px">Your combos on this game</h2>${r.combos.map(c=>`<div class="moment" style="cursor:pointer" onclick="openCombo('${c.t}')"><span class="k">🎯</span><span><b>${esc(c.label)}</b> <span class="m">${c.legs} picks · ${pct(c.p)} to hit</span></span><b>${money(c.pays)}</b></div>`).join('')||'<div class="m">None pending.</div>'}
   ${r.whatif?`<h2 style="margin:16px 0 6px">What if…</h2><div class="whatif"><div class="wi up"><span>${esc(short(l.name))} get the next ${esc(r.whatif.unit)}</span><b>${pct(r.whatif.up)}</b><small>to win${r.combos[0]&&r.combos[0].if_up!=null?` · ${esc(r.combos[0].label)} worth ≈${money(r.combos[0].if_up)}`:''}</small></div>
    <div class="wi down"><span>${esc(short(l.opp||'They'))} get it</span><b>${pct(r.whatif.down)}</b><small>to win${r.combos[0]&&r.combos[0].if_down!=null?` · ≈${money(r.combos[0].if_down)}`:''}</small></div></div>
    ${r.combos[0]&&r.combos[0].now!=null?`<div class="m" style="font-size:12px;margin-top:6px">Worth ≈${money(r.combos[0].now)} now. Estimates use Kalshi's usual cash-out discount.</div>`:''}`:''}</div></div>
  ${l.url?`<div class="row" style="margin-top:14px"><a class="btn" href="${esc(l.url)}" target="_blank">Kalshi game page ↗</a></div>`:''}`;}
function winChart(pts,plays){if(!pts||pts.length<2)return '<div class="m" style="padding:18px 4px">The win-chance line fills in as the Mac watches this game.</div>';
 const W=Math.round(Math.max(340,Math.min(820,window.innerWidth-70))),H=170,pl=36,iw=W-pl-8,ih=H-30;const t0=pts[0][0],t1=pts[pts.length-1][0];
 const X=t=>pl+(t-t0)/Math.max(1,t1-t0)*iw,Y=v=>8+ih-v*ih;const d=pts.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');
 const last=pts[pts.length-1][1];const col=last>=.5?'var(--yes)':'var(--no)';const tl=t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
 return `<div class="key"><span><i style="background:${col}"></i>Chance to win</span><span><i style="background:var(--sub);height:8px;width:2px"></i>Score change</span></div><svg viewBox="0 0 ${W} ${H}">
  ${[0,.25,.5,.75,1].map(v=>`<line x1="${pl}" x2="${W-8}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" ${v===.5?'stroke-dasharray="4 4"':''}/><text x="${pl-6}" y="${Y(v)+4}" font-size="11" text-anchor="end" fill="var(--mute)">${v*100}%</text>`).join('')}
  ${(plays||[]).slice(1).filter(p=>p.ts>=t0).map(p=>`<line x1="${X(p.ts)}" x2="${X(p.ts)}" y1="8" y2="${8+ih}" stroke="var(--sub)" stroke-width="1" opacity=".35"/>`).join('')}
  <path d="${d} L${X(t1)} ${8+ih} L${pl} ${8+ih}Z" fill="${col}" opacity=".08"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round"/>
  <text x="${pl}" y="${H-4}" font-size="11" fill="var(--mute)">${tl(t0)}</text><text x="${W-8}" y="${H-4}" font-size="11" fill="var(--mute)" text-anchor="end">${tl(t1)}</text></svg>`;}
// ---------------- live events from the Mac
async function loadRecap(){const h=new Date().getHours();const day=new Date().toDateString();
 let seen='';try{seen=localStorage.getItem('cw_recap')||''}catch(e){}
 if(h<5||h>=14||seen===day){S.recap=null;return;}S.recap=await api('/app/api/recap').catch(()=>null);if(S.view==='live')renderLive();}
function recapCard(){const r=S.recap;if(!r||!r.bets||!r.bets.length)return '';
 return `<div class="card recap"><div class="rh"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">Yesterday</div>
  <b style="font-size:26px" class="${r.pl>=0?'up':'down'}">${smoney(r.pl)}</b> <span class="m">${r.won} up · ${r.lost} down${r.streak>1?` · 🔥 ${r.streak} days up in a row`:''}</span></div>
  <button class="x" onclick="try{localStorage.setItem('cw_recap',new Date().toDateString())}catch(e){};S.recap=null;renderLive()">✕</button></div>
  ${r.best&&r.best.pl>0?`<div class="mini">Best<b class="up">${esc(r.best.what)} ${smoney(r.best.pl)}</b></div>`:''}${r.worst&&r.worst.pl<0?`<div class="mini">Worst<b class="down">${esc(r.worst.what)} ${smoney(r.worst.pl)}</b></div>`:''}
  ${r.note?`<div class="m" style="font-size:12.5px;margin-top:6px">${esc(r.note)}</div>`:''}</div>`;}
function celebrate(){hap('success');const box=document.createElement('div');box.className='confetti';const cols=['#4f8cff','#3ecf8e','#ffb020','#ff6b9a','#b48cff'];
 for(let i=0;i<70;i++){const s=document.createElement('i');s.style.left=Math.random()*100+'vw';s.style.background=cols[i%cols.length];s.style.animationDelay=Math.random()*.4+'s';s.style.transform=`rotate(${Math.random()*360}deg)`;box.appendChild(s);}
 document.body.appendChild(box);setTimeout(()=>box.remove(),2600);}
function connect(){if(!window.EventSource)return;try{const es=new EventSource('/app/events');S.es=es;
 es.onopen=()=>{S.live_ok=true;stat();};
 es.onerror=()=>{S.live_ok=false;stat();};
 es.onmessage=e=>{let ev;try{ev=JSON.parse(e.data)}catch(x){return}
  if(ev.kind==='tick'){if(['live','games'].includes(S.view)&&Date.now()-(S.lastLoad||0)>4000&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}return;}
  S.events=(S.events||[]).concat([ev]).slice(-30);
  if(ev.kind==='settled'&&/ won$/.test(ev.text||''))celebrate();
  if(['score','advice','alert','settled','idea'].includes(ev.kind)){const k=ev.kind+'|'+ev.text;S.seen=S.seen||{};if(Date.now()-(S.seen[k]||0)>90000){S.seen[k]=Date.now();toast(ev.text,ev.kind==='score'?6000:4500,ev.kind==='score'?(ev.good?'good':'bad'):null);}}
  if(S.gameOpen&&ev.ticker===S.gameOpen)drawGame();
  if(S.view==='live'||S.view==='games'){S.lastLoad=Date.now();load(S.view,ev.kind==='advice'||ev.kind==='settled'||ev.kind==='idea');}};
 }catch(x){}}
function stat(){const el=$('#st');if(!el)return;el.innerHTML=`<span class="dot ${S.live_ok===false?'off':''}"></span>${S.live_ok===false?'Reconnecting…':'Mac · live'}`;}
// ---------------- settings
const UNITS={panel_budget:['$',''],take_profit:['','% of payout'],stake:['$',''],budget:['$',''],accept_pct:['','%'],live_min:['','%'],max_share:['','%'],bankroll:['$',''],refresh_secs:['','s'],cash_every:['',' min'],auto_cap:['',''],hedge_cap:['$','']};
const RANGES={panel_budget:[10,200,5],take_profit:[0,95,5],stake:[1,20,1],budget:[10,200,10],accept_pct:[50,100,5],live_min:[10,50,5],max_share:[20,100,10],bankroll:[100,5000,100],refresh_secs:[10,120,5],cash_every:[1,10,1],auto_cap:[1,10,1],hedge_cap:[25,500,25]};
function fmtv(k,v){if(k==='take_profit'&&+v===0)return 'Off';const u=UNITS[k]||['',''];return u[0]+(+v).toLocaleString()+u[1];}
function rng(k,label,sub,dis){const v=S.set.values[k],[lo,hi,st]=RANGES[k];const p=Math.round((Math.min(Math.max(v,lo),hi)-lo)/(hi-lo)*100);
 return `<div class="srow ${dis?'dim':''}"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><div class="rng"><input type="range" min="${lo}" max="${hi}" step="${st}" value="${v}" style="--p:${p}%"
  oninput="this.style.setProperty('--p',Math.round((this.value-${lo})/${hi-lo}*100)+'%');this.nextElementSibling.textContent=fmtv('${k}',this.value)" onchange="setv('${k}',+this.value)"><output>${fmtv(k,v)}</output></div></div>`;}
function tgl(k,label,sub,dis){return `<label class="srow ${dis?'dim':''}"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><input type="checkbox" class="tg" ${S.set.values[k]?'checked':''} onchange="setv('${k}',this.checked)"></label>`;}
function seg(k,label,sub,names){const v=S.set.values[k];return `<div class="srow"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><div class="seg">${names.map((n,i)=>`<button class="${v===i?'on':''}" onclick="setv('${k}',${i});renderSettings()">${esc(n)}</button>`).join('')}</div></div>`;}
function stp(k,lo,hi){const v=S.set.values[k];return `<div class="stp"><button onclick="bump('${k}',-1,${lo},${hi})">−</button><span>${v}</span><button onclick="bump('${k}',1,${lo},${hi})">＋</button></div>`;}
function bump(k,d,lo,hi){const v=Math.min(hi,Math.max(lo,(S.set.values[k]||0)+d));if(v===S.set.values[k])return;setv(k,v);
 const t=k.split('_')[0];const mn=t+'_min',mx=t+'_max';if(S.set.values[mn]>S.set.values[mx]){const o=k===mn?mx:mn;setv(o,S.set.values[k]);}renderSettings();}
function scard(id,ic,title,sub,inner){return `<section class="scard" id="s-${id}"><header><span class="ic">${ic}</span><div><h3>${title}</h3>${sub?`<p>${sub}</p>`:''}</div></header>${inner}</section>`;}
const PEND={};let saveT=null;
function setv(k,v){S.set.values[k]=v;PEND[k]=v;saved('Saving…');clearTimeout(saveT);saveT=setTimeout(flush,450);
 if(['auto_sell','auto_hedge','include_live','auto_cash','size_auto'].includes(k))renderSettings();}
async function flush(){const vals=Object.assign({},PEND);for(const k in PEND)delete PEND[k];
 const r=await api('/app/api/settings',{lg:S.set.lg,values:vals}).catch(()=>({ok:false}));
 if(r.ok){S.build=null;saved('Saved','ok');if(r.synced===true)toast('Saved · the Mac watcher has it now.');else if(r.synced===false)toast('Saved here, but the Mac watcher didn\'t get it. Try again.');}
 else{saved('Not saved');toast(r.msg||'Couldn\'t save. Check the connection.');}}
function saved(t,c){const e=$('#saved');if(e){e.className='saved '+(c||'');e.innerHTML=(t==='Saving…'?'<span class="spin"></span>':c==='ok'?'✓':'')+' '+t;}}
function sport(lg){S.slg=lg;S.set=null;renderSettings();load('settings');}
function renderSettings(){const m=$('#main');const d=S.set;if(!d){m.innerHTML=`<div class="set"><div></div><div>${skel(8)}</div></div>`;return;}
 const v=d.values,mode=d.mode,mac=S.mac;
 const cap=mode==='mix'?'Mix cap':mode==='day'?'Daily cap':'Weekend cap';
 const days=mode==='mix'?seg('mix_window','Games from','Which games Mixed sports can combine',d.windows)+tgl('next_day','Same day means tomorrow'):
  mode==='day'?tgl('next_day','Use tomorrow\'s games','Instead of today\'s'):
  tgl('thursday','Thursday games')+tgl('saturday','Saturday games')+tgl('monday','Monday games')+`<div class="srow"><div class="l"><small>Sunday is always in.</small></div></div>`;
 const tiers=(d.full?[['full','Full slate','Every game on the slate in one bet. You choose how many underdogs it picks.','upsets',0,8,'underdogs']]:[]).concat([['safer','Safer','Short combos, more likely to hit.',null,2,8,'games each'],['middle','Middle','The core of the mix.',null,2,12,'games each'],['moonshot','Moonshot','Long shots, big payouts.',null,2,16,'games each']]);
 const mix=`<div class="mixl">${tiers.map(([t,n,s,alt,lo,hi,unit])=>{const b=alt||t;
  return `<div class="mixr"><div><b>${n}</b><small>${s}</small></div><div class="mixs"><div><span>How many</span>${stp(t+'_count',0,10)}</div><div><span>${alt?'Underdogs':'Games each'}</span>${stp(b+'_min',alt?0:lo,hi)}<span>to</span>${stp(b+'_max',alt?0:lo,hi)}</div></div></div>`;}).join('')}</div>`;
 const secs=[['money','💵','Money'],['mix','🧩','Combo mix'],['games','🗓️','Games & picks'],['killer','🔥','Killer deals'],['maker','📌','Standing orders'],['cash','💸','Cash out & hedging'],['alerts','🔔','Notifications'],['mac','💻',LOCAL?'This Mac':'The Mac'],['keys','🔑','Accounts & keys']];
 const ago=s=>s<3600?Math.round(s/60)+' min':s<86400?Math.round(s/3600)+' hr':Math.round(s/86400)+' days';
 const macCard=LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Tailscale</span><b>${mac.ts?esc(mac.ts):'<span class="down">Not signed in</span>'}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · auto cash-out paused':''}</b></div>
   <div><span>Combo Hub passcode</span><b>${esc(mac.pass)}</b></div><div><span>Updates</span><b>${mac.auto_update?'Automatic':'Phone-approved · '+esc(mac.approved||'—')}</b></div></div>
   <div class="sact"><button class="btn acc" onclick="macDo('update',this)">Update now</button><button class="btn" onclick="macCode()">Phone pairing code</button><button class="btn" onclick="macPass()">Change passcode</button><button class="btn" onclick="S.showlog=!S.showlog;renderSettings()">${S.showlog?'Hide':'Show'} activity</button><button class="btn ghost" onclick="macDo('advanced',this)">Kalshi key & removal…</button></div>
   <label class="srow"><div class="l"><b>Install updates automatically</b><small>${mac.auto_update?'New versions install within about 10 minutes, no tap needed.':'Waits until your phone runs the new version and approves it.'}</small></div><input type="checkbox" class="tg" ${mac.auto_update?'checked':''} onchange="api('/app/mac',{a:'autoupdate',on:this.checked}).then(r=>{toast(r.msg);load('settings')})"></label>
   <div class="srow"><div class="l"><b>Alerts</b><small>${mac.last_push&&mac.last_push.at?`Last sent ${ago2(mac.last_push.at)} ago${mac.last_push.ok===false?' · <span class="down">ntfy refused it ('+mac.last_push.code+')</span>':''}: ${esc(mac.last_push.title)}`:'None sent since the Mac last restarted.'}${mac.quiet?' · Quiet hours now (10 PM–7 AM): only urgent ones go out.':''}</small></div><button class="btn" onclick="macDo('testpush',this)">Send test</button></div>
   ${httpsRow(mac)}${mac.history?`<div class="srow"><div class="l"><b>History on this Mac</b><small>${(mac.history.q||0).toLocaleString()} Kalshi quotes · ${(mac.history.t||0).toLocaleString()} live ticks · ${(mac.history.b||0).toLocaleString()} combos tracked</small></div></div>`:''}
   ${S.showlog?`<div class="logbox">${esc((mac.log||[]).join('\n'))}</div>`:''}`
  :!LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Newest</span><b>${mac.latest?(mac.latest===mac.engine?'<span class="up">Up to date</span>':esc(mac.latest)+(mac.waiting?' · waiting':' · installing soon')):'—'}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · paused':''}</b></div></div>
   <div class="srow"><div class="l"><small>Updates install ${mac.auto_update?'automatically within about 10 minutes':'after your phone approves them'}. The pairing code, passcode and update controls are on the Mac itself.</small></div></div>`
  :`<div class="srow"><div class="l"><b>${LOCAL?'Couldn\'t read the Mac\'s status':'Couldn\'t reach the Mac'}</b><small>${LOCAL?'Reload in a moment.':'It may be asleep or restarting. Pull to refresh in a minute.'}</small></div></div>`;
 m.innerHTML=`<div class="set"><nav class="sidx">${secs.map(([id,ic,t])=>`<a href="#s-${id}" onclick="event.preventDefault();document.getElementById('s-${id}').scrollIntoView({behavior:'smooth'})">${ic} ${t}</a>`).join('')}<div class="sv">Planner ${esc(d.version)}</div></nav><div>
 <div class="shead"><div><h1>Settings</h1><p>Planner settings are per sport. Changes save as you go.</p></div><div class="saved" id="saved"></div></div>
 <div class="chips" style="margin-bottom:18px">${d.leagues.map(([k,n,ic])=>`<button class="chip ${k===d.lg?'on':''}" onclick="sport('${k}')">${ic} ${esc(n)}</button>`).join('')}</div>
 ${scard('money','💵','Money','What each combo costs and the price you\'ll accept from Kalshi.',
   rng('panel_budget',"Today's panel",'The most the daily panel spends in one day')+cutCard(S.panelCuts)+skimRow(S.skim)+rng('stake','Per combo')+rng('budget',cap,'The most the planner spends in one '+(mode==='day'?'day':mode==='mix'?'mix':'weekend'))+rng('accept_pct','Cut-off for your own combos','Kalshi prices paying less than this share of fair get marked')+tgl('size_auto','Bet more when the price is good','$3 near the cut-off, up to $10 well above fair'))}
 ${scard('mix','🧩','Combo mix','How many of each kind to build each day, and how big each one is.',mix)}
 ${scard('games','🗓️','Games & picks','Which games go in, and how picks are spread.',days+tgl('include_live','Include games already in progress','With extra safety checks')+rng('live_min','Live picks need at least','Chance to win right now',!v.include_live)
   +rng('max_share','One pick in at most','Share of combos for any single team')+tgl('hedge_close','Split coin-flip games','Put both sides of close games across combos')+tgl('dogs_late','Underdogs late','Favourites in the early games')+tgl('skip_news','Skip games with breaking news','When Kalshi and the sportsbooks disagree a lot'))}
 ${d.killer?scard('killer','🔥','Killer deals','Rare deals so good the Mac may buy them on its own.',killerCard(d.killer)):''}
 ${d.maker?scard('maker','📌','Standing orders','Buy orders resting under fair, managed by the Mac.',makerCard(d.maker)):''}
 ${scard('cash','💸','Cash out & hedging','When to take money off the table. The Mac watches these all day.',
   rng('bankroll','Betting bankroll','Bigger sure amounts against this get favoured')+seg('ride','Let it ride','How long to hold before cashing out',d.ride)
   +tgl('auto_cash','Keep a cash-out offer ready','On every live combo')+rng('cash_every','Fresh offers every','',!v.auto_cash)+rng('refresh_secs','Live updates every')
   +tgl('auto_sell','Auto cash-out','The Mac sells by itself, logged and capped')
   +tgl('smart_sell','Smart profit-taking','Sells when locking in beats the risk of holding, by sport: a one-goal hockey lead is fragile, an early NBA lead isn\'t',!v.auto_sell)
   +rng('take_profit','Take profit at','Sell once Kalshi offers this much of the payout, if it\'s at least 25% more than you paid',!v.auto_sell)
   +tgl('lock_trail','Lock in a run-up','After the offer reaches 60% of the payout, sell if it drops 20% from its high, while still a profit',!v.auto_sell)
   +tgl('stop_loss','Sell at a loss when a game turns','Off: never sells below what you paid',!v.auto_sell)
   +rng('auto_cap','Auto cash-outs a day, at most','',!v.auto_sell)
   +tgl('auto_hedge','Hedge instead when it locks in more','A small purchase of the other side',!v.auto_sell)+tgl('prefer_hedge','Prefer hedging','Even at up to 5% less than the cash-out',!v.auto_sell)+rng('hedge_cap','Most to spend on one hedge','',!v.auto_sell))}
 ${scard('alerts','🔔','Notifications','From the Mac. Bundled to one every 30 minutes, quiet 10 PM–7 AM. Urgent ones come right away.',
   fidRow()+pushRow()+tgl('notify_value','Combos quoting at a fair price')+tgl('notify_price','A better price on a combo')+tgl('notify_cash','Cash-outs and hedges')+tgl('notify_news','Big line moves and news'))}
 ${scard('mac','💻',LOCAL?'This Mac':'The Mac',LOCAL?'The watcher and Combo Hub run here, and keep themselves up to date.':'',macCard)}
 ${scard('keys','🔑','Accounts & keys','Keys never leave the device they\'re on.',`<div class="kv"><div><span>Kalshi</span><b style="display:flex;align-items:center;gap:7px;word-break:normal">${d.keys.kalshi?'<span class="dot" style="flex:none"></span><span>Connected through the Mac</span>':'<span class="down">Not connected</span>'}</b></div><div><span>Sportsbook odds</span><b>${d.keys.odds?'Key saved':'Free sources only'}</b></div></div>
   <div class="srow"><div class="l"><small>Change the Mac's Kalshi key under This Mac › Kalshi key. The phone's keys are in the planner on the iPhone.</small></div><a class="btn ghost" href="${S.inapp?'combo://phone':'/app/classic'}">${S.inapp?'Phone screens':'Classic screens'}</a></div>`)}
 </div></div>`;}
async function macDo(a,b){if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> '+b.textContent;}const r=await api('/app/mac',{a}).catch(()=>({ok:false}));
 toast(r.msg||(r.ok?'Done.':'That didn\'t work.'),5000);if(a==='update'&&r.ok)setTimeout(()=>location.reload(),70000);else load('settings');}
async function macCode(){const r=await api('/app/mac',{a:'code'});modal(`<h3>Phone pairing code</h3><p>On the iPhone: planner › Settings › Watcher, paste this and Save. Only needed for a new phone or a reinstall.</p>
 <div class="code" id="pc">${esc(r.code||'')}</div><p class="m" style="font-size:12.5px">Hub: ${esc(r.hub||'Tailscale not signed in: the phone can only use the Mac at home.')}</p>
 <div class="row"><button class="btn" onclick="closeModal()">Close</button><button class="btn acc" onclick="navigator.clipboard.writeText($('#pc').textContent).then(()=>toast('Copied'))">Copy</button></div>`);}
function macPass(){modal(`<h3>Combo Hub passcode</h3><p>Needed on devices other than this Mac. Your phone's Open Combo Hub link signs in by itself.</p>
 <input class="txt" id="np" placeholder="At least 6 characters" autocomplete="new-password"><p class="m" id="perr" style="color:var(--no);min-height:18px"></p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="savePass()">Save passcode</button></div>`);setTimeout(()=>$('#np').focus(),50);}
async function savePass(){const r=await api('/app/mac',{a:'passcode',pass:$('#np').value});if(!r.ok){$('#perr').textContent=r.msg;return;}closeModal();toast(r.msg,5000);load('settings');}
// ---------------- refresh loop
window.__inapp=function(){S.inapp=true;if(!document.getElementById('phonescr'))$('#dd').insertAdjacentHTML('beforeend','<a id="phonescr" href="combo://phone">Phone screens (no Mac)</a>');};
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
    import threading, types, itertools
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Bridge:
        def __init__(self):
            self.cv = threading.Condition()
            self.html, self.v, self.q, self.res, self.seen = "", 0, [], {}, 0.0
            self.ids = itertools.count(1)

        def active(self):
            return time.time() - self.seen < 120

        def load(self, h):
            with self.cv:
                self.html, self.v, self.q = h, self.v + 1, []
                self.cv.notify_all()

        def quiet(self, h):
            """The page changed in place (already sent to the browser): remember it for a reload."""
            with self.cv:
                self.html = h

        def js(self, code, timeout=4.0, wait=False):
            if not self.active():
                return ""
            with self.cv:
                i = next(self.ids)
                self.q.append({"id": i, "code": code, "w": wait})
                self.cv.notify_all()
                if not wait:
                    return ""                       # the planner never needs these answers: don't wait
                end = time.time() + timeout
                while i not in self.res and time.time() < end:
                    self.cv.wait(end - time.time())
                return self.res.pop(i, "")

        def poll(self, v):
            self.seen = time.time()
            with self.cv:
                end = time.time() + 20
                while v == self.v and not self.q and time.time() < end:
                    self.cv.wait(end - time.time())
                out, self.q = self.q, []
                return {"v": self.v, "js": out}

        def result(self, i, value):
            with self.cv:
                self.res[i] = value
                self.cv.notify_all()
                if len(self.res) > 200:
                    self.res.clear()

    B = Bridge()

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
            B.load(h)

        def evaluate_javascript(self, js):
            # whole-page swaps become a fresh page in the browser (so a reload shows the same thing)
            if js.startswith("typeof window.__load") or js.startswith("typeof window.__swap"):
                return "function"
            if js.startswith("window.__load(") and js.endswith(")"):
                try:
                    B.load(json.loads(js[len("window.__load("):-1]))
                    return ""
                except ValueError:
                    pass
            if js.startswith("window.__swap(") and js.endswith(")"):
                try:                                # a refresh of the same page: update it in place
                    body = json.loads(js[len("window.__swap("):-1])
                    head = B.html.split("<body", 1)[0] if "<body" in B.html else "<html><head></head>"
                    B.quiet(head + "<body>" + body + "</body></html>")
                except ValueError:
                    pass
                return B.js(js.replace("location.href=", "__cw.href="))
            return B.js(js)

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
        got = B.js("confirm(%s)?'1':''" % json.dumps(f"{title}\n\n{message}".strip()), timeout=120, wait=True)
        if got != "1":
            raise KeyboardInterrupt
        return 1
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
    A.window_open = lambda: A.APP.get("web") is not None and B.active()   # live updates pause with no browser
    A.open_outside = lambda url: B.js("window.open(%s,'_blank');''" % json.dumps(url))
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
    started = {"run": False}

    # ---- Combo Hub's own screens: plain data in, actions out (same engine, same rules as the phone)
    alock = threading.RLock()
    LIVE = {"at": 0.0, "data": None}
    BUILD = {"lg": None}

    def jsonable(x):
        return json.loads(json.dumps(x, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)))

    def live_refresh():
        try:
            api_live(fresh=True)
        finally:
            LIVE["busy"] = False

    def api_live(fresh=False):
        if not fresh and LIVE["data"] and time.time() - LIVE["at"] < 600:
            if time.time() - LIVE["at"] > 8 and not LIVE.get("busy"):      # stale: answer now, refresh behind it
                LIVE["busy"] = True
                threading.Thread(target=live_refresh, daemon=True).start()
            return live_extras(LIVE["data"])
        with alock:
            if fresh or not LIVE["data"] or time.time() - LIVE["at"] > 8:
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
                LIVE.update(at=time.time(), data=jsonable(A.MINE.get("view") or {}))
            out = LIVE["data"]
        return live_extras(out)

    def live_extras(out):
        try:
            ideas = jsonable(A.live_suggestions()) if A.STORE.get("db") else []
        except Exception:
            ideas = []
        try:
            orders = jsonable(A.maker_summary()["open"]) if A.STORE.get("db") else []
        except Exception:
            orders = []
        return dict(out, ideas=ideas, orders=orders, auto_sell=bool(A.CFG.get("auto_sell"))) if isinstance(out, dict) else out

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
        BUILD.update(lg=lg, note=s["note"], at=s["at"], days=s["days"], lines=s["lines"])
        return True

    def api_build(lg, rebuild=True, warming=False):
        import random
        BUILD.setdefault("seen", {})[lg] = time.time()
        if not warming:
            BUILD["touched"] = time.time()
        with alock:
            if not rebuild and BUILD["lg"] != lg and use_snap(lg):
                rebuild = False
            elif rebuild or BUILD["lg"] != lg:
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
                BUILD.update(lg=lg, note=note, at=time.time(), days=days)
                try:                                    # spreads and totals, priced with the score model
                    codes = [c for c in A.MIX_SPORTS] if lg == "mix" else [lg]
                    BUILD["lines"] = [x for c in codes for x in A.line_candidates(c, everything=True)][:40]
                except Exception as err:
                    print("lines:", err, flush=True)
                    BUILD["lines"] = []
                SNAP[lg] = {"at": time.time(), "ctx": dict(A.CTX), "note": note, "days": days, "lines": BUILD["lines"]}
            games = A.CTX.get("all_games") or {}
            board = []
            for e, sides in games.items():
                teams = [x for x in sides if not x.get("tie")]
                board.append({"event": e, "start": A.KICKOFF.get(e), "label": A.start_label(e),
                              "started": any(A.started(x) for x in sides),
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
                                           for k in ("nfl", "nba", "nhl", "ncaaf", "ncaamb", "ncaawb", "soccer", "ufc", "tennis", "euroleague")
                                           if k in A.SPORTS]})

    def api_results():
        with alock:
            bets, balance, note = A.fetch_account(max_age=30, every_league=True)
            bets = bets or []
            done = [a for a in bets if a["status"] in ("won", "lost", "cashed")]
            back = lambda a: a["back"] if a["status"] == "cashed" else a["pays"] if a["status"] == "won" else 0.0
            weeks = {}
            for a in done:
                wk = a.get("week") or "?"
                w = weeks.setdefault(wk, {"week": wk, "pl": 0.0, "n": 0, "won": 0})
                w["pl"] += back(a) - a["cost"]
                w["n"] += 1
                w["won"] += a["status"] == "won"
            hist = []
            when = {}
            if A.STORE.get("db"):                       # the day each combo finished, from the Mac's record
                for r in A.store_rows("select combo, settled, first_seen from bets"):
                    when[r["combo"]] = (r["settled"], r["first_seen"])
            for a in sorted(done, key=lambda a: (when.get(a["ticker"], (0, 0))[0] or 0, a.get("week") or ""), reverse=True)[:400]:
                names = []
                for l in a.get("legs") or []:
                    t = l.get("ticker") or ""
                    nm = A.PICK_NAME.get(t) or A.sport_teams(A.ticker_sport(t) or "nfl").get(t.rsplit("-", 1)[-1]) or t.rsplit("-", 1)[-1]
                    names.append(("not " if l.get("side") == "no" else "") + nm)
                st, fs = when.get(a["ticker"], (None, None))
                day = time.strftime("%Y-%m-%d", time.localtime(st)) if st else (a.get("week") or "")
                sports = sorted({A.ticker_sport(l.get("ticker") or "") or "" for l in a.get("legs") or []} - {""}) or (a.get("lgs") or [])
                hist.append({"t": a["ticker"], "status": a["status"], "cost": a["cost"], "back": round(back(a), 2),
                             "pl": round(back(a) - a["cost"], 2), "pays": a["pays"], "week": a.get("week"), "day": day,
                             "bought": time.strftime("%Y-%m-%d", time.localtime(fs)) if fs else None,
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
                         "games": (real or {}).get("games") or (p or {}).get("games"),
                         "reserved": sk.get("reserved", 0), "skim_note": sk.get("skim_note"),
                         "approved_other": bool(real and real["status"] != "draft" and view not in ("all", "")),
                         "extra": A.panel_get("extra") if (real and real["status"] == "approved" and view in ("all", "")) else None})

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
        for v in d.get("combos") or []:
            for lg in v.get("legs") or []:
                if lg["ticker"] == t:
                    leg = leg or lg
                    if v["group"] == "pending":
                        combos.append({"t": v["t"], "label": v["label"], "p": v.get("p"), "pays": v["pays"],
                                       "cost": v["cost"], "legs": len(v["legs"])})
        story = A.game_story(t) if A.STORE.get("db") else {"ticks": [], "plays": []}
        wi = None
        if leg and leg.get("state") == "live":
            ch = leg.get("live") if leg.get("live") is not None else leg.get("chance")
            try:
                wi = A.what_if(t, ch, leg.get("side", "yes"))
            except Exception:
                wi = None
            if wi and ch:
                disc = A.kalshi_discount(True)
                for c in combos:
                    if c.get("p"):
                        c["if_up"] = round(c["pays"] * c["p"] * wi["up"] / ch * disc, 2)
                        c["if_down"] = round(c["pays"] * c["p"] * wi["down"] / ch * disc, 2)
                        c["now"] = round(c["pays"] * c["p"] * disc, 2)
        return jsonable({"leg": leg, "combos": combos, "story": story, "whatif": wi})

    def api_games():
        d = api_live() or {}
        games = d.get("games") or []
        out = []
        tick_of = {}
        for v in d.get("combos") or []:
            for lg in v.get("legs") or []:
                tick_of[(lg["name"], lg.get("opp"))] = lg["ticker"]
        for g in games:
            tk = g.get("ticker") or tick_of.get((g["name"], g.get("opp")))
            hist = A.store_rows("select ts, chance from ticks where ticker=? and ts > ? order by ts",
                                (tk, time.time() - 8 * 3600)) if tk and A.STORE.get("db") else []
            out.append(dict(g, ticker=tk, spark=[[round(r["ts"]), r["chance"]] for r in hist if r["chance"] is not None][-240:]))
        return jsonable({"games": out, "at": d.get("at")})

    SET_KEYS = ("stake", "budget", "accept_pct", "size_auto", "full_count", "upsets_min", "upsets_max",
                "safer_count", "safer_min", "safer_max", "middle_count", "middle_min", "middle_max",
                "moonshot_count", "moonshot_min", "moonshot_max", "thursday", "saturday", "monday", "next_day",
                "mix_window", "max_share", "hedge_close", "include_live", "live_min", "dogs_late", "skip_news",
                "bankroll", "auto_cash", "refresh_secs", "cash_every", "ride", "auto_sell", "auto_cap", "auto_hedge",
                "prefer_hedge", "hedge_cap", "notify_value", "notify_price", "notify_cash", "notify_news", "killer_mode",
                "maker_mode", "take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget")

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
                             "leagues": [[k, v.get("short") or v.get("name") or k.upper(), v.get("icon", "")]
                                         for k, v in A.LEAGUES.items()]})

    def api_act(d):
        a, t = str(d.get("a", "")), str(d.get("t", ""))
        with alock:
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
                    return {"ok": False, "msg": "That idea has expired."}
                row = rows[0]
                if row["n"] == 1:                           # a single game: today's price, straight from the book
                    tk = json.loads(row["legs"])[0]
                    if BUILD.get("lg") != row["lg"]:
                        api_build(row["lg"], rebuild=True)
                    side = next((x for sd in (A.CTX.get("all_games") or {}).values() for x in sd if x["ticker"] == tk), None)
                    dpt = A.book_depth(tk, max_age=0)
                    fair = (side or {}).get("fair") or row.get("pfair") or 0   # spreads/totals: the model's chance
                    if not fair or not dpt or dpt.get("ask") is None:
                        return {"ok": False, "msg": "Kalshi isn't listing that game right now."}
                    ask = dpt["ask"]
                    fee = A.single_fee(ask)
                    edge = fair - ask - fee
                    pct = fair / (ask + fee) if ask else 0
                    stake = A.edge_stake(pct, A.CFG.get("size_min", 3), A.CFG.get("size_max", 10), fair)
                    n = max(1, int(stake / (ask + fee)))
                    n = min(n, int(dpt.get("ask_size") or n))
                    spent = A.week_spend() if A.can_trade() else 0
                    if spent + n * (ask + fee) > A.CFG["budget"] + 0.01:
                        return {"ok": False, "msg": f"That would go over your {A.money(A.CFG['budget'])} cap."}
                    return jsonable({"ok": True, "single": True, "price": ask, "n": n, "stake": round(n * (ask + fee), 2),
                                     "pays": float(n), "pct": pct, "edge": round(edge, 4), "fair": fair,
                                     "clears": edge >= A.SINGLE_MIN_EDGE * 0.6})
                if row["kick"] and row["kick"] < time.time() + 60:
                    return {"ok": False, "msg": "A game in it is starting, so this one's off the table."}
                if row.get("live") and row["ts"] < time.time() - 600:
                    return {"ok": False, "msg": "That idea had a game in progress and is more than 10 minutes old."}
                if BUILD.get("lg") != row["lg"]:
                    api_build(row["lg"], rebuild=True)
                k, why = A.add_own_combo(json.loads(row["legs"]))
                if not k:
                    return {"ok": False, "msg": why or "Kalshi isn't listing those games any more."}
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
                filled, err = A.buy_single(json.loads(rows[0]["legs"])[0], n, price)
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
                    r = {"error": f"{type(err).__name__}: {err}"}
                print(f"buy combo {i}:", r, flush=True)
                LIVE["at"] = 0
                if not r.get("error") and 1 <= i <= len(A.CTX.get("combos") or []):
                    BUILD.setdefault("bought", set()).add(legset(A.CTX["combos"][i - 1]))
                return jsonable({"ok": not r.get("error"), "msg": r.get("error") or "Bought.", "pays": r.get("pays")})
            if a == "panel_approve":
                ok, msg = A.panel_approve(d.get("ids"), d.get("view") or "all", d.get("at"))
                return {"ok": ok, "msg": msg}
            if a == "skim_moved":
                amt = A.skim_moved()
                return {"ok": True, "msg": f"Got it. The app counts your whole Kalshi balance again ({A.money(amt)} was set aside)."}
            if a == "panel_add":
                ok, msg = A.panel_add(d.get("ids") or [], d.get("view") or "")
                return {"ok": ok, "msg": msg}
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


    def page(frag=False, local=False):
        h = B.html or ("<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                       "<body style='background:#000;color:#8e8e93;font:600 17px -apple-system;display:flex;"
                       "align-items:center;justify-content:center;height:90vh'>Starting the planner…</body></html>")
        h = h.replace("location.href=", "__cw.href=")
        if frag:
            return h
        where = A.APP.get("where") or "mine"
        tabs = "".join(f"<button data-t='{k}' class='{'on' if k == where else ''}' onclick=\"__cwtab('{k}')\">"
                       f"{ICONS.get(k, '')}<span>{label}</span></button>" for k, icon, label in A.TABS)
        side = "".join(f"<button data-t='{k}' class='{'on' if k == where else ''}' onclick=\"__cwtab('{k}')\">"
                       f"{ICONS.get(k, '')}<span>{label}</span></button>" for k, icon, label in A.TABS)
        side = (f"<aside id='cwside'><div class='brand'><div class='mark'>{MARK}</div>Combo Hub</div><nav>{side}</nav>"
                f"<div class='foot'>Running on your Mac · v{A.VERSION}<br>Live data refreshes by itself"
                "<button onclick=\"__cwtab('refresh')\">↻ Refresh now</button>"
                + ("<button onclick=\"__cwadmin(this)\">⚙︎ Mac settings</button>" if local else "")
                + "</div></aside>")
        wrap = (f"<div id='cwwrap'>{SHELL_CSS}{side}<div id='cwbar'>{tabs}</div>"
                "<button id='cwref' aria-label='Refresh' onclick=\"__cwtab('refresh')\"><svg viewBox='0 0 24 24' width='18' height='18'>"
                "<path d='M19 12a7 7 0 1 1-2.05-4.95M19 4.5V8h-3.5' fill='none' stroke='currentColor' stroke-width='2.2' "
                "stroke-linecap='round' stroke-linejoin='round'/></svg></button>"
                + BRIDGE_JS.replace("__CWV__", str(B.v)) + "</div>")
        h = h.replace("</body>", wrap + "</body>") if "</body>" in h else h + wrap
        h = h.replace("<head>", "<head>" + PWA_HEAD, 1) if "<head>" in h else PWA_HEAD + h
        return h

    def start():
        if not started["run"]:
            started["run"] = True
            A.RUN_OPTS["goto"] = "mine" if A.can_trade() else "build"
            threading.Thread(target=A.run, daemon=True, name="app").start()
            if A.can_trade():                       # open on Live, like the phone
                def to_live():
                    for _ in range(120):
                        if started.get("user"):             # you've tapped something: leave you there
                            return
                        if "id='budgetline'" in B.html and A.APP.get("settings_wait"):
                            time.sleep(1)
                            return A.native_nav("mine")
                        if A.APP.get("where") == "mine":
                            return
                        time.sleep(0.5)
                threading.Thread(target=to_live, daemon=True).start()

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
            if self.path.startswith("/app/poll"):
                was_idle = not B.active()
                try:
                    v = int(self.path.split("v=", 1)[1].split("&")[0])
                except (IndexError, ValueError):
                    v = -1
                if was_idle and started["run"]:
                    if not started.get("shown") and A.can_trade() and A.APP.get("where") != "mine":
                        threading.Timer(1.0, A.native_nav, ("mine",)).start()   # very first visit: open on Live
                    elif A.APP.get("where") == "mine" and not A.APP.get("settings_wait"):
                        threading.Timer(1.0, A.native_nav, ("refresh",)).start()   # back on Live: fresh numbers
                started["shown"] = True                     # after that, never move you off the screen you're on
                return self._send(200, json.dumps(dict(B.poll(v), where=A.APP.get("where") or "")))
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
                    elif path == "/app/api/settings":
                        out = api_settings(q.get("lg") or "")
                    else:
                        return self._send(404, "{}")
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    out = {"error": f"{type(err).__name__}: {err}"}
                return self._send(200, json.dumps(out))
            if path == "/app/classic":
                B.seen = time.time()
                start()
                frag = "frag=1" in self.path
                return self._send(200, page(frag, local), "text/html; charset=utf-8",
                                  {"X-CW-Where": A.APP.get("where") or ""})
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
            if self.path == "/app/result":
                B.result(d.get("id"), str(d.get("value", "")))
                return self._send(200, "{}")
            if self.path in ("/app/nav", "/app/tab"):
                started["user"] = started["shown"] = True
            if self.path == "/app/nav":
                u = str(d.get("u", ""))
                web = A.APP.get("web")
                dg = getattr(web, "delegate", None)
                if u.startswith("combo://") and dg is not None:
                    threading.Thread(target=dg.webview_should_start_load, args=(web, u, 0), daemon=True).start()
                return self._send(200, "{}")
            if self.path == "/app/tab":
                t = str(d.get("t", ""))
                if t in ("mine", "build", "results", "settings", "refresh"):
                    threading.Thread(target=A.native_nav, args=(t,), daemon=True).start()
                return self._send(200, "{}")
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
        """Keeps pages ready: Live refreshed every 20s, and the Build for the sports you've looked at in the last
        day rebuilt every 5 minutes, only while nobody is tapping, so a page opens from what's already there."""
        time.sleep(20)
        while True:
            try:
                if not LIVE.get("busy") and time.time() - LIVE["at"] > 20:
                    LIVE["busy"] = True
                    live_refresh()
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
            time.sleep(15)
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
    import base64, subprocess
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
             click="/app")
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
                self.send_header("Set-Cookie", f"cw={cookie}; Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict")
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
                        "waiting": conf.get("waiting") or "", "latest": LATEST_SEEN.get("v", "")}
                return self._send(200, json.dumps(info).encode())
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
            if web and u.path == "/app/classic" and "frag=1" not in u.query:
                tok = web.session(self)
                if not tok:
                    return self._html(200, web.login_page("", web.rp_of(self)))
                return webapp_proxy(self, tok, "GET", self.path)
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
        threading.Thread(target=tailscale_https, args=(conf, port), daemon=True, name="https").start()
    ip = hub_address()
    log(f"hub serving the phone on port {port}" + (f" at http://{ip}:{port}" if ip else " (no Tailscale address found)")
        + (" · web view on the same address" if web else ""))
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
        threading.Thread(target=accuracy_loop, args=(odds,), daemon=True, name="accuracy").start()
        if conf.get("webapp", True):
            start_webapp()
    threading.Thread(target=update_loop, args=(E, conf), daemon=True, name="updates").start()
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
