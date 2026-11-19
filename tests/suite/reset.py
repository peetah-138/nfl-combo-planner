import json, os
s = json.load(open("run/combo_settings.json"))
s.update(kalshi_key_id="fake-key-id", odds_key="abc", auto_sell=False, ride=2, auto_cash=True, tp_auto=False, auto_cap=5, hedge_cap=100)
json.dump(s, open("run/combo_settings.json", "w"))
json.dump({"league": "nfl"}, open("run/combo_league.json", "w"))
for f in "combo_buy_ratio.json combo_check.py combo_widget.py combo_hedges.json combo_autosell_log.jsonl combo_pi_approve.json closing_chances.json combo_quote_times.json combo_settings_mix.json".split():
    try: os.remove("run/" + f)
    except FileNotFoundError: pass
for f in os.listdir("run"):
    if f.startswith("combo_settings_") and any(k in f for k in ("soccer", "ufc", "tennis", "ncaamb", "ncaawb", "euroleague")): os.remove("run/" + f)
# the web app's own settings (wahome): back to the starting point, so one test's choices (e.g. "tomorrow's games")
# never leak into the next
import shutil
if os.path.isdir("wahome"):
    for f in os.listdir("wahome"):
        if f.startswith("combo_settings_") and f.endswith(".json"):
            os.remove("wahome/" + f)
    if os.path.exists("fixtures/home_settings.json"):
        shutil.copy("fixtures/home_settings.json", "wahome/combo_settings.json")
# a requested panel rebuild (flag and progress note) never carries into the next test
for f in ("wahome/panel_rebuild.flag", "wahome/combo_rebuild.json"):
    try: os.remove(f)
    except FileNotFoundError: pass
