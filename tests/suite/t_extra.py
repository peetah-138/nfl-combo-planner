import os,time,tempfile,importlib.util
os.environ["COMBOWATCH_HOME"]=os.path.abspath("wahome")
spec=importlib.util.spec_from_file_location("E","wahome/engine.py");E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))  # midday "Pacific" whenever it runs, so the fake games (2.5 h out) are in today's panel day
E.store_open(os.path.join(tempfile.mkdtemp(),"h.db")); E.HERE=tempfile.mkdtemp(); E.SIZING_FILE=os.path.join(E.HERE,"s.json"); E.CUTOFF_FILE=os.path.join(E.HERE,"c.json")
E.REBUILD_FLAG=os.path.join(E.HERE,"flag")
E.fetch_account=lambda **k: ([],300.0,None)
ok=lambda n,c: print(("PASS " if c else "FAIL ")+n)
now=time.time()
def mk(t,ev,f,p,k):
    l={"ticker":t,"event":ev,"pick":t,"p":p,"fair":f}; E.KICKOFF[ev]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(k))
    return E._cand("single","nba",[l],f,(f-p-E.single_fee(p))/(p+E.single_fee(p)),"w",price=p)
E.PANEL_POOL={"nba":(now,[mk("N1","KXNBAGAME-1",.6,.52,now+9000),mk("N2","KXNBAGAME-2",.58,.5,now+9000)])}
E.panel_pass(); E.panel_approve(None,"all")
first_ids={c["id"] for c in E.panel_get()["items"]}
# a new good bet turns up after approval
E.PANEL_POOL["nba"]=(now,E.PANEL_POOL["nba"][1]+[mk("N3","KXNBAGAME-3",.62,.52,now+9000)])
msgs=E.panel_pass()
x=E.panel_get("extra")
ok("extras exclude games already on the panel", x and all(c["id"] not in first_ids for c in x["items"]) and any("N3" in c["id"] for c in x["items"]))
ok("you're told about it once", any(m.startswith("🆕") for m in msgs) and not any(m.startswith("🆕") for m in E.panel_pass()))
okA,msg=E.panel_add([c["id"] for c in x["items"]],"extra"); ok("add extras to today's panel", okA and any("N3" in c["id"] and c["state"]=="scheduled" for c in E.panel_get()["items"]))
ok("approval kept", E.panel_get()["status"]=="approved")
# rebuild flag
E.panel_cancel(); okR,msg=E.panel_restart()
ok("restart asks the Mac to rebuild now", os.path.exists(E.REBUILD_FLAG) and "watch it here" in msg and "minute" not in msg)
ok("the request is taken once", E.rebuild_asked() and not E.rebuild_asked())
E.NEXT_KICK={"nba":now+3600,"nfl":now+5*86400}; ok("near-game sports found", E.sports_near()==["nba"])
