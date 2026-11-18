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
WATCHER_VERSION = "2026.11.17.70"

# Settings the phone may change on the watcher. Keys and anything else are never accepted.
SYNCED = ("bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap",
          "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news")


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

    def add(self, msg, kind=None):
        low = msg.lower()
        kind = kind or ("cash" if ("cash" in low or "hedge" in low) else "info")
        auto_done = "auto" in low and ("cashed" in low or "hedged" in low or "sold" in low)
        if kind in self.SWITCH and not self.E.CFG.get(self.SWITCH[kind], True) and not auto_done:
            return False                              # switched off (actions it took are always reported)
        if kind in ("cash", "info") and any(w in low for w in self.URGENT):
            push(self.conf, msg.replace("Open the planner to confirm.", "Open the planner to cash out."),
                 pause_button=bool(self.E.CFG.get("auto_sell")))
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
        return len(msgs)


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


def shadow_loop(odds, notifier=None, every=1800):
    """Paper full-auto trading on the Mac (see the planner's shadow section). Real quotes, no money."""
    time.sleep(120)
    while True:
        for code in SHADOW_LEAGUES:
            try:
                with odds.lock:
                    snap = odds.get(code, "")            # free lines + any sharp lines already cached
                    did = odds.engine().shadow_pass(snap, log=log, alert=notifier.add if notifier else None)
                    for m in odds.moves(code, held_teams(odds)) if notifier else []:
                        notifier.add(m, "news")
                if did:
                    log(f"shadow {code}:", "; ".join(did))
            except Exception as err:
                log(f"shadow {code} skipped:", type(err).__name__, err)
        time.sleep(every)



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


class Web:
    """A small page for any browser on your Tailscale network: your live combos with a real cash-out
    button, the shadow record, and what the Mac has been doing. Passcode required; sessions last 30 days."""
    def __init__(self, conf, E):
        import secrets
        self.conf, self.E, self.sessions, self.fails = conf, E, {}, []
        if not conf.get("web_pass"):
            conf["web_pass"] = "".join(secrets.choice("23456789abcdefghjkmnpqrstuvwxyz") for _ in range(8))
            E.save_json(CONF, conf)
        self.lock = threading.Lock()

    def session(self, handler):
        import http.cookies
        c = http.cookies.SimpleCookie(handler.headers.get("Cookie") or "")
        tok = c["cw"].value if "cw" in c else ""
        exp = self.sessions.get(tok)
        return tok if exp and exp > time.time() else None

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
        self.sessions[tok] = time.time() + 30 * 86400
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

    def login_page(self, msg=""):
        import html as h
        return ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>Combo Hub</title><style>{WEB_CSS}</style></head><body><main><h1>Combo Hub</h1>"
                f"<div class='card'><form method='post' action='/login'><div class='mute'>Passcode (shown by the Mac setup)</div>"
                f"<div class='row' style='margin-top:8px'><input name='pass' type='password' autocomplete='current-password' autofocus>"
                f"<button>Open</button></div></form>{('<p>' + h.escape(msg) + '</p>') if msg else ''}</div></main></body></html>")


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
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="Combos">
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
.top{position:sticky;top:0;z-index:20;height:62px;display:flex;align-items:center;gap:22px;padding:0 24px;padding-top:env(safe-area-inset-top);
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
main{max-width:1520px;margin:0 auto;padding:22px 24px 60px}
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
.leg.won{background:var(--yesbg);color:var(--yes)}.leg.live{background:var(--livebg);color:var(--live)}.leg.lost{background:var(--nobg);color:var(--no);text-decoration:line-through}
.bar{height:5px;border-radius:9px;background:var(--panel2);overflow:hidden;width:84px;margin:6px 0 0 auto}.bar i{display:block;height:100%;background:var(--acc)}
.verdict{font-size:11px;font-weight:800;padding:4px 8px;border-radius:6px;letter-spacing:.03em;justify-self:end}
.verdict.hold{background:var(--accbg);color:var(--acc)}.verdict.sell,.verdict.won{background:var(--yesbg);color:var(--yes)}.verdict.out,.verdict.lost{background:var(--nobg);color:var(--no)}.verdict.cashed{background:var(--panel2);color:var(--sub)}
.offer b{display:block}.offer small{color:var(--mute);font-size:11.5px;font-weight:500}
.exp{background:var(--panel2);border-bottom:1px solid var(--line);padding:6px 16px 14px}
.lrow{display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line)}
.lrow:last-of-type{border-bottom:0}.lrow .who b{font-weight:600}.lrow .who span{color:var(--sub);font-size:12.5px}
.mark{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:800;background:var(--panel);color:var(--mute);border:1px solid var(--line)}
.mark.won{background:var(--yes);color:#fff;border:0}.mark.lost{background:var(--no);color:#fff;border:0}.mark.live{border:2px solid var(--live);background:var(--livebg)}
.acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding-top:12px}.acts .s{font-size:12.5px;margin-right:auto}
.side .card,.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:15px 17px;margin-bottom:14px}
.card h3{margin:0 0 10px;font-size:14px;display:flex;justify-content:space-between;align-items:center}.card h3 span{color:var(--mute);font-size:12px;font-weight:600}
.g{display:grid;grid-template-columns:1fr auto;gap:1px 10px;padding:10px 0;border-top:1px solid var(--line)}.g:first-of-type{border-top:0;padding-top:2px}
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
 padding:11px 16px;border-radius:12px;font-weight:600;transition:.25s;z-index:50;max-width:min(560px,92vw);text-align:center;pointer-events:none}
.toast.on{opacity:1;transform:translateX(-50%)}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:60;padding:20px}
.modal.on{display:flex}.sheet{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:22px;max-width:420px;width:100%;box-shadow:0 30px 80px rgba(0,0,0,.45)}
.sheet h3{margin:0 0 6px;font-size:19px;letter-spacing:-.02em}.sheet p{color:var(--sub);margin:0 0 18px}.sheet .row{display:flex;gap:10px;justify-content:flex-end}
.spin{width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;display:inline-block;animation:sp .7s linear infinite;vertical-align:-2px}
@keyframes sp{to{transform:rotate(360deg)}}
.tabbar{display:none}
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
 .grid{grid-template-columns:1fr}.side{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}.side .card{margin:0}
 .kpis{grid-template-columns:repeat(5,minmax(0,1fr))}.kpi:nth-child(n+4){display:block}
 .thead{display:none}
 .trow{grid-template-columns:1fr auto;grid-template-areas:"name ver" "legs legs" "nums nums";gap:8px;padding:14px;min-height:0}
 .trow .name{grid-area:name}.trow .legs{grid-area:legs}.trow .verdict{grid-area:ver}.trow .numwrap{grid-area:nums;display:grid!important;grid-template-columns:repeat(4,1fr);gap:6px}
 .trow .numwrap>div{text-align:left!important}.trow .numwrap>div::before{content:attr(data-l);display:block;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
 .bar{margin-left:0}.status span:last-child{display:none}
 h2{flex-wrap:wrap}h2 .r{margin-left:0;width:100%;order:3}
 .chips{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}.chips::-webkit-scrollbar{display:none}}
/* phone */
@media (max-width:900px){
 .top{height:auto;padding:calc(10px + env(safe-area-inset-top)) 16px 10px;gap:10px}
 .nav,.status,.cta,.ts.wk{display:none}.tr{gap:12px}
 main{padding:14px 14px calc(96px + env(safe-area-inset-bottom))}
 .grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr);gap:10px}.kpi:first-child{grid-column:span 2}
 .kpi b{font-size:22px}.thead{display:none}
 .trow{grid-template-columns:1fr auto;grid-template-areas:"name ver" "legs legs" "nums nums";gap:8px;padding:14px;min-height:0}
 .trow .name{grid-area:name}.trow .legs{grid-area:legs}.trow .verdict{grid-area:ver}.trow .numwrap{grid-area:nums;display:grid!important;grid-template-columns:repeat(4,1fr);gap:6px}
 .trow .numwrap>div{text-align:left!important}.trow .numwrap>div::before{content:attr(data-l);display:block;color:var(--mute);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
 .bar{margin-left:0}
 .alert{flex-wrap:wrap}.alert .acts2{width:100%;display:flex;gap:8px}.alert .acts2 .btn{flex:1}
 .mrow{grid-template-columns:1fr 1fr;grid-template-areas:"when when" "a b"}.mrow .when{grid-area:when}
 .slip{position:static}
 .chips{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin-left:-14px;margin-right:-14px;padding:0 14px}.chips::-webkit-scrollbar{display:none}
 h2{flex-wrap:wrap}h2 .r{margin-left:0;width:100%;order:3}
 .pickbtn .full{display:none}.pickbtn .short{display:inline}
 .hrow{grid-template-columns:1fr auto auto;grid-template-areas:"p p p" "w n v"}.hrow .hp{grid-area:p}
 .tabbar{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:30;justify-content:space-around;padding:7px 6px calc(6px + env(safe-area-inset-bottom));
  background:color-mix(in srgb,var(--bg) 80%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);border-top:1px solid var(--line)}
 .tabbar button{flex:1;border:0;background:none;color:var(--mute);display:flex;flex-direction:column;align-items:center;gap:3px;font-size:10.5px;font-weight:700}
 .tabbar button svg{width:25px;height:25px}.tabbar button.on{color:var(--acc)}
}
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
const SPN={nfl:'NFL',nba:'NBA',nhl:'NHL',ncaaf:'CFB',ncaamb:'CBB',ncaawb:'WCBB',soccer:'Soccer',ufc:'UFC',tennis:'Tennis',euroleague:'Euro'};
const ICON={nfl:'🏈',nba:'🏀',nhl:'🏒',ncaaf:'🎓',ncaamb:'🏀',ncaawb:'🏀',soccer:'⚽',ufc:'🥊',tennis:'🎾',euroleague:'🏀',other:'🎯'};
const SVG={live:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7" opacity=".45"/></svg>',
 build:'<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
 results:'<svg viewBox="0 0 24 24"><path d="M5 19v-7M12 19V6M19 19v-10" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
 settings:'<svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="7" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="17" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
 more:'<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg>'};
const S={view:(localStorage.getItem('cw_view')||'live'),live:null,build:null,res:null,open:{},filter:'all',lg:localStorage.getItem('cw_lg')||'nba',slip:[],busy:{}};
function toast(m,ms){const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('on'),ms||3200);}
function menu(){$('#dd').classList.toggle('open');}
document.addEventListener('click',e=>{if(!e.target.closest('.menu'))$('#dd').classList.remove('open');});
function admin(){api('/app/admin',{}).then(()=>toast('Opening Mac settings…'));}
function modal(h){$('#sheet').innerHTML=h;$('#modal').classList.add('on');}
function closeModal(){$('#modal').classList.remove('on');}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal();});
function chrome(){const tabs=[['live','Live'],['build','Build'],['results','Results'],['settings','Settings']];
 $('#nav').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${l}</button>`).join('');
 $('#tabbar').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${SVG[k]}${l}</button>`).join('');
}
function menuSheet(){modal(`<h3>More</h3><p>Planner settings and the classic screens open in the same window.</p>
 <div style="display:grid;gap:8px"><a class="btn" href="/app/classic">Planner settings</a>${LOCAL?'<button class="btn" onclick="admin();closeModal()">Mac settings</button>':''}<button class="btn" onclick="closeModal()">Close</button></div>`);}
function go(v){S.view=v;try{localStorage.setItem('cw_view',v)}catch(e){};chrome();render();load(v);window.scrollTo(0,0);}
function render(){({live:renderLive,build:renderBuild,results:renderResults,settings:renderSettings}[S.view]||renderLive)();}
async function load(v,fresh){try{
 if(v==='live'){S.live=await api('/app/api/live'+(fresh?'?fresh=1':''));head(S.live);}
 if(v==='build'){S.build=await api('/app/api/build?lg='+S.lg+(fresh?'&fresh=1':''));}
 if(v==='results'){S.res=await api('/app/api/results');head(S.res);}
 if(v==='settings'){const [st,mac]=await Promise.all([api('/app/api/settings?lg='+(S.slg||S.lg)),LOCAL?api('/app/mac',{a:'status'}).catch(()=>null):null]);S.set=st;S.mac=mac;}
 if(S.view===v)render();}catch(e){if(e)console.log(e);}}
function head(d){if(!d)return;if(d.balance!=null)$('#bal').textContent=money(d.balance);
 if(d.week_pl!=null){const w=$('#wk');w.textContent=smoney(d.week_pl);w.className=d.week_pl>=0?'up':'down';}}
function skel(n){return Array.from({length:n},()=>'<div class="skel" style="height:66px;margin-bottom:10px"></div>').join('');}
// ---------------- LIVE
function legCls(l){return l.res==='yes'?'won':l.res==='no'?'lost':l.state==='live'?'live':'';}
function legTag(l){const c=legCls(l);const sc=l.state==='live'&&l.sc?` ${l.sc.me}–${l.sc.opp}`:'';return `<span class="leg ${c}">${c==='won'?'✓ ':c==='live'?'● ':''}${esc(short(l.name))}${sc}</span>`;}
function legTags(ls){const o=[...ls].sort((a,b)=>(b.state==='live')-(a.state==='live')||(b.res==='yes')-(a.res==='yes'));
 const max=7;return o.slice(0,max).map(legTag).join('')+(o.length>max?`<span class="leg">+${o.length-max}</span>`:'');}
function short(n){n=String(n||'');const p=n.split(' ');return p.length>1&&n.length>9?p.slice(-1)[0]:n;}
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
 ${todo.length?`<h2>Needs a look <span class="n">${todo.length}</span></h2>`+todo.map(c=>`<div class="alert"><div class="ic">⚡</div><div style="flex:1;min-width:0"><b>${esc(c.label)} · worth cashing out</b>
   <p>Kalshi offers ${money(c.offer)} (you paid ${money(c.cost)}). Holding is worth about ${money(c.hold_value)} to you.</p></div>
   <div class="acts2" style="display:flex;gap:8px"><button class="btn ghost" onclick="act('keep','${c.t}')">Keep</button><button class="btn yes" onclick="sell('${c.t}')">Cash out ${money(c.offer)}</button></div></div>`).join(''):''}
 <h2>Your combos <span class="n">${pend.length}</span><span class="r chips">${[['all','Riding'],['live','Live now'],...sports.filter(s=>SPN[s]).map(s=>[s,(ICON[s]||'')+' '+SPN[s]]),['done','Settled']].map(([k,l])=>`<button class="chip ${S.filter===k?'on':''}" onclick="S.filter='${k}';renderLive()">${l}</button>`).join('')}</span></h2>
 <div class="tbl"><div class="thead"><div>Combo</div><div>Picks</div><div class="num">Paid</div><div class="num">Pays</div><div class="num">To hit</div><div class="num">Kalshi offer</div><div></div></div>
 ${shown.map(rowLive).join('')||'<div class="empty"><b>Nothing here</b>Combos you place on Kalshi show up here with live scores and cash-out offers.</div>'}</div>
 </div><aside class="side">${sideLive(d)}</aside></div>`;}
function rowLive(c){const [vc,vt]=verdictOf(c);const open=S.open[c.t];
 const offer=c.group!=='pending'?(c.group==='cashed'?`<b>${money(c.back)}</b><small>cashed out</small>`:'—'):c.offer!=null?`<b>${c.offer_real?'':'≈ '}${money(c.offer)}</b><small>${c.offer_real?'vs '+money(c.hold_value)+' holding':'estimate'}</small>`:'<small>—</small>';
 return `<div class="trow" onclick="tog('${c.t}')"><div class="name"><b>${ICON[c.sports[0]]||''} ${esc(c.label)}</b><span>${esc(nextLine(c))}</span></div>
  <div class="legs">${legTags(c.legs)}</div>
  <div class="numwrap"><div class="num" data-l="Paid">${money(c.cost)}</div><div class="num" data-l="Pays">${money(c.pays)}</div>
  <div class="num" data-l="To hit">${c.group==='pending'?pct(c.p):'—'}${c.group==='pending'?`<div class="bar"><i style="width:${Math.max(1,Math.min(100,c.p*100))}%"></i></div>`:''}</div>
  <div class="num offer" data-l="Offer">${offer}</div></div><div class="verdict ${vc}">${vt}</div></div>
  ${open?`<div class="exp">${c.legs.map(l=>`<div class="lrow"><span class="mark ${legCls(l)}">${l.res==='yes'?'✓':l.res==='no'?'✕':''}</span>
   <div class="who"><b>${ICON[l.sport]||''} ${esc(l.name)}</b> <span>${l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</span>${l.url?` <a href="${esc(l.url)}" target="_blank" onclick="event.stopPropagation()">game ↗</a>`:''}</div>
   <b>${l.res?'':pct(l.live!=null?l.live:l.chance)}${l.live!=null&&!l.res?' <span class="m" style="font-weight:500;font-size:11px">live</span>':''}</b></div>`).join('')}
   ${c.group==='pending'?`<div class="acts"><span class="s">${c.offer_real?`Kalshi offers <b>${money(c.offer)}</b> · holding is worth about ${money(c.hold_value)}${c.threshold?` · sell at ${money(c.threshold)}+`:''}`:'Ask Kalshi what it will pay for this combo right now.'}</span>
    ${c.hedge&&!c.hedge.done?`<button class="btn" onclick="event.stopPropagation();hedge('${c.t}')">Hedge ${esc(short(c.hedge.name))} · ${money(c.hedge.cost)}</button>`:''}
    <button class="btn" ${S.busy[c.t]?'disabled':''} onclick="event.stopPropagation();ask('${c.t}')">${S.busy[c.t]?'<span class="spin"></span> Asking…':c.offer_real?'New offer':'Get cash-out offer'}</button>
    ${c.offer_real?`<button class="btn yes" onclick="event.stopPropagation();sell('${c.t}')">Cash out ${money(c.offer)}</button>`:''}</div>`:''}</div>`:''}`;}
function tog(t){S.open[t]=!S.open[t];renderLive();}
function sideLive(d){const gs=d.games||[];const r=d.risk;
 return `<div class="card"><h3>Games you need <span>${gs.length}</span></h3>${gs.slice(0,8).map(g=>`<div class="g"><div class="t">${ICON[g.sport]||''} ${esc(g.name)}${g.state==='live'?'<span class="tag">LIVE</span>':''}</div>
  <div class="e">${g.state==='live'&&g.sc?`<b>${g.sc.me}–${g.sc.opp}</b>${esc(g.sc.detail||'')}`:`<b>${pct(g.chance)}</b>${esc(g.starts||'')}`}</div>
  <div class="x">In ${g.combos} combo${g.combos>1?'s':''} · ${money(g.pays)} riding</div></div>`).join('')||'<div class="m">Nothing pending.</div>'}</div>
 ${r?`<div class="card"><h3>If ${esc(short(r.name))} lose <span>biggest risk</span></h3><div class="mini">Combos out<b>${r.combos} of ${d.riding}</b></div><div class="mini">Payout riding<b>${money(r.pays)}</b></div><div class="mini">${esc(short(r.name))} to win<b>${pct(r.chance)}</b></div></div>`:''}
 <div class="card"><h3>Locked in <span>today</span></h3><div class="mini">Won or cashed<b class="up">${money(d.locked)}</b></div><div class="mini">Holding is worth<b>${money(d.hold_value)}</b></div></div>`;}
async function ask(t){S.busy[t]=true;S.open[t]=true;renderLive();const r=await api('/app/api/act',{a:'ask',t});S.busy[t]=false;
 if(!r.ok)toast(r.msg||'No offer came in.');await load('live',true);}
function sell(t){const c=(S.live.combos||[]).find(x=>x.t===t);if(!c)return;
 modal(`<h3>Cash out ${esc(c.label)} for ${money(c.offer)}?</h3><p>You paid ${money(c.cost)} (${smoney(c.offer-c.cost)}). If you hold instead: ${pct(c.p)} chance of ${money(c.pays)}. Kalshi's offer only lasts a few seconds.</p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn yes" id="sellgo" onclick="doSell('${t}')">Cash out</button></div>`);}
async function doSell(t){$('#sellgo').innerHTML='<span class="spin"></span>';const r=await api('/app/api/act',{a:'go',t});closeModal();toast(r.msg||(r.ok?'Done.':'Didn\'t go through.'),5000);load('live',true);}
async function hedge(t){const c=(S.live.combos||[]).find(x=>x.t===t);modal(`<h3>Hedge ${esc(c.label)}?</h3><p>Buys the other side of its last game for about ${money(c.hedge.cost)}, so you collect about ${money(c.hedge.locked)} whichever team wins.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();api('/app/api/act',{a:'hedgego',t:'${t}'}).then(r=>{toast(r.msg||'Done.',5000);load('live',true)})">Place hedge</button></div>`);}
async function act(a,t){const r=await api('/app/api/act',{a,t});if(r.msg)toast(r.msg);load('live',true);}
// ---------------- BUILD
function renderBuild(){const d=S.build;const m=$('#main');
 const lgs=(d&&d.leagues)||[['nfl','NFL','🏈'],['nba','NBA','🏀'],['nhl','NHL','🏒'],['ncaaf','CFB','🎓']];
 const chipRow=`<div class="chips" style="margin-bottom:14px">${lgs.map(([k,n,i])=>`<button class="chip ${S.lg===k?'on':''}" onclick="setLg('${k}')">${i} ${n}</button>`).join('')}</div>`;
 if(!d||d.lg!==S.lg){m.innerHTML=chipRow+'<div class="grid"><div>'+skel(7)+'</div><div class="skel" style="height:300px"></div></div>';return;}
 m.innerHTML=chipRow+`<div class="grid"><div>
  <h2>${esc(d.icon)} ${esc(d.name)} games <span class="n">${d.board.length}</span><span class="r m" style="font-size:12px">Kalshi price · fair chance from the sportsbooks</span></h2>
  <div class="board">${d.board.map(g=>`<div class="mrow"><div class="when">${g.started?'<span class="tag">LIVE</span>':esc(g.label||'')}</div>
   ${g.sides.filter(s=>!s.tie).map(s=>{const on=S.slip.includes(s.ticker);return `<button class="pickbtn ${on?'on':''}" ${g.started?'disabled':''} onclick="pick('${s.ticker}','${g.event}')"><span class="nm"><span class="full">${esc(s.pick)}</span><span class="short">${esc(short(s.pick))}</span>${s.edge!=null&&s.edge>=.01?'<span class="val">VALUE</span>':''}</span>
    <span class="pr"><b>${s.p!=null?Math.round(s.p*100)+'¢':'—'}</b><span>${s.fair!=null?'fair '+pct(s.fair):''}</span></span></button>`}).join('')}</div>`).join('')||'<div class="empty"><b>No games right now</b>Try another sport.</div>'}</div>
  <h2>Suggested combos <span class="n">${d.combos.length}</span><span class="r"><button class="btn" onclick="load('build',true)">Rebuild</button></span></h2>
  <div class="cgrid">${d.combos.map(ccard).join('')}</div>
 </div><aside>${slip(d)}</aside></div>`;}
function setLg(k){S.lg=k;S.slip=[];try{localStorage.setItem('cw_lg',k)}catch(e){};S.build=null;renderBuild();load('build');}
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
function ccard(c){const o=S.quotes&&S.quotes[c.i];const fresh=o&&Date.now()/1000-o.at<20;
 return `<div class="ccard"><div class="hd"><div><div class="tier">${esc(c.tier||c.kind||'')}</div><b>${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold">${pct(c.chance)}</span></div>
  <div class="legs">${c.legs.map(l=>`<span class="leg">${esc(short(l.pick))} ${pct(l.fair)}</span>`).join('')}</div>
  <div class="s" style="font-size:12.5px">${c.est?`Kalshi will likely pay about ${money(c.est)} (${pct(c.est_pct)} of fair)`:'Get a price to see what Kalshi pays.'}</div>
  <div style="display:flex;gap:8px">${fresh?`<button class="btn yes" style="flex:1" onclick="buy(${c.i})">Buy ${money(o.stake)} → ${money(o.pays)}${o.ok?'':' (under cut-off)'}</button>`:
   `<button class="btn" style="flex:1" id="q${c.i}" onclick="quote(${c.i})">Get price</button>`}</div></div>`;}
async function quote(i){const b=$('#q'+i);if(b)b.innerHTML='<span class="spin"></span> Asking Kalshi…';const r=await api('/app/api/act',{a:'quote',i});
 if(!r.ok){toast(r.error||r.msg||'No price came in.');renderBuild();return;}S.quotes=S.quotes||{};S.quotes[i]={pays:r.pays,stake:r.stake,ok:r.ok,at:Date.now()/1000};renderBuild();
 toast(`Kalshi pays ${money(r.pays)} for ${money(r.stake)} · ${pct(r.pct)} of fair`,5000);setTimeout(renderBuild,20500);}
async function buy(i,custom){const r=await api('/app/api/act',{a:'buy',i});toast(r.ok?`Bought. It shows on Live within a minute.`:(r.msg||'Didn\'t go through.'),5000);
 if(custom)S.custom=null;else if(S.quotes)delete S.quotes[i];if(r.ok&&custom)S.slip=[];renderBuild();}
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
  <h2>History <span class="n">${d.history.length}</span></h2><div class="tbl">${d.history.map(h=>`<div class="hrow"><div class="m" style="font-size:12.5px">${esc(h.week||'')}</div>
   <div class="hp"><div class="legs">${h.picks.map(p=>`<span class="leg">${esc(short(p))}</span>`).join('')}</div></div>
   <div class="num">${money(h.cost)}</div><div class="num ${h.back-h.cost>=0?'up':'down'}">${smoney(h.back-h.cost)}</div><span class="verdict ${h.status}">${h.status.toUpperCase()}</span></div>`).join('')||'<div class="empty"><b>No settled combos yet</b></div>'}</div>
 </div><aside class="side">
  <div class="card"><h3>Shadow auto-trading <span>paper</span></h3>${sh&&sh.quotes?`<div class="mini">Settled<b>${sh.n}</b></div><div class="mini">Paper P/L<b class="${sh.back-sh.staked>=0?'up':'down'}">${smoney(sh.back-sh.staked)}</b></div>
   <div class="mini">Open<b>${sh.open}</b></div><div class="mini">Kalshi quotes, median<b>${pct(sh.median)} of fair</b></div><div class="mini">Buys at<b>${sh.min_pct}%+</b></div>`:'<div class="m">No quotes yet. The Mac asks within 8 hours of game time.</div>'}</div>
  <div class="card"><h3>Most accurate odds</h3><div class="m" style="font-size:13px">${esc(d.accuracy_text||'')}</div></div>
 </aside></div>`;}
// ---------------- settings
const UNITS={stake:['$',''],budget:['$',''],accept_pct:['','%'],live_min:['','%'],max_share:['','%'],bankroll:['$',''],refresh_secs:['','s'],cash_every:['',' min'],auto_cap:['',''],hedge_cap:['$','']};
const RANGES={stake:[1,20,1],budget:[10,200,10],accept_pct:[50,100,5],live_min:[10,50,5],max_share:[20,100,10],bankroll:[100,5000,100],refresh_secs:[10,120,5],cash_every:[1,10,1],auto_cap:[1,10,1],hedge_cap:[25,500,25]};
function fmtv(k,v){const u=UNITS[k]||['',''];return u[0]+(+v).toLocaleString()+u[1];}
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
 const tiers=(d.full?[['full','Full slate','Every game','upsets',0,8,'underdogs']]:[]).concat([['safer','Safer','Short combos',null,2,8],['middle','Middle','The core of the mix',null,2,12],['moonshot','Moonshot','Long shots, big payouts',null,2,16]]);
 const mix=`<div class="mixt"><div class="h">Type</div><div class="h">Combos</div><div class="h">Fewest</div><div class="h">Most</div>${tiers.map(([t,n,s,alt,lo,hi,unit])=>{const b=alt||t;
  return `<div><b>${n}</b><small>${s}${unit?' · '+unit:' · games'}</small></div><div>${stp(t+'_count',0,10)}</div><div>${stp(b+'_min',alt?0:lo,hi)}</div><div>${stp(b+'_max',alt?0:lo,hi)}</div>`;}).join('')}</div>`;
 const secs=[['money','💵','Money'],['mix','🧩','Combo mix'],['games','🗓️','Games & picks'],['cash','💸','Cash out & hedging'],['alerts','🔔','Notifications'],['mac','💻',LOCAL?'This Mac':'The Mac'],['keys','🔑','Accounts & keys']];
 const ago=s=>s<3600?Math.round(s/60)+' min':s<86400?Math.round(s/3600)+' hr':Math.round(s/86400)+' days';
 const macCard=LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Tailscale</span><b>${mac.ts?esc(mac.ts):'<span class="down">Not signed in</span>'}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · auto cash-out paused':''}</b></div>
   <div><span>Combo Hub passcode</span><b>${esc(mac.pass)}</b></div><div><span>Phone-approved update</span><b>${esc(mac.approved||'—')}</b></div></div>
   <div class="sact"><button class="btn acc" onclick="macDo('update',this)">Update now</button><button class="btn" onclick="macCode()">Phone pairing code</button><button class="btn" onclick="macPass()">Change passcode</button><button class="btn" onclick="S.showlog=!S.showlog;renderSettings()">${S.showlog?'Hide':'Show'} activity</button><button class="btn ghost" onclick="macDo('advanced',this)">Kalshi key & removal…</button></div>
   ${S.showlog?`<div class="logbox">${esc((mac.log||[]).join('\n'))}</div>`:''}`
  :`<div class="srow"><div class="l"><b>${LOCAL?'Couldn\'t read the Mac\'s status':'Mac controls are on the Mac itself'}</b><small>${LOCAL?'Reload in a moment.':'Open Combo Hub on the Mac for updates, the pairing code and the passcode.'}</small></div></div>`;
 m.innerHTML=`<div class="set"><nav class="sidx">${secs.map(([id,ic,t])=>`<a href="#s-${id}" onclick="event.preventDefault();document.getElementById('s-${id}').scrollIntoView({behavior:'smooth'})">${ic} ${t}</a>`).join('')}<div class="sv">Planner ${esc(d.version)}</div></nav><div>
 <div class="shead"><div><h1>Settings</h1><p>Planner settings are per sport. Changes save as you go.</p></div><div class="saved" id="saved"></div></div>
 <div class="chips" style="margin-bottom:18px">${d.leagues.map(([k,n,ic])=>`<button class="chip ${k===d.lg?'on':''}" onclick="sport('${k}')">${ic} ${esc(n)}</button>`).join('')}</div>
 ${scard('money','💵','Money','What each combo costs and the price you\'ll accept from Kalshi.',
   rng('stake','Per combo')+rng('budget',cap,'The most the planner spends in one '+(mode==='day'?'day':mode==='mix'?'mix':'weekend'))+rng('accept_pct','Fair-price cut-off','Kalshi prices paying less than this share of fair get marked')+tgl('size_auto','Bet more when the price is good','$3 near the cut-off, up to $10 well above fair'))}
 ${scard('mix','🧩','Combo mix','How many of each kind to build, and how many games in each.',mix)}
 ${scard('games','🗓️','Games & picks','Which games go in, and how picks are spread.',days+tgl('include_live','Include games already in progress','With extra safety checks')+rng('live_min','Live picks need at least','Chance to win right now',!v.include_live)
   +rng('max_share','One pick in at most','Share of combos for any single team')+tgl('hedge_close','Split coin-flip games','Put both sides of close games across combos')+tgl('dogs_late','Underdogs late','Favourites in the early games')+tgl('skip_news','Skip games with breaking news','When Kalshi and the sportsbooks disagree a lot'))}
 ${scard('cash','💸','Cash out & hedging','When to take money off the table. The Mac watches these all day.',
   rng('bankroll','Betting bankroll','Bigger sure amounts against this get favoured')+seg('ride','Let it ride','How long to hold before cashing out',d.ride)
   +tgl('auto_cash','Keep a cash-out offer ready','On every live combo')+rng('cash_every','Fresh offers every','',!v.auto_cash)+rng('refresh_secs','Live updates every')
   +tgl('auto_sell','Auto cash-out at my Let it ride level','The Mac sells by itself, logged and capped')+rng('auto_cap','Auto cash-outs a day, at most','',!v.auto_sell)
   +tgl('auto_hedge','Hedge instead when it locks in more','A small purchase of the other side',!v.auto_sell)+tgl('prefer_hedge','Prefer hedging','Even at up to 5% less than the cash-out',!v.auto_sell)+rng('hedge_cap','Most to spend on one hedge','',!v.auto_sell))}
 ${scard('alerts','🔔','Notifications','From the Mac. Bundled to one every 30 minutes, quiet 10 PM–7 AM. Urgent ones come right away.',
   tgl('notify_value','Combos quoting at a fair price')+tgl('notify_price','A better price on a combo')+tgl('notify_cash','Cash-outs and hedges')+tgl('notify_news','Big line moves and news'))}
 ${scard('mac','💻',LOCAL?'This Mac':'The Mac',LOCAL?'The watcher and Combo Hub run here. Updates install by themselves once your phone approves them.':'',macCard)}
 ${scard('keys','🔑','Accounts & keys','Keys never leave the device they\'re on.',`<div class="kv"><div><span>Kalshi</span><b>${d.keys.kalshi?'<span class="dot"></span>Connected through the Mac':'<span class="down">Not connected</span>'}</b></div><div><span>Sportsbook odds</span><b>${d.keys.odds?'Key saved':'Free sources only'}</b></div></div>
   <div class="srow"><div class="l"><small>Change the Mac's Kalshi key under This Mac › Kalshi key. The phone's keys are in the planner on the iPhone.</small></div><a class="btn ghost" href="/app/classic">Classic screens</a></div>`)}
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
chrome();render();load(S.view);
setInterval(()=>{if(document.hidden)return;if(S.view==='live'&&!$('#modal').classList.contains('on'))load('live');},12000);
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

    def api_live(fresh=False):
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
            return LIVE["data"]

    def side_view(s):
        return {"ticker": s["ticker"], "pick": s["pick"], "abbr": s.get("abbr", ""), "p": s.get("p"),
                "bid": s.get("bid"), "fair": s.get("fair"), "edge": s.get("edge"), "src": s.get("src"),
                "tie": bool(s.get("tie")), "event": s["event"]}

    def combo_view(i, c):
        est = A.est_offer(c)
        return {"i": i, "kind": c.get("kind"), "tier": c.get("tier"), "fair": c.get("fair"), "min": c.get("min"),
                "kalshi": c.get("kalshi"), "est": est[0], "est_pct": est[1],
                "chance": 1.0 / (c["fair"] / A.CTX.get("stake", A.CFG["stake"])) if c.get("fair") else None,
                "legs": [side_view(l) for l in c["legs"]],
                "offer": {k: v for k, v in (A.CTX.get("offers", {}).get(i) or {}).items() if k in ("pays", "stake", "at")} or None}

    def api_build(lg, rebuild=True):
        import random
        with alock:
            if rebuild or BUILD["lg"] != lg:
                A.set_league(lg)
                games, days, slate = A.week_games(A.fetch_markets())
                try:
                    book, note = A.fetch_book_odds(A.CFG.get("odds_key", ""))
                except Exception as err:
                    book, note = {}, f"No sportsbook lines ({type(err).__name__})."
                A.attach_fair(games, book)
                combos, _ = A.build_combos(games, A.CFG.get("picks") or {}, random.Random()) if games else ([], None)
                A.CTX.clear()
                A.CTX.update(combos=combos, all_games=games, games=dict(games), stake=A.CFG["stake"], offers={},
                             build_id=None)
                BUILD.update(lg=lg, note=note, at=time.time())
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
                             "board": board, "combos": [combo_view(i, c) for i, c in enumerate(A.CTX.get("combos") or [], 1)],
                             "leagues": [[k, A.SPORTS.get(k, {}).get("name", k.upper()), A.SPORTS.get(k, {}).get("icon", "")]
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
            for a in sorted(done, key=lambda a: a.get("week") or "", reverse=True)[:60]:
                names = []
                for l in a.get("legs") or []:
                    t = l.get("ticker") or ""
                    nm = A.PICK_NAME.get(t) or A.sport_teams(A.ticker_sport(t) or "nfl").get(t.rsplit("-", 1)[-1]) or t.rsplit("-", 1)[-1]
                    names.append(("not " if l.get("side") == "no" else "") + nm)
                hist.append({"t": a["ticker"], "status": a["status"], "cost": a["cost"], "back": round(back(a), 2),
                             "pays": a["pays"], "week": a.get("week"), "picks": names, "sports": a.get("lgs") or []})
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
                             "edge": edge})

    SET_KEYS = ("stake", "budget", "accept_pct", "size_auto", "full_count", "upsets_min", "upsets_max",
                "safer_count", "safer_min", "safer_max", "middle_count", "middle_min", "middle_max",
                "moonshot_count", "moonshot_min", "moonshot_max", "thursday", "saturday", "monday", "next_day",
                "mix_window", "max_share", "hedge_close", "include_live", "live_min", "dogs_late", "skip_news",
                "bankroll", "auto_cash", "refresh_secs", "cash_every", "ride", "auto_sell", "auto_cap", "auto_hedge",
                "prefer_hedge", "hedge_cap", "notify_value", "notify_price", "notify_cash", "notify_news")

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
            synced = None
            if vals:
                before = {k: A.CFG.get(k) for k in A.WATCHER_SYNCED}
                for k, v in vals.items():
                    if k not in SET_KEYS or k not in A.CFG:
                        continue
                    cur = A.CFG[k]
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
                except (RuntimeError, PermissionError) as err:
                    return {"ok": False, "error": str(err).replace(" Try Swap.", "")}
                return jsonable({"ok": not r.get("error"), **{k: r.get(k) for k in ("pays", "stake", "pct", "ok", "error")}})
            if a == "buy":
                i = int(d.get("i", 0))
                r = A.accept_offer(i)
                LIVE["at"] = 0
                return jsonable({"ok": not r.get("error"), "msg": r.get("error") or "Bought.", "pays": r.get("pays")})
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
                        out = api_build(lg if lg in A.LEAGUES else "nba", rebuild=q.get("fresh") == "1" or BUILD["lg"] != lg)
                    elif path == "/app/api/results":
                        out = api_results()
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
        web.sessions = {k: v for k, v in web.sessions.items() if k == tok}   # everyone else signs in again
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
                                                         "X-CW-Local": "1" if handler.client_address[0] == "127.0.0.1" else "0"})
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
            return {"path": web.issue_once()} if web else {"err": "kalshi", "msg": "Web view is off."}
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
                if not tok or self.headers.get("X-CW") != tok or self.client_address[0] != "127.0.0.1":
                    return self._send(403, b"")
                ok = open_admin()
                return self._send(200, json.dumps({"ok": ok}).encode())
            if web and self.path == "/app/mac":             # This Mac (Settings): only from the Mac itself
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok or self.client_address[0] != "127.0.0.1" or not 0 <= n < 10_000:
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
                return self._html(303, "", cookie=tok, location="/") if tok else self._html(200, web.login_page(msg))
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
            if web and u.path == "/once":
                tok = web.use_once((parse_qs(u.query).get("t") or [""])[0])
                return self._html(303, "", cookie=tok, location="/") if tok else \
                    self._html(200, web.login_page("That link was already used or expired. Tap Open Combo Hub again."))
            if web and u.path == "/app/classic" and "frag=1" not in u.query:
                tok = web.session(self)
                if not tok:
                    return self._html(200, web.login_page())
                return webapp_proxy(self, tok, "GET", self.path)
            if web and (u.path.startswith("/app/") or (u.path == "/app" and "frag=1" in u.query)):
                tok = web.session(self)
                if not tok or self.headers.get("X-CW") != tok:
                    return self._send(403, b"")
                return webapp_proxy(self, tok, "GET", self.path)
            if web and u.path in ("/", "/index.html", "/simple"):
                tok = web.session(self)
                if not tok and self.client_address[0] == "127.0.0.1":   # on the Mac itself: no passcode
                    tok = web.new_session()
                    return self._html(303, "", cookie=tok, location=self.path)
                if not tok:
                    return self._html(200, web.login_page())
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
    if conf.get("hub", sys.platform == "darwin"):      # the Mac hub; a Pi only if asked
        odds = HubOdds()
        start_hub(conf, E, odds)
        if conf.get("shadow", True):
            threading.Thread(target=shadow_loop, args=(odds, notifier), daemon=True, name="shadow").start()
        threading.Thread(target=accuracy_loop, args=(odds,), daemon=True, name="accuracy").start()
        if conf.get("webapp", True):
            start_webapp()
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
            if backup:
                E.CFG["auto_sell"] = False
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
        playing = any(lv for h in (E.MINE.get("hold") or {}).values() for _, lv, _ in h.get("legs_left") or [])
        every = 5 if playing else int(E.CFG.get("refresh_secs", 15))   # quicker while your games are on
        time.sleep(max(3, every - (time.time() - t0)))


if __name__ == "__main__":
    if "--webapp" in sys.argv:
        sys.exit(webapp_main() or 0)
    sys.exit(main() or 0)
