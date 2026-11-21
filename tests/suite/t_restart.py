import os,time,tempfile,importlib.util
os.environ["COMBOWATCH_HOME"]=os.path.abspath("wahome")
spec=importlib.util.spec_from_file_location("E","wahome/engine.py");E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))  # midday "Pacific" whenever it runs, so the fake games (2.5 h out) are in today's panel day
E.store_open(os.path.join(tempfile.mkdtemp(),"h.db")); E.HERE=tempfile.mkdtemp(); E.SIZING_FILE=os.path.join(E.HERE,"s.json"); E.CUTOFF_FILE=os.path.join(E.HERE,"c.json")
E.fetch_account=lambda **k: ([],300.0,None)
ok=lambda n,c: print(("PASS " if c else "FAIL ")+n)
now=time.time()
def mk(t,ev,f,p,k):
    l={"ticker":t,"event":ev,"pick":t,"p":p,"fair":f}; E.KICKOFF[ev]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(k))
    return E._cand("single","nba",[l],f,(f-p-E.single_fee(p))/(p+E.single_fee(p)),"w",price=p)
E.PANEL_POOL={"nba":(now,[mk("N1","KXNBAGAME-1",.6,.52,now+9000),mk("N2","KXNBAGAME-2",.58,.5,now+9000),mk("N3","KXNBAGAME-3",.62,.53,now+9000)])}
E.panel_pass(); E.panel_approve(None,"all")
first=E.panel_get()["items"][0]["id"]
E._set_items(E._panel_day(),"real",{first:{"state":"bought"}})
E.panel_cancel()
okR,msg=E.panel_restart(); print(msg)
ok("restart accepted", okR)
ok("no current panel until the Mac rebuilds", E.panel_get() is None)
E.panel_pass(); p=E.panel_get()
ok("fresh draft built", p and p["status"]=="draft")
ok("budget reduced by what was already bought", abs(p["budget"]-(E.CFG.get("panel_budget",40)-E.spent_earlier_today()))<0.01 and E.spent_earlier_today()>0)
ok("bought bet still on the record", any(c["id"]==first and c.get("state")=="bought" for c in E.day_items(E._panel_day())))
ok("approve works on the fresh panel", E.panel_approve(None,"all")[0])
ok("fresh panel doesn't bet the same game again", all(first != c["id"] for c in E.panel_get()["items"]))
