# install_planner.py - one-time switch to the auto-updating NFL combo planner.
# Paste this into a new Pythonista file and tap Run once. It:
#   1. downloads the latest planner from your GitHub repo,
#   2. checks it's complete and runs on this phone's Python,
#   3. saves your current planner as nfl_combo_planner_backup.py,
#   4. installs the new one as nfl_combo_planner.py.
# Your settings, keys and history are separate files and aren't touched.
# After this, use the Update button inside the planner instead.
import os, re, requests

URL = "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/nfl_combo_planner.py"
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "nfl_combo_planner.py")


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
        compile(src, "nfl_combo_planner.py", "exec")
    except SyntaxError as err:
        return print(f"The download has a problem (line {err.lineno}). Nothing was changed.")
    if os.path.exists(TARGET):
        with open(TARGET, encoding="utf-8") as f:
            old = f.read()
        with open(os.path.join(HERE, "nfl_combo_planner_backup.py"), "w", encoding="utf-8") as f:
            f.write(old)
        print("Saved your current planner as nfl_combo_planner_backup.py")
    with open(TARGET + ".new", "w", encoding="utf-8") as f:
        f.write(src)
    os.replace(TARGET + ".new", TARGET)
    print(f"Installed version {ver.group(1)}.")
    print("Done! Open nfl_combo_planner.py and tap Run. From now on, use its Update button.")
    print("You can delete this install_planner.py file.")


main()
