import os,importlib.util
os.environ["COMBOWATCH_HOME"]=os.path.abspath("wahome")
spec=importlib.util.spec_from_file_location("E","wahome/engine.py");E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
ok=lambda n,c: print(("PASS " if c else "FAIL ")+n)
# two games whose teams share mascots ("Bears", "Seahawks"-style collisions)
E.espn_lines=lambda code:{
 frozenset({"brown bears","unc wilmington seahawks"}):{"home":"Brown Bears","away":"UNC Wilmington Seahawks","home_abbr":"BRWN","away_abbr":"UNCW","spread_home":-4.5,"total":140,"start":None},
 frozenset({"baylor bears","tennessee tech golden eagles"}):{"home":"Baylor Bears","away":"Tennessee Tech Golden Eagles","home_abbr":"BAY","away_abbr":"TNTC","spread_home":-18.5,"total":145,"start":None}}
def m(ev,tk,sub,strike,p): return {"ticker":tk,"event_ticker":ev,"yes_sub_title":sub,"floor_strike":strike,"yes_ask_dollars":str(p+.01),"yes_bid_dollars":str(p-.01),"last_price_dollars":str(p),"kind":"spread"}
E.line_markets=lambda code:[
 m("KXNCAAMBSPREAD-26NOV18UNCWBRWN","KXNCAAMBSPREAD-26NOV18UNCWBRWN-UNCW1","UNC Wilmington wins by over 1.5 Points",1.5,.30),
 m("KXNCAAMBSPREAD-26NOV18UNCWBRWN","KXNCAAMBSPREAD-26NOV18UNCWBRWN-BRWN4","Brown wins by over 4.5 Points",4.5,.48),
 m("KXNCAAMBSPREAD-26NOV18TNTCBAY","KXNCAAMBSPREAD-26NOV18TNTCBAY-BAY17","Baylor wins by over 17.5 Points",17.5,.47),
 m("KXNCAAMBSPREAD-26NOV18XXXYYY","KXNCAAMBSPREAD-26NOV18XXXYYY-XXX3","Bears win by over 3.5 Points",3.5,.2)]
E.price=lambda mm: float(mm["last_price_dollars"])
out={x["ticker"]:x for x in E.line_candidates("ncaamb",everything=True)}
for t,x in out.items(): print(" ",x["pick"],"fair",x["fair"],"price",x["p"])
u=out.get("KXNCAAMBSPREAD-26NOV18UNCWBRWN-UNCW1")
ok("underdog UNCW +1.5 gets an underdog chance (<50%)", u and u["fair"]<0.5)
ok("Brown -4.5 near 50%", out.get("KXNCAAMBSPREAD-26NOV18UNCWBRWN-BRWN4") and 0.4<out["KXNCAAMBSPREAD-26NOV18UNCWBRWN-BRWN4"]["fair"]<0.6)
ok("unknown game skipped, not matched by 'Bears'", "KXNCAAMBSPREAD-26NOV18XXXYYY-XXX3" not in out)
ok("no wild disagreements with the market", all(abs(x["fair"]-x["p"])<=0.15 for x in out.values()))
