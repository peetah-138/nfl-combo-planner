# install_planner.py - installs (or repairs) the Kalshi combo planner.
# Paste this into a new Pythonista file and tap Run once. It:
#   1. downloads the latest planner from GitHub and checks it runs on this phone's Python,
#   2. saves it as combo_planner_engine.py (a large file: don't open it in the editor),
#   3. makes nfl_combo_planner.py a tiny 3-line file that starts it. Open and Run that one.
# Your Kalshi key, settings and history are separate files and aren't touched.
# After this, use Check for updates inside the planner.
import os, re, requests

URL = "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/nfl_combo_planner.py"
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "combo_planner_engine.py")
LAUNCHER = os.path.join(HERE, "nfl_combo_planner.py")
LAUNCHER_CODE = '''# Kalshi combo planner (NFL and college basketball). Tap Run.
# The planner itself is combo_planner_engine.py. Don't open that one: it's large and updates replace it.
import os, runpy; runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "combo_planner_engine.py"), run_name="__main__")
'''


def to_txt(path):
    """Keep big old copies out of the editor: rename x.py to x.txt."""
    if os.path.exists(path):
        os.replace(path, path[:-3] + ".txt")
        print("Renamed", os.path.basename(path), "to", os.path.basename(path)[:-3] + ".txt")


def main():
    print("Downloading the planner...")
    try:
        r = requests.get(URL, timeout=30, headers={"Cache-Control": "no-cache"})
        r.raise_for_status()
    except requests.RequestException as err:
        return print(f"Couldn't download it ({err}). Check your connection and run this again.")
    src = r.content.decode("utf-8")
    ver = re.search(r'^VERSION = "([0-9.]+)"', src, re.M)
    if not ver or "def main():" not in src or len(src) < 50000:
        return print("The download didn't look like the complete planner. Nothing was changed.")
    try:
        compile(src, "combo_planner_engine.py", "exec")
    except SyntaxError as err:
        return print(f"The download has a problem (line {err.lineno}). Nothing was changed.")
    # an old full-size planner in the file you tap becomes a .txt backup
    if os.path.exists(LAUNCHER) and os.path.getsize(LAUNCHER) > 5000:
        with open(LAUNCHER, encoding="utf-8", errors="replace") as f:
            old = f.read()
        with open(os.path.join(HERE, "nfl_combo_planner_backup.txt"), "w", encoding="utf-8") as f:
            f.write(old)
        print("Saved your old planner as nfl_combo_planner_backup.txt")
    to_txt(os.path.join(HERE, "nfl_combo_planner_backup.py"))
    with open(ENGINE + ".new", "w", encoding="utf-8") as f:
        f.write(src)
    os.replace(ENGINE + ".new", ENGINE)
    with open(LAUNCHER + ".new", "w", encoding="utf-8") as f:
        f.write(LAUNCHER_CODE)
    os.replace(LAUNCHER + ".new", LAUNCHER)
    print(f"Installed version {ver.group(1)}.")
    print("Done! Open nfl_combo_planner.py (it's only 3 lines now) and tap Run.")
    print("You can delete this install_planner.py file.")


main()
