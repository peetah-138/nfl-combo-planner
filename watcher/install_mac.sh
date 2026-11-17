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
#   bash install_mac.sh --passcode NEW      set your own web view passcode
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
GUI=0
AUTO=0       # --auto: driven by the Combo Watcher app (answers come in CW_* variables; progress as STEP: lines)
if [ "${1:-}" = "--gui" ]; then GUI=1; shift; fi
if [ "${1:-}" = "--auto" ]; then AUTO=1; shift; fi
TITLE="Combo Watcher Setup"

say() {      # a message (GUI dialog or terminal text)
  if [ "$GUI" = 1 ]; then
    osascript - "$1" "$TITLE" <<'AS' >/dev/null
on run argv
  display dialog (item 1 of argv) with title (item 2 of argv) buttons {"OK"} default button "OK"
end run
AS
  elif [ "$AUTO" = 1 ]; then printf 'MSG: %s\n' "$(printf '%s' "$1" | tr '\n' ' ')"
  else echo; echo "$1"; fi
}

ask() {      # ask for a line of text; Cancel quits setup
  if [ "$GUI" = 1 ]; then
    osascript - "$1" "${2:-}" "$TITLE" <<'AS' || { echo "Setup cancelled."; exit 1; }
on run argv
  set r to display dialog (item 1 of argv) default answer (item 2 of argv) with title (item 3 of argv) buttons {"Cancel", "Continue"} default button "Continue" cancel button "Cancel"
  return text returned of r
end run
AS
  else read -r -p "$1 " reply </dev/tty; echo "$reply"; fi
}

choose() {   # pick one of several buttons (GUI) or type a number; prints the choice
  local msg="$1"; shift
  if [ "$GUI" = 1 ]; then
    osascript - "$msg" "$TITLE" "$@" <<'AS' || { echo "Setup cancelled."; exit 1; }
on run argv
  set opts to items 3 thru -1 of argv
  set r to choose from list opts with prompt (item 1 of argv) with title (item 2 of argv) default items {item 1 of opts}
  if r is false then error number -128
  return item 1 of r
end run
AS
  else
    echo "$msg"; local i=1; for o in "$@"; do echo "  $i) $o"; i=$((i + 1)); done
    read -r -p "Number: " n </dev/tty; eval "echo \"\${$n}\""
  fi
}

tailscale_ip() {
  ifconfig 2>/dev/null | awk '/inet 100\./{print $2}' | while read -r a; do
    o2=$(echo "$a" | cut -d. -f2); [ "$o2" -ge 64 ] && [ "$o2" -le 127 ] && echo "$a" && break; done
}

show_code() {   # the pairing code to paste on the phone (GUI: with a Copy button)
  local code="$1" hub="$2" pass="${3:-}"
  local msg
  if [ -n "$hub" ]; then
    msg="Last step, on your iPhone: open the planner > Settings > Watcher, replace the code with this one, and tap Save.

Mac hub: $hub (over Tailscale, works on any network)

Web view: open $hub in any browser on your Tailscale network (iPhone, iPad, this Mac). Passcode: $pass"
  else
    msg="Tailscale isn't signed in on this Mac yet, so the phone can't use it as its hub. This code still turns on alerts and auto cash-out. Run setup again after signing in to Tailscale to get the full code.

On your iPhone: planner > Settings > Watcher, paste this code, tap Save."
  fi
  if [ "$AUTO" = 1 ]; then
    printf 'CODE: %s\nHUB: %s\nPASS: %s\n' "$code" "$hub" "$pass"
  elif [ "$GUI" = 1 ]; then
    b=$(osascript - "$msg" "$code" "$TITLE" <<'AS'
on run argv
  set r to display dialog (item 1 of argv) default answer (item 2 of argv) with title (item 3 of argv) buttons {"Done", "Copy code"} default button "Copy code"
  return button returned of r
end run
AS
)
    if [ "$b" = "Copy code" ]; then
      printf '%s' "$code" | pbcopy
      say "Copied. With Handoff on (same Apple ID), you can paste it straight into the planner on your iPhone. Or AirDrop it, or type it in from this window by running setup again and choosing Show phone pairing code."
    fi
  else
    echo; echo "$msg"; echo "     $code"
  fi
}

pair_code() {   # the phone's pairing code, with this Mac's Tailscale address as the hub
  local ip
  ip=$(tailscale_ip)
  "$PY" - "$DIR/watcher.json" "$ip" <<'PYEOF'
import base64, json, sys
c = json.load(open(sys.argv[1]))
out = {"topic": c["topic"], "secret": c["secret"]}
if sys.argv[2]:
    out["hub"] = f"http://{sys.argv[2]}:{c.get('hub_port', 8765)}"
print(base64.urlsafe_b64encode(json.dumps(out).encode()).decode().rstrip("="))
print(out.get("hub", ""))
print(c.get("web_pass", ""))
PYEOF
}

if [ "$GUI" = 1 ] && [ -f "$DIR/watcher.json" ] && [ -x "$PY" ] && [ -z "${1:-}" ]; then
  pick=$(choose "Combo Watcher is installed on this Mac. What would you like to do?" \
    "Update or repair it" "Show phone pairing code" "Set my own web passcode" "Check that it's running" "Use a different Kalshi key" "Remove it from this Mac")
  case "$pick" in
    "Show phone pairing code") set -- --code ;;
    "Set my own web passcode") set -- --passcode ;;
    "Check that it's running") set -- --status ;;
    "Use a different Kalshi key") set -- --new-key ;;
    "Remove it from this Mac") set -- --uninstall ;;
    *) set -- ;;
  esac
fi

case "${1:-}" in
  --passcode)
    np="${2:-}"
    [ -z "$np" ] && np=$(ask "Choose a passcode for Combo Hub (at least 6 characters). It's only needed on devices other than this Mac and your phone's Open Combo Hub link." "")
    if [ "${#np}" -lt 6 ]; then say "That's too short. Use at least 6 characters."; exit 1; fi
    "$PY" -c "import json,sys;p='$DIR/watcher.json';c=json.load(open(p));c['web_pass']=sys.argv[1];json.dump(c,open(p,'w'))" "$np"
    launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || true
    say "Done. Combo Hub's passcode is now: $np
(Anyone signed in on another device will need to sign in again.)"
    exit 0 ;;
  --code)
    out=$(pair_code); show_code "$(echo "$out" | sed -n 1p)" "$(echo "$out" | sed -n 2p)" "$(echo "$out" | sed -n 3p)"
    exit 0 ;;
  --status)
    if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
      state=$(launchctl print "gui/$(id -u)/$LABEL" | awk -F'= ' '/^\tstate/{print $2; exit}')
      head="Combo Watcher is ${state:-loaded} on this Mac."
    else
      head="Combo Watcher is NOT running. Run setup again and choose Update or repair it."
    fi
    ip=$(tailscale_ip)
    head="$head
Tailscale: ${ip:-not signed in}"
    if [ "$AUTO" = 1 ]; then
      printf 'STATE: %s\nTS: %s\n' "${state:-stopped}" "${ip:-}"; tail -n 12 "$LOG" 2>/dev/null | sed 's/^/LOG: /'
    elif [ "$GUI" = 1 ]; then
      say "$head

Latest activity:
$(tail -n 8 "$LOG" 2>/dev/null | cut -c1-140 || echo '(nothing yet)')"
    else
      echo "$head"; echo "--- last 25 log lines ($LOG) ---"; tail -n 25 "$LOG" 2>/dev/null || echo "(no log yet)"
    fi
    exit 0 ;;
  --uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    say "Combo Watcher is stopped and removed from this Mac's startup. Its files are still in your home folder under combowatch (delete that folder to remove everything). Remember to revoke its Kalshi API key."
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
if [ "$GUI" = 1 ] && [ ! -f "$DIR/watcher.json" ]; then
  say "This sets up your MacBook as the combo planner's hub. It takes about 5 minutes:

1. Tailscale (so your iPhone can reach this Mac from anywhere)
2. A Kalshi API key just for this Mac
3. Your phone's pairing code

Nothing needs an admin password. You can rerun this file any time to update, check on it, or remove it."
fi
if [ "$GUI" = 1 ] && [ -z "$(tailscale_ip)" ]; then
  while [ -z "$(tailscale_ip)" ]; do
    if [ -d /Applications/Tailscale.app ]; then
      open -a Tailscale 2>/dev/null || true
      t="Tailscale is installed but not signed in. In the Tailscale menu-bar icon, sign in with the same account as your iPhone, then click Check again."
    else
      open "https://tailscale.com/download/mac" 2>/dev/null || true
      t="Step 1: install Tailscale. Its download page just opened in your browser (the Mac App Store version is fine). Install it, open it, and sign in with the same account as your iPhone. Then click Check again."
    fi
    b=$(osascript - "$t" "$TITLE" <<'AS'
on run argv
  set r to display dialog (item 1 of argv) with title (item 2 of argv) buttons {"Skip for now", "Check again"} default button "Check again"
  return button returned of r
end run
AS
) || b="Skip for now"
    [ "$b" = "Skip for now" ] && break
    sleep 2
  done
fi
mkdir -p "$DIR" && chmod 700 "$DIR"
umask 077

# Python: a private copy via uv (no Xcode tools, no admin password, nothing system-wide).
UV="$(command -v uv || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
echo "STEP: python"
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

echo "STEP: download"
echo "Downloading the planner..."
tmp=$(mktemp -d)
curl -fsSL "$REPO/nfl_combo_planner.py" -o "$tmp/engine.py"
curl -fsSL "$REPO/watcher/combo_watcher.py" -o "$tmp/combo_watcher.py"
"$PY" -m py_compile "$tmp/engine.py" "$tmp/combo_watcher.py"
install -m 600 "$tmp/engine.py" "$DIR/engine.py"
install -m 600 "$tmp/combo_watcher.py" "$DIR/combo_watcher.py"
rm -rf "$tmp"

echo "STEP: key"
if [ -f "$DIR/kalshi_private_key.pem" ] && [ "${1:-}" != "--new-key" ]; then
  echo "Kalshi key already set up (run with --new-key to replace it)."
else
  if [ "$AUTO" = 1 ]; then
    KEYID="${CW_KEYID:-}"
    if [ -z "$KEYID" ] || [ ! -f "${CW_KEYFILE:-}" ] || ! grep -q "BEGIN" "$CW_KEYFILE"; then
      echo "ERROR: The Key ID or private key file is missing or isn't a Kalshi private key."; exit 3
    fi
    pem=$(cat "$CW_KEYFILE")$'\n'
  elif [ "$GUI" = 1 ]; then
    open "https://kalshi.com/account/profile" 2>/dev/null || true
    say "Step 2: make a NEW Kalshi API key just for this Mac (so you can revoke it on its own).

Kalshi just opened in your browser. Go to Account > API keys > Create key, with read + write access (needed for cash-outs and trades). Kalshi shows a Key ID and downloads a private key file.

Click OK when you have both."
    KEYID=$(ask "Paste the Key ID:" "")
    keyfile=$(osascript - "$TITLE" <<'AS' || true
on run argv
  POSIX path of (choose file with prompt "Choose the private key file Kalshi downloaded (usually in Downloads):" default location (path to downloads folder))
end run
AS
)
    if [ -z "$keyfile" ] || ! grep -q "BEGIN" "$keyfile" 2>/dev/null; then
      say "That file doesn't look like a private key (it should contain a BEGIN ... PRIVATE KEY line). Run setup again and choose the file Kalshi downloaded."
      exit 1
    fi
    pem=$(cat "$keyfile")$'\n'
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
  fi
  printf '%s' "$pem" > "$DIR/kalshi_private_key.pem"
  chmod 600 "$DIR/kalshi_private_key.pem"
  if [ -f "$DIR/combo_settings.json" ]; then
    "$PY" -c "import json,sys;p='$DIR/combo_settings.json';c=json.load(open(p));c['kalshi_key_id']=sys.argv[1];json.dump(c,open(p,'w'))" "$KEYID"
  else
    printf '{"kalshi_key_id": "%s", "auto_cash": false}\n' "$KEYID" > "$DIR/combo_settings.json"
  fi
  chmod 600 "$DIR/combo_settings.json"
  if [ "$GUI" = 1 ] && [ -n "${keyfile:-}" ]; then
    b=$(osascript - "$TITLE" <<'AS' || true
on run argv
  set r to display dialog "Your key is saved privately for the watcher. Move the downloaded key file to the Trash so there's no loose copy?" with title (item 1 of argv) buttons {"Keep it", "Move to Trash"} default button "Move to Trash"
  return button returned of r
end run
AS
)
    [ "$b" = "Move to Trash" ] && osascript -e "tell application \"Finder\" to delete (POSIX file \"$keyfile\" as alias)" >/dev/null 2>&1 || true
  fi
fi

echo "STEP: pairing"
new_pairing=0
if [ ! -f "$DIR/watcher.json" ]; then
  if [ "$AUTO" = 1 ]; then
    PAIR="${CW_PAIR:-}"
  elif [ "$GUI" = 1 ]; then
    PAIR=$(ask "Step 3: your phone's current pairing code, so your ntfy alerts keep working.

On your iPhone: planner > Settings > Watcher, copy the code (with Handoff it pastes right here). Leave this empty to start a new pairing instead." "")
  else
    echo
    echo "Already paired a Pi with your phone? Paste the pairing code from the phone"
    echo "(planner Settings > Watcher) to keep the same ntfy topic and pairing. Or just press Enter for a new one."
    read -r -p "Pairing code: " PAIR </dev/tty
  fi
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
"$PY" - "$DIR/watcher.json" <<'PYEOF'
import json, secrets, sys
c = json.load(open(sys.argv[1]))
if not c.get("web_pass"):
    c["web_pass"] = "".join(secrets.choice("23456789abcdefghjkmnpqrstuvwxyz") for _ in range(8))
    json.dump(c, open(sys.argv[1], "w"))
PYEOF

echo "STEP: start"
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
# restart the background job; macOS takes a moment to let go of the old one, so wait and retry
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
for _ in $(seq 1 20); do
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || break
  sleep 0.5
done
loaded=0
for _ in 1 2 3 4 5; do
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then loaded=1; break; fi
  if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then   # it's back already: just restart it
    launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null && loaded=1 && break
  fi
  sleep 2
done
if [ "$loaded" != 1 ]; then
  say "macOS wouldn't start the background job just now. Restart the Mac (or log out and back in) and it starts by itself; or run this setup again in a minute."
  exit 1
fi

echo
echo "STEP: kalshi"
echo "Starting... (checking Kalshi)"
kalshi="wait"                                    # the watcher retries a slow first check by itself
for _ in $(seq 1 45); do
  sleep 2
  new=$(tail -n +$((start + 1)) "$LOG" 2>/dev/null || true)
  if echo "$new" | grep -q "Kalshi OK"; then kalshi=ok; break; fi
  if echo "$new" | grep -q "no Kalshi access"; then kalshi=fail; break; fi
  if [ "$(echo "$new" | grep -c "Kalshi check failed")" -ge 3 ]; then kalshi=fail; break; fi
done
tail -n 4 "$LOG" 2>/dev/null || true
[ "$AUTO" = 1 ] && echo "KALSHI: $kalshi $(tail -n +$((start + 1)) "$LOG" 2>/dev/null | grep -E 'Kalshi check failed|no Kalshi access' | tail -1 | cut -c21-200)"

out=$(pair_code); code=$(echo "$out" | sed -n 1p); hub=$(echo "$out" | sed -n 2p)
topic=$("$PY" -c "import json;print(json.load(open('$DIR/watcher.json'))['topic'])")
if [ "$kalshi" = fail ] && [ "$AUTO" != 1 ]; then
  say "The watcher is installed, but Kalshi didn't accept its key yet:

$(tail -n +$((start + 1)) "$LOG" | grep -E 'Kalshi check failed|no Kalshi access' | tail -1 | cut -c21-200)

Check the Key ID and file, then run setup again and choose Use a different Kalshi key."
fi
[ "$AUTO" = 1 ] && [ "$new_pairing" = 1 ] && echo "TOPIC: $topic"
if [ "$new_pairing" = 1 ] && [ "$AUTO" != 1 ]; then
  say "In the ntfy app on your iPhone, tap + and subscribe to this topic (keep it private):

$topic"
fi
if [ "$AUTO" = 1 ]; then
  printf 'CODE: %s\nHUB: %s\nPASS: %s\nCHANGED: %s\n' "$code" "$hub" "$(echo "$out" | sed -n 3p)" \
    "$([ "$code" != "$(cat "$DIR/.shown_code" 2>/dev/null)" ] && echo yes || echo no)"
  printf '%s' "$code" > "$DIR/.shown_code"
elif [ "$code" != "$(cat "$DIR/.shown_code" 2>/dev/null)" ]; then   # only when the phone needs a new code
  show_code "$code" "$hub" "$(echo "$out" | sed -n 3p)"
  printf '%s' "$code" > "$DIR/.shown_code"
fi
# a Desktop icon for the web view on this Mac (no passcode needed on the Mac itself)
cat > "$HOME/Desktop/Combo Hub.webloc" <<'WEBLOC'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>URL</key><string>http://localhost:8765/</string></dict></plist>
WEBLOC
[ "$AUTO" = 1 ] && { echo "DONE"; exit 0; }
say "All set. Combo Watcher is running on this Mac.

Keep it plugged in with the lid OPEN (the screen can go dark; a closed lid puts it to sleep). Moving it to another Wi-Fi network is fine: Tailscale keeps the same address.

If macOS asks whether python3.12 may accept incoming connections, click Allow. After a restart, log in once and it starts by itself.

Combo Hub (the web view) is now on your Desktop. On your iPhone, tap Open Combo Hub on the planner's Live screen."
[ "$GUI" = 1 ] && open "http://localhost:8765/" 2>/dev/null || true
[ "$GUI" = 1 ] || echo "Check on it any time:  bash install_mac.sh --status     Live log:  tail -f ~/combowatch/watcher.log"
