#!/bin/bash
# Local DEV environment: the real planner web app on http://127.0.0.1:18800/app with fake Kalshi/ESPN data,
# seeded bets, a throwaway home folder, no Kalshi key (trading impossible) and no hub. Ctrl-C to stop; the
# throwaway folder is deleted. Never touches ~/combowatch. See DEV.md.
R="$(cd "$(dirname "$0")" && pwd)"
PORT=18800
case "$PORT" in 8765|8766) echo "refusing port $PORT (the real hub/app)"; exit 2;; esac
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is busy: another dev instance may be running (try: lsof -nP -iTCP:$PORT -sTCP:LISTEN). Not starting."; exit 2
fi
DEVHOME="$(mktemp -d "$HOME/combodev.XXXX")" || exit 1
case "$DEVHOME" in "$HOME"/combodev.*) ;; *) echo "unexpected dev home $DEVHOME"; exit 2;; esac
[ "$(cd "$DEVHOME" && pwd -P)" = "$(cd "$HOME/combowatch" 2>/dev/null && pwd -P)" ] && { echo "dev home is the real home. Refusing."; exit 2; }
PID=""
cleanup() {
  trap - EXIT INT TERM HUP
  [ -n "$PID" ] && kill "$PID" 2>/dev/null && wait "$PID" 2>/dev/null
  case "$DEVHOME" in "$HOME"/combodev.*) rm -rf "$DEVHOME";; esac
  echo "dev environment stopped, $DEVHOME removed"
}
trap cleanup EXIT INT TERM HUP
touch "$DEVHOME/.devhome"
ln -s "$R/nfl_combo_planner.py" "$DEVHOME/engine.py"          # the engine keeps its files next to this link, i.e. in the dev home
cp "$R/tests/suite/fixtures/home_settings.json" "$DEVHOME/combo_settings.json"
# No topic/secret on purpose: without them the web app never configures a hub or posts settings anywhere.
echo '{"hub": false, "webapp": false, "shadow": false, "auto_update": false, "web_pass": "dev"}' > "$DEVHOME/watcher.json"
# The fixture's fake Key ID is removed: with no key id and no key file, can_trade() is false.
python3 - "$DEVHOME/combo_settings.json" <<'P' || exit 1
import json, sys
s = json.load(open(sys.argv[1])); s["kalshi_key_id"] = ""; s["watcher_code"] = ""; s["odds_key"] = ""; s["auto_sell"] = False
json.dump(s, open(sys.argv[1], "w"))
P
export COMBOWATCH_HOME="$DEVHOME" COMBOWATCH_NTFY="http://127.0.0.1:9" CW_WEBAPP_PORT="$PORT" COMBO_NO_TAILSCALE=1
python3 "$R/tests/dev_webapp.py" &
PID=$!
wait "$PID"
