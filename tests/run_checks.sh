#!/bin/bash
# The full check list. Everything must pass before any push (Pete's rule). Run from anywhere:
#   bash tests/run_checks.sh
# It copies the suite to a temporary folder, so it never touches your real ~/combowatch or the repo's files.
# One PASS/FAIL line per check, then ALL CHECKS PASSED or SOME CHECKS FAILED. Takes about 4 minutes.
# By default it runs everything. CI splits it into parallel jobs with these (see tests/README.md):
#   CHECK_GROUPS="static engine sim pages"   which parts to run (space or comma separated; default all four)
#   CHECK_ENGINE_SHARD=i/N                    only engine-test shard i of N (same split as CHECK_SHARD)
#   CHECK_SHARD=i/N                           only page-test shard i of N (tests/suite/checklist.py splits them)
#   CHECK_RETRY=1                             rerun a page test listed in checklist.RETRY once if it fails (CI only)
R="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/combochecks.XXXXXX")"
trap 'pkill -f "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
cp -R "$R/tests/suite/." "$WORK/"
cd "$WORK" || exit 1
mkdir -p wahome wtest run
cp "$R/nfl_combo_planner.py" wahome/engine.py
cp "$R/watcher/combo_watcher.py" wtest/combo_watcher.py
cp -R "$R/watcher/spa" wtest/spa            # the web app's files sit next to the watcher, as on the Mac
cp "$R/nfl_combo_planner.py" run/nfl_combo_planner.py
cp fixtures/run_settings.json run/combo_settings.json
cp fixtures/home_settings.json wahome/combo_settings.json
. "$R/tests/python_env.sh"   # sets PY: a Python >= 3.10 with playwright (see tests/README.md); prints which one and its sqlite
"$PY" - <<'P'
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
# Nothing a test does may touch the real Tailscale (`tailscale serve` re-points Pete's real secure address) or post to a
# real ntfy topic. The watcher refuses the Tailscale command line when this is set (and outside ~/combowatch anyway).
export COMBO_NO_TAILSCALE=1 COMBOWATCH_NTFY="http://ntfy.invalid"
PB=${CHECK_PORT_BASE:-18766}               # first test port; set CHECK_PORT_BASE so two runs at once (e.g. two worktrees) do not collide
case "$PB$CHECK_WORKERS" in *[!0-9]*) echo "CHECK_PORT_BASE and CHECK_WORKERS must be numbers"; exit 2;; esac
if [ "$PB" -lt 1024 ] || [ "$PB" -gt 65000 ] || { [ "$PB" -le 8766 ] && [ $((PB + ${CHECK_WORKERS:-4})) -ge 8765 ]; }; then
  echo "CHECK_PORT_BASE=$PB is out of range (use 1024 or more, and never the real app's 8765/8766)"; exit 2
fi
export CW_WEBAPP_PORT=$PB             # tests run their own web apps on $PB+ (18766+), never on the real one (8766)
command -v timeout >/dev/null 2>&1 || timeout(){ perl -e 'alarm shift; exec @ARGV' "$@"; }   # macOS has no timeout
G=" $(echo "${CHECK_GROUPS:-static engine sim pages}" | tr ',' ' ') "
for g in $G; do case "$g" in static|engine|sim|pages) ;; *) echo "CHECK_GROUPS: unknown group '$g' (use static engine sim pages)"; exit 2;; esac; done
on(){ case "$G" in *" $1 "*) return 0;; esac; return 1; }
case "$CHECK_SHARD" in ""|[1-9]/[1-9]|[1-9]/[1-9][0-9]|[1-9][0-9]/[1-9][0-9]) ;; *) echo "CHECK_SHARD must look like 2/5"; exit 2;; esac
case "$CHECK_ENGINE_SHARD" in ""|[1-9]/[1-9]|[1-9]/[1-9][0-9]|[1-9][0-9]/[1-9][0-9]) ;; *) echo "CHECK_ENGINE_SHARD must look like 2/4"; exit 2;; esac
[ -n "$CHECK_ENGINE_SHARD" ] && ! on engine && { echo "CHECK_ENGINE_SHARD splits the engine tests: add engine to CHECK_GROUPS"; exit 2; }
[ -n "$CHECK_SHARD" ] && ! on pages && { echo "CHECK_SHARD splits the page tests: add pages to CHECK_GROUPS"; exit 2; }
keep(){ local t; for t in $1; do case " $CHECK_ONLY " in *" $t "*) echo "$t";; esac; done; }   # CHECK_ONLY filter
PARTIAL=""; [ "$G" != " static engine sim pages " ] && PARTIAL="groups:$G"
[ -n "$CHECK_SHARD" ] && PARTIAL="$PARTIAL shard $CHECK_SHARD"; [ -n "$CHECK_ENGINE_SHARD" ] && PARTIAL="$PARTIAL engine shard $CHECK_ENGINE_SHARD"; [ -n "$CHECK_ONLY" ] && PARTIAL="$PARTIAL only: $CHECK_ONLY"
fail=0
ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; echo "$2" | head -12 | sed 's/^/     /'; fail=1; }
need(){ command -v "$1" >/dev/null 2>&1 || { bad "setup: $1 is missing" "$2"; }; }
on static && need node "Install Node (e.g. brew install node). It checks the web app's JavaScript."
on pages && { "$PY" -c "import playwright" 2>/dev/null || bad "setup: playwright is missing" "see tests/README.md (one-time setup), or set CHECK_PYTHON"; }
on static && { "$PY" -c "import pyflakes" 2>/dev/null || bad "setup: pyflakes is missing" "see tests/README.md (one-time setup), or set CHECK_PYTHON"; }

if on static; then
"$PY" -m py_compile "$R/nfl_combo_planner.py" "$R/watcher/combo_watcher.py" && ok compile || bad compile
if command -v python3.10 >/dev/null 2>&1; then python3.10 -m py_compile "$R/nfl_combo_planner.py" "$R/watcher/combo_watcher.py" && ok "compile (3.10)" || bad "compile (3.10)"
else "$PY" - "$R" <<'P' && ok "compile (3.10 grammar, partial: CI runs a real python3.10)" || bad "compile (3.10 grammar)"   # no python3.10 here: parse with its grammar (feature_version misses some newer syntax, e.g. nested f-string quotes)
import ast, sys
for f in ("nfl_combo_planner.py", "watcher/combo_watcher.py"):
    ast.parse(open(sys.argv[1] + "/" + f).read(), f, feature_version=(3, 10))
P
fi
"$PY" - "$R" <<'P' && ok "javascript syntax (each watcher/spa file and the assembled pages)" || bad "javascript syntax"
import glob, importlib.util, os, subprocess, sys, tempfile
os.environ["COMBOWATCH_HOME"] = tempfile.mkdtemp()      # never the real ~/combowatch
for f in sorted(glob.glob(os.path.join(sys.argv[1], "watcher/spa/*.js"))):
    if subprocess.run(["node", "--check", f]).returncode: sys.exit(1)
spec = importlib.util.spec_from_file_location("W", os.path.join(sys.argv[1], "watcher/combo_watcher.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
if W.SPA_PROBLEM: print(W.SPA_PROBLEM); sys.exit(1)
for h in (W.SPA, W.LOGIN_HTML):
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write(W.spa_scripts(h)); f.close()
    if subprocess.run(["node", "--check", f.name]).returncode: sys.exit(1)
P
"$PY" -m pyflakes "$R/nfl_combo_planner.py" "$R/watcher/combo_watcher.py" "$R/tools/verify_spa_split.py" 2>&1 | grep -E "undefined name|referenced before|unable to detect" > pf.txt; [ -s pf.txt ] && bad "undefined names" "$(cat pf.txt)" || ok "no undefined names"
if [ -n "$SECRET_PATTERN" ]; then          # set it (privately, e.g. in your shell profile) to the strings that must never be committed
  (cd "$R" && ! git grep -nIE "$SECRET_PATTERN" >/dev/null) && ok "no secrets in repo" || bad "secrets in repo" "$(cd "$R" && git grep -nlIE "$SECRET_PATTERN")"
else
  "$PY" - "$R" <<'K' && ok "no private keys in repo (set SECRET_PATTERN for the full check)" || bad "a private key is in the repo"
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
v1=$(grep -m1 '^VERSION = ' "$R/nfl_combo_planner.py" | cut -d'"' -f2); v2=$(grep -m1 '^WATCHER_VERSION = ' "$R/watcher/combo_watcher.py" | cut -d'"' -f2); v3=$(cat "$R/version.txt")
[ "$v1" = "$v2" ] && [ "$v2" = "$v3" ] && ok "versions agree ($v1)" || bad "versions disagree" "engine $v1 / watcher $v2 / version.txt $v3"
for t in $("$PY" checklist.py static); do   # static checks written as scripts (suite/st_*.py)
  o=$("$PY" $t.py 2>&1); echo "$o" | grep -q FAIL && bad "static $t" "$(echo "$o" | grep FAIL)" || (echo "$o" | grep -q PASS && ok "static $t ($(echo "$o" | grep -c PASS) checks)" || bad "static $t" "$o")
done
fi   # static

# the test lists and their split come from suite/checklist.py, which finds every test by its "# CHECK:" header (t_shards.py checks each is in exactly one shard)
if on engine; then
  ENG=$("$PY" checklist.py engine "$CHECK_ENGINE_SHARD") || bad "engine test list" "checklist.py engine failed"
  [ -n "$CHECK_ONLY" ] && ENG=$(keep "$ENG")
  # netguard/sitecustomize.py refuses every real (non-local) connection in an engine test and prints a FAIL line
  # naming the host, so a test that slips past its stubs fails at once instead of depending on ESPN (GitHub #189)
  NG="$WORK/netguard${PYTHONPATH:+:$PYTHONPATH}"
  for t in $ENG; do
    # a test that crashes after some PASS lines used to count as passed: its exit status counts too
    o=$(PYTHONPATH="$NG" "$PY" $t.py 2>&1); rc=$?
    if echo "$o" | grep -q FAIL; then bad "engine $t" "$(echo "$o" | grep FAIL)"
    elif [ "$rc" -ne 0 ]; then bad "engine $t" "stopped with exit status $rc: $(echo "$o" | tail -4)"
    elif echo "$o" | grep -q PASS; then ok "engine $t ($(echo "$o" | grep -c PASS) checks)"
    else bad "engine $t" "$o"; fi
  done
fi
# ---- the slow part runs side by side: the simulated Mac in one lane, the page tests spread over workers,
# each worker with its own copy of everything and its own port (18766, 18767, ...), so nothing is shared.
N=${CHECK_WORKERS:-4}
PAGE=""
if on pages; then PAGE=$("$PY" checklist.py page "$CHECK_SHARD") || bad "page test list" "checklist.py page '$CHECK_SHARD' failed"; fi
[ -n "$CHECK_ONLY" ] && PAGE=$(keep "$PAGE")   # e.g. CHECK_ONLY="test_klive" while fixing one
[ -n "$CHECK_ONLY" ] && [ -z "$PAGE$ENG" ] && bad "CHECK_ONLY" "'$CHECK_ONLY' names no engine or page test in the groups being run"
RETRY=" $("$PY" checklist.py retry) "
page_bad(){   # $1 = a page test's output; succeeds (= the test failed) on no output, a real traceback, JS errors or PROBLEMS
  local o tb benign
  o=$(grep -v Deprecation "$1" 2>/dev/null)
  tb=$(echo "$o" | grep -c Traceback); benign=$(echo "$o" | grep -cE "BrokenPipeError|ConnectionResetError|ConnectionAbortedError")
  [ -z "$o" ] || [ "$tb" -gt "$benign" ] || echo "$o" | grep -qE "JS errors: \[.+\]|errs: \[.+\]|PROBLEMS"
}
page_why(){   # $1 = a failed page test's output -> what went wrong, the PROBLEM lines first, then the end of a traceback
  # (the old "first 16 lines around any match" showed only passing lines when the failure came late, e.g. test_hsw's WebKit pass)
  local o; o=$(grep -v Deprecation "$1" 2>/dev/null)
  [ -z "$o" ] && { echo "(no output)"; return; }
  echo "$o" | grep -E 'PROBLEM|JS errors: \[.+\]|errs: \[.+\]' | head -5
  echo "$o" | grep -q Traceback && echo "$o" | awk '/Traceback/{n=NR} {l[NR]=$0} END{for(i=n;i<=NR;i++)print l[i]}' | grep -vE '^\s+(self\._sync|return (task|await|func)|\^+$)' | tail -7
}
if [ -n "$PAGE" ] || on sim; then
  for w in $(seq 0 $((N-1))); do
    p=$((PB + w))
    "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$p)) else 1)" || bad "setup: port $p is busy" "Something is already listening on a test port; stop it and rerun."
  done
fi
if on sim; then
  ( timeout 200 "$PY" macsmoke/run.py > out_macsmoke.txt 2>&1; UPD=1 SECS=5 timeout 200 "$PY" macsmoke/run.py > out_macupd.txt 2>&1 ) &
fi
lanes=()
if [ -n "$PAGE" ]; then   # longest tests first, each to the lightest lane (balanced by checklist.SECS)
  w=0; while IFS= read -r l; do lanes[$w]="$l"; w=$((w+1)); done < <("$PY" checklist.py lanes "$N" $PAGE)
fi
for w in $(seq 0 $((N-1))); do
  [ -n "${lanes[$w]}" ] || continue
  D="$WORK/lane$w"; mkdir -p "$D"
  (cd "$WORK" && tar cf - --exclude='./lane*' --exclude='./out_*' .) | (cd "$D" && tar xf -)
  ( cd "$D" && export CW_WEBAPP_PORT=$((PB + w)) && for t in ${lanes[$w]}; do
      s0=$(date +%s); "$PY" reset.py; timeout 400 "$PY" $t.py > "$WORK/out_$t.txt" 2>&1
      if [ "$CHECK_RETRY" = 1 ] && case "$RETRY" in *" $t "*) true;; *) false;; esac && page_bad "$WORK/out_$t.txt"; then
        mv "$WORK/out_$t.txt" "$WORK/first_$t.txt"; "$PY" reset.py; timeout 400 "$PY" $t.py > "$WORK/out_$t.txt" 2>&1
        : > "$WORK/retried_$t.txt"
      fi
      echo $(( $(date +%s) - s0 )) > "$WORK/secs_$t.txt"; done ) &
done
wait
if on sim; then
  o=$(cat out_macsmoke.txt); echo "$o" | grep -q "no problems in the log" && echo "$o" | grep -q "started: True" && ! echo "$o" | grep -q "PROBLEMS" && ok "simulated Mac runs clean" || bad "simulated Mac" "$o"
  o=$(cat out_macupd.txt); echo "$o" | grep -q "update installed: True" && ! echo "$o" | grep -q "PROBLEMS: update check" && ok "simulated Mac installs an update" || bad "simulated Mac update" "$o"
fi
for t in $PAGE; do
  sec="$(cat "secs_$t.txt" 2>/dev/null)s"; [ -f "retried_$t.txt" ] && sec="$sec, RETRIED: the first try failed"
  if page_bad "out_$t.txt"; then
    bad "page test $t ($sec)" "$(page_why "out_$t.txt")"
  else
    ok "page test $t ($sec)"
    [ -f "retried_$t.txt" ] && grep -v Deprecation "first_$t.txt" | grep -E 'Traceback|errs: \[.+|PROBLEMS|JS errors' | head -6 | sed 's/^/     first try: /'
  fi
done
[ $fail = 0 ] || { echo "SOME CHECKS FAILED"; exit 1; }
# only a run of the whole list may say ALL CHECKS PASSED (a part of it, e.g. one CI shard, says which part it was)
if [ -n "$PARTIAL" ]; then echo "PART PASSED ($PARTIAL ): not the full check list"; else echo "ALL CHECKS PASSED"; fi
