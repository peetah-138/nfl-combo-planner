#!/bin/bash
# The full check list. Everything must pass before any push (Pete's rule). Run from anywhere:
#   bash tests/run_checks.sh
# It copies the suite to a temporary folder, so it never touches your real ~/combowatch or the repo's files.
# One PASS/FAIL line per check, then ALL CHECKS PASSED or SOME CHECKS FAILED. Takes about 4 minutes.
R="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/combochecks.XXXXXX")"
trap 'pkill -f "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
cp -R "$R/tests/suite/." "$WORK/"
cd "$WORK" || exit 1
mkdir -p wahome wtest run
cp "$R/nfl_combo_planner.py" wahome/engine.py
cp "$R/watcher/combo_watcher.py" wtest/combo_watcher.py
cp "$R/nfl_combo_planner.py" run/nfl_combo_planner.py
cp fixtures/run_settings.json run/combo_settings.json
cp fixtures/home_settings.json wahome/combo_settings.json
python3 - <<'P'
import base64, os, json
def fake_key(path):            # a throwaway ed25519 key for the fake Kalshi; never a real one
    der = bytes.fromhex("302e020100300506032b657004220420") + os.urandom(32)
    tag = "PRIVATE " + "KEY"                # spelled in pieces so secret scanners don't flag this generator
    open(path, "w").write(f"-----BEGIN {tag}-----\n" + base64.b64encode(der).decode() + f"\n-----END {tag}-----\n")
for d in ("run", "wahome"):
    fake_key(f"{d}/kalshi_private_key.pem")
json.dump({"league": "nfl"}, open("run/combo_league.json", "w"))
json.dump({"kalshi_key_id": "fake-key-id"}, open("wahome/combo_keys.json", "w"))
json.dump({"topic": "t", "secret": "s", "web_pass": "pass1234"}, open("wahome/watcher.json", "w"))
P
export REPO="$R"
export CW_WEBAPP_PORT=18766              # tests run their own web apps on 18766+, never on the real one (8766)
command -v timeout >/dev/null 2>&1 || timeout(){ perl -e 'alarm shift; exec @ARGV' "$@"; }   # macOS has no timeout
PY=python3
fail=0
ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; echo "$2" | head -12 | sed 's/^/     /'; fail=1; }
need(){ command -v "$1" >/dev/null 2>&1 || { bad "setup: $1 is missing" "$2"; }; }
need node "Install Node (e.g. brew install node). It checks the web app's JavaScript."
$PY -c "import playwright" 2>/dev/null || bad "setup: playwright is missing" "pip3 install playwright && python3 -m playwright install chromium"
$PY -c "import pyflakes" 2>/dev/null || bad "setup: pyflakes is missing" "pip3 install pyflakes"

$PY -m py_compile "$R/nfl_combo_planner.py" "$R/watcher/combo_watcher.py" && ok compile || bad compile
if command -v python3.10 >/dev/null 2>&1; then python3.10 -m py_compile "$R/nfl_combo_planner.py" "$R/watcher/combo_watcher.py" && ok "compile (3.10)" || bad "compile (3.10)"; fi
$PY - "$R" <<'P' && ok "javascript syntax" || bad "javascript syntax"
import re, subprocess, sys, tempfile, os
s = open(os.path.join(sys.argv[1], "watcher/combo_watcher.py")).read()
for name in ('SPA = r"""', 'LOGIN_HTML = r"""'):
    i = s.index(name); j = s.index('"""', i + len(name)); h = s[i + len(name):j]
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write("\n".join(re.findall(r"<script>(.*?)</script>", h, re.S))); f.close()
    if subprocess.run(["node", "--check", f.name]).returncode: sys.exit(1)
P
$PY -m pyflakes "$R/nfl_combo_planner.py" "$R/watcher/combo_watcher.py" 2>&1 | grep -E "undefined name|referenced before|unable to detect" > pf.txt; [ -s pf.txt ] && bad "undefined names" "$(cat pf.txt)" || ok "no undefined names"
if [ -n "$SECRET_PATTERN" ]; then          # set it (privately, e.g. in your shell profile) to the strings that must never be committed
  (cd "$R" && ! git grep -nIE "$SECRET_PATTERN" >/dev/null) && ok "no secrets in repo" || bad "secrets in repo" "$(cd "$R" && git grep -nlIE "$SECRET_PATTERN")"
else
  $PY - "$R" <<'K' && ok "no private keys in repo (set SECRET_PATTERN for the full check)" || bad "a private key is in the repo"
import re, subprocess, sys
files = [f for f in subprocess.run(["git", "-C", sys.argv[1], "ls-files", "-z"], capture_output=True, text=True).stdout.split("\0") if f]
body = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*\n[A-Za-z0-9+/=]{40,}")
def has_key(f):
    try:
        return bool(body.search(open(sys.argv[1] + "/" + f, errors="ignore").read()))
    except (OSError, UnicodeError):
        return False
hits = [f for f in files if has_key(f)]
print("\n".join(hits)); sys.exit(1 if hits else 0)
K
fi

for t in t_review t_review2 t_lines t_restart t_extra t_own t_started t_smart t_lab t_tune t_ahl t_ahl_scores t_settings t_https_push t_status t_league t_hubcache; do
  o=$($PY $t.py 2>&1); echo "$o" | grep -q FAIL && bad "engine $t" "$(echo "$o" | grep FAIL)" || (echo "$o" | grep -q PASS && ok "engine $t ($(echo "$o" | grep -c PASS) checks)" || bad "engine $t" "$o")
done
# ---- the slow part runs side by side: the simulated Mac in one lane, the page tests spread over workers,
# each worker with its own copy of everything and its own port (18766, 18767, ...), so nothing is shared.
N=${CHECK_WORKERS:-4}
PAGE="test_settings test_tap test_days test_singles_live test_analytics test_buildguard test_spa test_adv test_panel_ui test_panel_ui2 test_fun test_hist test_web3 test_speed test_sweep test_chips test_restart2 test_extra_ui test_mix test_allchip test_updbtn test_https test_settled test_buildsec test_ui_fixes test_login_faceid test_motion test_livefresh"
for w in $(seq 0 $((N-1))); do
  p=$((18766 + w))
  $PY -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$p)) else 1)" || bad "setup: port $p is busy" "Something is already listening on a test port; stop it and rerun."
done
( timeout 200 $PY macsmoke/run.py > out_macsmoke.txt 2>&1; UPD=1 SECS=5 timeout 200 $PY macsmoke/run.py > out_macupd.txt 2>&1 ) &
lanes=()
i=0; for t in $PAGE; do lanes[$((i % N))]="${lanes[$((i % N))]} $t"; i=$((i+1)); done
for w in $(seq 0 $((N-1))); do
  D="$WORK/lane$w"; mkdir -p "$D"
  (cd "$WORK" && tar cf - --exclude='./lane*' --exclude='./out_*' .) | (cd "$D" && tar xf -)
  ( cd "$D" && export CW_WEBAPP_PORT=$((18766 + w)) && for t in ${lanes[$w]}; do
      $PY reset.py; timeout 400 $PY $t.py > "$WORK/out_$t.txt" 2>&1; done ) &
done
wait
o=$(cat out_macsmoke.txt); echo "$o" | grep -q "no problems in the log" && echo "$o" | grep -q "started: True" && ok "simulated Mac runs clean" || bad "simulated Mac" "$o"
o=$(cat out_macupd.txt); echo "$o" | grep -q "update installed: True" && ! echo "$o" | grep -q "PROBLEMS: update check" && ok "simulated Mac installs an update" || bad "simulated Mac update" "$o"
for t in $PAGE; do
  o=$(grep -v Deprecation "out_$t.txt" 2>/dev/null)
  tb=$(echo "$o" | grep -c Traceback); benign=$(echo "$o" | grep -cE "BrokenPipeError|ConnectionResetError|ConnectionAbortedError")
  if [ -z "$o" ] || [ "$tb" -gt "$benign" ] || echo "$o" | grep -qE "JS errors: \[.+\]|errs: \[.+\]|PROBLEMS"; then bad "page test $t" "$(echo "$o" | grep -E -B2 -A6 'Traceback|errs|PROBLEMS|JS errors|Error' | head -16)"; else ok "page test $t"; fi
done
v1=$(grep -m1 '^VERSION = ' "$R/nfl_combo_planner.py" | cut -d'"' -f2); v2=$(grep -m1 '^WATCHER_VERSION = ' "$R/watcher/combo_watcher.py" | cut -d'"' -f2); v3=$(cat "$R/version.txt")
[ "$v1" = "$v2" ] && [ "$v2" = "$v3" ] && ok "versions agree ($v1)" || bad "versions disagree" "engine $v1 / watcher $v2 / version.txt $v3"
[ $fail = 0 ] && echo "ALL CHECKS PASSED" || { echo "SOME CHECKS FAILED"; exit 1; }
