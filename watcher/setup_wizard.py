#!/usr/bin/env python3
"""Combo Watcher setup: a small local app (shown in its own window) that installs, checks, updates or
removes the combo planner's watcher and hub on this Mac. It drives install_mac.sh --auto and shows
its progress. Everything stays on this Mac: the page is served on 127.0.0.1 with a one-time token."""
import json, os, re, secrets, shutil, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR = os.path.expanduser("~/combowatch")
ARGS = dict(zip(sys.argv[1::2], sys.argv[2::2]))
INSTALLER = ARGS.get("--installer", os.path.join(os.path.dirname(__file__), "install_mac.sh"))
WINDOW_JS = ARGS.get("--window", os.path.join(os.path.dirname(__file__), "wizard_window.js"))
ICON = ARGS.get("--icon", "")
TOKEN = secrets.token_urlsafe(18)
LINKS = {"tailscale": "https://tailscale.com/download/mac", "kalshi": "https://kalshi.com/account/profile",
         "hub": "http://localhost:8765/", "ntfy": "https://apps.apple.com/app/ntfy/id1625396347"}
JOB = {"running": False, "lines": [], "steps": [], "result": {}, "error": "", "done": False}
KEY = {"path": "", "name": "", "tmp": ""}
LAST = {"t": time.time()}


def sh(*cmd, timeout=20, env=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def tailscale_ip():
    for ip in re.findall(r"inet (100\.(\d+)\.\d+\.\d+)", sh("ifconfig")):
        if 64 <= int(ip[1]) <= 127:
            return ip[0]
    return ""


def state():
    installed = os.path.exists(os.path.join(DIR, "watcher.json")) and os.path.exists(os.path.join(DIR, ".venv/bin/python"))
    pr = sh("launchctl", "print", f"gui/{os.getuid()}/com.combowatch.watcher")
    m = re.search(r"\n\s*state = (\w+)", pr)
    log = []
    try:
        with open(os.path.join(DIR, "watcher.log"), encoding="utf-8", errors="replace") as f:
            log = [l.rstrip() for l in f.readlines()[-200:]]
    except OSError:
        pass
    ver = next((re.search(r"engine ([\d.]+) started", l).group(1) for l in reversed(log) if re.search(r"engine ([\d.]+) started", l)), "")
    kalshi = next(("ok" if "Kalshi OK" in l else "trying" for l in reversed(log) if "Kalshi OK" in l or "Kalshi check failed" in l), "")
    return {"installed": installed, "running": bool(m and m.group(1) == "running"), "version": ver,
            "tailscale": tailscale_ip(), "tailscale_app": os.path.isdir("/Applications/Tailscale.app"),
            "kalshi": kalshi, "has_key": os.path.exists(os.path.join(DIR, "kalshi_private_key.pem")),
            "log": [l[:180] for l in log[-14:]]}


def run_installer(args, env_extra):
    JOB.update(running=True, lines=[], steps=[], result={}, error="", done=False)
    env = dict(os.environ, **env_extra)
    try:
        p = subprocess.Popen(["bash", INSTALLER, "--auto", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env=env)
        for line in p.stdout:
            line = line.rstrip()
            JOB["lines"].append(line[:200])
            if line.startswith("STEP: "):
                JOB["steps"].append(line[6:])
            elif re.match(r"^(CODE|HUB|PASS|CHANGED|TOPIC|KALSHI|STATE|TS): ", line):
                k, v = line.split(": ", 1)
                JOB["result"][k.lower()] = v
            elif line.startswith("ERROR: ") or line.startswith("MSG: "):
                JOB["result"].setdefault("msgs", []).append(line.split(": ", 1)[1])
        p.wait()
        if p.returncode:
            JOB["error"] = next((l[7:] for l in JOB["lines"] if l.startswith("ERROR: ")), "") or \
                next((l[5:] for l in reversed(JOB["lines"]) if l.startswith("MSG: ")), "") or \
                f"Setup stopped (code {p.returncode}). " + " / ".join(JOB["lines"][-2:])
    except OSError as err:
        JOB["error"] = str(err)
    finally:
        if KEY.get("tmp"):
            try:
                os.remove(KEY["tmp"])
            except OSError:
                pass
            KEY["tmp"] = ""
        JOB.update(running=False, done=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def ok(self, obj):
        self.send(200, json.dumps(obj))

    def do_GET(self):
        LAST["t"] = time.time()
        if self.path.split("?")[0] == "/" and f"t={TOKEN}" in self.path:
            return self.send(200, PAGE.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if self.headers.get("X-Token") != TOKEN:
            return self.send(403, "{}")
        if self.path == "/api/state":
            return self.ok(state())
        if self.path == "/api/progress":
            return self.ok({k: JOB[k] for k in ("running", "steps", "result", "error", "done")} | {"tail": JOB["lines"][-6:]})
        self.send(404, "{}")

    def do_POST(self):
        LAST["t"] = time.time()
        if self.headers.get("X-Token") != TOKEN:
            return self.send(403, "{}")
        n = int(self.headers.get("Content-Length") or 0)
        try:
            d = json.loads(self.rfile.read(n) or b"{}") if 0 <= n < 200_000 else {}
        except ValueError:
            d = {}
        p = self.path
        if p == "/api/open":
            url = LINKS.get(d.get("what"))
            if url:
                sh("open", url)
            return self.ok({"ok": bool(url)})
        if p == "/api/opentailscale":
            sh("open", "-a", "Tailscale")
            return self.ok({"ok": True})
        if p == "/api/paste":
            return self.ok({"text": sh("pbpaste")[:5000]})
        if p == "/api/copy":
            subprocess.run(["pbcopy"], input=str(d.get("text", "")), text=True)
            return self.ok({"ok": True})
        if p == "/api/choosekey":
            out = sh("osascript", "-e", 'POSIX path of (choose file with prompt "Choose the private key file Kalshi '
                     'downloaded (usually in Downloads):" default location (path to downloads folder))', timeout=600).strip()
            if not out:
                return self.ok({"ok": False})
            try:
                txt = open(out, encoding="utf-8", errors="replace").read(20000)
            except OSError:
                txt = ""
            if "BEGIN" not in txt or "PRIVATE KEY" not in txt:
                return self.ok({"ok": False, "error": "That file isn't a private key. Choose the file Kalshi downloaded when you made the key."})
            KEY.update(path=out, name=os.path.basename(out))
            return self.ok({"ok": True, "name": KEY["name"]})
        if p == "/api/pastekey":
            txt = str(d.get("pem", ""))
            if "BEGIN" not in txt or "PRIVATE KEY" not in txt:
                return self.ok({"ok": False, "error": "That isn't a private key. It starts with -----BEGIN and ends with -----END."})
            fd, tmp = __import__("tempfile").mkstemp(prefix="cwkey", dir=DIR if os.path.isdir(DIR) else None)
            with os.fdopen(fd, "w") as f:
                f.write(txt.strip() + "\n")
            KEY.update(path=tmp, name="pasted key", tmp=tmp)
            return self.ok({"ok": True, "name": "Pasted key"})
        if p == "/api/install":
            if JOB["running"]:
                return self.ok({"ok": False, "error": "Already running."})
            mode = d.get("mode", "install")
            args = ["--new-key"] if mode == "newkey" else []
            env = {"CW_KEYID": str(d.get("keyid", "")).strip(), "CW_KEYFILE": KEY.get("path", ""),
                   "CW_PAIR": re.sub(r"\s+", "", str(d.get("pair", "")))}
            if mode in ("install", "newkey") and not state()["has_key"] or mode == "newkey":
                if not env["CW_KEYID"] or not env["CW_KEYFILE"]:
                    return self.ok({"ok": False, "error": "Add the Key ID and the private key first."})
            threading.Thread(target=run_installer, args=(args, env), daemon=True).start()
            return self.ok({"ok": True})
        if p == "/api/code":
            out = sh("bash", INSTALLER, "--auto", "--code", timeout=30)
            return self.ok(dict(re.findall(r"^(CODE|HUB|PASS): (.*)$", out, re.M)))
        if p == "/api/passcode":
            np = str(d.get("pass", ""))
            if len(np) < 6:
                return self.ok({"ok": False, "error": "Use at least 6 characters."})
            sh("bash", INSTALLER, "--auto", "--passcode", np, timeout=30)
            return self.ok({"ok": True})
        if p == "/api/uninstall":
            sh("bash", INSTALLER, "--auto", "--uninstall", timeout=60)
            return self.ok({"ok": True})
        if p == "/api/trashkey":
            if KEY.get("path") and not KEY.get("tmp") and os.path.exists(KEY["path"]):
                sh("osascript", "-e", f'tell application "Finder" to delete (POSIX file {json.dumps(KEY["path"])} as alias)')
            return self.ok({"ok": True})
        if p == "/api/quit":
            self.ok({"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        self.send(404, "{}")


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Combo Watcher</title>
<style>
:root{--bg:#f5f5f7;--panel:#ffffff;--side:#ececf0;--ink:#1d1d1f;--mute:#6e6e73;--line:rgba(0,0,0,.09);--acc:#0a6cff;--accbg:rgba(10,108,255,.1);
 --good:#1f9d55;--goodbg:rgba(31,157,85,.12);--warn:#c25400;--warnbg:rgba(255,149,0,.14);--field:#f2f2f5}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1e;--panel:#232326;--side:#18181a;--ink:#f5f5f7;--mute:#98989f;--line:rgba(255,255,255,.09);
 --acc:#3d8bff;--accbg:rgba(61,139,255,.16);--good:#34c759;--goodbg:rgba(52,199,89,.14);--warn:#ff9f0a;--warnbg:rgba(255,159,10,.15);--field:#2c2c2e}}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;display:flex;user-select:none;-webkit-user-select:none}
aside{width:236px;flex:none;background:var(--side);border-right:1px solid var(--line);padding:46px 18px 20px;display:flex;flex-direction:column}
.logo{display:flex;align-items:center;gap:11px;margin:0 6px 30px}
.logo .mk{width:40px;height:40px;border-radius:10px;background:linear-gradient(145deg,#2f8cff,#7a5cff 60%,#c84bff);
 display:grid;place-items:center;box-shadow:0 6px 16px rgba(90,90,255,.35)}
.logo b{font-size:16px;letter-spacing:-.01em}.logo small{display:block;color:var(--mute);font-size:12px}
ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px}
ol li{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;color:var(--mute);font-weight:500}
ol li .n{width:22px;height:22px;border-radius:50%;border:1.5px solid currentColor;display:grid;place-items:center;font-size:11px;font-weight:700;flex:none}
ol li.on{background:var(--accbg);color:var(--acc)}ol li.done{color:var(--ink)}
ol li.done .n{background:var(--good);border-color:var(--good);color:#fff}
.side-foot{margin-top:auto;color:var(--mute);font-size:12px;padding:0 6px}
main{flex:1;display:flex;flex-direction:column;min-width:0}
.view{flex:1;overflow:auto;padding:52px 52px 24px;animation:in .28s cubic-bezier(.2,.7,.3,1)}
@keyframes in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
h1{font-size:28px;letter-spacing:-.025em;margin:0 0 8px;font-weight:700}
.lead{color:var(--mute);font-size:15px;margin:0 0 26px;max-width:520px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 14px;max-width:560px}
.card h3{margin:0 0 4px;font-size:15px}.card p{margin:0;color:var(--mute)}
.row{display:flex;align-items:center;gap:12px}.grow{flex:1;min-width:0}
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:99px;font-size:12px;font-weight:600}
.pill.good{background:var(--goodbg);color:var(--good)}.pill.warn{background:var(--warnbg);color:var(--warn)}.pill.wait{background:var(--accbg);color:var(--acc)}
.pill i{width:7px;height:7px;border-radius:50%;background:currentColor;display:block}
label{display:block;font-weight:600;margin:0 0 6px}
input,textarea{width:100%;font:13px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);background:var(--field);border:1px solid var(--line);
 border-radius:9px;padding:10px 12px;outline:none;user-select:text;-webkit-user-select:text}
input:focus,textarea:focus{border-color:var(--acc);box-shadow:0 0 0 3px var(--accbg)}
textarea{height:96px;resize:none}
.btn{font:600 13.5px -apple-system,system-ui;border-radius:9px;padding:9px 16px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:default}
.btn:hover{filter:brightness(.97)}.btn:active{transform:scale(.98)}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#fff;box-shadow:0 1px 2px rgba(0,0,0,.15)}
.btn.link{background:none;border:0;color:var(--acc);padding:6px 4px}
.btn.danger{color:#e5484d}
.btn[disabled]{opacity:.45;pointer-events:none}
footer{display:flex;justify-content:flex-end;gap:10px;padding:16px 52px 22px;border-top:1px solid var(--line);background:var(--bg)}
.chk{display:flex;align-items:center;gap:10px;margin:8px 0}
.chk .ic{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;flex:none;background:var(--field);color:var(--mute)}
.chk.done .ic{background:var(--good);color:#fff}.chk.now .ic{background:var(--accbg);color:var(--acc)}
.chk.now .ic::after{content:"";width:10px;height:10px;border-radius:50%;border:2px solid currentColor;border-right-color:transparent;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.code{font:12.5px ui-monospace,Menlo,monospace;word-break:break-all;background:var(--field);border-radius:9px;padding:12px;user-select:text;-webkit-user-select:text}
.err{color:#e5484d;margin:8px 0 0;font-weight:500}
.mono{font:12px ui-monospace,Menlo,monospace;color:var(--mute);white-space:pre-wrap;margin:0}
.badge{width:56px;height:56px;border-radius:16px;display:grid;place-items:center;margin:0 0 18px;box-shadow:0 8px 22px rgba(80,90,255,.28)}
</style></head><body>
<aside><div class="logo"><div class="mk"><svg width="22" height="22" viewBox="0 0 24 24"><path d="M4 15.5l4.2-4.2 3.3 3.3L20 6" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="20" cy="6" r="1.6" fill="#fff"/></svg></div>
<div><b>Combo Watcher</b><small>for your Mac</small></div></div>
<ol id="steps"></ol><div class="side-foot" id="sidefoot">Everything stays on this Mac.</div></aside>
<main><div class="view" id="view"></div><footer id="foot"></footer></main>
<script>
const T="__TOKEN__";const $=s=>document.querySelector(s);
const api=(p,b)=>fetch(p,b===undefined?{headers:{'X-Token':T}}:{method:'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>r.json());
const S={step:0,st:null,keyid:'',keyname:'',pair:'',mode:'install',res:null};
const STEPS=['Welcome','Tailscale','Kalshi key','Your phone','Install'];
function rail(i,done){$('#steps').innerHTML=STEPS.map((s,k)=>`<li class="${k<i||done?'done':k===i?'on':''}"><span class="n">${k<i||done?'✓':k+1}</span>${s}</li>`).join('');}
function foot(btns){$('#foot').innerHTML=btns.map(b=>`<button class="btn ${b.cls||''}" ${b.dis?'disabled':''} onclick="${b.on}">${b.t}</button>`).join('');}
function view(h){const v=$('#view');v.innerHTML=h;v.style.animation='none';v.offsetHeight;v.style.animation='';}
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function start(){S.st=await api('/api/state');S.st.installed?dash():welcome();}
function welcome(){rail(0);view(`<div class="badge" style="background:linear-gradient(145deg,#2f8cff,#7a5cff 60%,#c84bff)"><svg width="30" height="30" viewBox="0 0 24 24"><path d="M4 15.5l4.2-4.2 3.3 3.3L20 6" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div><h1>Set up your Mac as the hub</h1>
<p class="lead">Your MacBook will watch your combos around the clock, keep data fresh for your iPhone, run Combo Hub, and place the trades you tap. It takes about five minutes and needs no admin password.</p>
<div class="card"><div class="row"><div class="grow"><h3>What you'll need</h3><p>Tailscale on this Mac and your iPhone · a new Kalshi API key · your phone nearby</p></div></div></div>`);
foot([{t:'Get started',cls:'primary',on:'tail()'}]);}
async function tail(){rail(1);S.st=await api('/api/state');const ok=!!S.st.tailscale;
view(`<h1>Connect with Tailscale</h1><p class="lead">Tailscale is a free private network, so your iPhone can reach this Mac from anywhere, safely.</p>
<div class="card"><div class="row"><div class="grow"><h3>Tailscale on this Mac</h3><p>${ok?'Signed in · '+S.st.tailscale:S.st.tailscale_app?'Installed, not signed in yet':'Not installed yet'}</p></div>
<span class="pill ${ok?'good':'warn'}"><i></i>${ok?'Connected':'Waiting'}</span></div>
${ok?'':`<div class="row" style="margin-top:14px">${S.st.tailscale_app?'<button class="btn primary" onclick="api(\'/api/opentailscale\',{})">Open Tailscale</button>':'<button class="btn primary" onclick="api(\'/api/open\',{what:\'tailscale\'})">Download Tailscale</button>'}<span class="mute" style="color:var(--mute)">Sign in with the same account as your iPhone.</span></div>`}</div>`);
foot([{t:'Back',on:'welcome()'},{t:ok?'Continue':'Skip for now',cls:ok?'primary':'',on:'key()'}]);
clearTimeout(S.tt);if(!ok)S.tt=setTimeout(()=>{if($('#steps li.on')&&$('#steps li.on').textContent.includes('Tailscale'))tail();},2500);}
function key(){rail(2);const has=S.st.has_key&&S.mode!=='newkey';
view(`<h1>${has?'Kalshi is connected':'Add a Kalshi key for this Mac'}</h1>
<p class="lead">${has?'This Mac already has its own Kalshi key. You can keep it.':'Make a new API key just for this Mac, with read and write access, so you can turn it off on its own any time.'}</p>
${has?`<div class="card"><div class="row"><div class="grow"><h3>Mac's Kalshi key</h3><p>Saved privately in your home folder</p></div><span class="pill good"><i></i>Saved</span></div></div>
<button class="btn link" onclick="S.mode='newkey';key()">Use a different key…</button>`:
`<div class="card"><div class="row"><div class="grow"><h3>1 · Create the key</h3><p>Kalshi › Account › API keys › Create key</p></div><button class="btn" onclick="api('/api/open',{what:'kalshi'})">Open Kalshi</button></div></div>
<div class="card"><label>2 · Key ID</label><div class="row"><input id="kid" placeholder="e.g. a1b2c3d4-…" value="${esc(S.keyid)}" oninput="S.keyid=this.value;kv()"><button class="btn" onclick="pasteInto('kid')">Paste</button></div></div>
<div class="card"><label>3 · Private key</label><div class="row"><div class="grow"><p id="kname">${S.keyname?'✓ '+esc(S.keyname):'The file Kalshi downloaded (usually in Downloads)'}</p></div>
<button class="btn" onclick="chooseKey()">Choose file…</button><button class="btn link" onclick="pasteKey()">Paste instead</button></div><div class="err" id="kerr"></div></div>`}`);
kv();}
function kv(){const has=S.st.has_key&&S.mode!=='newkey';foot([{t:'Back',on:'tail()'},{t:'Continue',cls:'primary',dis:!has&&!(S.keyid.trim()&&S.keyname),on:'phone()'}]);}
async function pasteInto(id){const r=await api('/api/paste',{});$('#'+id).value=r.text.trim();$('#'+id).dispatchEvent(new Event('input'));}
async function chooseKey(){const r=await api('/api/choosekey',{});if(r.ok){S.keyname=r.name;$('#kname').textContent='✓ '+r.name;$('#kerr').textContent='';}else if(r.error)$('#kerr').textContent=r.error;kv();}
async function pasteKey(){const t=(await api('/api/paste',{})).text;const r=await api('/api/pastekey',{pem:t});
 if(r.ok){S.keyname=r.name;$('#kname').textContent='✓ '+r.name;$('#kerr').textContent='';}else $('#kerr').textContent=r.error+' Copy the whole key first, then tap Paste instead.';kv();}
function phone(){rail(3);if(S.st.installed){return install();}
view(`<h1>Link your iPhone</h1><p class="lead">Paste the pairing code from the planner on your phone, so your alerts and settings keep working. No code yet? Leave it empty and we'll make a new one.</p>
<div class="card"><label>Pairing code <span style="color:var(--mute);font-weight:400">· planner › Settings › Pi watcher</span></label>
<textarea id="pair" placeholder="Paste the code here (copy it on your iPhone; with Handoff it pastes on this Mac)" oninput="S.pair=this.value">${esc(S.pair)}</textarea>
<div class="row" style="margin-top:10px"><button class="btn" onclick="pasteInto('pair')">Paste</button></div></div>`);
foot([{t:'Back',on:'key()'},{t:'Install',cls:'primary',on:'install()'}]);}
const LABELS={python:'Preparing Python',download:'Downloading the planner',key:'Saving your Kalshi key',pairing:'Linking your phone',start:'Starting the watcher',kalshi:'Checking your Kalshi account'};
async function install(){rail(4);foot([]);
const r=await api('/api/install',{mode:S.mode,keyid:S.keyid,pair:S.pair});
if(!r.ok){view(`<h1>Almost</h1><p class="err">${esc(r.error)}</p>`);foot([{t:'Back',on:'key()'}]);return;}
poll();}
async function poll(){const p=await api('/api/progress');const order=Object.keys(LABELS);const cur=p.steps[p.steps.length-1];
view(`<h1>${p.done?(p.error?'Something went wrong':'All set'):'Setting up…'}</h1><p class="lead">${p.done?'':'This takes a minute or two. You can leave this window open.'}</p>
<div class="card">${order.map(k=>{const i=p.steps.indexOf(k);const st=i<0?'':(k===cur&&!p.done?'now':'done');return `<div class="chk ${st}"><span class="ic">${st==='done'?'✓':''}</span>${LABELS[k]}</div>`}).join('')}</div>
${p.error?`<div class="card"><p class="err">${esc(p.error)}</p></div>`:''}`);
if(!p.done){setTimeout(poll,700);return;}
if(p.error){foot([{t:'Back',on:'key()'},{t:'Try again',cls:'primary',on:'install()'}]);return;}
S.res=p.result;rail(5,true);done();}
function done(){const r=S.res||{},ok=(r.kalshi||'').startsWith('ok');
view(`<div class="badge" style="background:linear-gradient(145deg,#34c759,#1f9d55);box-shadow:0 8px 22px rgba(31,157,85,.3)"><svg width="30" height="30" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></div><h1>Your Mac is the hub</h1><p class="lead">It's running in the background and starts by itself after a restart. Keep it plugged in with the lid open.</p>
<div class="card"><div class="row"><div class="grow"><h3>Kalshi</h3><p>${ok?'Connected':'Still connecting: this can take a minute after starting'}</p></div><span class="pill ${ok?'good':'wait'}"><i></i>${ok?'Connected':'Connecting'}</span></div></div>
${r.changed==='yes'||r.topic?`<div class="card"><h3>On your iPhone</h3><p style="margin-bottom:10px">Planner › Settings › Pi watcher: replace the code with this one and tap Save.</p>
<div class="code">${esc(r.code)}</div><div class="row" style="margin-top:10px"><button class="btn primary" onclick="copy('${esc(r.code)}',this)">Copy code</button></div></div>`:''}
${r.topic?`<div class="card"><h3>Alerts</h3><p>In the ntfy app on your iPhone, subscribe to <b class="code" style="display:inline;padding:2px 6px">${esc(r.topic)}</b></p></div>`:''}
<div class="card"><div class="row"><div class="grow"><h3>Combo Hub</h3><p>The planner in your browser · passcode ${esc(r.pass||'')}</p></div><button class="btn" onclick="api('/api/open',{what:'hub'})">Open</button></div></div>
${S.keyname&&S.keyname!=='Pasted key'?'<button class="btn link" onclick="api(\'/api/trashkey\',{});this.textContent=\'Moved the key file to the Trash ✓\'">Move the downloaded key file to the Trash</button>':''}`);
foot([{t:'Done',cls:'primary',on:"api('/api/quit',{})"}]);}
async function copy(t,b){await api('/api/copy',{text:t});b.textContent='Copied ✓';}
async function dash(){S.st=await api('/api/state');const s=S.st;$('#steps').innerHTML='';$('#sidefoot').textContent='Combo Watcher '+(s.version?'v'+s.version:'');
const ts=!!s.tailscale,run=s.running,k=s.kalshi==='ok';
view(`<h1>Combo Watcher</h1><p class="lead">Your Mac is ${run?'watching your combos and serving your iPhone.':'set up, but the watcher isn\'t running right now.'}</p>
<div class="card"><div class="row"><div class="grow"><h3>Watcher</h3><p>${run?'Running'+(s.version?' · v'+s.version:''):'Stopped'}</p></div><span class="pill ${run?'good':'warn'}"><i></i>${run?'Running':'Stopped'}</span></div></div>
<div class="card"><div class="row"><div class="grow"><h3>Kalshi</h3><p>${k?'Connected':s.kalshi==='trying'?'Retrying the connection':'Not checked yet'}</p></div><span class="pill ${k?'good':'wait'}"><i></i>${k?'Connected':'Checking'}</span></div></div>
<div class="card"><div class="row"><div class="grow"><h3>Tailscale</h3><p>${ts?s.tailscale+' · reachable from your iPhone':'Not signed in: your phone can\'t reach this Mac'}</p></div><span class="pill ${ts?'good':'warn'}"><i></i>${ts?'Connected':'Off'}</span></div></div>
<div class="card"><h3 style="margin-bottom:8px">Recent activity</h3><pre class="mono">${esc((s.log||[]).slice(-8).join('\n'))||'Nothing yet'}</pre></div>
<div class="row" style="gap:8px;flex-wrap:wrap;max-width:560px">
<button class="btn" onclick="showCode()">Phone pairing code</button><button class="btn" onclick="passcode()">Change passcode</button>
<button class="btn" onclick="S.mode='newkey';S.st.has_key=false;key();foot([{t:'Back',on:'dash()'},{t:'Save key',cls:'primary',on:'install()'}])">Replace Kalshi key</button>
<button class="btn danger" onclick="removeIt()">Remove…</button></div>`);
foot([{t:'Open Combo Hub',on:"api('/api/open',{what:'hub'})"},{t:'Update now',cls:'primary',on:"S.mode='repair';rail(4);install()"}]);
clearTimeout(S.dt);S.dt=setTimeout(()=>{if($('#steps').innerHTML===''&&document.querySelector('h1').textContent==='Combo Watcher')dash();},5000);}
async function showCode(){const r=await api('/api/code',{});view(`<h1>Phone pairing code</h1><p class="lead">On your iPhone: planner › Settings › Pi watcher. You only need this if you're pairing a new phone.</p>
<div class="card"><div class="code">${esc(r.CODE)}</div><div class="row" style="margin-top:10px"><button class="btn primary" onclick="copy('${esc(r.CODE)}',this)">Copy code</button></div></div>
<div class="card"><h3>Combo Hub</h3><p>${esc(r.HUB||'')} · passcode ${esc(r.PASS||'')}</p></div>`);foot([{t:'Back',cls:'primary',on:'dash()'}]);}
function passcode(){view(`<h1>Combo Hub passcode</h1><p class="lead">Needed only on devices other than this Mac and your iPhone's Open Combo Hub link.</p>
<div class="card"><label>New passcode</label><input id="np" type="text" placeholder="At least 6 characters"><div class="err" id="perr"></div></div>`);
foot([{t:'Back',on:'dash()'},{t:'Save',cls:'primary',on:'savePass()'}]);}
async function savePass(){const r=await api('/api/passcode',{pass:$('#np').value});if(r.ok)dash();else $('#perr').textContent=r.error;}
function removeIt(){view(`<h1>Remove Combo Watcher?</h1><p class="lead">It stops and won't start again. Your files stay in your home folder. Remember to turn off its Kalshi API key on Kalshi.</p>`);
foot([{t:'Cancel',on:'dash()'},{t:'Remove',cls:'primary',on:"api('/api/uninstall',{}).then(dash)"}]);}
start();
</script></body></html>"""


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={TOKEN}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    opened_window = False
    if os.path.exists(WINDOW_JS) and shutil.which("osascript"):
        t0 = time.time()
        p = subprocess.Popen(["osascript", "-l", "JavaScript", WINDOW_JS, url, ICON],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            p.wait(timeout=4)
        except subprocess.TimeoutExpired:
            opened_window = True
            p.wait()                                    # the window is open: wait until it's closed
            return 0
        if time.time() - t0 < 4:
            sys.stderr.write((p.stderr.read() or b"").decode()[-400:])
    if not opened_window:                               # no window: use the browser instead
        subprocess.run(["open", url])
        while time.time() - LAST["t"] < 1800:
            time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
