#!/usr/bin/env bash
# Installs (or repairs) the combo planner watcher on a Mac that stays plugged in.
#   curl -fsSLO https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/watcher/install_mac.sh
#   bash install_mac.sh
# Everything lives in ~/combowatch (readable only by you). It runs in the background whenever you're
# logged in, restarts itself if it stops, keeps the Mac awake while it's plugged in, and updates
# itself only to versions your phone has approved. No admin password needed.
#
#   bash install_mac.sh --status            is it running? last lines of its log
#   bash install_mac.sh --code              print the phone's pairing code (with this Mac's hub address)
#   bash install_mac.sh --healthcheck URL   dead-man alert (free healthchecks.io check)
#   bash install_mac.sh --new-key           replace its Kalshi key
#   bash install_mac.sh --uninstall         stop it and remove it (keeps ~/combowatch)
set -euo pipefail
REPO=https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main
DIR="$HOME/combowatch"
LABEL=com.combowatch.watcher
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$DIR/watcher.log"
PY="$DIR/.venv/bin/python"

pair_code() {   # the phone's pairing code, with this Mac's Tailscale address as the hub
  local ip
  ip=$(ifconfig 2>/dev/null | awk '/inet 100\./{print $2}' | while read -r a; do
         o2=$(echo "$a" | cut -d. -f2); [ "$o2" -ge 64 ] && [ "$o2" -le 127 ] && echo "$a" && break; done)
  "$PY" - "$DIR/watcher.json" "$ip" <<'PYEOF'
import base64, json, sys
c = json.load(open(sys.argv[1]))
out = {"topic": c["topic"], "secret": c["secret"]}
if sys.argv[2]:
    out["hub"] = f"http://{sys.argv[2]}:{c.get('hub_port', 8765)}"
print(base64.urlsafe_b64encode(json.dumps(out).encode()).decode().rstrip("="))
print(out.get("hub", ""))
PYEOF
}

case "${1:-}" in
  --code)
    out=$(pair_code); code=$(echo "$out" | sed -n 1p); hub=$(echo "$out" | sed -n 2p)
    if [ -z "$hub" ]; then
      echo "No Tailscale address found. Open the Tailscale app on this Mac, sign in, then run this again."; exit 1
    fi
    echo "Mac hub: $hub"
    echo "In the planner on your phone: Settings > Pi watcher, replace the code with this one, tap Save:"
    echo "     $code"
    exit 0 ;;
  --status)
    if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
      state=$(launchctl print "gui/$(id -u)/$LABEL" | awk -F'= ' '/^\tstate/{print $2; exit}')
      echo "Watcher is loaded (state: ${state:-unknown})."
    else
      echo "Watcher is NOT running. Run: bash install_mac.sh"
    fi
    echo "--- last 25 log lines ($LOG) ---"
    tail -n 25 "$LOG" 2>/dev/null || echo "(no log yet)"
    exit 0 ;;
  --uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Stopped and removed the background job. Your files are still in $DIR (delete it to remove everything)."
    exit 0 ;;
  --healthcheck)
    url="${2:-}"
    if [[ ! "$url" =~ ^https://hc-ping\.com/[A-Za-z0-9/_-]+$ ]]; then
      echo "Usage: bash install_mac.sh --healthcheck https://hc-ping.com/<your check's id>"; exit 1
    fi
    "$PY" -c "import json,sys;p='$DIR/watcher.json';c=json.load(open(p));c['healthcheck_url']=sys.argv[1];json.dump(c,open(p,'w'))" "$url"
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
    echo "Dead-man alert on: healthchecks.io will tell you if the Mac stops checking in."
    exit 0 ;;
esac

echo "== Combo planner watcher setup (Mac) =="
mkdir -p "$DIR" && chmod 700 "$DIR"
umask 077

# Python: a private copy via uv (no Xcode tools, no admin password, nothing system-wide).
UV="$(command -v uv || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
if [ -z "$UV" ]; then
  echo "Installing uv (a small Python installer, about 30 MB)..."
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
  UV="$HOME/.local/bin/uv"
fi
if [ ! -x "$PY" ]; then
  echo "Setting up Python..."
  "$UV" venv -q --python 3.12 "$DIR/.venv"
fi
"$UV" pip install -q --python "$PY" requests

echo "Downloading the planner..."
tmp=$(mktemp -d)
curl -fsSL "$REPO/nfl_combo_planner.py" -o "$tmp/engine.py"
curl -fsSL "$REPO/watcher/combo_watcher.py" -o "$tmp/combo_watcher.py"
"$PY" -m py_compile "$tmp/engine.py" "$tmp/combo_watcher.py"
install -m 600 "$tmp/engine.py" "$DIR/engine.py"
install -m 600 "$tmp/combo_watcher.py" "$DIR/combo_watcher.py"
rm -rf "$tmp"

if [ -f "$DIR/kalshi_private_key.pem" ] && [ "${1:-}" != "--new-key" ]; then
  echo "Kalshi key already set up (run with --new-key to replace it)."
else
  echo
  echo "Make a NEW Kalshi API key just for this Mac (Kalshi > Account > API keys), so you can revoke it on its own."
  echo "Give it read + write access if you want Auto cash-out and auto-hedge (read-only is fine for alerts only)."
  read -r -p "Paste its Key ID and press Enter: " KEYID </dev/tty
  echo "Now paste its private key (the whole thing, BEGIN to END lines), then press Enter:"
  pem=""
  while IFS= read -r line </dev/tty; do
    pem+="$line"$'\n'
    [[ "$line" == *"-----END"* ]] && break
  done
  printf '%s' "$pem" > "$DIR/kalshi_private_key.pem"
  chmod 600 "$DIR/kalshi_private_key.pem"
  if [ -f "$DIR/combo_settings.json" ]; then
    "$PY" -c "import json,sys;p='$DIR/combo_settings.json';c=json.load(open(p));c['kalshi_key_id']=sys.argv[1];json.dump(c,open(p,'w'))" "$KEYID"
  else
    printf '{"kalshi_key_id": "%s", "auto_cash": false}\n' "$KEYID" > "$DIR/combo_settings.json"
  fi
  chmod 600 "$DIR/combo_settings.json"
fi

new_pairing=0
if [ ! -f "$DIR/watcher.json" ]; then
  echo
  echo "Already paired a Pi with your phone? Paste the pairing code from the phone"
  echo "(planner Settings > Pi watcher) to keep the same ntfy topic and pairing. Or just press Enter for a new one."
  read -r -p "Pairing code: " PAIR </dev/tty
  if [ -n "$PAIR" ]; then
    "$PY" - "$PAIR" "$DIR/watcher.json" <<'PYEOF'
import base64, json, sys
code, path = sys.argv[1].strip(), sys.argv[2]
c = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)))
assert c.get("topic") and c.get("secret"), "that isn't a pairing code"
json.dump({"topic": c["topic"], "secret": c["secret"]}, open(path, "w"))
PYEOF
  else
    "$PY" - "$DIR/watcher.json" <<'PYEOF'
import json, secrets, sys
topic = "combos-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y")
json.dump({"topic": topic, "secret": secrets.token_hex(32)}, open(sys.argv[1], "w"))
PYEOF
    new_pairing=1
  fi
  chmod 600 "$DIR/watcher.json"
fi

# Background job: starts at login, restarts if it stops, keeps the Mac awake (caffeinate) while plugged in.
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-i</string><string>-s</string>
    <string>$PY</string><string>$DIR/combo_watcher.py</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>COMBOWATCH_HOME</key><string>$DIR</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLISTEOF
# keep the log small: start fresh if it's over 5 MB
if [ -f "$LOG" ] && [ $(( $(wc -c <"$LOG") )) -gt 5000000 ]; then mv "$LOG" "$LOG.old"; fi
start=0; [ -f "$LOG" ] && start=$(( $(wc -l <"$LOG") ))
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo
echo "Starting... (checking Kalshi)"
for _ in $(seq 1 20); do
  sleep 2
  if tail -n +$((start + 1)) "$LOG" 2>/dev/null | grep -qE "started|Kalshi check failed|no Kalshi access"; then break; fi
done
tail -n 4 "$LOG" 2>/dev/null || true

out=$(pair_code); code=$(echo "$out" | sed -n 1p); hub=$(echo "$out" | sed -n 2p)
topic=$("$PY" -c "import json;print(json.load(open('$DIR/watcher.json'))['topic'])")
echo
echo "== Done. The watcher and hub are running on this Mac. =="
if [ "$new_pairing" = 1 ]; then
  echo
  echo "In the ntfy app on your iPhone, tap + and subscribe to this topic (keep it private):"
  echo "     $topic"
fi
echo
if [ -n "$hub" ]; then
  echo "Mac hub: $hub (over Tailscale)"
  echo "In the planner on your phone: Settings > Pi watcher, replace the code with this one, tap Save:"
else
  echo "No Tailscale address yet, so the phone can't use this Mac as its hub. Install Tailscale"
  echo "(tailscale.com/download), sign in with the same account as your iPhone, then run: bash install_mac.sh --code"
  echo "Meanwhile, this pairing code turns on alerts and auto cash-out (Settings > Pi watcher):"
fi
echo "     $code"
echo
echo "If macOS asks whether python3.12 may accept incoming connections, click Allow."
echo
echo "Keep the Mac plugged in with the lid OPEN (the screen can turn off; a closed lid puts it to sleep)."
echo "After a restart or power cut, log in once and it starts again by itself."
echo "Check on it any time:  bash install_mac.sh --status     Live log:  tail -f ~/combowatch/watcher.log"
