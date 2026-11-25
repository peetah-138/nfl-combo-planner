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
from contextlib import nullcontext
import base64, hashlib, hmac, importlib.util, json, os, re, shutil, sys, threading, time, traceback

import requests

HOME = os.environ.get("COMBOWATCH_HOME") or os.path.expanduser("~/combowatch")
ENGINE = os.path.join(HOME, "engine.py")
CONF = os.path.join(HOME, "watcher.json")
REPO = "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/"
NTFY = os.environ.get("COMBOWATCH_NTFY", "https://ntfy.sh")
WATCHER_VERSION = "2026.11.25.140"

# Settings the phone may change on the watcher. Keys and anything else are never accepted.
SYNCED = ("take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap", "flex_sell", "flex_learn", "flex_backstop", "sell_more_cheap", "sell_more_loss", "sell_more_cap", "learned_guards",
          "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news",
          "killer_mode", "maker_mode", "accept_pct", "size_min", "size_max", "budget", "include_live", "live_min", "panel_live",
          "line_model", "panel_rank_dollars", "idea_bar_strict", "stop_loss_mode")


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


def web_push(title, body, url="/", tag=None, urgent=False):
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
            web_url = (base + (click or "/")) if base else (click or "/")
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


def is_backup(conf):
    return (conf or {}).get("role") == "backup"


def backup_safe(conf, E):
    """The Pi is alerts-only: every automatic trading switch forced off in its engine, and the engine told it's a
    backup (its kalshi_send / can_trade refuse anything that could trade). Runs before any trading call and after
    every settings copy from the phone, so a synced Auto cash-out = on never reaches the Pi's loop."""
    if not is_backup(conf):
        return False
    os.environ["COMBO_ROLE"] = "backup"
    E.ROLE_BACKUP = True
    E.CFG["auto_sell"] = False
    E.CFG["auto_cash"] = False
    E.CFG["auto_hedge"] = False
    E.CFG["killer_mode"] = "off"
    E.CFG["maker_mode"] = "off"
    return True


def watcher_paused():
    """Pause (from an alert) as the watcher holds it right now (not the settings file); the Pi counts as paused."""
    conf = DEP.get("conf") or {}
    return bool(conf.get("paused")) or is_backup(conf)


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
            if k in data.get("cfg", {}) and k not in ("stop_loss", "stop_loss_mode"):
                E.CFG[k] = data["cfg"][k]
        if hasattr(E, "sl_sync"):                      # 'Selling at a loss' (#228): a stale old switch never loosens it
            E.sl_sync(E.CFG, data.get("cfg", {}))
        elif "stop_loss" in data.get("cfg", {}):
            E.CFG["stop_loss"] = data["cfg"]["stop_loss"]
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
    backup_safe(conf, E)                               # the Pi: whatever the phone sent, it never trades
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
                            backup_safe(conf, E)
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


GH_API = "https://api.github.com/repos/peetah-138/nfl-combo-planner"
GH_GIT = "https://github.com/peetah-138/nfl-combo-planner.git"


def repo_sha():
    """The newest commit on main (40 hex characters), or "" when GitHub doesn't say. Asks the API first, then
    git's own ref list (not counted against the API's hourly limit), so a rate limit can't hold an update back."""
    try:
        r = requests.get(GH_API + "/commits/main", timeout=10, headers={"Accept": "application/vnd.github.sha"})
        sha = r.text.strip()
        if r.ok and re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    except requests.RequestException:
        pass
    try:
        r = requests.get(GH_GIT + "/info/refs", params={"service": "git-upload-pack"}, timeout=10)
        m = re.search(rb"(?:^|\n)[0-9a-f]{4}([0-9a-f]{40}) refs/heads/main\n", r.content) if r.ok else None
        if m:
            return m.group(1).decode()
    except requests.RequestException:
        pass
    return ""


def repo_now():
    """The repo at its newest commit. Plain raw links to main can be up to 5 minutes stale right after a
    publish, so this asks GitHub for the latest commit and reads the files at exactly that commit."""
    sha = repo_sha()
    return REPO.replace("/main/", f"/{sha}/") if sha else REPO


def update_if_newer(E, conf):
    """Install a newer engine and watcher from GitHub. With automatic updates on, any new version
    whose two files agree on it; otherwise only the exact files your phone installed (it sends
    their SHA-256, signed). The web app's files (watcher/spa/) come from the same commit and must all arrive
    intact before anything is replaced; if any is missing or changed, this version keeps running.
    Returns True if the watcher should restart."""
    sha = repo_sha()
    base = REPO.replace("/main/", f"/{sha}/") if sha else REPO
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
    if not sha:
        log(f"update {latest} waiting: GitHub didn't say which commit is newest, so the web app's files can't be checked")
        return False
    # the web app's files must be the ones the phone approved, unless this Mac takes automatic updates anyway (on
    # purpose, #160: a phone's digest that can't be read or lags must never hold a fix back from an automatic Mac)
    approved = None if auto_updates(conf) else ok.get("spa")
    if not auto_updates(conf) and not approved:
        log(f"update {latest} waiting: your phone hasn't approved this version's web app files yet")
        return False
    me = os.path.abspath(__file__)
    with spa_locked():
        try:
            new_spa = spa_fetch(sha, approved, stamp=latest)
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as err:
            log(f"update {latest} skipped: the web app's files didn't all arrive intact ({err}); keeping this version")
            return False
        try:                                         # everything written first, then swapped in back to back
            for path, text in ((ENGINE + ".new", src), (me + ".new", wsrc)):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            old_spa = spa_swap(new_spa)
        except OSError as err:
            spa_drop(new_spa)
            for path in (ENGINE + ".new", me + ".new"):
                if os.path.isfile(path):
                    os.remove(path)
            log(f"update {latest} skipped: couldn't write the new files ({err}); keeping this version")
            return False
        prev = ENGINE + ".prev"                      # the running engine, kept until both files are in place
        copied = False
        try:
            if os.path.isfile(prev):
                os.remove(prev)                       # never a leftover from an earlier, interrupted update
            if os.path.isfile(ENGINE):
                shutil.copy2(ENGINE, prev)
                copied = True
            os.replace(ENGINE + ".new", ENGINE)
            os.replace(me + ".new", me)
        except OSError as err:
            try:
                if copied:
                    os.replace(prev, ENGINE)          # never a new engine next to the old watcher
            except OSError:
                pass
            for path in (ENGINE + ".new", me + ".new"):
                try:
                    os.remove(path)
                except OSError:
                    pass
            spa_restore(old_spa)
            log(f"update {latest} failed while installing ({err}); the old files were put back")
            return False
        try:
            os.remove(prev)
        except OSError:
            pass
        spa_drop(old_spa)
    conf.pop("waiting", None)
    log("updated to", latest, "(automatic)" if auto else "(approved by your phone)", "- restarting")
    return True


UPDATED = {}
TAP_BUSY = os.path.join(HOME, "combo_tap_busy.json")   # the web app is mid-order on a tap (updates wait)
TAP_BUSY_MAX = 240                                     # a mark older than this is stale (a crashed tap)


def tap_busy():
    try:
        with open(TAP_BUSY, encoding="utf-8") as f:
            at = float(json.load(f).get("at", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return 0 <= time.time() - at < TAP_BUSY_MAX


RESTARTING = os.path.join(HOME, "combo_restarting.json")   # an update is installed: the web app takes no new taps
RESTART_MAX = 300                                          # a mark older than this is stale (the restart happened)


def restarting():
    try:
        with open(RESTARTING, encoding="utf-8") as f:
            at = float(json.load(f).get("at", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return 0 <= time.time() - at < RESTART_MAX


RUNNING = {}    # update_loop leaves the engine here, so the restart can see an auto cash-out round in progress


def sell_busy():
    """An auto cash-out round is running in this process (MINE busy or selling): exiting now could kill it between
    sending an accept and recording the outcome."""
    try:
        m = RUNNING["E"].MINE
        return bool(m.get("busy") or m.get("selling"))
    except (KeyError, AttributeError):
        return False


def restart_when_quiet(wait=TAP_BUSY_MAX):
    """Before the watcher exits for an update: tell the web app to take no new taps, then wait (bounded) until no
    tap is mid-order and no auto cash-out round is running (two quiet checks in a row), so neither the hub that
    relays an order nor a sale between its accept and its recorded outcome is killed."""
    try:
        with open(RESTARTING, "w", encoding="utf-8") as f:
            json.dump({"at": time.time()}, f)
    except OSError:
        pass
    end, quiet = time.time() + wait, 0
    while time.time() < end and quiet < 2:
        time.sleep(1)
        quiet = 0 if tap_busy() or sell_busy() else quiet + 1
    if quiet < 2:
        log("restarting although a tap still looks busy (it waited the most it may)")


def update_loop(E, conf):
    """Checks for new versions on its own thread, so nothing else going wrong in the watcher can ever
    stop an update (a fix) from arriving. After installing, the watcher exits and launchd starts the new one."""
    RUNNING["E"] = E
    time.sleep(30)
    last = 0.0
    while True:
        try:
            if conf.pop("update_now", False) or time.time() - last > (600 if auto_updates(conf) else 1800):
                last = time.time()
                if tap_busy():                      # a buy or sale tap is mid-order in the web app: install after it
                    log("update waits: a tap is placing an order")
                    conf["update_now"] = True
                    time.sleep(15)
                    continue
                if update_if_newer(E, conf):
                    restart_when_quiet()            # no tap is cut off mid-order by the restart
                    UPDATED["now"] = True
                    time.sleep(20)                  # let the main loop exit cleanly; if it's stuck, exit anyway
                    log("restarting for the update")
                    os._exit(0)
        except Exception as err:
            log("update check failed:", type(err).__name__, err)
        time.sleep(15)


# ---- the web app's files (watcher/spa/) ------------------------------------------------------------------------
# The single-page app and the login page are plain files in a folder named spa next to this file, one per screen,
# so changes to different screens never touch the same file. spa/MANIFEST.json lists them in load order. At import
# they are joined back into the same two strings as before (SPA, LOGIN_HTML): the shell's "@@SPA_CSS@@" line is
# replaced by the css files and its "@@SPA_JS@@" line by the js files, in the listed order; the login page is one
# file. Keep the manifest's shape (shell/css/js/login) stable: the running updater reads the next version's.
# Updates (update_if_newer) and repairs (spa_repair) download every listed file at one exact commit, check each
# against GitHub's own hash of it, assemble it (and `node --check` its scripts when node is on this computer) in a
# new folder, and only then swap the folder in. Anything missing or changed = nothing is replaced.
SPA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spa")
SPA_CSS_MARK, SPA_JS_MARK = "@@SPA_CSS@@\n", "@@SPA_JS@@\n"
SPA_LOCK = threading.Lock()
SPA_STAMP = ".version"          # inside an installed spa folder: the watcher version it was fetched for


class spa_locked:
    """Held around fetching and swapping the web app's files: one thread here (SPA_LOCK) and one process on this
    computer (a lock file next to the folder), so the watcher's repair and an installer's --install-spa never
    trip over each other."""

    def __enter__(self):
        import fcntl
        SPA_LOCK.acquire()
        try:
            self.f = open(os.path.join(os.path.dirname(SPA_DIR), ".spa.lock"), "a")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except BaseException:
            SPA_LOCK.release()
            raise
        return self

    def __exit__(self, *a):
        import fcntl
        try:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()
        finally:
            SPA_LOCK.release()
        return False


def spa_stamp(folder=SPA_DIR):
    """The version an installed spa folder was fetched for ("" when unstamped, e.g. in the repo)."""
    try:
        with open(os.path.join(folder, SPA_STAMP), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""
SPA_FALLBACK = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Combo Hub</title></head>'
                '<body style="margin:0;padding:28px 20px;background:#0b0d12;color:#eef1f6;'
                'font:16px/1.45 -apple-system,BlinkMacSystemFont,system-ui,sans-serif">'
                '<h2 style="margin:0 0 8px">Combo Hub is finishing an update</h2>'
                '<p style="color:#a1aabb">The Mac is fetching the rest of the app. Your bets are still being watched. '
                'Reload this page in a minute.</p></body></html>\n')


def spa_manifest(folder=SPA_DIR):
    """The manifest in folder: (manifest, every file it lists). Raises ValueError if it is malformed."""
    with open(os.path.join(folder, "MANIFEST.json"), encoding="utf-8") as f:
        m = json.load(f)
    if not isinstance(m, dict) or not isinstance(m.get("css"), list) or not isinstance(m.get("js"), list):
        raise ValueError("MANIFEST.json isn't a web app manifest")
    files = [m.get("shell"), *m["css"], *m["js"], m.get("login")]
    for n in files:
        if not isinstance(n, str) or not re.fullmatch(r"[a-z0-9_]+\.(html|css|js)", n):
            raise ValueError(f"MANIFEST.json lists a bad file name: {n!r}")
    if len(set(files)) != len(files):
        raise ValueError("MANIFEST.json lists a file twice")
    return m, files


def spa_assemble(folder=SPA_DIR):
    """(SPA, LOGIN_HTML) built from the files in folder. Raises OSError/ValueError if anything is missing,
    empty or out of shape; never returns a partial page."""
    m, _ = spa_manifest(folder)

    def get(name):
        with open(os.path.join(folder, name), encoding="utf-8", newline="") as f:    # exact text, no newline changes
            s = f.read()
        if not s.strip():
            raise ValueError(f"{name} is empty")
        if name != m["shell"] and (SPA_CSS_MARK.strip() in s or SPA_JS_MARK.strip() in s):
            raise ValueError(f"{name} contains a shell placeholder")
        return s
    shell = get(m["shell"])
    if shell.count(SPA_CSS_MARK) != 1 or shell.count(SPA_JS_MARK) != 1:
        raise ValueError(f"{m['shell']} needs exactly one {SPA_CSS_MARK.strip()} line and one {SPA_JS_MARK.strip()} line")
    css = "".join(get(n) for n in m["css"])
    js = "".join(get(n) for n in m["js"])
    spa = shell.replace(SPA_CSS_MARK, css).replace(SPA_JS_MARK, js)
    login = get(m["login"])
    if not spa.startswith("<!doctype html>") or not spa.rstrip().endswith("</html>") or "__CWTOK__" not in spa:
        raise ValueError("the assembled web app is out of shape")
    if not login.startswith("<!doctype html>") or "__MSG__" not in login:
        raise ValueError("the login page is out of shape")
    return spa, login


def spa_scripts(page):
    """Every inline <script> block of a page, joined (what `node --check` reads)."""
    return "\n".join(re.findall(r"<script>(.*?)</script>", page, re.S))


def spa_node_check(spa, login):
    """`node --check` the assembled scripts when node is on this computer (it usually isn't on Pete's Mac: then
    the per-file hashes and the assembly are the check). Raises ValueError on a syntax error."""
    import shutil, subprocess, tempfile
    node = shutil.which("node") or next((p for p in ("/opt/homebrew/bin/node", "/usr/local/bin/node")
                                         if os.access(p, os.X_OK)), None)
    if not node:
        return False
    try:                                              # an old node can't read today's JavaScript: skip, don't block
        v = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15).stdout
        if int((re.match(r"v(\d+)", v.strip()) or [0, 0])[1]) < 18:
            log("web app check: node is too old to check the scripts (", v.strip(), "); skipped")
            return False
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        log("web app check: node didn't answer (", err, "); skipped")
        return False
    for name, page in (("web app", spa), ("login page", login)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(spa_scripts(page))
        try:
            r = subprocess.run([node, "--check", f.name], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as err:
            log(f"web app check: node couldn't check the {name}'s script ({err}); skipped")
            return False
        finally:
            os.unlink(f.name)
        if r.returncode:
            raise ValueError(f"the {name}'s script doesn't parse: {(r.stderr or '').strip()[-200:]}")
    return True


def git_blob_sha(b):
    """GitHub's own hash of a file's bytes (the git blob SHA-1 its file list reports)."""
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def spa_digest(spa, login):
    """The web app's fingerprint, as the phone approves it (the engine's spa_approval_digest computes the same)."""
    return hashlib.sha256((spa + "\0" + login).encode("utf-8")).hexdigest()


def spa_fetch(sha, approved=None, stamp=WATCHER_VERSION):
    """Download the web app's files at exactly commit sha into a new folder next to the installed one, check them
    all and return that folder (spa_swap puts it in place). With approved (updates your phone approves), the
    assembled app must also have exactly that spa_digest. Raises on anything missing, changed, cut short, broken
    or not approved, and then leaves nothing behind; the installed folder is never touched here. The folder is
    stamped with the watcher version it is for (stamp). Call inside spa_locked()."""
    import shutil, tempfile
    if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
        raise ValueError("no exact commit to fetch the web app from")
    r = requests.get(GH_API + "/contents/watcher/spa", params={"ref": sha}, timeout=15,
                     headers={"Accept": "application/vnd.github+json"})
    if not r.ok:
        raise ValueError(f"GitHub's file list answered {r.status_code}")
    listing = r.json()
    if not isinstance(listing, list):
        raise ValueError("GitHub's file list is out of shape")
    want = {e.get("name"): e.get("sha") for e in listing if isinstance(e, dict) and e.get("type") == "file"}
    parent = os.path.dirname(SPA_DIR)
    for old in os.listdir(parent):                    # leftovers of an interrupted fetch (an hour old or more)
        try:
            if old.startswith(".spa-new-") and time.time() - os.path.getmtime(os.path.join(parent, old)) > 3600:
                shutil.rmtree(os.path.join(parent, old), ignore_errors=True)
        except OSError:
            pass
    tmp = tempfile.mkdtemp(prefix=".spa-new-", dir=parent)
    try:
        def grab(name):
            if not want.get(name):
                raise ValueError(f"{name} isn't on GitHub at {sha[:7]}")
            g = requests.get(REPO.replace("/main/", f"/{sha}/") + "watcher/spa/" + name, timeout=30)
            if not g.ok:
                raise ValueError(f"{name} answered {g.status_code}")
            if git_blob_sha(g.content) != want[name]:
                raise ValueError(f"{name} arrived changed or cut short")
            fd = os.open(os.path.join(tmp, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(g.content)
        grab("MANIFEST.json")
        for name in spa_manifest(tmp)[1]:
            grab(name)
        spa, login = spa_assemble(tmp)
        if approved is not None and spa_digest(spa, login) != approved:
            raise ValueError("they don't match what your phone approved")
        spa_node_check(spa, login)
        with open(os.path.join(tmp, SPA_STAMP), "w", encoding="utf-8") as f:
            f.write(stamp + "\n")
        return tmp
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def spa_swap(new):
    """Put the checked folder new in place of the installed one. Returns the old folder's new name (for
    spa_restore/spa_drop), or None when there wasn't one."""
    import shutil
    old = SPA_DIR + ".old"
    shutil.rmtree(old, ignore_errors=True)
    had = os.path.isdir(SPA_DIR)
    if had:
        os.replace(SPA_DIR, old)
    try:
        os.replace(new, SPA_DIR)
    except OSError:
        if had:
            os.replace(old, SPA_DIR)
        raise
    return old if had else None


def spa_restore(old):
    """Undo spa_swap (the rest of an update failed): the previous folder goes back."""
    import shutil
    if old and os.path.isdir(old):
        shutil.rmtree(SPA_DIR, ignore_errors=True)
        os.replace(old, SPA_DIR)


def spa_drop(old):
    import shutil
    if old:
        shutil.rmtree(old, ignore_errors=True)


def spa_repair(conf=None):
    """Fetch the web app's files for exactly this watcher: after an older updater (one that didn't know about the
    spa folder) installed it, when the folder was deleted or damaged, and from the installers (--install-spa).
    Only when GitHub's newest watcher is this very file, byte for byte; otherwise the normal update brings a newer
    version together with its own files. With automatic updates off (a Pi, usually), only files your phone
    approved for this version (their spa_digest). True once installed."""
    if conf is None:
        try:
            conf = load_conf()
        except (OSError, ValueError):
            conf = {}
    here = os.path.dirname(os.path.abspath(__file__))
    if any(os.path.exists(os.path.join(d, ".git")) for d in (here, os.path.dirname(here))):
        log("web app files: this watcher runs from a git checkout; its spa folder is the repo's, left alone")
        return False
    approved = None
    if not auto_updates(conf):
        ok = conf.get("approve") or {}
        approved = ok.get("spa") if ok.get("version") == WATCHER_VERSION else None
        if not approved:
            log("web app files: waiting for your phone to approve this version's files")
            return False
    sha = repo_sha()
    if not sha:
        log("web app files: GitHub didn't say which commit is newest; trying again later")
        return False
    try:
        g = requests.get(REPO.replace("/main/", f"/{sha}/") + "watcher/combo_watcher.py", timeout=30)
        with open(os.path.abspath(__file__), "rb") as f:
            mine = f.read()
        if not g.ok or g.content != mine:
            log("web app files: GitHub's newest watcher isn't this one; the next update brings both")
            return False
        with spa_locked():
            spa_drop(spa_swap(spa_fetch(sha, approved)))
    except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as err:
        log("web app files couldn't be fetched:", err)
        return False
    log("web app files installed for this version", WATCHER_VERSION)
    return True


def spa_repair_start(conf):
    def run():
        spa_repair_loop(conf)                       # returns only once the files are installed
        if not UPDATED.get("now"):
            return
        time.sleep(20)                              # the main loop exits on UPDATED; if it's stuck, exit anyway
        log("restarting for the web app files")
        os._exit(0)
    threading.Thread(target=run, daemon=True, name="spa-repair").start()


def spa_repair_loop(conf=None):
    """main() runs this when the web app's files were missing or broken at start: it fetches them (retrying every
    10 minutes) and then restarts the watcher so Combo Hub serves them. Trading carries on throughout."""
    while True:
        try:
            if spa_repair(conf):
                log("restarting so Combo Hub uses its web app files")
                restart_when_quiet()
                UPDATED["now"] = True
                return
        except Exception as err:
            log("web app repair failed:", type(err).__name__, err)
        time.sleep(600)


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
# Non-GET requests the phone may forward are only the ones the app itself sends (GitHub #102): order create/cancel,
# quote requests (RFQs) and accepting a quote, and making a combo market. Anything else (batch or amend orders, other
# writes under /portfolio) is refused with a logged reason. Money moves between pots stay on pot_move only.
_ID = r"[A-Za-z0-9_.:-]{1,120}"
HUB_WRITES = {
    "POST": re.compile(r"/portfolio/orders|/portfolio/events/orders|/communications/rfqs|"
                       r"/multivariate_event_collections/" + _ID),
    "PUT": re.compile(r"/communications/rfqs/" + _ID + r"/quotes/" + _ID + r"/accept"),
    "DELETE": re.compile(r"/portfolio/(events/)?orders/" + _ID + r"|/communications/rfqs/" + _ID),
}


def hub_refusal(method, path):
    """Why the Mac won't forward this request for the phone, or '' when it may. GETs need only HUB_PATHS; anything
    that writes must match HUB_WRITES exactly (fail closed), with no transfer/allocation/subaccount words."""
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return "method not allowed"
    if not HUB_PATHS.match(path):
        return "path not allowed"
    if method == "GET":
        return ""
    if ".." in path or re.search(r"transfer|balance_allocation|subaccount", path.lower()):
        return "path not allowed for a write"
    if not HUB_WRITES[method].fullmatch(path):
        return "write not on the allow-list"
    return ""


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
        self.pending, self.told, self.retry = {}, {}, {}
        self.saving, self.skip_log = False, {}

    def engine(self):
        if self.H is None:
            self.H = load_engine()
            self.H.present = self.H.loading = lambda *a, **k: None
            try:                                    # the shadow, buy ideas and killer deals write history too
                self.H.store_open(os.path.join(HOME, "combo_history.db"))
            except Exception as err:
                log("history off for the odds engine:", err)
            self.H.console_note = lambda msg: log(msg)
            self.H.TRADING_PAUSED = watcher_paused     # killer deals and standing orders: Pause read live
            if is_backup(DEP.get("conf")):
                self.H.ROLE_BACKUP = True
        return self.H

    @staticmethod
    def soonest(snap, *more):
        """The next start time in the snapshots (free lines, and the sharp lines' own: tennis, UFC, EuroLeague and
        the AHL have no free lines, and still need the near-game refresh)."""
        import datetime as dt
        now, best = time.time(), None
        for start in [v for s in (snap,) + more if s for v in (s.get("kick") or {}).values()]:
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
                soon = self.soonest(f[1], sh[1] if sh else None)
                ttl = self.SHARP_NEAR_TTL if soon and soon - now < self.NEAR else self.SHARP_TTL
                due = (not sh or now - sh[0] > ttl) and now >= self.retry.get(league, 0)
                if due and not self.worth_credits(H, league, now):
                    due = False                 # low on credits: this league has nothing near that matters, and
                    if sh:                      # its sharp lines are past their time, so they go (free lines only):
                        sh = None               # never price a far-off game on a line days old
                        self.sharp.pop(league, None)
                if due:
                    got = H.sharp_snapshot(key)
                    if got["fair"]:
                        sh = (now, got)
                        self.sharp[league] = sh
                        self.retry.pop(league, None)
                    else:                       # an empty answer (out of credits, an outage): the old lines are
                        sh = None               # past their time, so they go (free lines only) until a retry
                        self.sharp.pop(league, None)
                        self.retry[league] = now + min(ttl, self.SHARP_NEAR_TTL)
                    log(f"odds service asked for {league}: {len(got['fair'])} teams")
            snap = H.merge_books(sh[1] if sh else H.empty_snapshot(), f[1])
            if sh:
                snap["note"] += f" Sportsbook lines checked {int((now - sh[0]) / 60)} min ago (shared by the Mac)."
            if key and self.saving:
                snap["note"] += " Saving sportsbook credits: lines refresh only for games starting soon that you have bets or good prices on."
            return snap

    def worth_credits(self, H, league, now):
        """Spend a call on this league? Always, unless credits are low: then only when a panel candidate, a panel bet
        or a bet you hold has a game in this league starting within 4 hours or under way. It only decides which lines
        get read; nothing here buys, sells or prices. Also sends the one low-credit alert. Never raises."""
        try:
            saving, c = H.odds_saving(now)
            self.saving = saving
            self.credits_alert(H, c)
            if not saving:
                return True
            E = WATCHER.get("E")
            held = (E.held_for_credits() if E else []) + H.held_for_credits()
            if H.odds_worth_reading(league, H.odds_interest(held, now), now):
                return True
            if now - self.skip_log.get(league, 0) > 1800:
                self.skip_log[league] = now
                log(f"odds credits low ({int(c['remaining'])} left): skipped {league}, nothing near that matters")
            return False
        except Exception as err:
            log("odds credits check skipped:", type(err).__name__, err)
            return True

    @staticmethod
    def credits_alert(H, c):
        """One push per low state (per reason, per reset cycle), sent off the odds lock."""
        got = H.odds_low_alert(c)
        if not got or (c or {}).get("alerted") == got[0]:
            return False
        H.odds_mark(alerted=got[0])
        conf = DEP.get("conf")
        log("odds credits:", got[1])
        if conf and conf.get("topic"):
            threading.Thread(target=push, args=(conf, got[1]), kwargs={"title": "Odds credits", "tag": "credits"},
                             daemon=True).start()
        return True


COMBO_TICKER = re.compile(r"^[A-Za-z0-9._-]{3,120}$")


def combo_link(E, msg):
    """Where tapping an alert about one combo goes (#210): '/#c=<ticker>' when the text names exactly one of the
    combos Live shows right now ("Combo 24", matched as a whole word so "Combo 2" isn't "Combo 24"), else None (the
    tap opens Live as before). Labels are read from this refresh's own data, so they match the text just built."""
    try:
        named = set(re.findall(r"\bCombo (\d+)\b", msg or ""))
        if len(named) != 1:
            return None
        want = "Combo " + named.pop()
        mine = dict(E.MINE.get("snap") or {})
        mine.update(E.MINE.get("hold") or {})
        hits = {t for t, c in mine.items() if (c or {}).get("label") == want and COMBO_TICKER.match(t or "")}
        return "/#c=" + hits.pop() if len(hits) == 1 else None     # URL-safe characters only (COMBO_TICKER)
    except Exception:
        return None


def single_link(E, msg):
    """Where tapping an alert about one single bet, spread or total goes: '/#b=<ticker>' when the text names the
    label of exactly one bet in Live's singles right now (a label that is part of a longer matching label doesn't
    count), else None. Only the market ticker goes in the link (URL-safe characters only, COMBO_TICKER)."""
    try:
        hits = {}
        for x in list(getattr(E, "SINGLES", {}).get("items") or []):
            lab, t = (x or {}).get("label") or "", (x or {}).get("t") or ""
            if len(lab) >= 3 and lab in (msg or "") and COMBO_TICKER.match(t):
                hits[t] = lab
        labs = set(hits.values())
        hits = {t: lab for t, lab in hits.items() if not any(lab != o and lab in o for o in labs)}
        return "/#b=" + next(iter(hits)) if len(hits) == 1 else None
    except Exception:
        return None


def trade_link(E, msg):
    """The tap target of any trade alert: the combo it names, else the single bet it names, else None (the tap opens
    the app as before). Only a view route: no keys, tokens or account ids ever go in it."""
    return combo_link(E, msg) or single_link(E, msg)


class Notifier:
    """Urgent alerts (cash-outs, hedges, anything done automatically, combos at risk) go out at once.
    Everything else waits and goes out together, at most once every 30 minutes, never 10 PM-7 AM.
    Each kind can be switched off in the phone's Settings."""
    URGENT = ("cash out", "cashing out", "cashed out", "cash-out", "hedge", "auto", "turning", "at risk", "can't", "couldn't",
              "refused", "paused", "🤖")      # 🤖: everything the app did by itself (a single's sale had no other word)
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
                 web_msg=msg.replace("Open the planner to confirm.", "Tap to decide."), click=trade_link(self.E, msg))
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

    def send(self, title, body, url="/", tag=None, urgent=False):
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
ICON_PNG = "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"

SW_JS = """// Combo Hub service worker (v2: taps open '/', legacy '/app' targets are mapped): shows the Mac's notifications and opens the right screen when tapped.
// It has no fetch handler and caches nothing, so it can never serve an old page (#150). The next line carries the app version, so every release changes this file's bytes and the browser installs the new worker.
// app-version: @@VER@@
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data.json(); } catch (x) { d = {title: 'Combo Hub', body: e.data ? e.data.text() : ''}; }
  e.waitUntil(self.registration.showNotification(d.title || 'Combo Hub',
    {body: d.body || '', tag: d.tag || undefined, data: {url: d.url || '/'}, icon: '/icon.png', badge: '/icon.png'}));
});
// Notifications sent before 2026-11-20 carry '/app' (the API prefix, not a page: it used to answer an empty
// file that iOS showed as "app, Zero KB"). The page is at '/', so those taps are mapped there (#79).
function tapTarget(raw) {
  let u;
  try { u = new URL(raw || '/', self.location.origin); } catch (x) { u = new URL('/', self.location.origin); }
  if (u.pathname === '/app' || u.pathname === '/app/') {
    return new URL('/' + u.search + u.hash, self.location.origin).href;
  }
  return u.href;
}
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = tapTarget(e.notification.data && e.notification.data.url);
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(cs => {
    for (const c of cs) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
"""

NOT_FOUND_HTML = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
                  "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Combo Hub</title>"
                  "<body style='font:17px -apple-system,system-ui,sans-serif;padding:40px;line-height:1.5;"
                  "background:#0b0d12;color:#e8eaf0'><h2>That page isn't here</h2>"
                  "<p>Nothing is at this address. Combo Hub opens from the home page.</p>"
                  "<p><a href='/' style='color:#5ac8fa;font-size:19px'>Open Combo Hub</a></p></body></html>")

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
                push(conf, m, click=trade_link(H, m))
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
            for m in E.killer_sweep():
                log(m)
                if DEP.get("conf"):
                    push(DEP["conf"], m, priority="high", click=trade_link(E, m))
            E.maker_resolve()
            got = E.resolve_quotes()
            E.resolve_closes()
            E.smart_buy_learn()                    # Smart Buy: results of checked bets, then the dial per league
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
        carried = False                                   # (#341 C) at most one cost-carry paper quote a round
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
                    carry_legs = None
                    if not carried and hasattr(odds.engine(), "carry_pick"):
                        try:                              # paper only: pick here, quote below outside the lock
                            carry_legs = odds.engine().carry_pick(snap)
                        except Exception as err:
                            log(f"cost-carry {code} skipped:", type(err).__name__, err)
                    for m in odds.moves(code, held_teams(odds)) if notifier else []:
                        notifier.add(m, "news")
                if carry_legs:                            # (#341 C) one combo quote, never accepted (withdrawn),
                    try:                                  # OUTSIDE odds.lock: it waits up to 15 s for makers
                        got = odds.engine().carry_pass(legs=carry_legs, log=log)
                        carried = True                    # one attempt a round, priced or not
                        did = (did or []) + got
                    except Exception as err:
                        log(f"cost-carry {code} skipped:", type(err).__name__, err)
                if did:
                    log(f"shadow {code}:", "; ".join(did))
            except Exception as err:
                log(f"shadow {code} skipped:", type(err).__name__, err)
        try:                                              # rebuild today's panel; settle; weekly cut-off review
            with odds.lock:
                H = odds.engine()
                did = H.panel_pass(log=log) + H.panel_settle() + [f"cut-off {m}" for m in H.adjust_cutoffs()] \
                    + [f"smart sell {m}" for m in H.smart_tune()] \
                    + [f"spread/total bar {m}" for m in H.line_edge_tune()]      # never raises (logs instead)
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
        smart_buy_universe(odds)                          # (#137) paper scoring of every priced market, OUTSIDE odds.lock
        try:                                              # the smart-sell scorecard (#115): read-only, OUTSIDE odds.lock
            n_out = odds.engine().sale_outcomes()         # (public Kalshi reads; itself at most every 10 minutes)
            if n_out:
                log(f"smart-sell scorecard: {n_out} sold bet(s) now know what holding would have paid")
        except Exception as err:
            log("smart-sell scorecard skipped:", type(err).__name__, err)
        try:                                              # self-tuning (#228), OUTSIDE odds.lock: brake every 30 min,
            lines, pushes = odds.engine().knob_pass()     # stepper weekly, time-bounded; reads history only and writes
            for m in lines:                               # combo_knobs.json + knob_shadow. With 'Let smart sell tune
                log("knobs:", m)                          # its own numbers' on, smart sell's exit numbers read them
            for m in pushes if notifier else []:          # (PR3); everything else stays a test
                notifier.add(m)                           # a brake only: one per league per 14 days
        except Exception as err:
            log("self-tuning test skipped:", type(err).__name__, err)
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
        smart_buy_universe(odds)


def smart_buy_universe(odds):
    """Smart Buy's paper work (#137), all OUTSIDE odds.lock (the lock panel_loop holds to place a real approved buy)
    and in the shadow engine (H), never the trading one: score every market the panel looks priced (0.15 s of
    simulation a pass), then, when due, the backfill from history (daily, 3 s a run) and the paper book (every 6 h).
    Writes exit_shadow rows and the sb_paper table only; each step self-throttles and never raises."""
    try:
        H = odds.engine()
    except Exception as err:
        log("smart buy paper scoring skipped:", type(err).__name__, err)
        return
    for name in ("smart_buy_universe", "smart_buy_backfill", "sb_paper_build"):
        try:
            if hasattr(H, name):
                n = getattr(H, name)()
                if n and name != "smart_buy_universe":
                    log(f"smart buy on paper: {name} wrote {n} rows")
        except Exception as err:
            log(f"smart buy paper {name} skipped:", type(err).__name__, err)



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


# SPA and LOGIN_HTML are built from watcher/spa/ at the end of this file (after SPA_LEGACY_Z).


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
            with H.manual_tap():                    # Pete's own tap: a region hold doesn't stop it (#134)
                r = H.get_offer(i)
            if r.get("error"):
                return r["error"]
            b["offers"][i] = dict(H.CTX["offers"][i], got=time.time(), pct=r.get("pct"), ok=r.get("ok"))
        pct = f" ({r['pct']:.0%} of fair)" if r.get("pct") else ""
        verdict = "" if r.get("ok") else f" That's under your {r.get('bar') or b['cut']}% cut-off."
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
            with H.manual_tap():
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

# SPA (the web app's page) is built at import from watcher/spa/: see spa_assemble and the SPA_PROBLEM block above.


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

    def manual_alert(msg):                          # a manual buy whose spend couldn't be saved: tell Pete (once a run)
        try:
            push(load_conf(), msg, title="Combo planner", priority="high", click="/")
        except Exception as err:
            log("manual buy alert failed:", type(err).__name__)
    A.MANUAL_ALERT = manual_alert
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

    def paused_now():
        """The Pause switch (from an alert), read fresh for every manual buy. No settings file = no watcher to pause;
        a file that can't be read counts as paused (never buy on a guess)."""
        if not os.path.exists(CONF):
            return False
        try:
            c = load_conf()
            return bool(c.get("paused")) or is_backup(c)
        except (OSError, ValueError, AttributeError):
            return True
    A.TRADING_PAUSED = paused_now                   # the engine's own buy paths (accept_offer) read it too

    def backup_now():
        """This device is the alerts-only backup (the Pi), read fresh; a settings file that can't be read counts as
        the backup. Pete's own single-bet Sell skips Pause (#245) but never this."""
        if A.role_backup():
            return True
        if not os.path.exists(CONF):
            return False
        try:
            return is_backup(load_conf())
        except (OSError, ValueError, AttributeError):
            return True
    try:
        if is_backup(load_conf()):
            A.ROLE_BACKUP = True                    # a web app on the Pi never trades either
    except (OSError, ValueError, AttributeError):
        pass

    def single_side(t, lg):
        """The board's side for one market (its fair chance, game and kind, and when that price was read), from the
        board on screen or another sport's saved board. Read only: never rebuilds or switches the board (that would
        hold the tap lock and change what Build shows). A market no board has is priced from Kalshi alone."""
        def find(ctx, lines, at):
            for x in lines or []:
                if x.get("ticker") == t:
                    return dict(x, fair_at=at)
            games = (ctx or {}).get("all_games") or {}
            for e, sd in games.items():
                for x in sd:
                    if x.get("ticker") == t:
                        return dict(x, event=x.get("event") or e, opp=A.opp_of(games, x), fair_at=at)
            return None
        x = find(A.CTX, BUILD.get("lines"), BUILD.get("at") or 0)
        for k in sorted(list(SNAP), key=lambda k: (k != lg, -((SNAP.get(k) or {}).get("at") or 0))) if x is None else ():
            sn = SNAP.get(k) or {}
            x = find(sn.get("ctx"), sn.get("lines"), sn.get("at") or 0)
            if x is not None:
                break
        return x or {"ticker": t}

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

    MONEY = {"seen": 0.0}

    def money_check():
        """Display only (#242): when the watcher stamped that money moved (a sale, hedge, fill or settlement), drop this
        app's account, singles, scoreboard and profit-line caches so the next build reads them fresh. Returns the
        stamp's time. One file stat; never raises."""
        m = getattr(A, "money_seen", float)()
        if m > MONEY["seen"]:
            MONEY["seen"] = m
            try:
                A.ACCT_CACHE["at"] = 0
                A.SINGLES["at"] = 0
                A.BOARD["at"] = 0
                A.PNL.clear()
            except Exception:
                pass
        return m

    def live_moved():
        """Money moved after the Live snapshot on hand began building."""
        return money_check() > (LIVE.get("from") or 0)

    def api_live(fresh=False, warm=False):
        """The Live numbers. A snapshot younger than the limit is served as is; an older one is rebuilt first and
        the fresh one is served (waiting a few seconds at most), so the page isn't one refresh behind. If the
        build is stuck behind another job or fails, the last good copy is served."""
        if not fresh and not warm:
            LIVE["asked"] = time.time()
        limit = live_limit() - (2 if warm else 0)
        moved = live_moved()
        if not fresh and LIVE["data"] and time.time() - LIVE["at"] < limit and not moved:
            return live_extras(LIVE["data"])
        patient = not fresh and LIVE["data"] is not None and time.time() - LIVE["at"] < 600
        if not alock.acquire(timeout=6 if patient else -1):
            return live_extras(LIVE["data"])                    # busy elsewhere (e.g. pricing a combo): last good copy
        try:
            if fresh or not LIVE["data"] or time.time() - LIVE["at"] > limit or live_moved():
                LIVE["from"] = time.time()               # a stamp after this point means this build may miss it
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
                "live": bool(on), "fast": bool(LIVE.get("fast")),
                "ver": str(getattr(A, "VERSION", "") or "")}       # the running version: the page compares it to the one it loaded with (#150)

    def live_extras(out):
        try:
            info = {}
            ideas = jsonable(A.live_ideas(info=info)) if A.STORE.get("db") else []
            ideas_extra = {"ideas_limit": A.ideas_shown(), "ideas_hidden": info.get("hidden", 0),
                           "ideas_sb": info.get("sb_skipped") or []}
        except Exception:
            ideas, ideas_extra = None, {}                      # unreadable: the page leaves the section out, not "nothing clears"
        try:
            orders = jsonable(A.maker_summary()["open"]) if A.STORE.get("db") else []
        except Exception:
            orders = []
        try:
            pnl = A.pnl_series() if A.STORE.get("db") else None    # #221: the hero chart's profit line (cached)
        except Exception:
            pnl = None
        return dict(out, ideas=ideas, orders=orders, pnl=pnl, sales=recent_sales(), **ideas_extra,
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
        kind, tier, live = A.combo_star(c)                  # a pick under way now: no star, no guess from past prices
        est = (None, None) if live else A.est_offer(c)
        try:
            pred = None if live else A.predict_quote(c)
        except Exception:
            pred = None
        fx, heavy = A.exposure_factor(c["legs"])
        size = A.stake_for(pred["pct"], c["legs"]) if pred and A.CFG.get("size_auto") else None
        return {"i": i, "kind": kind, "tier": tier, "live": live, "fair": c.get("fair"), "min": c.get("min"),
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
    LINES = {}                                          # sport -> its last spread/total recommendations (issue #117)
    LINES_BUSY = set()

    def lines_work(lg):
        """Spreads and totals for one Build sport, worked out OFF the app lock (they read Kalshi's order books and run
        Smart Buy's simulator), so taps never wait on them. Recommend-only: nothing here buys. Never raises."""
        try:
            codes = [c for c in A.MIX_SPORTS] if lg == "mix" else [lg]
            recs, priced, nobook = [], 0, 0
            for c in codes:
                got, info = A.line_recommend(c)
                recs += got
                priced += info.get("priced") or 0
                nobook += (info.get("skipped") or {}).get("book") or 0
            got = {"at": time.time(), "lines": sorted(recs, key=lambda x: -(x.get("exp") or 0))[:12],
                   "priced": priced, "nobook": nobook}
            LINES[lg] = got
            if BUILD.get("lg") == lg:                   # Buy straight reads the board's lines (single_side)
                BUILD.update(lines=got["lines"], lines_priced=priced, lines_nobook=nobook)
            if lg in SNAP:
                SNAP[lg].update(lines=got["lines"], lines_priced=priced, lines_nobook=nobook)
        except Exception as err:
            print("lines:", type(err).__name__, err, flush=True)
        finally:
            LINES_BUSY.discard(lg)

    def lines_kick(lg, wait=0.0):
        """Start working out a sport's spreads/totals in the background when its copy is over a minute old (one at a
        time per sport); wait up to `wait` seconds for it. The page shows the last good copy meanwhile."""
        got = LINES.get(lg)
        if lg not in LINES_BUSY and (not got or time.time() - got["at"] > 60):
            LINES_BUSY.add(lg)
            th = threading.Thread(target=lines_work, args=(lg,), daemon=True)
            th.start()
            if wait:
                th.join(wait)

    LS = {}                                             # sport -> its last long shots (issue #341), worked out off the lock
    LS_BUSY = set()
    LS_EVERY = 900                                      # a sport's long shots are asked for again at most every 15 minutes

    def ls_open():
        """Combos with a live Kalshi quote on screen right now: never re-quoted underneath Pete (a new request for the
        same combo would withdraw his)."""
        try:
            return {frozenset(o.get("legs") or []) for o in list((A.CTX.get("offers") or {}).values())}
        except Exception:
            return set()

    def longshots_work(lg, games):
        """Long shots for one Build sport, OFF the app lock (each asks Kalshi's combo makers, up to 15 s). Recommend-only:
        nothing here buys. Never raises."""
        try:
            recs, info = A.longshot_build(games, paused=paused_now(), skip=ls_open)
            LS[lg] = {"at": time.time(), "recs": recs, "info": info}
        except Exception as err:
            print("long shots:", type(err).__name__, err, flush=True)
            LS[lg] = {"at": time.time(), "recs": [], "info": {"why": "Couldn't work out long shots just now."}}
        finally:
            LS_BUSY.discard(lg)

    def longshots_kick(lg, games):
        """Start working out a sport's long shots in the background when its copy is over LS_EVERY old (one at a time
        per sport). Pause empties them at once. The page shows the last copy meanwhile."""
        got = LS.get(lg)
        if paused_now():
            LS[lg] = {"at": time.time(), "recs": [], "info": {"why": A.LONGSHOT_WHY["paused"]}}
            return
        if lg in LS_BUSY or (got and time.time() - got["at"] < LS_EVERY and not (got.get("info") or {}).get("why") == A.LONGSHOT_WHY["paused"]):
            return
        LS_BUSY.add(lg)
        snap = {e: [dict(x) for x in sd] for e, sd in (games or {}).items()}
        threading.Thread(target=longshots_work, args=(lg, snap), daemon=True).start()

    def ls_view(lg):
        got = LS.get(lg) or {}
        info = got.get("info") or {}
        bought = owned_sets()
        return {"recs": [dict(r, bought=frozenset(l["ticker"] for l in r["legs"]) in bought) for r in got.get("recs") or []],
                "why": info.get("why"), "busy": lg in LS_BUSY, "at": got.get("at"), "looked": info.get("looked") or 0,
                "quoted": info.get("quoted") or 0}

    def use_snap(lg):
        s = SNAP.get(lg)
        if not s or time.time() - s["at"] > 600:
            return False
        A.set_league(lg)
        A.CTX.clear()
        A.CTX.update(s["ctx"])
        BUILD.update(lg=lg, last=lg, note=s["note"], at=s["at"], days=s["days"], lines=s["lines"],
                     lines_priced=s.get("lines_priced") or 0, lines_nobook=s.get("lines_nobook") or 0)
        return True

    def overlap_legs(over, legs):
        """The over-the-line game a list of legs (dicts or tickers) touches, or None."""
        legs = legs or []
        return A.overlap_of(over, [l.get("event") or "" for l in legs if isinstance(l, dict)],
                            [l.get("ticker") or "" if isinstance(l, dict) else str(l) for l in legs])

    def combo_over(legs, raw_allow):
        """The over-the-line game a freshly swapped or flipped combo touches (display only), or None."""
        try:
            return overlap_legs(A.overlap_games(allow=A.overlap_allow(raw_allow)), legs)
        except Exception as e:
            log(f"overlap check (swap/flip) failed: {e}")
            return None

    def overlap_info():
        """The guard's settings for the page's wording."""
        on, n, pct = A.overlap_settings()
        return {"on": on, "n": n, "pct": pct}

    def overlap_ls(view, over):
        if over and isinstance(view, dict):
            view = dict(view, recs=[dict(r, over=overlap_legs(over, r.get("legs"))) for r in view.get("recs") or []])
        return view

    def overlap_live(out, raw_allow):
        """Live's Buy ideas: each on a game Pete already has enough on is marked (greyed with Add anyway). Never raises."""
        try:
            if isinstance(out, dict) and out.get("ideas"):
                over = A.overlap_games(allow=A.overlap_allow(raw_allow))
                out = dict(out, ideas=[dict(x, over=overlap_legs(over, x.get("legs"))) for x in out["ideas"]],
                           overlap=overlap_info())
        except Exception as err:
            log("overlap (live):", type(err).__name__, err)
        return out

    def overlap_panel(out, raw_allow):
        """The New-since-you-approved extras: each on a game Pete already has enough on is marked. Never raises."""
        try:
            x = out.get("extra") if isinstance(out, dict) else None
            if x and x.get("items"):
                over = A.overlap_games(allow=A.overlap_allow(raw_allow))
                out = dict(out, extra=dict(x, items=[dict(c, over=overlap_legs(over, c.get("legs"))) for c in x["items"]]),
                           overlap=overlap_info())
        except Exception as err:
            log("overlap (panel):", type(err).__name__, err)
        return out

    def overlap_extra_ids(ids, raw_allow):
        """(ids to add, ids left out, unreadable): extras on a game over the line stay out unless Pete tapped Add anyway
        on it. This one buys, so it fails closed: if his open bets can't be read, nothing is added (the lists only grey)."""
        ids = list(ids) if isinstance(ids, (list, tuple)) else []
        try:
            if not A.overlap_settings()[0]:
                return ids, [], False
            x = A.panel_extras() or {}
            over = A.overlap_games(allow=A.overlap_allow(raw_allow), exposure=A.game_exposure())
            bad = {c["id"] for c in x.get("items") or [] if overlap_legs(over, c.get("legs"))}
        except Exception as err:
            log(f"panel extras: couldn't check open bets per game ({type(err).__name__}: {err}); none added")
            return [], ids, True
        return [i for i in ids if i not in bad], [i for i in ids if i in bad], False

    def api_build(lg, rebuild=True, warming=False, allow=None):
        import random
        BUILD.setdefault("seen", {})[lg] = time.time()
        if not warming:
            BUILD["touched"] = time.time()
        lines_kick(lg, wait=0 if warming else 1.5)     # before the lock: never holds it
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
                # (#341) suggested combos: games before their start, or under way only where the live checks passed
                pre = {e: sd for e, sd in games.items() if e in live_ok or not any(A.started(x) for x in sd)}
                rnd = {e: sd for e, sd in pre.items() if not any(A.started(x) for x in sd)}   # random ones: pregame only
                combos, _ = A.build_combos(rnd, A.CFG.get("picks") or {}, random.Random()) if rnd else ([], None)
                try:                                    # the value search's best few go first
                    vals = A.value_combos(pre, A.CFG["stake"], k=4, live_ok=live_ok) if pre else []
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
                lc = LINES.get(lg) or {}                # spreads and totals: recommendations only (issue #117),
                BUILD.update(lines=lc.get("lines") or [], lines_priced=lc.get("priced") or 0,   # worked out off the lock
                             lines_nobook=lc.get("nobook") or 0)
                SNAP[lg] = {"at": time.time(), "ctx": dict(A.CTX), "note": note, "days": days, "lines": BUILD["lines"],
                            "lines_priced": BUILD["lines_priced"], "lines_nobook": BUILD["lines_nobook"]}
            games = A.CTX.get("all_games") or {}
            if not warming:                             # (#341) off the lock, only for a Build Pete opened: never waits
                longshots_kick(lg, games)
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
            over = A.overlap_games(allow=allow or ())   # games Pete already has enough on: greyed (display only)
            for g in board:
                g["over"] = A.overlap_of(over, [g["event"]])
            own_sets = owned_sets()
            pairs = [(combo_view(i, c, own_sets), c) for i, c in enumerate(A.CTX.get("combos") or [], 1)
                     if c.get("kind") != "longshot"]   # (#341) a long shot priced from its own card stays in Long shots
            for v, c in pairs:                          # marked, never removed: every card keeps its own number (rule 7)
                v["over"] = overlap_legs(over, c.get("legs"))
            cviews = [v for v, _ in pairs]
            lines_now = (LINES.get(lg) or {}).get("lines", BUILD.get("lines") or [])   # #117: already vetted recommendations
            pregame = {e: sd for e, sd in games.items() if not any(A.started(x) for x in sd)}
            held = A.held_markets()                     # (#414) a market Pete holds or just bought leaves the pick lists
            fresh = {e: sd for e, sd in games.items() if not any(x.get("ticker") in held for x in sd)}   # either side of it
            try:                                        # Best bets today (#63): recommend-only, display only
                best = A.best_bets_feed(                # without games over the line (they're listed as left out)
                    {e: sd for e, sd in pregame.items() if e in fresh and not A.overlap_of(over, [e])},
                    [x for x in lines_now if x.get("ticker") not in held
                     and not A.overlap_of(over, [x.get("event") or ""], [x.get("ticker") or ""])],
                    [(v["i"], c, (v["pred"]["pct"] if v.get("pred") and (v["pred"].get("n") or 0) >= 20 else v.get("est_pct")))
                     for v, c in pairs if not v.get("bought") and not v.get("over")])
            except Exception as err:
                print("best bets:", err, flush=True)
                best = {"items": [], "why": "Couldn't work out today's best bets right now.", "looked": {}}
            best["over"] = [dict(A.overlap_of(over, [e]), event=e) for e in pregame if A.overlap_of(over, [e])]
            return jsonable({"lg": lg, "name": A.LG()["name"], "icon": A.LG().get("icon", ""), "note": BUILD.get("note", ""),
                             "stake": A.CTX.get("stake"), "budget": A.CFG.get("budget"), "cut": A.CFG.get("accept_pct"),
                             "spent": A.week_spend_shown() if A.can_trade() else 0,   # display only, never a cap check
                             "board": board, "combos": cviews, "best": best,
                             "singles": [dict(x, over=A.overlap_of(over, [], [x["ticker"]])) for x in singles_view(fresh)],
                             "lines": [x for x in lines_now if x.get("ticker") not in held], "longshots": overlap_ls(ls_view(lg), over),
                             "overlap": overlap_info(),
                             "lines_priced": (LINES.get(lg) or {}).get("priced", BUILD.get("lines_priced") or 0),
                             "lines_nobook": (LINES.get(lg) or {}).get("nobook", BUILD.get("lines_nobook") or 0),
                             "days": {"mode": "mix" if A.is_mix() else "day" if A.by_day() else "week",
                                      **{k: A.CFG.get(k) for k in ("next_day", "thursday", "saturday", "monday", "mix_window")},
                                      "wed": sum(1 for x in (BUILD.get("days") or {}).values() if x == "Wednesday"),
                                      "windows": A.MIX_WINDOWS},
                             "leagues": [["mix", "Mix sports", A.LEAGUES.get("mix", {}).get("icon", "🎲")]]
                                        + [[k, A.SPORTS.get(k, {}).get("name", k.upper()), A.SPORTS.get(k, {}).get("icon", "")]
                                           for k in ("nfl", "nba", "nhl", "ahl", "ncaaf", "ncaamb", "ncaawb", "soccer", "ufc", "tennis", "euroleague")
                                           if k in A.SPORTS]})

    def api_results():
        money_check()                                   # money moved (#242): the account and scoreboard read fresh
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
                             "mkt": paper_part("mkt_fair_summary"), "carry": paper_part("carry_summary"),
                             "panel": A.panel_record() if A.STORE.get("db") else None, "board": board()})

    CLOSED_WHY = {"smart": "smart sell took the profit", "take profit": "took the profit", "lock in": "locked in a profit",
                  "checkpoint": "checkpoint sale", "cut loss": "cut the loss", "stop loss": "stop-loss"}

    CLOSED_CACHE = {}      # (#407) ticker -> (when, answer): one closed-bet page costs one account read and one log scan
    CLOSED_TTL, CLOSED_TTL_MISS, CLOSED_CACHE_MAX = 20, 4, 64   # seconds kept (a miss only briefly: a bet just closed shows up soon)

    def api_closed(t):
        """The closed-bet detail (api_closed_work), kept for CLOSED_TTL seconds per ticker so repeated requests (a page
        refreshing, a scan of ids) don't each hold the account lock for an account read and rescan the whole sell log
        (#407). A closed bet doesn't change, so the answer is the same; a bet that wasn't found is remembered for only a
        few seconds. Anything that isn't a valid ticker is answered before the cache, as before."""
        if not COMBO_TICKER.match(t or ""):
            return {"found": False}
        now = time.time()
        hit = CLOSED_CACHE.get(t)
        if hit and now - hit[0] < (CLOSED_TTL if hit[1].get("found") else CLOSED_TTL_MISS):
            return hit[1]
        out = api_closed_work(t)
        if isinstance(out, dict):
            for k in [k for k, v in CLOSED_CACHE.items() if now - v[0] > CLOSED_TTL]:
                CLOSED_CACHE.pop(k, None)
            while len(CLOSED_CACHE) >= CLOSED_CACHE_MAX:
                CLOSED_CACHE.pop(next(iter(CLOSED_CACHE)), None)
            CLOSED_CACHE[t] = (now, out)
        return out

    def api_closed_work(t):
        """Read-only detail of a bet that has already closed (sold, settled or expired), from what the app already stores:
        the account's bets, the history file, the automatic cash-out log. Only this bet's own ticker is looked up; nothing
        about the account itself goes out. found:False when it is nowhere (the page then says so)."""
        if not COMBO_TICKER.match(t or ""):
            return {"found": False}
        out = {"found": False, "t": t, "attempts": []}
        with alock:
            bets, _bal, _note = A.fetch_account(max_age=30, every_league=True)
        a = next((x for x in (bets or []) if x.get("ticker") == t), None)
        rows = A.store_rows("select ts, result, why, kind, offer, cost, pays, frac from sell_log where ticker=? order by ts", (t,)) if A.STORE.get("db") else []
        single = next((x for x in (api_live() or {}).get("singles") or [] if x.get("t") == t and x.get("state") == "done"), None)
        sale = next((r for r in reversed(rows) if r.get("result") == "sold"), None)
        if a and a.get("status") in ("won", "lost", "cashed"):
            names = []
            for l in a.get("legs") or []:
                lt = l.get("ticker") or ""
                nm = A.PICK_NAME.get(lt) or A.sport_teams(A.ticker_sport(lt) or "nfl").get(lt.rsplit("-", 1)[-1]) or lt.rsplit("-", 1)[-1]
                names.append({"name": ("not " if l.get("side") == "no" else "") + nm, "res": l.get("res"), "t": lt})
            back = a["back"] if a["status"] == "cashed" else a["pays"] if a["status"] == "won" else 0.0
            snap = (A.MINE.get("snap") or {}).get(t) or {}
            out.update(found=True, kind="combo", label=snap.get("label") or "Combo", picks=names, status=a["status"], cost=a["cost"],
                       back=round(back, 2), pays=a["pays"], closed_ts=A.realized_ts(a))
        elif single:
            out.update(found=True, kind="single", label=single.get("label"), game=single.get("game"), picks=[{"name": single.get("label"), "res": single.get("res"), "t": t}],
                       status="won" if single.get("res") == "yes" else "lost", cost=single.get("cost"), pays=single.get("pays"),
                       back=single.get("pays") if single.get("res") == "yes" else 0.0)
        elif sale:
            out.update(found=True, kind=sale.get("kind") or "single", label=None, picks=[], status="cashed", cost=sale.get("cost"),
                       back=sale.get("offer"), pays=sale.get("pays"), closed_ts=sale.get("ts"))
        if not out["found"]:
            return out
        if out.get("closed_ts") is None and sale:
            out["closed_ts"] = sale.get("ts")
        if out.get("closed_ts"):
            out["closed"] = time.strftime("%a %b %d, %I:%M %p", time.localtime(out["closed_ts"])).replace(" 0", " ")
        if out.get("cost") is not None and out.get("back") is not None:
            out["pl"] = round(out["back"] - out["cost"], 2)
            out["pl_pct"] = round(out["pl"] / out["cost"] * 100, 2) if out["cost"] else None
        out["stamp"] = {"won": "WON", "lost": "LOST", "cashed": "SOLD EARLY", "expired": "EXPIRED"}.get(out.get("status"), "CLOSED")
        out["sports"] = sorted({A.ticker_sport(l.get("t") or "") or "" for l in out.get("picks") or []} - {""}) or \
            ([A.ticker_sport(t)] if A.ticker_sport(t) else [])
        if sale and sale.get("chance") is not None:
            out["chance"] = sale.get("chance")
        sold_by_app = sale and (sale.get("why") or "")
        out["why"] = ("Cashed out automatically: " + CLOSED_WHY.get(sold_by_app, sold_by_app)) if sold_by_app else \
            {"won": "Settled: every pick won", "lost": "Settled: a pick lost", "cashed": "Cashed out by you"}.get(out["status"], "Closed")
        try:
            with open(A.SELL_LOG, encoding="utf-8") as f:
                for line in f:
                    if t not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("ticker") == t:
                        out["attempts"].append({"when": d.get("when"), "result": d.get("result"), "why": d.get("why"), "note": d.get("note"),
                                                "offer": d.get("offer"), "tries": [{"offer": x.get("offer"), "quote": x.get("quote"), "error": x.get("error")}
                                                                                  for x in (d.get("tries") or [])[:12] if isinstance(x, dict)]})
            out["attempts"] = out["attempts"][-40:]
        except OSError:
            pass
        out["chart"] = A.combo_history(t) if A.STORE.get("db") and out["kind"] == "combo" else {"offers": [], "ticks": {}}
        return jsonable(out)

    def paper_part(name):
        """One of the #341 paper tests' summaries for What's working; None when it can't be read (never breaks Results)."""
        try:
            return getattr(A, name)() if A.STORE.get("db") and hasattr(A, name) else None
        except Exception as err:
            log(f"{name}:", type(err).__name__, err)
            return None

    def board():
        """The profit scoreboard (#138), read-only from the history file; None when it can't be read (the page says so)."""
        try:
            return A.profit_board() if A.STORE.get("db") else None
        except Exception as err:
            log("profit scoreboard:", type(err).__name__, err)
            return None

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

    def funnel_now():
        """(#341) the Mac's last panel funnel, under an hour old, for the page's "Why so few?" (None otherwise)."""
        try:
            f = A.load_json(getattr(A, "FUNNEL_FILE", ""), {}) if getattr(A, "FUNNEL_FILE", "") else {}
            return f if f.get("why") and time.time() - float(f.get("at") or 0) < 3600 else None
        except Exception:
            return None

    def api_panel(view="all"):
        """Today's panel (or one sport's), its record and the cut-offs."""
        if not A.STORE.get("db"):
            return {"panel": None}
        real = A.panel_get("real")
        p = real if view in ("all", "") else A.panel_get(f"view:{view}")
        sk = A.load_json(A.SIZING_FILE, {})
        return jsonable({"panel": p, "view": view, "record": A.panel_record(), "cutoffs": A.cutoff_summary(),
                         "rebuild": A.rebuild_status(), "funnel": funnel_now(),
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
                                       "cost": v["cost"], "legs": len(v["legs"]),
                                       "parts": [{"plain": q.get("plain"), "matchup": q.get("matchup")} for q in v["legs"]]})
        for x in d.get("singles") or []:                    # your single bets and spreads on this game
            if game and (x["t"].split("-") + ["", ""])[1] == game and x.get("state") in ("live", "pre"):
                combos.append({"t": x["t"], "label": x["label"], "p": x.get("chance"), "pays": x["pays"],
                               "cost": x["cost"], "legs": 1, "single": True, "worth": x.get("worth"), "how": x.get("how"),
                               "plain": x.get("plain"), "matchup": x.get("matchup")})
        if leg is None and A.STORE.get("db"):               # a game from a buy idea you hold nothing on yet (display only)
            try:
                leg = A.idea_game_leg(t)
            except Exception as err:
                A.klive_log_once("ideagame", t, err)
        leg = A.label_game_page(dict(leg)) if leg else leg    # display only: what the bet is, and which game
        story = A.game_story(t) if A.STORE.get("db") else {"ticks": [], "plays": []}
        start = None                                        # kickoff / tip-off (epoch s): where the chance chart begins (display only)
        try:
            gs, gsrc = A.game_start(t.rsplit("-", 1)[0], t) if "-" in t else (None, None)
            if gs and gsrc in ("book", "feed"):             # never the settle-time estimate: it can be hours off
                start = gs.timestamp()
        except Exception as err:
            A.klive_log_once("gamestart", t, err)
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
        buy = []                                         # the two pinned Buy buttons: each team's Kalshi price now
        try:
            if leg and leg.get("kind") in (None, "win") and leg.get("state") != "over" and leg.get("phase") != "over" \
                    and "-" in t:
                sides = A.event_sides(t.rsplit("-", 1)[0])
                if 2 <= len(sides) <= 3 and all(s["ask"] and s["ticker"] for s in sides):
                    buy = [{"t": s["ticker"], "name": s["name"], "ask": s["ask"],
                            "mult": round(1 / (s["ask"] + A.single_fee(s["ask"])), 2)} for s in sides]
                    buy.sort(key=lambda s: s["t"] != t)  # the team of your pick first
        except Exception as err:                         # display only: no buttons, never a broken page
            A.klive_log_once("gamebuy", t, err)
            buy = []
        return jsonable({"leg": leg, "combos": combos, "story": story, "whatif": wi, "start": start,
                         "detail": detail, "buy": buy, "fresh": freshness()})

    def api_game_warm(t):
        """Warm one live football game's page data in the background (display only; the Games tab calls this when a card
        is shown or pressed). Starts a polite, capped fetch of the ESPN summary and the teams' last 5 / season leaders so the
        game page opens with them ready. Never prices, buys or sells; any trouble answers {"ok": False}."""
        t = str(t or "")[:80]
        try:
            sport = A.ticker_sport(t) if t else None
            if sport not in ("nfl", "ncaaf"):
                return {"ok": False}
            d = api_live() or {}
            game = (t.split("-") + ["", ""])[1]
            leg = next((x for x in (d.get("singles") or []) if x.get("t") == t), None)
            for v in d.get("combos") or []:
                for lg in v.get("legs") or []:
                    if leg is None and game and (lg["ticker"].split("-") + ["", ""])[1] == game:
                        leg = lg
            if not leg or leg.get("state") != "live":
                return {"ok": False}
            full = A.leg_score(leg)
            if not (full and full.get("game")):
                return {"ok": False}
            return {"ok": bool(A.game_prefetch(full["game"], sport)), "known": True}     # known: a live football game (ok False = just throttled)
        except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError) as err:
            A.klive_log_once("gamedetail", t or "warm", err)
            return {"ok": False}

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
            bet = {"t": x["t"], "label": x.get("label"), "plain": x.get("plain"), "kind": x.get("kind"), "cost": x.get("cost"),
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
                        "chance": ch, "singles": [bet], "matchup": x.get("matchup"), "found": x.get("found"),
                        "league": x.get("league")})
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
                "bankroll", "auto_cash", "refresh_secs", "cash_every", "ride", "auto_sell", "auto_cap", "flex_sell", "flex_learn", "flex_backstop", "auto_hedge",
                "prefer_hedge", "hedge_cap", "notify_value", "notify_price", "notify_cash", "notify_news", "killer_mode",
                "maker_mode", "take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "panel_live", "line_model",
                "panel_rank_dollars", "idea_bar_strict", "smart_buy_gate", "ideas_shown", "knobs_live", "learned_guards", "stop_loss_mode",
                "overlap_guard", "overlap_n", "overlap_pct", "sell_more_cheap", "sell_more_loss", "sell_more_cap")

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

    def _pots():
        try:                                            # Kalshi's cash by pot (read-only); never holds up Settings
            return A.kalshi_pots()
        except Exception:
            return None

    def api_settings(lg, vals=None):
        pots = _pots() if vals is None else None       # reads only, outside the lock (it may ask the Mac)
        try:                                            # pot names (public exchange status) and recent moves
            potnames = {str(k): v for k, v in A.pot_names().items()} if vals is None else None
            potmoves = A.pot_moves(refresh=True) if vals is None else None
        except Exception:
            potnames = potmoves = None
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
                    if k == "stop_loss_mode":           # #228 PR5: the 2-way choice (a saved 'never' becomes 'tune'); the old switch kept in step
                        A.sl_sync(A.CFG, {k: v})
                        continue
                    if k == "stop_loss":                # an older page's on/off may only make it stricter
                        if "stop_loss_mode" not in vals:
                            A.sl_sync(A.CFG, {k: bool(v)})
                        continue
                    try:
                        v = bool(v) if isinstance(cur, bool) else int(round(float(v))) if isinstance(cur, int) \
                            else float(v) if isinstance(cur, float) else None
                    except (TypeError, ValueError):
                        continue
                    if k == "auto_cap" and v is not None and A.auto_cap_limit(v) is None:
                        v = A.AUTO_CAP_UNLIMITED            # any value over the slider's numbers = Unlimited (#217)
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
                    if not synced and paused_now():     # the Mac never heard the resume: nothing turns on here
                        turned = [k for k in ("killer_mode", "maker_mode") if A.CFG.get(k) == "on" and before.get(k) != "on"]
                        for k in turned:
                            A.CFG[k] = before.get(k) or "watch"
                        if A.CFG.get("auto_sell") and not before.get("auto_sell"):
                            A.CFG["auto_sell"] = False
                            turned.append("auto_sell")
                        if turned:
                            A.save_cfg()
                            log("settings: couldn't reach the Mac while paused, so these stay off:", turned)
            mode = "mix" if A.is_mix() else "day" if A.by_day() else "week"
            return jsonable({"ok": True, "lg": A.LEAGUE["code"], "name": A.LG()["name"], "mode": mode,
                             "full": bool(A.LG().get("full")), "synced": synced,
                             "values": {k: A.CFG.get(k) for k in SET_KEYS if k in A.CFG},
                             "keys": {"kalshi": bool(A.CFG.get("kalshi_key_id")) or bool(A.hub_conf()),
                                      "odds": bool(A.CFG.get("odds_key"))},
                             "ride": [n for n, _ in A.RIDE], "windows": A.MIX_WINDOWS, "version": A.VERSION,
                             "killer": A.killer_summary() if A.STORE.get("db") else None,
                             "maker": A.maker_summary() if A.STORE.get("db") else None,
                             "blocks": A.order_blocks(), "flexfb": A.flex_fb_view(),
                             "more": A.more_view(),
                             "pots": pots, "potnames": potnames, "potmoves": potmoves,
                             "guards": A.guards_view(A.LEAGUE["code"]),
                             "leagues": [[k, v.get("short") or v.get("name") or k.upper(), v.get("icon", "")]
                                         for k, v in A.LEAGUES.items()]})

    def pot_plan(t, msg, cost=None):
        """The move that would let a buy refused for its pot fill (pot_shortfall), from what the order needed: the
        refusal's own words ("needs about $9.90"), else the cost on the sheet. Never raises; reads only."""
        try:
            m = re.search(r"needs about \$([0-9][0-9,]*\.?[0-9]*)", str(msg or ""))
            need = float(m.group(1).replace(",", "")) if m else float(cost or 0)
            return A.pot_shortfall(t, need) if 0 < need <= 10000 else None
        except Exception:
            return None

    def combo_ev_cal(c, r):
        """(#361) The quote's expected profit on the chance corrected by your own record (calib_fair, as notify_bar does),
        for the sheet to show beside the books' one. Display only: nothing reads it to size or buy. A pick under way
        (priced on its live chance) or a chance that can't be corrected: None. Never raises."""
        try:
            if r.get("live") or not r.get("pct") or not r.get("stake"):
                return None
            legs = c.get("legs") or []
            shown = A.math.prod(l["fair"] for l in legs)
            cal = A.math.prod(A.calib_fair(A.ticker_sport(l["ticker"]) or A.LEAGUE["code"], l.get("fair_book") or l["fair"],
                                         l.get("ticker")) for l in legs)
            if not (shown > 0 and cal > 0):
                return None
            return round(r["stake"] * (r["pct"] * cal / shown - 1), 2)
        except Exception:
            return None

    def combo_offer(i, own=None):
        """Kalshi's price for combo i: at Pete's own amount when he set one (already checked by own_stake), else at the
        recommended size (the price sets it, less if he's heavy on a team), as before. Adds what the sheet shows beside
        it: the recommended size (rec), the expected profit in dollars at the books' chance (ev), the room left under
        the cap and the most this bet may be. Prices only: the buy is still accept_offer on this exact offer."""
        c = A.CTX["combos"][i - 1]
        if c.get("kind") == "longshot":             # (#341) its own size: quarter Kelly, at most $5
            r = A.get_offer(i, amount=own if own is not None else c.get("ls_stake"))
            r = dict(r, own=own is not None, min=A.OWN_MIN)
            if r.get("error"):
                return r
            r["rec"] = c.get("ls_stake")
            h = A.longshot_hold(A.CTX.get("stake", A.CFG["stake"]) / c["fair"], r.get("price"), r["stake"]) \
                if c.get("fair") and r.get("price") else None
            r["ev"] = h["exp"] if h else None              # held to the end, after the fee (as the card)
            try:
                r["room"] = round(max(0.0, A.CFG["budget"] - A.week_spend_shown()), 2)
            except Exception:
                r["room"] = None
            r["max"] = min(A.OWN_MAX, r["room"]) if r["room"] is not None else A.OWN_MAX
            ov = overlap_warn(c.get("legs") or [])
            if ov:
                r["overlap"] = ov[0]["t"]
                r["warn"] = list(r.get("warn") or []) + ov
            return r
        r = A.get_offer(i, amount=own)
        rec = None
        if not r.get("error") and r.get("pct"):
            rec = A.stake_for(r["pct"], c["legs"]) if A.CFG.get("size_auto") else None
            if own is None and rec and abs(rec - r["stake"]) > 0.01:
                r2 = A.get_offer(i, amount=rec)
                if not r2.get("error"):
                    r = r2
        r = dict(r, own=own is not None, min=A.OWN_MIN)
        if r.get("error"):
            return r
        r["rec"] = rec or A.CTX.get("stake")
        fair = r.get("fair", c.get("fair"))
        if fair:                                       # the books' chance of the combo (a pick under way: its live one)
            r["ev"] = round(r["pays"] * A.CTX.get("stake", A.CFG["stake"]) / fair - r["stake"], 2)
            r["ev_cal"] = combo_ev_cal(c, r)           # (#361) display only: `ev` above still drives rec / small
        if not r.get("ok") or r.get("ev") is None or r["ev"] <= 0:
            r["rec"], r["small"] = round(max(A.OWN_MIN, 2.0), 2), True   # (#358) no edge: never "recommended", the smallest bet
        try:
            r["room"] = round(max(0.0, A.CFG["budget"] - A.week_spend_shown()), 2)   # display only: the cap itself is
        except Exception:                              # get_offer's / accept_offer's own fresh check
            r["room"] = None
        r["max"] = min(A.OWN_MAX, r["room"]) if r["room"] is not None else A.OWN_MAX
        ov = overlap_warn(c.get("legs") or [])         # display only: the price, the Buy and its checks are unchanged
        if ov:
            r["overlap"] = ov[0]["t"]
            r["warn"] = list(r.get("warn") or []) + ov
        return r

    def overlap_warn(legs):
        """The quote's "you already have bets on this game" line, as a warn entry ([] when none). Never raises."""
        try:
            t = A.overlap_note(legs)
        except Exception:
            t = None
        return [{"k": "overlap", "t": t}] if t else []

    REPRICE_AT = {}        # (#358) a Skipped / Didn't buy card's last fresh price, by panel id: one per REPRICE_SECS
    REPRICE_SECS = 8
    IDEA_Q = {}            # Live single-game ideas: the size and price the Mac quoted, by idea id (Buy must match)
    IDEA_Q_SECS = 25       # the card's price lasts 20 s; a little slack for the tap to arrive

    class tap_mark:
        """While a tap is placing an order: a mark the watcher's update loop reads (it installs only after), so an
        update never restarts the web app mid-order."""
        def __init__(self, on=True):
            self.on = on

        def __enter__(self):
            if self.on:
                try:
                    A.save_json(TAP_BUSY, {"at": time.time(), "pid": os.getpid()})
                except Exception:
                    pass
            return self

        def __exit__(self, *exc):
            if self.on:
                try:
                    os.remove(TAP_BUSY)
                except OSError:
                    pass
            return False

    SHUT = {"on": False}

    def idea_act(a, d, t):
        """Live Buy ideas, no orders: hide ideas (X, swipe, Not now, Clear all, a bought one), bring them back (Undo,
        'show them again'), and a read of the order book for the detail page (only a market that is in an idea on the
        list). Not a money action: no app lock, no Pause check, nothing is priced or bought here."""
        ok_id = lambda i: isinstance(i, str) and re.fullmatch(r"i[0-9a-f]{12}", i)
        ids = [i for i in (d.get("ids") or []) if ok_id(i)][:40] if isinstance(d.get("ids"), list) else []
        try:
            if a == "idea_dismiss":
                seen = d.get("seen") if isinstance(d.get("seen"), dict) else {}
                r = A.idea_dismiss(ids, everything=d.get("all") is True, bought=d.get("why") == "bought",
                                   seen={k: v for k, v in list(seen.items())[:40] if k in ids})
                return {"ok": True, "n": r["n"], "ids": r["ids"]}
            if a == "idea_undo":
                r = A.idea_undismiss(ids, everything=d.get("all") is True)
                return {"ok": True, "n": r["n"]}
            tk = t if re.fullmatch(r"[A-Z0-9._-]{3,120}", t) else ""
            if not tk or not any(tk in (x.get("legs") or []) for x in A.live_ideas()):
                return {"ok": False, "msg": "That market isn't in an idea right now."}
            dpt = A.book_depth(tk)                      # Kalshi's public order book, cached for a minute
            if not dpt:
                return {"ok": False, "msg": "Couldn't read Kalshi's book just now."}
            return jsonable({"ok": True, **{k: dpt.get(k) for k in ("bid", "ask", "spread", "ask_size", "thin")}})
        except Exception as err:
            log("idea action failed:", a, type(err).__name__, err)
            return {"ok": False, "msg": "Couldn't do that just now. Try again."}

    def api_act(d):
        if SHUT["on"] or restarting():
            msg = "The Mac is restarting. Nothing was done; try again in a moment."
            return {"ok": False, "msg": msg, "error": msg, "busy": True}
        try:
            A.refusal_take()                                # this thread's last Kalshi refusal belongs to this tap only
            with A.manual_tap():                            # Pete's own tap: not held by a region hold, and it renews one (#134)
                r = _api_act(d)
            ref = A.refusal_take()
            if ref and isinstance(r, dict) and (r.get("error") or r.get("ok") is False):
                r = dict(r, refusal=ref)                    # Kalshi's own words, in full, for the page (#134)
            return r
        except ActBusy:
            msg = "The app is busy updating. Nothing was done; try again in a moment."
            log("tap waited too long for the app lock:", str(d.get("a", ""))[:20])
            return {"ok": False, "msg": msg, "error": msg, "busy": True}

    def _api_act(d):
        a, t = str(d.get("a", "")), str(d.get("t", ""))
        was = BUILD.get("lg") or BUILD.get("last")
        if a in ("custom", "quote", "buy", "swap", "flip", "longshot") and not A.CTX.get("all_games") and was:
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
        if a in ("idea_dismiss", "idea_undo", "idea_depth"):    # Live Buy ideas: hide / bring back / a look at the book (no orders)
            return idea_act(a, d, t)
        if a == "panel_whatif":                     # reads only, no app lock: the card's numbers at Pete's own amounts
            ids = d.get("ids")
            try:
                return jsonable(A.panel_whatif(str(d.get("view") or "all")[:20],
                                               [str(x) for x in ids][:60] if isinstance(ids, list) else None,
                                               d.get("stakes")))
            except Exception as err:
                log("panel what-if failed:", type(err).__name__, err)
                return {"ok": False, "msg": "Couldn't work that out just now."}
        with act_lock():
            if a in ("ask", "askhalf", "go", "keep", "hedgego"):
                if t not in (A.MINE.get("hold") or {}):
                    return {"ok": False, "msg": "That combo isn't live any more."}
                with tap_mark(a in ("go", "hedgego")), (A.manual_sell_mark(t) if a == "go" else nullcontext()):   # (#400) the auto seller skips it
                    A.cash_action("drop" if a == "keep" else a, t)
                LIVE["at"] = 0
                o = A.MINE["cash"].get(t) or {}
                flash = A.MINE.pop("flash", None)
                msg = A.re.sub("<[^>]+>", "", flash or "") or (o.get("error") or "")
                return {"ok": not o.get("error"), "msg": msg, "offer": o.get("offer"), "frac": o.get("frac", 1.0)}
            if a == "longshot" and paused_now():           # (#341) a long shot's price: refused while paused, as quotes
                return {"ok": False, "paused": True, "msg": A.PAUSE_MSG, "error": A.PAUSE_MSG}
            if a in ("quote", "idea", "buy") and paused_now():
                return {"ok": False, "paused": True, "msg": A.PAUSE_MSG, "error": A.PAUSE_MSG}
            if a == "panel_reprice" and paused_now():       # (#358) a fresh price for a panel card: refused while paused
                return {"ok": False, "paused": True, "msg": A.PAUSE_MSG, "error": A.PAUSE_MSG}
            if a == "longshot":                         # (#341) a long shot on screen into the combo list, then its price
                lg = BUILD.get("lg")
                rec = next((r for r in (LS.get(lg) or {}).get("recs") or [] if r["id"] == str(d.get("id", ""))), None)
                shown = d.get("legs")
                if not rec or not isinstance(shown, list) or sorted(map(str, shown)) != sorted(l["ticker"] for l in rec["legs"]):
                    return {"ok": False, "error": "That long shot has changed. Pull down to reload Build, then try again."}
                pool = {x["ticker"]: x for sd in (A.CTX.get("all_games") or {}).values() for x in sd}
                legs = []
                for l in rec["legs"]:                   # each pick again on the board's fresh prices, as the Mac chose it
                    x = pool.get(l["ticker"])
                    f, _how = A.longshot_leg_fair(x) if x else (None, "gone")
                    if f is None or not A.LONGSHOT["leg_lo"] <= f <= A.LONGSHOT["leg_hi"]:
                        return {"ok": False, "error": f"{l.get('pick') or 'A pick'} isn't a long-shot pick any more (its game "
                                                      "is close to starting or its price moved). Pull down to reload Build."}
                    legs.append(dict(x, fair=f, fair_book=x.get("fair")))
                st = A.CTX.get("stake") or A.CFG["stake"]
                fair_pay = st / A.math.prod(x["fair"] for x in legs)
                new = {"kind": "longshot", "tier": "Long shot", "legs": legs, "fair": fair_pay,
                       "min": fair_pay * A.CFG["accept_pct"] / 100, "ls_stake": rec["stake"],
                       "kalshi": st / A.math.prod(x["p"] for x in legs)}
                combos = A.CTX.setdefault("combos", [])
                key = frozenset(l["ticker"] for l in rec["legs"])
                i = next((k for k, c in enumerate(combos, 1) if c.get("kind") == "longshot" and legset(c) == key), 0)
                if i:
                    combos[i - 1] = new                 # today's chance and stake, never an older one
                    A.CTX.get("offers", {}).pop(i, None)
                else:
                    combos.append(new)
                    i = len(combos)
                own, bad = A.own_stake(d.get("stake"))
                if bad:
                    return {"ok": False, "error": bad, "bad_stake": True}
                try:
                    r = combo_offer(i, own)
                except (RuntimeError, PermissionError) as err:
                    return {"ok": False, "error": str(err).replace(" Try Swap.", "")}
                return jsonable({"ok": not r.get("error"), "i": i, "clears": r.get("ok"), "cut": 100,
                                 **{k: r.get(k) for k in ("pays", "stake", "pct", "error", "check", "rec", "ev", "ev_cal", "room",
                                                          "max", "min", "own")}})
            if a == "quote":
                i = int(d.get("i", 0))
                shown = d.get("legs")
                cur = (A.CTX.get("combos") or [])[i - 1] if 1 <= i <= len(A.CTX.get("combos") or []) else None
                if shown is not None and (not cur or sorted(map(str, shown)) != sorted(l["ticker"] for l in cur["legs"])):
                    return {"ok": False, "error": "The board was refreshed with new combos. Pull down to reload Build, then try again."}
                own, bad = A.own_stake(d.get("stake"))   # Pete's own amount (#145), checked here, never the page's word
                if bad:
                    return {"ok": False, "error": bad, "bad_stake": True}
                try:
                    r = combo_offer(i, own)
                except (RuntimeError, PermissionError) as err:
                    return {"ok": False, "error": str(err).replace(" Try Swap.", "")}
                return jsonable({"ok": not r.get("error"), "clears": r.get("ok"), "cut": r.get("bar") or A.CFG["accept_pct"],
                                 **{k: r.get(k) for k in ("pays", "stake", "pct", "error", "check", "rec", "ev", "ev_cal", "room",
                                                          "max", "min", "own", "why", "nofair", "live", "small", "overlap", "warn")}})
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
                    if not dpt or dpt.get("ask") is None:
                        return {"ok": False, "gone": True, "msg": "Kalshi isn't listing that game right now."}
                    # the fair chance (#255): before the game the board's (spreads/totals: the model's), as before; a
                    # game under way only a live one (a fresh live line, else the live model), never the board's number
                    fi = A.idea_single_fair(tk, side, row.get("pfair"), dpt, kick=row.get("kick"),
                                            row_live=bool(row.get("live")))
                    if fi["over"]:
                        return {"ok": False, "gone": True, "msg": "That game is over. Kalshi settles it when the result is in."}
                    fair = fi["fair"]
                    if fair is None and fi["live"]:      # (#255) say why: this card shows Kalshi's price only, a manual tap
                        log(f"idea {str(d.get('id', ''))[:12]} {tk}: no live fair price ({fi['nofair'] or 'none'}); "
                            "card shows Kalshi's price only, no edge claimed")
                    if fair is None and not fi["live"]:
                        return {"ok": False, "gone": True, "msg": "Kalshi isn't listing that game right now."}
                    own, bad = A.own_stake(d.get("stake"))   # Pete's own amount (#145), checked here
                    if bad:
                        return {"ok": False, "msg": bad, "bad_stake": True}
                    ask = dpt["ask"]
                    fee = A.single_fee(ask)
                    edge = fair - ask - fee if fair is not None else None
                    pct = (fair / (ask + fee) if ask else 0) if fair is not None else None
                    rec = (A.edge_stake(pct, A.CFG.get("size_min", 3), A.CFG.get("size_max", 10), fair) if fair is not None else
                           max(A.OWN_MIN, 2.0))                # no fair price: Buy straight's smallest bet, no edge claimed
                    stake = own if own is not None else rec
                    n = int(stake / (ask + fee) + 1e-9) if own is not None else max(1, int(stake / (ask + fee)))
                    note = None
                    if dpt.get("ask_size") and n > int(dpt["ask_size"]):   # Kalshi's sizes can be fractional now ("0.40")
                        n = int(dpt["ask_size"])
                        note = f"Only {int(dpt['ask_size'])} contracts are for sale at {ask * 100:.0f}¢, so it buys {n}."
                    if n < 1:
                        return {"ok": False, "msg": (f"That's under one contract at {ask * 100:.0f}¢. Pick a bigger amount."
                                                     if own is not None and not note else
                                                     "Kalshi has under one contract for sale at that price right now.")}
                    if not A.can_trade():
                        return {"ok": False, "msg": A.NO_TRADE_MSG}
                    no, spent, budget = A.single_cap_block(tk, n * (ask + fee))   # its own league's cap; unreadable = refused
                    if no:
                        return {"ok": False, "msg": no, "capped": True}
                    cost = round(n * (ask + fee), 2)
                    for k in [k for k, v in IDEA_Q.items() if time.time() - v["at"] > IDEA_Q_SECS * 4]:
                        IDEA_Q.pop(k, None)
                    IDEA_Q[str(d.get("id", ""))] = {"n": n, "price": ask, "at": time.time(), "t": tk}   # what Buy may send
                    doubt = any(w["k"] in ("thin", "decided", "disagree") for w in fi["warn"])   # under way: as the panel
                    clears = fair is not None and edge >= A.SINGLE_MIN_EDGE * 0.6 and not (fi["live"] and doubt)
                    if clears and fi["live"]:               # (#341) under way: green only with a likely profitable exit
                        clears = A.live_exit_ok(tk, (side or {}).get("event") or tk.rsplit("-", 1)[0], fair, ask)
                    return jsonable({"ok": True, "single": True, "price": ask, "n": n, "stake": cost,
                                     "pays": float(n), "pct": pct, "edge": round(edge, 4) if edge is not None else None,
                                     "fair": fair, "clears": bool(clears), "rec": rec, "own": own is not None,
                                     "ev": round(n * fair - cost, 2) if fair is not None else None, "note": note, "min": A.OWN_MIN,
                                     "max": A.OWN_MAX, "live": fi["live"], "how": fi["how"], "fair_src": fi["src"],
                                     "nofair": fi["nofair"], "warn": fi["warn"] + overlap_warn([tk]),
                                     "room": round(max(0.0, budget - spent), 2) if spent is not None else None})
                if row["kick"] and row["kick"] < time.time() + 60:
                    return {"ok": False, "gone": True, "msg": "A game in it is starting, so this one's off the table."}
                if row.get("live") and row["ts"] < time.time() - 600:
                    return {"ok": False, "gone": True, "msg": "That idea had a game in progress and is more than 10 minutes old."}
                if BUILD.get("lg") != row["lg"]:
                    api_build(row["lg"], rebuild=True)
                own, bad = A.own_stake(d.get("stake"))   # Pete's own amount (#145), checked here
                if bad:
                    return {"ok": False, "msg": bad, "bad_stake": True}
                k, why = A.add_own_combo(json.loads(row["legs"]))
                if not k:
                    return {"ok": False, "gone": True, "msg": why or "Kalshi isn't listing those games any more."}
                c = (A.CTX.get("combos") or [])[k - 1] if 1 <= k <= len(A.CTX.get("combos") or []) else {}
                gap = A.idea_combo_live_gap(c.get("legs"))   # #255: a game under way the board only has pre-game for
                small = None
                if gap and own is None:                 # no fair price: priced at the smallest usual stake, never
                    small = round(max(A.OWN_MIN, 2.0), 2)   # sized on a pre-game or stale edge (Buy straight's $2)
                try:
                    r = combo_offer(k, own if small is None else small)
                except (RuntimeError, PermissionError) as err:
                    return {"ok": False, "msg": str(err).replace(" Try Swap.", "")}
                if r.get("error"):
                    return {"ok": False, "msg": r["error"]}
                out = {"ok": True, "i": k, "legs": [l["ticker"] for l in c.get("legs") or []], "pays": r["pays"], "stake": r["stake"], "pct": r.get("pct"),
                       "clears": r.get("ok"), **{x: r.get(x) for x in ("rec", "ev", "room", "max", "min", "own", "small", "overlap", "warn")}}
                if gap:                                 # (#358) priced on the live chance when every live guard passes
                    out.update(live=True, fair_src="live" if r.get("fair") else "none",
                               **({"rec": small, "own": False, "small": True} if small is not None else {}))
                if gap and not r.get("fair"):           # no live fair price to check it against: yellow Buy anyway only
                    out.update(clears=False, pct=None, ev=None,
                               nofair=r.get("nofair") or
                               f"the {' and '.join(gap[:2])} game{'s have' if len(gap) > 1 else ' has'} started, "
                               "and a combo with a game under way has no live fair price")
                return jsonable(out)
            if a == "singlequote":                      # Buy straight: one team (or a spread/total), priced now
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t):
                    return {"ok": False, "msg": "That market isn't recognized."}
                lg = str(d.get("lg") or A.ticker_sport(t) or "")
                return jsonable(A.single_buy_quote(single_side(t, lg), d.get("stake"), paused=paused_now()))
            if a == "singlebuy" and d.get("q"):          # Buy straight: the quote on screen, once
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t) or not re.fullmatch(r"[0-9a-f]{16}", str(d.get("q"))):
                    return {"ok": False, "msg": "That price isn't recognized. Get a fresh one."}
                with tap_mark():
                    r = A.single_buy(str(d["q"]), t, anyway=bool(d.get("anyway")), paused=paused_now(), log=log)
                LIVE["at"] = 0
                if not r.get("ok") and not r.get("check") and "market's pot has" in str(r.get("msg") or ""):
                    r = dict(r, pot=pot_plan(t, r.get("msg"), d.get("cost")))   # offer a move (a refusal: nothing bought)
                return jsonable(r)
            if a == "sellquote":                        # Sell a single (issue #238): what it gets now, from a fresh book
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t):
                    return {"ok": False, "msg": "That bet isn't recognized."}
                if backup_now():                        # the Pi never trades (Pause no longer stops this tap: #245)
                    return {"ok": False, "msg": A.NO_SELL_MSG}
                return jsonable(A.single_sell_quote(t, paused=paused_now()))   # Pause only adds the calm note
            if a == "singlesell":                       # Pete's second tap on the sell sheet: the quote on screen, once
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t) or not re.fullmatch(r"[0-9a-f]{16}", str(d.get("q") or "")):
                    return {"ok": False, "msg": "That price isn't recognized. Get a fresh one."}
                if backup_now():                        # the Pi never trades; Pause doesn't block Pete's own sale (#245)
                    return {"ok": False, "msg": A.NO_SELL_MSG}
                with tap_mark(), A.manual_sell_mark(t):   # an update never restarts the web app mid-order; auto sells skip it (#400)
                    r = A.single_sell(str(d["q"]), t, anyway=d.get("anyway") is True, paused=paused_now, log=log)
                LIVE["at"] = 0
                return jsonable(r)
            if a == "singlebuy":
                rows = A.store_rows("select legs from suggestions where id=? and n=1", (str(d.get("id", "")),))
                if not rows:
                    return {"ok": False, "msg": "That idea has expired."}
                try:
                    n, price = int(d.get("n") or 0), float(d.get("price") or 0)
                except (TypeError, ValueError):
                    n, price = 0, 0.0
                iq = IDEA_Q.get(str(d.get("id", ""))) or {}   # the size and price the Mac itself quoted (never the page's)
                if (not iq or time.time() - iq["at"] > IDEA_Q_SECS or iq["n"] != n or abs(iq["price"] - price) > 1e-9):
                    return {"ok": False, "expired": True, "msg": "That price isn't the one the Mac gave you any more. "
                                                                  "Get today's price again."}
                if not 1 <= n <= 1000 or not 0.01 <= price <= 0.97 or n * (price + A.single_fee(price)) > A.OWN_MAX + 0.01:
                    return {"ok": False, "msg": "That size or price isn't allowed."}
                tk = str(json.loads(rows[0]["legs"])[0])
                if tk != iq.get("t"):
                    return {"ok": False, "msg": "That market isn't recognized."}
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", tk):
                    return {"ok": False, "msg": "That market isn't recognized."}
                # Pause, trading access, the unknown-outcome block and the market's own league cap, then one order
                with tap_mark():                        # an update never restarts the web app mid-order
                    r = A.idea_single_buy(tk, n, price, paused=paused_now(), log=log, key=str(d.get("id", "")))
                LIVE["at"] = 0
                return jsonable(r)
            if a == "buy":
                i = int(d.get("i", 0))
                shown = d.get("legs")                   # rule 7 (#203): the Mac re-checks them against the offer and the combo
                shown = [str(x) for x in shown] if isinstance(shown, list) else []   # none sent = still checked offer vs card
                print(f"buy combo {i}: accepting Kalshi's quote", flush=True)
                try:
                    with tap_mark():
                        r = A.accept_offer(i, expect_legs=shown)
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    if A.order_outcome(err) == "refused":       # a definite refusal: nothing was bought
                        r = {"error": A.order_words(err)}
                    else:                                       # unexpected: it may have gone out, so never "nothing"
                        r = {"error": f"Something went wrong ({type(err).__name__}). It may or may not have been "
                                      "bought: check Kalshi before trying again.", "check": True}
                print(f"buy combo {i}:", r, flush=True)
                LIVE["at"] = 0
                if (not r.get("error") or r.get("check")) and 1 <= i <= len(A.CTX.get("combos") or []):
                    BUILD.setdefault("bought", set()).add(legset(A.CTX["combos"][i - 1]))   # never offered again here
                    try:                                # a Buy idea for these picks stays off the list too (#270)
                        A.idea_mark_bought([l["ticker"] for l in A.CTX["combos"][i - 1].get("legs") or [] if l.get("ticker")])
                    except Exception:
                        pass
                return jsonable({"ok": not r.get("error"), "msg": r.get("error") or "Bought.", "pays": r.get("pays"),
                                 "check": bool(r.get("check"))})
            if a == "panel_reprice":                # (#358) a Skipped / Didn't buy card: where it would land now (reads only)
                pid = str(d.get("id") or "")[:120]
                last = REPRICE_AT.get(pid, 0)
                if time.time() - last < REPRICE_SECS:
                    return {"ok": False, "msg": "Just priced. Give it a few seconds."}
                for k in [k for k, v in REPRICE_AT.items() if time.time() - v > 60]:
                    REPRICE_AT.pop(k, None)
                REPRICE_AT[pid] = time.time()
                try:
                    return jsonable(A.panel_reprice(pid, paused=paused_now()))
                except Exception as err:
                    log("panel reprice failed:", type(err).__name__, err)
                    return {"ok": False, "msg": "Couldn't get a fresh price just now. Try again in a minute."}
            if a == "panel_approve":
                ok, msg = A.panel_approve(d.get("ids"), d.get("view") or "all", d.get("at"), stakes=d.get("stakes"))
                return {"ok": ok, "msg": msg}
            if a == "clear_block":                  # Pete lifts an "unknown outcome" block after checking Kalshi
                key = str(d.get("key", ""))[:200]
                if not A.clear_order_block(key):
                    return {"ok": False, "msg": "That block has already ended."}
                log("order block cleared from Settings:", key)
                return {"ok": True, "msg": "Cleared. New orders on that market can go again; the unclear one is never resent."}
            if a == "pot_quote":                    # the move sheet's numbers (reads only)
                return jsonable(A.pot_transfer_quote(d.get("from"), d.get("to"), str(d.get("amount", ""))[:12]))
            if a == "pot_move":                     # Pete's second tap on the move sheet: one move, never automatic
                with tap_mark():                    # an update never restarts the web app mid-move
                    r = A.pot_transfer(d.get("from"), d.get("to"), str(d.get("amount", ""))[:12],
                                       cid=str(d.get("cid") or "")[:40], paused=paused_now())
                log("pot move from the app:", r.get("status") or ("refused" if not r.get("check") else "check"))
                return jsonable(r)
            if a == "pot_clear":                    # Pete clears an open move after checking Kalshi
                if not A.pot_clear(str(d.get("cid", ""))[:40]):
                    return {"ok": False, "msg": "That move isn't open any more."}
                log("pot move cleared from Settings")
                return {"ok": True, "msg": "Cleared. Moves between pots can go again; the unclear one is never resent."}
            if a == "skim_moved":
                amt = A.skim_moved()
                return {"ok": True, "msg": f"Got it. The app counts your whole Kalshi balance again ({A.money(amt)} was set aside)."}
            if a == "panel_add":
                ids, left = d.get("ids") or [], []
                if (d.get("view") or "") == "extra":     # an extra on a greyed game only with Pete's own Add anyway
                    ids, left, unread = overlap_extra_ids(ids, d.get("allow"))
                    if unread:
                        return {"ok": False, "msg": "Couldn't check your open bets on those games. Try again in a minute."}
                    if left and not ids:
                        return {"ok": False, "msg": "You already have enough on those games. Tap Add anyway on one first."}
                ok, msg = A.panel_add(ids, d.get("view") or "", stakes=d.get("stakes"))
                if left:
                    msg = f"{msg} Left out {len(left)} on games you already have enough on."
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
                v = combo_view(i, A.CTX["combos"][i - 1])
                v["over"] = combo_over(A.CTX["combos"][i - 1].get("legs"), d.get("allow"))
                return jsonable({"ok": True, "verdict": verdict, "text": text, "combo": v})
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
                v = combo_view(i, pick)
                v["over"] = combo_over(pick.get("legs"), d.get("allow"))
                return jsonable({"ok": True, "combo": v})
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
                return self._send(200, SPA.replace("__CWLOCAL__", "true" if local else "false")
                                  .replace("__CWVER__", str(getattr(A, "VERSION", "") or "")), "text/html; charset=utf-8")
            if path.startswith("/app/api/"):
                from urllib.parse import parse_qs
                q = {k: v[0] for k, v in parse_qs(query).items()}
                try:
                    if path == "/app/api/live":
                        out = overlap_live(api_live(fresh=q.get("fresh") == "1"), q.get("allow"))
                    elif path == "/app/api/build":
                        lg = q.get("lg") or "nba"
                        out = api_build(lg if lg in A.LEAGUES else "nba", rebuild=q.get("fresh") == "1",
                                        allow=A.overlap_allow(q.get("allow")))
                    elif path == "/app/api/results":
                        out = api_results()
                    elif path == "/app/api/analytics":
                        out = jsonable(A.analytics()) if A.STORE.get("db") else {}
                        if isinstance(out, dict) and isinstance(out.get("smart_buy"), dict):
                            on = A.smart_buy_on()                  # the switch, read now (analytics is cached 10 min)
                            sb = out["smart_buy"]
                            if on and "rows" not in sb:            # switched on since the cache was built
                                try:
                                    sb = jsonable(dict(A.smart_buy_summary(), gate=A.smart_buy_gate_summary()))
                                except Exception as err:
                                    log("smart buy summary:", type(err).__name__, err)
                            out["smart_buy"] = dict(sb, on=on)
                    elif path == "/app/api/recap":
                        out = jsonable(A.recap()) if A.STORE.get("db") else {}
                    elif path == "/app/api/panel":
                        out = overlap_panel(api_panel(q.get("v") or "all"), q.get("allow"))
                    elif path == "/app/api/orders":
                        out = api_orders()
                    elif path == "/app/api/closed":
                        out = api_closed(q.get("t") or "")
                    elif path == "/app/api/combo":
                        out = api_combo(q.get("t") or "")
                    elif path == "/app/api/game":
                        out = api_game(q.get("t") or "")
                    elif path == "/app/api/game_warm":
                        out = api_game_warm(q.get("t") or "")
                    elif path == "/app/api/games":
                        out = api_games()
                    elif path == "/app/api/ver":            # read-only: the running version (a parked page checks it, #150)
                        out = {"ok": True, "ver": str(getattr(A, "VERSION", "") or "")}
                    elif path == "/app/api/pulse":          # read-only: the hero chart's Week range (pulse keeps 30 days)
                        try:
                            h = max(1, min(720, int(q.get("h") or 16)))
                        except ValueError:
                            h = 16
                        db = A.STORE.get("db")
                        out = {"h": h, "pulse": A.pulse_series(hours=h, points=200) if db else [],
                               "pnl": A.pnl_series(hours=h, points=200) if db else None}
                    elif path == "/app/api/settings":
                        out = api_settings(q.get("lg") or "")
                    else:
                        return self._send(404, "{}")
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    out = {"error": f"{type(err).__name__}: {err}"}
                if isinstance(out, dict) and path in ("/app/api/live", "/app/api/build", "/app/api/settings", "/app/api/panel"):
                    try:                                    # Kalshi's refusals (issue #134): the page shows a calm banner
                        out = dict(out, restrict=A.restriction_info())
                    except Exception as err:
                        log("restriction info:", type(err).__name__, err)
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
                SHUT["on"] = True                   # no new taps from here on
                got = alock.acquire(timeout=120)    # a tap mid-order finishes first (bounded), then exit
                log("web app exiting after the watcher restarted" + ("" if got else " (a tap was still running)"))
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
            if not LIVE.get("busy") and (time.time() - LIVE["at"] > pace or asked and live_moved()):
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
                        cur, saved, was_at = BUILD.get("lg"), dict(A.CTX), BUILD.get("at")
                        try:
                            api_build(lg, rebuild=True, warming=True)
                        finally:
                            if cur and cur != lg:              # put back what you were looking at
                                A.set_league(cur)
                                A.CTX.clear()
                                A.CTX.update(saved)
                                s = SNAP.get(cur)
                                if s:
                                    BUILD.update(lg=cur, note=s["note"], days=s["days"], lines=s["lines"],
                                                 lines_priced=s.get("lines_priced") or 0,
                                                 lines_nobook=s.get("lines_nobook") or 0)
                                BUILD["at"] = was_at            # the restored board's own age (Buy straight reads it)
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


def odds_info(E):
    """Settings › The Mac: the odds service's credits as last seen (read from the answers we already got; no call).
    None when there's no key or nothing recorded yet. Only numbers and flags: never the key."""
    try:
        if not E or not (getattr(E, "CFG", {}) or {}).get("odds_key"):
            return None
        c = E.odds_credits()
        return {k: c.get(k) for k in ("remaining", "used", "last", "at", "per_day", "runs_out", "reset", "reset_guess",
                                      "low", "why", "saving")} if c else {"none": True}
    except Exception as err:
        log("odds credits unreadable:", type(err).__name__, err)
        return None


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
                "log": tail, "odds": odds_info(E), "logs": log_status(conf)}
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
             click="/", web=False)
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
    if a == "logaccess":                                    # dev Mac log reading (issue #377): on = a new code
        return log_access_set(conf, E, bool(d.get("on")))
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
    act = method == "POST" and path.split("?")[0] == "/app/api/act"
    try:
        with urllib.request.urlopen(req, timeout=PROXY_ACT_TIMEOUT if act else 40) as r:
            code, ctype, data = r.status, r.headers.get("Content-Type", "application/json"), r.read()
            where = r.headers.get("X-CW-Where") or ""
    except urllib.error.HTTPError as err:
        code, ctype, data = err.code, "application/json", b"{}"
    except (urllib.error.URLError, OSError) as err:
        refused = isinstance(getattr(err, "reason", err), ConnectionRefusedError)   # nothing reached the web app
        if act:                                     # a tap: maybe mid-order, so never a reload page
            code, ctype = (503, "application/json") if refused else (504, "application/json")
            try:
                order = str((json.loads(body or b"{}") or {}).get("a", "")) in ORDER_ACTS
            except (ValueError, AttributeError):
                order = True
            msg = ("The planner is starting on your Mac, so nothing was done. Try again in a moment." if refused else
                   "This may or may not have gone through: check Kalshi before trying again." if order else
                   "Your Mac took too long to answer. Pull to refresh to see whether it went through.")
            data = json.dumps({"ok": False, "msg": msg, "error": msg, "check": order and not refused}).encode()
            log("tap proxy:", "web app not running" if refused else f"no answer in {PROXY_ACT_TIMEOUT}s",
                f"({type(err).__name__})")
            return _proxy_send(handler, code, ctype, data, where)
        code, ctype = 503, "text/html; charset=utf-8"
        data = (b"<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'>"
                b"<body style='font:17px -apple-system;padding:40px'>The planner is starting on your Mac. "
                b"<script>setTimeout(function(){location.reload()},3000)</script>")
    if ctype.startswith("text/html"):
        data = data.replace(b"__CWTOK__", tok.encode())
    _proxy_send(handler, code, ctype, data, where)


PROXY_ACT_TIMEOUT = 300       # a tap: 20 s for the lock, then a combo buy (40 s accept + 15 s confirm) or a cash-out
#                               with up to 4 offers (each a quote, a 40 s accept and a 15 s confirm)
ORDER_ACTS = ("buy", "go", "hedgego", "singlebuy", "singlesell", "pot_move")   # taps that can move money (the rest only read)


def _proxy_send(handler, code, ctype, data, where=""):
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


# ---------------------------------------------------------------- dev Mac log reading (issue #377, docs/LOG_ACCESS.md)
# A read-only, redacted tail of this Mac's logs for the dev Mac, over Tailscale only. Off until Pete turns on
# Settings › This Mac › "Let the dev Mac read logs" on this Mac itself, which makes a read-only code (only its SHA-256
# is kept, in watcher.json). It never takes a lock, never changes anything and never reads anything but the two files
# below. Every answer is redacted here, before it leaves, and any error in that means nothing is sent (fail closed).
LOG_PATH = "/api/logs"
LOG_SOURCES = {"console": "watcher.log", "autosell": "combo_autosell_log.jsonl"}   # the only files it ever reads
LOG_DEF_LINES, LOG_MAX_LINES, LOG_MAX_BYTES = 200, 500, 200_000                   # per answer, after redaction
LOG_READ_BYTES = 1_500_000      # the most read from the end of a file per answer (never the whole file)
LOG_LINE_MAX = 2000             # characters kept of one line
LOG_RATE = (30, 60)             # answers per client per minute
LOG_BAD = (5, 600)              # wrong codes per client per 10 minutes before that client is turned away
LOG_BAD_ALL = (30, 600)         # wrong codes from everyone per 10 minutes before everyone is turned away
LOG_SECRET_MIN = 6              # live secret values this long or longer are masked wherever they appear
LOG_FIELDS = frozenset((        # the auto cash-out log's fields that are sent (anything else is dropped)
    "at", "when", "by", "ride", "result", "why", "note", "guard", "combo", "ticker", "kind", "side", "cost", "offer",
    "pays", "chance", "p", "frac", "live", "ask", "bid", "cut_off", "contracts", "count", "sold", "price", "league",
    "sport", "game", "score", "plan", "route", "ev", "hold", "expect", "err", "error", "msg", "reason", "legs", "leg",
    "wait", "stage", "mode", "slip", "thr", "value", "profit", "pnl", "fee", "fees", "version", "n", "rfq", "mins",
    "clock", "period", "lead", "need", "won", "left", "est", "disc", "learned", "knob", "band", "hedge", "stop_loss", "sl_mode"))
LOG_PUBLIC_HOSTS = ("kalshi.com", "espn.com", "github.com", "githubusercontent.com", "the-odds-api.com",
                    "polymarket.com", "hockeytech.com", "theahl.com")
LOG_STATE = {"read": 0}         # when the dev Mac last read the logs (shown in Settings)
_LOG_SALT = os.urandom(16)      # per process: an id is shown as a short tag, the same within one run


def _log_finite(x):
    return x == x and abs(x) != float("inf")


class LogLeak(Exception):
    """A redacted answer still held a live secret: nothing is sent."""


_LOG_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ")
_LOG_SELL = re.compile(r"^(.*?auto cash-out: )(\{.*)$")
_RX_PEM = re.compile(r"(?i)-----BEGIN[^\n]*?-----.*?(?:-----END[^\n]*?-----|\Z)", re.S)
_RX_HDR = re.compile(r"(?i)\b(proxy-authorization|authorization|x-cw|set-cookie|cookie|kalshi-access-key|"
                     r"kalshi-access-signature|x-api-key)([\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\r\n,;}]+)")
_RX_BEARER = re.compile(r"(?i)\b(bearer(?=\s+\S)|basic(?=\s+\S{6}))(\s+)[A-Za-z0-9._~+/=-]+")
_RX_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{2,}")
_RX_CWCOOKIE = re.compile(r"(?i)(?<![A-Za-z0-9_-])(cw)(\s*[:=]\s*)[^\s,;&\"']+")
_RX_KV = re.compile(r"(?i)(\\?[\"']?)(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{0,40}?(?:secret|token|passw(?:or)?d|passcode|web_pass|api[ _-]?key|apikey|"
                    r"key[ _-]?id|odds_key|private[ _-]?key|signature|session|cookie|topic|endpoint|p256dh|auth_?key|"
                    r"member[ _-]?id|user[ _-]?id|account[ _-]?id|subaccount|e-?mail|watcher_code|pairing|passkey|credential)"
                    r"[A-Za-z0-9_-]{0,40})\1(\s*[:=]\s*)(\\\"[^\"\\]*\\\"|\"(?:[^\"\\]|\\.)*\"|'[^']*'|\[[a-z: -]+\]|[^\s,;&}\])]+)")
_RX_KVSP = re.compile(r"(?i)\b(api[ _-]?key|key[ _-]?id|(?:user|member|account)[ _-]?id)(\s+)(?!\[)([A-Za-z0-9_-]{3,})")
_RX_URL = re.compile(r"(?i)\b(?:https?|wss?)://[^\s\"'<>\\]+")
_RX_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,8}")
_RX_TSNET = re.compile(r"(?i)(?<![a-z0-9.-])[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){0,6}\.(?:ts|tailscale)\.net\b")
_RX_IP4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\d)(?!\.\d)")
_RX_IP6 = re.compile(r"(?i)(?<![0-9a-z:])(?:(?:[0-9a-f]{1,4}:){5,7}[0-9a-f]{1,4}|"
                     r"(?:[0-9a-f]{1,4}:){1,6}:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,5})?)(?![0-9a-z:])")
_RX_UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_RX_HOMEDIR = re.compile(r"/(Users|home)/[^/\s\"':]+")
_RX_BLOB = re.compile(r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{32,}")
_RX_MONEYLINE = re.compile(r"(?i)(?<!insufficient_)(?<!insufficient )balance|by pot|\bpots?\b|bankroll|portfolio_value")
_RX_DOLLARS = re.compile(r"\$\s?-?[\d,]+(?:\.\d+)?")
_RX_BALNUM = re.compile(r"(?i)(balance[a-z_]*[\"']?\s*[:=]\s*)-?[\d.,]+")
_RX_CTRL = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u2060\ufeff]")


def log_enabled(conf):
    """On only when Pete turned it on and a code's hash is stored."""
    la = conf.get("log_access") if isinstance(conf, dict) else None
    return isinstance(la, dict) and la.get("on") is True and bool(re.fullmatch(r"[0-9a-f]{64}", str(la.get("hash") or "")))


def log_client_ok(ip, headers):
    """Only the tailnet: a Tailscale address, Tailscale's own https front door with a signed-in person, or this Mac
    itself. The home network and anything forwarded without a Tailscale identity (e.g. Funnel) are refused."""
    import ipaddress
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    if headers.get("Tailscale-Funnel-Request"):
        return False
    if a.is_loopback:
        fwd = headers.get("X-Forwarded-For") or headers.get("Forwarded") or headers.get("X-Forwarded-Host")
        return not fwd or bool(headers.get("Tailscale-User-Login"))
    return any(a in ipaddress.ip_network(n) for n in ("100.64.0.0/10", "fd7a:115c:a1e0::/48")
               if ipaddress.ip_network(n).version == a.version)


def log_token_ok(conf, auth):
    """Constant-time check of `Authorization: Bearer <code>` against the stored hash."""
    want = str(((conf.get("log_access") or {}).get("hash")) or "")
    m = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{20,200})", str(auth or "").strip())
    got = hashlib.sha256((m.group(1) if m else "-").encode()).hexdigest()
    return hmac.compare_digest(got.encode(), want.encode().ljust(64, b"-")[:64]) and bool(m) and len(want) == 64


def log_new_token(conf):
    """Turn log reading on with a fresh code (the old one stops working). Returns the code; only its hash is kept."""
    import secrets
    tok = secrets.token_urlsafe(32)
    conf["log_access"] = {"on": True, "hash": hashlib.sha256(tok.encode()).hexdigest(), "at": int(time.time())}
    return tok


class LogGate:
    """Rate limits: LOG_RATE answers per client, and wrong codes (per client and from everyone)."""

    def __init__(self):
        self.lock, self.hits, self.bad, self.bad_all = threading.Lock(), {}, {}, []

    @staticmethod
    def _recent(lst, win, now):
        return [t for t in lst if now - t < win]

    def allow(self, ip, now=None):
        now = now or time.time()
        with self.lock:
            if len(self.hits) > 500:
                self.hits = {k: v for k, v in self.hits.items() if self._recent(v, LOG_RATE[1], now)}
                self.bad = {k: v for k, v in self.bad.items() if self._recent(v, LOG_BAD[1], now)}
            self.bad_all = self._recent(self.bad_all, LOG_BAD_ALL[1], now)
            b = self.bad[ip] = self._recent(self.bad.get(ip, []), LOG_BAD[1], now)
            if len(b) >= LOG_BAD[0] or len(self.bad_all) >= LOG_BAD_ALL[0]:
                return False
            h = self.hits[ip] = self._recent(self.hits.get(ip, []), LOG_RATE[1], now)
            if len(h) >= LOG_RATE[0]:
                return False
            h.append(now)
            return True

    def wrong(self, ip, now=None):
        now = now or time.time()
        with self.lock:
            self.bad.setdefault(ip, []).append(now)
            self.bad_all.append(now)
            n = len(self.bad_all)
        if n in (LOG_BAD_ALL[0] // 2, LOG_BAD_ALL[0]):
            log(f"dev Mac log reading: {n} wrong codes in 10 minutes")


LOG_GATE = LogGate()


def log_secrets(conf, E=None):
    """The live secret values on this Mac, to mask wherever they appear (raises if they can't be read)."""
    from urllib.parse import quote, urlsplit
    vals = [conf.get(k) for k in ("topic", "secret", "web_pass", "passkey_user", "healthcheck_url")]
    vals += [p.get("id") for p in conf.get("passkeys") or [] if isinstance(p, dict)]
    host = urlsplit(str((conf.get("https") or {}).get("url") or "")).hostname or ""
    vals += [host] + host.split(".")[:2]                       # the machine and tailnet names on their own too
    cfg = getattr(E, "CFG", None) or {}
    vals += [cfg.get(k) for k in getattr(E, "KEY_FIELDS", ("kalshi_key_id", "odds_key", "watcher_code"))]
    out = set()
    for v in vals:
        if isinstance(v, str) and len(v.strip()) >= LOG_SECRET_MIN:
            v = v.strip()
            out.update((v, quote(v, safe=""), json.dumps(v)[1:-1]))
    return sorted(out, key=len, reverse=True)


def _log_url(m):
    from urllib.parse import urlsplit, parse_qsl, urlencode
    u = urlsplit(m.group(0))
    host = (u.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in LOG_PUBLIC_HOSTS):
        q = [(k, "[redacted]" if re.search(r"(?i)key|token|secret|sig|auth|pass|session|topic|mail|user|member|account", k)
              else v) for k, v in parse_qsl(u.query, keep_blank_values=True)]
        return f"{u.scheme}://{host}{u.path}" + ("?" + urlencode(q, safe="[]") if q else "")
    if host in ("127.0.0.1", "localhost"):
        return f"{u.scheme}://{host}" + (f":{u.port}" if u.port else "") + u.path
    return f"{u.scheme}://[host]"


def _log_kv(m):
    v = m.group(4)
    return f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)}" + ('"[redacted]"' if v.startswith('"') else "[redacted]")


def _log_ip4(m):
    o = [int(x) for x in m.groups()]
    if max(o) > 255 or o[0] == 127 or o == [0, 0, 0, 0]:
        return m.group(0)
    return "[ip]"


def _log_secretish(s):
    """A run of characters that looks like a key or code rather than a word, ticker or path."""
    if re.fullmatch(r"[A-Z0-9_.-]+", s) or re.fullmatch(r"[A-Za-z_.-]+", s):    # Kalshi tickers; plain words
        return False
    if len(s) >= 32:
        return True
    return len(s) >= 16 and bool(re.search(r"\d", s) and re.search(r"[a-z]", s) and re.search(r"[A-Z]", s))


def _log_blob(m):
    s = m.group(0)
    if "/" in s:                                                # a path: only the parts that look like keys
        return "/".join("[redacted]" if _log_secretish(x) else x for x in s.split("/"))
    return "[redacted]" if _log_secretish(s) else s


def log_redact(text, secrets_):
    """Mask secrets in one piece of log text. Order matters: whole secrets first, then shapes."""
    text = _RX_CTRL.sub("", text)                                # colour codes / zero-width marks can't split a secret
    if secrets_:
        text = re.sub("|".join(re.escape(s) for s in secrets_), "[secret]", text, flags=re.I)
    text = text[:LOG_LINE_MAX + 200]                             # bounded before the shape rules (they cost per character)
    if "-----begin" in text.lower():
        text = _RX_PEM.sub("[private key]", text)
    text = _RX_HDR.sub(lambda m: m.group(1) + m.group(2) + "[redacted]", text)
    text = _RX_BEARER.sub(lambda m: m.group(1) + m.group(2) + "[redacted]", text)
    text = _RX_JWT.sub("[token]", text)
    text = _RX_CWCOOKIE.sub(lambda m: m.group(1) + m.group(2) + "[redacted]", text)
    text = _RX_URL.sub(_log_url, text)
    text = _RX_KV.sub(_log_kv, text)
    text = _RX_KVSP.sub(lambda m: m.group(1) + m.group(2) + "[redacted]", text)
    if "@" in text:
        text = _RX_EMAIL.sub("[email]", text)
    if ".net" in text.lower():
        text = _RX_TSNET.sub("[tailnet-host]", text)
    text = _RX_IP4.sub(_log_ip4, text)
    text = _RX_IP6.sub("[ip]", text)
    text = _RX_UUID.sub(lambda m: "[id:" + hmac.new(_LOG_SALT, m.group(0).lower().encode(), "sha256").hexdigest()[:6] + "]",
                        text)
    text = _RX_HOMEDIR.sub(lambda m: f"/{m.group(1)}/[user]", text)
    text = _RX_BLOB.sub(_log_blob, text)
    if _RX_MONEYLINE.search(text):                             # account-level money (balances, pots): masked
        text = _RX_DOLLARS.sub("$[amount]", _RX_BALNUM.sub(lambda m: m.group(1) + "[amount]", text))
    return text


def log_fields(rec, secrets_):
    """One auto cash-out record: allowlisted fields only (simple values, or short lists/maps of them), redacted."""
    simple = (str, int, float, bool, type(None))

    def clean(v):
        if isinstance(v, float) and not _log_finite(v):
            return None                                          # not valid JSON
        return log_redact(v, secrets_)[:LOG_LINE_MAX] if isinstance(v, str) else v

    out = {}
    for k, v in (rec.items() if isinstance(rec, dict) else ()):
        if k not in LOG_FIELDS:
            continue
        if isinstance(v, simple):
            out[k] = clean(v)
        elif isinstance(v, list) and len(v) <= 50 and all(isinstance(x, simple) for x in v):
            out[k] = [clean(x) for x in v]
        elif isinstance(v, list) and len(v) <= 50 and all(isinstance(x, list) and all(isinstance(y, simple) for y in x) for x in v):
            out[k] = [[clean(y) for y in x] for x in v]
        elif isinstance(v, dict) and len(v) <= 50 and all(isinstance(x, simple) for x in v.values()):
            out[k] = {clean(str(a)): clean(x) for a, x in v.items() if str(a) in LOG_FIELDS}
    return out


def log_tail(path, budget=LOG_READ_BYTES):
    """The last `budget` bytes of a regular file (never a link), as whole lines. Missing = no lines."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return ""
    try:
        import stat
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("not a regular file")
        start = max(0, st.st_size - budget)
        os.lseek(fd, start, 0)
        chunks, left = [], st.st_size - start
        while left > 0:
            b = os.read(fd, min(left, 1 << 20))
            if not b:
                break
            chunks.append(b)
            left -= len(b)
    finally:
        os.close(fd)
    text = b"".join(chunks).decode("utf-8", "replace")
    if start > 0:
        text = text.split("\n", 1)[1] if "\n" in text else ""   # the first line was cut part-way
    return text


def log_answer(conf, E, source, since=None, limit=LOG_DEF_LINES, home=None):
    """The redacted answer for one source, as JSON bytes. Raises on anything unexpected (the caller sends nothing)."""
    name = LOG_SOURCES[source]                                  # KeyError for anything else
    path = os.path.join(home or HOME, name)
    secrets_ = log_secrets(conf, E)
    limit = max(1, min(LOG_MAX_LINES, int(limit)))
    text = log_tail(path)
    if source == "console" and "-----begin" in text.lower():
        text = _RX_PEM.sub("[private key]", text)              # a key block spans lines: masked before splitting
    rows = []
    last = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if source == "autosell":
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            t = rec.get("at") if isinstance(rec, dict) and isinstance(rec.get("at"), (int, float)) else None
            rows.append((t, rec))
        else:
            m = _LOG_TS.match(line)
            if not m and last is None:
                continue                                        # before the first dated line: maybe the middle of something cut
            if m:
                try:
                    last = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    pass
            rows.append((last, line))                           # a line with no time (a traceback) takes the one above
    if since is not None:
        rows = [r for r in rows if r[0] is not None and r[0] >= since]
    rows = rows[-limit:]
    out = []
    for t, x in rows:
        if source == "autosell":
            out.append({"t": t, "rec": log_fields(x, secrets_)})
            continue
        m = _LOG_SELL.match(x)
        if m:                                                   # the console copy of an auto cash-out record
            try:
                x = m.group(1) + json.dumps(log_fields(json.loads(m.group(2)), secrets_))
            except ValueError:
                x = m.group(1) + "[record not shown]"
        out.append({"t": t, "text": log_redact(x, secrets_)[:LOG_LINE_MAX]})
    paused = conf.get("paused")
    status = {"watcher": WATCHER_VERSION, "engine": str(getattr(E, "VERSION", "") or ""), "up": int(time.time() - STARTED),
              "paused": bool(paused), "paused_at": paused if isinstance(paused, (int, float)) and not isinstance(paused, bool) else None,
              "role": "backup" if is_backup(conf) else "main",
              "auto_sell": bool((getattr(E, "CFG", None) or {}).get("auto_sell")), "now": int(time.time())}
    ans = {"ok": True, "source": source, "status": status, "lines": out, "truncated": False}
    body = json.dumps(ans)                                       # ASCII only: a stray lone surrogate can't break it
    while len(body) > LOG_MAX_BYTES and ans["lines"]:
        drop = max(1, len(ans["lines"]) // 10)                   # the oldest go first
        ans["lines"] = ans["lines"][drop:]
        ans["truncated"] = True
        body = json.dumps(ans)
    low = body.lower()
    if any(s.lower() in low for s in secrets_) or re.search(r"(?i)begin[^\n]{0,20}private key", body):
        raise LogLeak("a secret survived redaction")
    return body.encode()


def log_status(conf):
    """For Settings on this Mac: on or off, since when, last read. Never the code or its hash."""
    la = conf.get("log_access") or {}
    return {"on": log_enabled(conf), "at": la.get("at") if log_enabled(conf) else None, "read": LOG_STATE["read"] or None}


def log_access_set(conf, E, on):
    """Settings › This Mac › "Let the dev Mac read logs". On makes a new code (shown once, the old one stops working)."""
    before = conf.get("log_access")
    tok = log_new_token(conf) if on else None
    if not on:
        conf.pop("log_access", None)
    try:
        E.save_json(CONF, conf, strict=True)                     # a code that wasn't saved must never be shown
    except Exception as err:
        if before is None:
            conf.pop("log_access", None)
        else:
            conf["log_access"] = before
        log("dev Mac log reading: setting not saved,", type(err).__name__)
        return {"ok": False, "msg": "Couldn't save that on this Mac. Nothing changed; try again.", "logs": log_status(conf)}
    log("dev Mac log reading", "turned on (new code)" if on else "turned off")
    if not on:
        return {"ok": True, "msg": "The dev Mac can no longer read logs.", "logs": log_status(conf)}
    ip = mac_tailscale_ip()
    url = f"http://{ip}:{conf.get('hub_port', 8765)}" if ip else ""
    return {"ok": True, "token": tok, "url": url, "logs": log_status(conf),
            "msg": "Copy the code now: it is shown only once."}


def log_send(handler, code, body=b""):
    """Every /api/logs answer: never cached, never sniffed, and an empty body for every refusal."""
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json" if body else "application/octet-stream")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if code == 405:
        handler.send_header("Allow", "GET")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if body:
        handler.wfile.write(body)


def log_route(handler, conf, E):
    """GET /api/logs?source=console|autosell&since=<unix seconds>&limit=N with `Authorization: Bearer <code>`.
    404 when off or not from the tailnet, 401 for a wrong code, 429 when too fast, 400 for a bad question, 503 when
    redaction failed. Every refusal has an empty body."""
    from urllib.parse import urlparse, parse_qs

    def send(code, body=b""):
        return log_send(handler, code, body)

    ip = handler.client_address[0]
    if not log_enabled(conf) or not log_client_ok(ip, handler.headers):
        return send(404)
    if not LOG_GATE.allow(ip):
        return send(429)
    if not log_token_ok(conf, handler.headers.get("Authorization")):
        LOG_GATE.wrong(ip)
        return send(401)
    q = parse_qs(urlparse(handler.path).query, keep_blank_values=True)
    if set(q) - {"source", "since", "limit"} or any(len(v) != 1 for v in q.values()):
        return send(400)
    source = q.get("source", ["console"])[0]
    try:
        since = float(q["since"][0]) if "since" in q else None
        limit = int(q.get("limit", [LOG_DEF_LINES])[0])
        if source not in LOG_SOURCES or (since is not None and not _log_finite(since)) or limit < 1:
            return send(400)
    except (ValueError, OverflowError):
        return send(400)
    try:
        body = log_answer(conf, E, source, since, limit)
    except Exception as err:                                     # fail closed: nothing of the log is sent
        log("dev Mac log read: nothing sent,", type(err).__name__)
        return send(503)
    LOG_STATE["read"] = int(time.time())
    return send(200, body)


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
            # money moved since the last read (#242): read Kalshi fresh, so the web app never caches the old account
            # Floor (#271): only when the cached copy is over HUB_FRESH_FLOOR seconds old, so a stamp that keeps changing
            # can't force a Kalshi read per request. A held-back copy is flagged: the app uses it but doesn't keep it.
            at = E.ACCT_CACHE.get("at") or 0
            moved = getattr(E, "money_seen", float)() > at
            floor = getattr(E, "HUB_FRESH_FLOOR", 3)
            held = moved and bool(E.ACCT_CACHE.get("value")) and time.time() - at < floor
            if held:
                print(f"hub account: fresh read held back ({time.time() - at:.1f}s-old copy, floor {floor}s)", flush=True)
            out = {"value": list(E.fetch_account(max_age=15 if held or not moved else 0, every_league=True))}
            if held:
                out["held_back"] = True
            return out
        if op == "pots":                                 # read-only: Kalshi's cash by pot from the last balance read
            return {"pots": E.kalshi_pots()}
        if op == "pot_move":                             # Pete's confirmed tap: move cash between pots (never automatic)
            paused = bool(req.get("paused"))
            try:
                paused = paused or (os.path.exists(CONF) and bool(load_conf().get("paused")))
            except (OSError, ValueError, AttributeError):
                paused = True                            # can't read the Pause switch: never move on a guess
            log("phone pot move:", str(req.get("amount"))[:12], str(req.get("frm"))[:4], "->", str(req.get("to"))[:4])
            return E.pot_transfer(req.get("frm"), req.get("to"), req.get("amount"), cid=req.get("cid"), paused=paused)
        if op == "pot_clear":
            return {"ok": E.pot_clear(str(req.get("cid") or "")[:40])}
        if op == "pot_moves":                            # read-only: recent moves, pending ones checked with Kalshi
            return {"moves": E.pot_moves(refresh=True)}
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
            why = hub_refusal(method, path)
            if why:
                if method != "GET":
                    log("phone request refused:", why, method, path[:80])
                return {"err": "kalshi", "msg": "That request isn't allowed through the Mac."}   # moves: pot_move only
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
            if self.path.split("?")[0] == LOG_PATH:            # dev Mac log reading is read-only (404 while off)
                return log_send(self, 405 if log_enabled(conf) else 404)
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
                        "checked": LATEST_SEEN.get("at") or 0, "odds": odds_info(eng)}
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
            if u.path == LOG_PATH:                              # dev Mac log reading (read-only, redacted)
                return log_route(self, conf, E)
            if web and u.path in ("/sw.js", "/manifest.webmanifest", "/icon.png", "/apple-touch-icon.png"):
                import base64
                body, ctype = ((SW_JS.replace("@@VER@@", WATCHER_VERSION).encode(), "text/javascript") if u.path == "/sw.js" else
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
            if (web and u.path in ("/app", "/app/") and "frag=1" not in u.query and not self.headers.get("X-CW")
                    and self._wants_page()):
                return self._html(302, "", location="/" + ("?" + u.query if u.query else ""))       # a tap or typed address, not the app's own call (#79)
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

        def _wants_page(self):
            """True for a browser navigation (a tap on a notification or link): it asked for a web page."""
            return "text/html" in (self.headers.get("Accept") or "")

        def _send(self, code, body):
            if code in (403, 404) and not body and self.command == "GET" and self._wants_page():
                # a page must never be an empty file (iOS offers it as "Zero KB"): say so and offer the way home (#79)
                return self._html(code, NOT_FOUND_HTML)
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
    if SPA_PROBLEM or SPA_STALE:            # the web app's files are missing, broken or another version's: fetch them
        if SPA_STALE:
            log("web app files are for version", spa_stamp(), "- fetching this version's")
        spa_repair_start(conf)
    if is_backup(conf):
        os.environ["COMBO_ROLE"] = "backup"           # every engine copy this process loads knows it never trades
    try:
        os.remove(RESTARTING)                         # this is the restarted watcher: taps may go again
    except OSError:
        pass
    E = load_engine()
    backup_safe(conf, E)
    # headless: nothing to draw, notifications go to ntfy, no cash-out quotes from here
    E.present = lambda *a, **k: None
    E.loading = lambda *a, **k: None
    E.notify = lambda msg: push(conf, msg.replace("Open the planner to confirm.", "Open the planner to cash out."),
                                pause_button=bool(E.CFG.get("auto_sell")), click=trade_link(E, msg))
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
    if not (E.can_trade() or (is_backup(conf) and E.has_kalshi_key())):
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
    backup = is_backup(conf)                         # a Pi kept as alerts-only backup for the Mac
    if backup:
        log("backup mode: alerts only, and only while the Mac is quiet; never trades")
    E.TRADING_PAUSED = watcher_paused                 # Pause as the watcher holds it, read live
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
            backup_safe(conf, E)                   # the Pi: trading off before anything below can run
            estimate_offers(E)
            E.ACCT_CACHE["at"] = 0
            alerts = E.live_check(None)            # also auto cash-out, if the phone turned it on
            if alerts:
                log("alerts:", alerts)
            try:                                   # history + live events for open screens
                for ev in E.record_view(E.MINE.get("view")):
                    BUS.publish(ev)
                BUS.publish({"kind": "tick", "money": getattr(E, "money_seen", float)()})   # money: open pages refetch (#242)
            except Exception as err:
                log("record failed:", type(err).__name__, err)
            if t0 - last["sell"] > 60 and not backup_safe(conf, E):
                last["sell"] = t0
                done = E.autosell_pass()
                if done:
                    log("auto-sell placed or moved:", done)
            if backup:
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


# ---- the web app's pages, built at import ------------------------------------------------------------------
# The login page and the web app (SPA) live in watcher/spa/ as plain files; spa_assemble (next to the updater) joins
# them back into these two strings. Missing or broken files never stop the watcher and never leave a blank page:
# Combo Hub serves the built-in copy below (SPA_LEGACY_Z), the trading loop keeps running, and main() fetches the
# files (spa_repair_loop). A folder stamped for another version is still served, and main() fetches this version's.
#
# SPA_LEGACY_Z: the web app exactly as it was when it moved out of this file (develop 395a7f4; zlib + base64 of
# SPA, a zero byte, LOGIN_HTML), for ONE release only: a Mac on 2026.11.21.126 updates with its old updater, which
# installs only the two Python files, so the first start of this version has no spa folder; it serves this copy
# until spa_repair has fetched the files (seconds, or whenever GitHub answers). Remove it (and this paragraph) only once
# every device (the Mac and the Pi) reports 2026.11.21.127 or later: a device that skips this release (offline, or a
# Pi waiting on the phone) still comes from 126 with the old updater and needs it. tools/verify_spa_split.py checks it matches the split's source.
SPA_LEGACY_Z = (
    "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"
    "JKUd0o96S6QkXuKnFGft4rvTm+l/ACAZnDw="
)


def spa_legacy():
    """(SPA, LOGIN_HTML) from the built-in copy, or None if it can't be read."""
    import base64, zlib
    try:
        spa, login = zlib.decompress(base64.b64decode(SPA_LEGACY_Z)).decode("utf-8").split("\0", 1)
        return (spa, login) if spa.startswith("<!doctype html>") and "__MSG__" in login else None
    except Exception:
        return None


SPA_PROBLEM = ""
SPA_STALE = spa_stamp() not in ("", WATCHER_VERSION)
try:
    SPA, LOGIN_HTML = spa_assemble()
except Exception as _spa_err:                    # anything at all: the watcher must still start and keep trading
    SPA_PROBLEM = f"{type(_spa_err).__name__}: {_spa_err}"
    _legacy = spa_legacy()
    SPA, LOGIN_HTML = _legacy or (SPA_FALLBACK, SPA_FALLBACK)
    if "--install-spa" not in sys.argv:          # the installer is about to fetch them: nothing to shout about
        log("WEB APP FILES MISSING OR BROKEN (spa folder):", SPA_PROBLEM, "- Combo Hub serves",
            "the built-in copy" if _legacy else "a holding page", "until they're fetched")


if __name__ == "__main__":
    if "--install-spa" in sys.argv:          # the installers: fetch this version's web app files now
        sys.exit(0 if spa_repair() else 1)
    if "--webapp" in sys.argv:
        sys.exit(webapp_main() or 0)
    sys.exit(main() or 0)
