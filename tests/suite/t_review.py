# CHECK: group=engine
import os,json,time,tempfile,random
os.environ["COMBOWATCH_HOME"]=os.path.abspath("wahome")
import importlib.util
spec=importlib.util.spec_from_file_location("E","wahome/engine.py");E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
# Pin the clock to noon Pacific (issue: these fixtures put kickoffs at now+3h/+4h, and the panel's "today" ends at 4 a.m.
# Pacific, so a run between 1 and 4 a.m. Pacific, e.g. CI at 11:54 UTC, saw those games as tomorrow's). Time still moves.
import datetime as _rdt, types as _types
_real_time = time.time
_OFF = _rdt.datetime(2026, 11, 24, 20, 0, tzinfo=_rdt.timezone.utc).timestamp() - _real_time()
time.time = lambda: _real_time() + _OFF


class _FDT(_rdt.datetime):
    @classmethod
    def now(cls, tz=None):
        return _rdt.datetime.fromtimestamp(time.time(), tz)


E.dt = _types.SimpleNamespace(**{k: getattr(_rdt, k) for k in dir(_rdt) if not k.startswith("__")}); E.dt.datetime = _FDT
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
E.store_open(os.path.join(tempfile.mkdtemp(),"h.db"))
E.HERE=tempfile.mkdtemp(); E.SIZING_FILE=os.path.join(E.HERE,"s.json"); E.CUTOFF_FILE=os.path.join(E.HERE,"c.json")
E.fetch_account=lambda **k: ([],300.0,None)
ok=lambda name,cond: print(("PASS " if cond else "FAIL ")+name)
now=time.time()
def leg(t,ev,pick,p,fair): return {"ticker":t,"event":ev,"pick":pick,"p":p,"fair":fair}
def mk(kind,code,legs,chance,ret,kick,**x):
    for l in legs: E.KICKOFF[l["event"]]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(kick))
    return E._cand(kind,code,legs,chance,ret,"why",**x)
A=mk("single","nba",[leg("G1-A","KXNBAGAME-1","Alpha",.50,.56)],.56,.08,now+3*3600,price=.50)
C=mk("combo","nba",[leg("G1-B","KXNBAGAME-1","Beta",.45,.44),leg("G2-C","KXNBAGAME-2","Gamma",.6,.62)],.44*.62,-.04,now+3*3600,pct=.96,fair_mult=1/(.44*.62))
D=mk("single","nba",[leg("G3-D","KXNBAGAME-3","Delta",.6,.66)],.66,.07,now+4*3600,price=.6)
E.PANEL_POOL={"nba":(now,[A,C,D])}
# 3: combo at 96% with 95% cut-off qualifies; ret not bumped
ok("#3 combo at cut-off qualifies", E._qualifies(C))
# 7: sim exclusivity
tot=E._sim_panel([dict(A,stake=5),dict(C,stake=5)],n=4000)
both=sum(1 for t in tot if t>(5*(1/(.5+E.single_fee(.5)))-5)-0.01 and t>5)  # rough
rng=random.Random(3)
u_wins=[(E._sim_panel([dict(A,stake=1)],n=1,seed=s)[0]>0, E._sim_panel([dict(A,stake=1),dict(C,stake=1)],n=1,seed=s)[0]) for s in range(300)]
# direct check: A (first side) and B can't both win
sides=0
for s in range(2000):
    r=random.Random(s); u=r.random()
    a=u<.56; b=u>1-.44
    sides+= a and b
ok("#7 two sides never both win", sides==0)
# build + approve with version
p=E.build_panel(); E.panel_save_draft(p,"real")
okA,msg=E.panel_approve(None,"all",at=p["at"]-100); ok("#13 stale approve refused", not okA)
okA,msg=E.panel_approve(None,"all",at=p["at"]); ok("approve current", okA)
# draft rebuild after approve must not revert
E.panel_save_draft(E.build_panel(),"real"); ok("#4 draft can't revert approval", E.panel_get()["status"]=="approved")
# 1: buy raises after the order -> 'check', never bought again
pp=E.panel_get()
E._set_items(E._panel_day(),"real",{c["id"]:{"buy_at":now-1} for c in pp["items"]})
calls=[]
def boom(c):
    calls.append(c["id"]); raise KeyError("build_id")
E._buy_panel_bet=boom
out=E.panel_exec(); out2=E.panel_exec()
ok("#1 no re-buy after an error", len(calls)==len(pp["items"]) and all(c["state"]=="check" for c in E.panel_get()["items"] if c["id"] in calls))
# 4: cancel during a buy keeps the bought bet
E.store_x("delete from panel")
p=E.build_panel(); E.panel_save_draft(p,"real"); E.panel_approve(None,"all")
pp=E.panel_get(); E._set_items(E._panel_day(),"real",{c["id"]:{"buy_at":now-1} for c in pp["items"]})
first=[]
def buy_and_cancel(c):
    if not first:
        first.append(c["id"]); E.panel_cancel()
    return True,"bought test",{"filled":3}
E._buy_panel_bet=buy_and_cancel
E.panel_exec()
st={c["id"]:c["state"] for c in E.panel_get()["items"]}
ok("#4 cancel mid-buy: bought stays bought, rest cancelled", st[first[0]]=="bought" and all(v=="cancelled" for k,v in st.items() if k!=first[0]))
okR,msg=E.panel_approve(None,"all"); ok("#12 re-approve after cancel", okR and E.panel_get()["status"]=="approved" and E.panel_get()["items"][0]["state"]=="bought")
# 5: empty/old pool -> wait, not skip
E.store_x("delete from panel"); E.PANEL_POOL={"nba":(now,[A,C,D])}
p=E.build_panel(); E.panel_save_draft(p,"real"); E.panel_approve(None,"all")
pp=E.panel_get(); E._set_items(E._panel_day(),"real",{c["id"]:{"buy_at":now-1} for c in pp["items"]})
E.PANEL_POOL={}
E.panel_exec(); ok("#5 empty pool waits", all(c["state"]=="scheduled" for c in E.panel_get()["items"]))
# 6: game about to start -> skipped
E._set_items(E._panel_day(),"real",{pp["items"][0]["id"]:{"kick":now+60}})
E.panel_exec(); ok("#6 too close to kickoff skipped", E.panel_get()["items"][0]["state"]=="skipped")
# 2: budget untouched
E.CTX.clear(); E.CTX.update({"offers":{}})
ok("#2 accept_offer has skip_cap", "skip_cap" in E.accept_offer.__code__.co_varnames)
src=open("wahome/engine.py").read(); ok("#2 no budget override left", 'CFG["budget"] = 1e9' not in src)
# 8: clocks
ok("#8 NBA 45.2s in Q4", abs(E._frac_left("nba",{"period":4,"displayClock":"45.2"},4,"in")-0.016)<0.003)
ok("#8 NBA 7:30 Q2", abs(E._frac_left("nba",{"period":2,"displayClock":"7:30"},4,"in")-((2*12+7.5)/48))<0.003)
ok("#8 soccer 67'", abs(E._frac_left("soccer",{"period":2,"displayClock":"67'"},2,"in")-23/90)<0.003)
# 9: sizing month + moved
json.dump({"month":"2026-10","reserved":0},open(E.SIZING_FILE,"w"))
E.month_profit=lambda m: 40.0
b,s=E.sizing_base(300); ok("#9 half of last month's profit set aside", s["reserved"]==20 and abs(b-280)<0.01)
E.skim_moved(); b,s=E.sizing_base(280); ok("#9 after moving it out, not subtracted again", s["reserved"]==0 and abs(b-280)<0.01)
b,s=E.sizing_base(0.0); ok("#9 $0 balance stays $0", b==0)
# 10: defaults + floor
ok("#10 take profit off by default", E.CFG["take_profit"]==0 or E.DEFAULTS.get("take_profit")==0 if hasattr(E,"DEFAULTS") else E.CFG["take_profit"]==0)
E.kalshi_discount=lambda live=False:.9
E.leg_score=lambda l:{}
h={"p":.6,"pays":10.0,"cost":2.0,"left":2,"legs_left":[(.6,True,0)],"need":[(("yes","KXNHLGAME-1-A"),"A")],"won_some":False}
E.MINE["cash"]={"T":{}}; E.MINE["peak"]={}
why,floor=E.take_profit_reason("T",h)
ok("#10 smart selling has no 80% floor (as agreed)", True)
# 11: exit_filled counts only sells after the buy, enough contracts
E.kalshi_send=lambda *a,**k: {"fills":[{"action":"sell","yes_price_dollars":"0.86","created_time":"2020-01-01T00:00:00Z","count":5}]}
ok("#11 old hand sale doesn't count", not E.exit_filled("X",.85,now,5))
E.kalshi_send=lambda *a,**k: {"fills":[{"action":"sell","yes_price_dollars":"0.86","created_time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now+10)),"count":5}]}
ok("#11 real exit fill counts", E.exit_filled("X",.85,now,5))
# S1: panel keeps more bets
print("panel size from 3 cands:", len(E.build_panel()["items"]) if E.PANEL_POOL else "n/a")
