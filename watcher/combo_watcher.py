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
WATCHER_VERSION = "2026.11.21.126"

# Settings the phone may change on the watcher. Keys and anything else are never accepted.
SYNCED = ("take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "bankroll", "ride", "tp_follow", "tp_auto", "tp_ladder", "refresh_secs", "auto_sell", "auto_cap",
          "auto_hedge", "hedge_cap", "prefer_hedge", "notify_value", "notify_price", "notify_cash", "notify_news",
          "killer_mode", "maker_mode", "accept_pct", "size_min", "size_max", "budget", "include_live", "live_min", "panel_live",
          "line_model")


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


GH_API = "https://api.github.com/repos/peetah-138/nfl-combo-planner"


def repo_sha():
    """The newest commit on main (40 hex characters), or "" when GitHub doesn't say."""
    try:
        r = requests.get(GH_API + "/commits/main", timeout=10, headers={"Accept": "application/vnd.github.sha"})
        sha = r.text.strip()
        if r.ok and re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
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
    # the web app's files must be the ones the phone approved, unless this Mac takes automatic updates anyway
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
        try:
            os.replace(ENGINE + ".new", ENGINE)
            os.replace(me + ".new", me)
        except OSError as err:
            spa_restore(old_spa)
            log(f"update {latest} failed while installing ({err}); the web app's files were put back")
            return False
        spa_drop(old_spa)
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
    threading.Thread(target=spa_repair_loop, args=(conf,), daemon=True, name="spa-repair").start()


def spa_repair_loop(conf=None):
    """main() runs this when the web app's files were missing or broken at start: it fetches them (retrying every
    10 minutes) and then restarts the watcher so Combo Hub serves them. Trading carries on throughout."""
    while True:
        try:
            if spa_repair(conf):
                log("restarting so Combo Hub uses its web app files")
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
ICON_PNG = "iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAIAAACyr5FlAAAPYklEQVR42u2dWYwcVxWGv3urx+7N0+OETRgTxzbgIewQwhYJxAu8gEQISwQoxEtYsvEAWcwqREBISDwgwDsGZSGASLATwHYgJg6EXYASg4AYiS2I1ZOZXsZddXmo6qmqrqqe6ur29HZalmLn1lTXf+qbu5x7zznq6m0GMHgfo1p/ARTRJu+fKvD/267spin+e7tsSv/woqsrXdr9b+srUK0LVfB7AiJU6+/+j3TT1HbD+O9drin+keIeXnRl0+V+9LLfp1pNqtXUix2VCdwtqx1DN8lqR9HVocm9iU7Jo+rr75nqx++Z6sfvmejq0KS7/T7VVzuqfthR9cOOoivapMWOoiupSYsdRVdSkxY7iq6kJi12FF1JTVrsKLqSHl6LHUVX0sPrXvwtYsfx1qX75W8RPsZPl0bsKLo6OMHEjqIr0QlGJqe92HHsdenofqDYUXSpJQ+p2FF0JTrBxI6iK94JJnYUXUm6tNhRdLXpUm1OMLGj6IqeH9NiR9GV1H9osaPoSmrSYkfRlRTfoMWOoispvkGLHUVXUpMWO4qupCYtdhRdSU1a7Ci6kpq02FF0JTVpsaPoSmrSYkfR1asTTOw4gbp0L/kkxI7jrUvTp3wSwsf46dK956MRO46rLh2b8kfsKLpUzIRU7Ci6TIddWbGj6DLB1YrwIbpinGAgfIiueCdYaLUifIiu9tAE4UN0xeXH1cH7Ch+iKxSa0HZf4UN0+aEJKnJf4UN0EZxzKOFDdEXqN4QO+wgfoiuYryXgBBM+VlaXUig11LrCTjDhY0X2wS2NArtJ08YYcrrd5kOiy49bET5WYp9TYducnqfpMF2iUsTS/G+eM2ew1NDpyqnW/EMF5iLKeKW/3Fa/yaCUf70J/tN4RcVU9MqEJvcOKBRxV6Zrar8y8oRdNaV/+Ay6tGahRmUNr3slL3kO654Ahv8+xs9OcuzH/P7PTJdxAu9m8Lo+fpkxhErAmUAFORMgxpydencZitpFm3op1hf/SP3WZWmqDTau5+rLOH8dbZ/5Kl/4Ovf9gkLe42MYdGmMP47I+HKW/NCWptbgnGk+9h7OX0fTxjGY1h/bplzk/e/gwmeyUPMWkMOgK7LxJnz02w+tNY1FykV2XsmaErZDzkKr1mpFYVk4Dsbwvst4/AzN5rDMT3W0qqDw0Uc+cprFBqU8H7uKTetxHCxN9KM1jqFS5qJnUWug1VDo0iqu6qTw0Rc+LE19kVKBj17FxqdgO+g4MoIz0BdfgKVbtx20Lt329cJHX/hwO4NGg3KBj1zFxvXYCX1GiA9FaTUWw6JLR4c34aNXPgw5zeIipQIfTk2G+2k6vu9g4Lp0sICx8NEXPixNvUGpwEeu7oIM936/+QNN21/pDFaX7z5XwkdfxmlNY5FSgQ9dzfnpyTAAjsODv2L1lOfqGLgu3Z59UvjogQ9LtUaTa7obTRyDpfnKYR75M/mpQJGTgerSMdlJhY9MfHhrkzwfuqa7PsNd3x4+zjfvpVTAcYZFlx9lL3z0YkfL9XQV+OC13ZFhDFqz6w4+dyurVw2XLh2MohY+stlRaxp1SgV2ZiJj9x3cdS/nVLKUzDq7utqi7IWP9HZ0m7xVazFjn7H7Du68l7UVbBt3n2tIdKmYuBXho5umpVXrzuvYkK3POMbaaWx7uHTFO8GEj5RN3o5ag1KBm65lw3psuzsy9nyVbx1jbQXHHtJ+Mew+Fz5SN3k7akVuuo4NT8W2sazuyZjGsYe3X4y4z4WPFE3uaFIscGNWMg4dC8wzhrBfXHKCKYMSPlIPxlp5fcaN78tCxt7bOXSUmeA8Y/j48EMTiL5+4SOhydKcWaRY5IZMZOy7nUOB0WTI51XtTjDho7Oxmk2mprg+Gxm3cegoayvYzmjMq2KcYKPOh1Io7cWG9NGOSmEcFhtc8fYsZOy/ncPHmJnGbo7MvDsctzKafKjA+9MaY9OoUa1yZtFbcPZuR6XAUK9z5VZeelH3ZNzGoaPMVLx9k1GZd0fmHCPIx9I5XsdmYZ6pVWx+Os9+Lk95KhgWHkMpX2cGO2oFDvU6O7Zy8cuzkHH4qOfpGq11WS4Uy7R0tkD5gUyhuKZwNBGBsCKlIvdZwfionEV1geIaXvN6LrqYc84FcGz+/jfuO8qJ+9A5pqb8wT59fBQKY6jV2b4tCxkHbuPuo8xUvLXJaMV9qc++2bTHMhGKijHRuCYVE+m0FN3Ufp+zHx+lcyzMc95G3raDdef5r0e1LvvlT7nlANUqq1Z7fKSMj3ItVauzfSuveEUWMg4fYaaC7Yxk3JdWJiFuZUTGF8tiYY5Nz+Canaw7D9v2TlV5PZnBtnn+hVz7AYoFFhu+h3vZet1ufEC9lpWMW7n7iO8dH8V1u1/Ga/T4MFgW84+xeQvv+QCFIo6DZfkdhouIZWHbrN/AtddTSMfHUn9br7NtWxYyvnQr9xwJzzNGkA+tArcbLT5yFvNzPG0L777eIyMpKsSycGzWb+C6FHx4vY6hXmNrJjIO3so9R7x5RtsZ4hHz6wQ9piPEh5Vjfo7NW3jXcmR4K47UfOjWqnXb9i7IcI8Ha81Xbufu7zBTae2ojXL+oPDG24jw4c4zNs/yrhtSkZGeD60wDvUaW7fz8m7IcK88foJ7vstMBbs5DvmlInErQ89HLsf8aTZt4cpuyEjDh1IYQ6POFZnIuP8B9h6gXMKYMck/Fhe3MsR8WBbzc2yezUJGIh9Wa57hUHfJuDgLGbv3kV/d8hyMRX66ULnyIefDyrEwx6Yt7LgxIxmxfDTq5CxvbXLFdl7WPRknHmDPPgp5b/9lbPIXhtznw8xHziVjtlcyonyUitSqLDZ4546sZOwln/fWOOOU31IrE8lBOXx8WBbzp9k0y/Z+kNHOxw2Uy7xjayYyTnhkaDDOuOU/VZ+/1ATd2zF+ccUg/eugp5ifY+Ms227qGxm+68FBaapVisWQxz0lGXv3ki94+y/Dk3+sX/51rcK/vsPWf1g5Fk6zcZbt3ZDhxhim+SiNMRnJ2LeXQj7sPRuv/Mm67djgUPHhzjNcMvJFTGoy3IMdmHR8qK7JeOAE+/Z48ww3GeNY5tdud4INCR9La5ONs2zb6ZGhdCo3pVLMz3H0Lq+3NyYVH92SUXDnGWYM868vvescgZMWJnD8gsgJDPe4wMqc/3C94xtnuaJLMrSmVmXfZ/j1zzn9X954eStoPd3rX56M+9m/h0JrnuEe0Rj+/Lh02eTeKy5uZdD9h2VRPZ2djF2f5A8P86Qn871DfO0AWqftP5Yl44f3cyA4mgQmh2PZf4Q8pMPARy5H9TTnz/LObsgwLTJ2f4pHfkt5DWcaVGb4/uE+8LFExv7d5PPe/osa9/oe/mEfhoMPbTH3HzZcwOUf7I4MpalV2fNJHnmYcisqxG72gQ+/z9hNodCavY57/Rf/8OyQ8KE1jSovejWX78xIxh9PUl6Dfcb/oh75cMn40f18aTd5d9XqTER9oFAg9cD50Ir6As94AW+6jrzrdeiGjL03e31GKJdBb3wskXFgV2s0MZNVPyoQtzJAPhT2GWbO5Q3vxRiMk2pxESLjJOVpnGa8sTLw4fcZuzxPlzETV18sHLcyID60ZrHOlgspVboeTfbdzKmTlKexm52M1RUfHhk/4OAXAztqk1d/Tre/10Hw4R4VfvoL03oqXTLqVfZ9glMPUVrjxRh2Pj/Wxoe7+o3xu9tYFg/+gC9/sbWjZia0PqGOea8rzoc7suSLXZPxp5OUpnGaac8X+nzs9w4DOzaO0/pjoxTa4off58u7yC+tTSa1fmWuPRCtdalRId/lWfWfuhcvzRjSkLG/RYbbZ5jU8XN2k+kZjn+bR//CpVt5Urho0vwch7/O8SMUSv5e69jXF0vSpfa/0cRulJvw3m5oP73f+/vKojrHq97KK9+CY6OtTjtq9QUO3MypkxSnvXO8GeLndI5aldV5nnsRT7uAtedSq/LH3/HLB/nXvyiUwMGZjPpiHR5eHbjEmPBPrjwfSnOmwePWs+MzYFA6Znxxj9LUaxy8mVMPUarQtHuKr1QWjk2t5rHixsatyjM1hWMmq/5c0sMnJIxb4fmHw6o8j57ie7egLYzjoeDvm9gojdLc8mlOPUS54me5yBzfYGyUolSmVCa/mkKR8jS5HI4j9W/DZ0iVGSQf7qvKF/nRXfzkHrTlrWZdn4frVl+sc+cXeOTXrGnNM/oSH2Ucr76ascNBrcIHqIOXmOiIMJDxxV08VR/jea/mwtfy5E3e5KNR408PcfwbnHqYUgXHlvqmKzS+qIOXhCekg+ZDWdQW0DmeuIFSBeDfj/LPv6JzrCr40afCxwrwkaNtXWr80ysrv7414NjkSxjDP05h2xiwpiiUMAbTDC35pH722V7fxsWtmAHPT40NhlWryZcolJiawjjt1yP518/+/KPdfT4kfODufTgeFpL/dCB86Ki5h4cPyX86WD50rLmFD+GjU7ly4WNi+VDtTjDhQ/gI53Vl2XLlwsck9x/LlysXPia2/4iLWxE+Jp6PUKUmhA/hg2gxHoPwIXzENunoyxM+hA/fzyF8CB+JoQnCh/AR26STcqcIH8KH7pBbR/iYcD606ph7SfiYZD50/HsVPoSPaLly4UP48IvxYBA+hI94J5iK/IDwIXyo0FJW+BA+ok4wf1dW+BA+ovk5om9I+BA+4uJWhA/hI+gEEz6Ej2VOggkfwkfECRZnbuFjkvlQvhMswdzCx8TyQcgJJnwIH3H9xzLlyoWPSe4/li9XLnxMIB8JcSvCh/DhhyZE36vwIXwsTUiFD+GDDikYhA/hIyYPaYdcW8LHhPOho7YTPoQPFZpzCB/CR6RJJ9lO+BA+tEq2nfAx4XzoJAMJH8KH7mAg4WPC+UiotyJ8CB/Bwz7Ch/ARU4xH+BA+4p1gBIJWhA/hI+QEI06w8CF8tG/ZCx/CR7sTTPgQPjo5wYQP4aOTE0z4ED46OcGED+GjkxNM+BA+/GI8nctRCx8TyAehk2DCh/AR13+EMvsIH8JHpDpkCnMLHxPFR7wTTPgQPpaeXCfZVPiQ/kOTbFPhY8L50FHbCR/CR/thH+FD+IjJQyp8CB+xTVol2074mHA+dNSswofwQXy9lTg++uVf71d+KfrEB33igz7xQQo+eq8znZ6PuLiV5N+tHvnoV/4xlZ4P04mP2KdSpms+lj2+H8NHx76wAx+qh/4jaECVgg8da+5sfNAnPugTH/HPsywfHe7TYaxM0X8s8zyp+ehL/0GK/uP/bBblkfvF4wkAAAAASUVORK5CYII="

SW_JS = """// Combo Hub service worker (v2: taps open '/', legacy '/app' targets are mapped): shows the Mac's notifications and opens the right screen when tapped.
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


# The login page and the web app (SPA) live in watcher/spa/ as plain files; spa_assemble (above, next to the
# updater) joins them back into these two strings at import. Missing or broken files never stop the watcher: the
# pages say the app is finishing an update, the trading loop keeps running, and main() fetches the files again.
# A folder stamped for another version (an installer's fetch failed after it put in new Python files) is still
# served, but main() fetches this version's files too.
SPA_PROBLEM = ""
SPA_STALE = spa_stamp() not in ("", WATCHER_VERSION)
try:
    SPA, LOGIN_HTML = spa_assemble()
except Exception as _spa_err:                    # anything at all: the watcher must still start and keep trading
    SPA_PROBLEM = f"{type(_spa_err).__name__}: {_spa_err}"
    if "--install-spa" not in sys.argv:          # the installer is about to fetch them: nothing to shout about
        log("WEB APP FILES MISSING OR BROKEN (spa folder):", SPA_PROBLEM, "- Combo Hub shows a holding page until they're fetched")
    SPA, LOGIN_HTML = SPA_FALLBACK, SPA_FALLBACK


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
            return bool(load_conf().get("paused"))
        except (OSError, ValueError, AttributeError):
            return True

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
        if leg is None and A.STORE.get("db"):               # a game from a buy idea you hold nothing on yet (display only)
            try:
                leg = A.idea_game_leg(t)
            except Exception as err:
                A.klive_log_once("ideagame", t, err)
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
        return jsonable({"leg": leg, "combos": combos, "story": story, "whatif": wi,
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
                "maker_mode", "take_profit", "lock_trail", "stop_loss", "smart_sell", "panel_budget", "panel_live", "line_model")

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
                             "pots": pots,
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
            if a == "singlequote":                      # Buy straight: one team (or a spread/total), priced now
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t):
                    return {"ok": False, "msg": "That market isn't recognized."}
                lg = str(d.get("lg") or A.ticker_sport(t) or "")
                return jsonable(A.single_buy_quote(single_side(t, lg), d.get("stake"), paused=paused_now()))
            if a == "singlebuy" and d.get("q"):          # Buy straight: the quote on screen, once
                if not re.fullmatch(r"[A-Z0-9._-]{3,120}", t) or not re.fullmatch(r"[0-9a-f]{16}", str(d.get("q"))):
                    return {"ok": False, "msg": "That price isn't recognized. Get a fresh one."}
                r = A.single_buy(str(d["q"]), t, anyway=bool(d.get("anyway")), paused=paused_now(), log=log)
                LIVE["at"] = 0
                return jsonable(r)
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
                    elif path == "/app/api/game_warm":
                        out = api_game_warm(q.get("t") or "")
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
                                    BUILD.update(lg=cur, note=s["note"], days=s["days"], lines=s["lines"])
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
        if op == "pots":                                 # read-only: Kalshi's cash by pot from the last balance read
            return {"pots": E.kalshi_pots()}
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
    if "--install-spa" in sys.argv:          # the installers: fetch this version's web app files now
        sys.exit(0 if spa_repair() else 1)
    if "--webapp" in sys.argv:
        sys.exit(webapp_main() or 0)
    sys.exit(main() or 0)
