# CHECK: group=engine
import os,sys,time,tempfile,random,types
os.environ["COMBOWATCH_HOME"]=os.path.abspath("wahome")
import importlib.util
spec=importlib.util.spec_from_file_location("E","wahome/engine.py");E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
ok=lambda name,cond: print(("PASS " if cond else "FAIL ")+name)
now=time.time()
def leg(t,ev,pick,p,fair): return {"ticker":t,"event":ev,"pick":pick,"p":p,"fair":fair}
def mk(kind,code,legs,chance,ret,kick,**x):
    for l in legs: E.KICKOFF[l["event"]]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(kick))
    return E._cand(kind,code,legs,chance,ret,"why",**x)
A=mk("single","nba",[leg("G1-A","KXNBAGAME-1","Alpha",.50,.56)],.56,.08,now+3*3600,price=.50)
C=mk("combo","nba",[leg("G1-B","KXNBAGAME-1","Beta",.45,.44),leg("G2-C","KXNBAGAME-2","Gamma",.6,.62)],.44*.62,-.04,now+3*3600,pct=.96,fair_mult=1/(.44*.62))
tot=E._sim_panel([dict(A,stake=1),dict(C,stake=1)],n=5000)
ok("#7 sim: single on A and combo with B never both pay", max(tot) < 3.0)
# S1 on many candidates
rng=random.Random(5); cands=[]
for i in range(60):
    f=rng.uniform(.35,.8); p=round(f-rng.uniform(0.0,0.06),2)
    x=leg(f"S{i}-A",f"KXNBAGAME-{i}","T%d"%i,p,f)
    edge=f-p-E.single_fee(p)
    cands.append(mk("single","nba",[x],f,edge/(p+E.single_fee(p)),now+3*3600+i*60,price=p))
picked,st=E.choose_panel(cands,40,300,size=10)
print("S1 panel:",len(picked),"bets, $",st["stake"],"p_ahead",st["p_ahead"])
ok("S1 panel uses more than 3 bets", len(picked)>3)
# passkeys removed on passcode change
sys.argv=["x"]; os.environ["COMBOWATCH_HOME"]=tempfile.mkdtemp()
spec=importlib.util.spec_from_file_location("W","wtest/combo_watcher.py");W=importlib.util.module_from_spec(spec);spec.loader.exec_module(W)
conf={"web_pass":"abcdefgh","passkeys":[{"id":"x","rp":"r"}]}
web=W.Web(conf,types.SimpleNamespace(save_json=lambda *a:0)); web.keep_only("tok")
ok("#16 passcode change removes Face ID", conf["passkeys"]==[])
pool=[dict(c, stake=E._size(c, 300)) for c in cands if E._qualifies(c)]
print("qualifying:",len(pool), "stakes:", sorted({c["stake"] for c in pool})[:6])
order=[]
P=E.PANEL 
# replicate greedy order quickly via choose with tolerance huge
E_choose=E.choose_panel
src=open("wahome/engine.py").read()
