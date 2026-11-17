#!/usr/bin/env bash
# Installs (or repairs) the combo planner watcher on a Raspberry Pi running Raspberry Pi OS.
#   curl -fsSLO https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/watcher/install_pi.sh
#   bash install_pi.sh
# It makes a locked-down "combowatch" service user, asks for the watcher's own Kalshi key,
# makes your private notification topic, starts the watcher, and prints the phone pairing code.
set -euo pipefail
REPO=https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main
DIR=/var/lib/combowatch
SVC=/etc/systemd/system/combowatch.service

if [ "${1:-}" = "--healthcheck" ]; then
  # Dead-man switch: a free healthchecks.io check (period 5 min, grace 5 min) that alerts you if the Pi goes quiet.
  url="${2:-}"
  if [[ ! "$url" =~ ^https://hc-ping\.com/[A-Za-z0-9/_-]+$ ]]; then
    echo "Usage: bash install_pi.sh --healthcheck https://hc-ping.com/<your check's id>"; exit 1
  fi
  sudo -u combowatch python3 -c "import json,sys;p='$DIR/watcher.json';c=json.load(open(p));c['healthcheck_url']=sys.argv[1];json.dump(c,open(p,'w'))" "$url"
  sudo systemctl restart combowatch
  echo "Dead-man alert on: healthchecks.io will tell you if the Pi stops checking in."
  exit 0
fi

if [ "${1:-}" = "--backup" ] || [ "${1:-}" = "--main" ]; then
  # --backup: the Mac is the main watcher; this Pi only sends alerts while the Mac is quiet, never trades.
  role=$([ "$1" = "--backup" ] && echo backup || echo main)
  sudo -u combowatch python3 -c "import json,sys;p='$DIR/watcher.json';c=json.load(open(p));c['role']=sys.argv[1];json.dump(c,open(p,'w'))" "$role"
  sudo systemctl restart combowatch
  echo "This Pi is now the $role watcher."
  [ "$role" = backup ] && echo "Give it a READ-ONLY Kalshi key if you can: bash install_pi.sh --new-key"
  exit 0
fi

echo "== Combo planner watcher setup =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-requests ca-certificates >/dev/null
id combowatch >/dev/null 2>&1 || sudo useradd --system --home-dir "$DIR" --create-home --shell /usr/sbin/nologin combowatch
sudo install -d -m 700 -o combowatch -g combowatch "$DIR"

echo "Downloading the planner..."
tmp=$(mktemp -d)
curl -fsSL "$REPO/nfl_combo_planner.py" -o "$tmp/engine.py"
curl -fsSL "$REPO/watcher/combo_watcher.py" -o "$tmp/combo_watcher.py"
python3 -m py_compile "$tmp/engine.py" "$tmp/combo_watcher.py"
sudo install -m 600 -o combowatch -g combowatch "$tmp/engine.py" "$DIR/engine.py"
sudo install -m 600 -o combowatch -g combowatch "$tmp/combo_watcher.py" "$DIR/combo_watcher.py"
rm -rf "$tmp"

if sudo test -f "$DIR/kalshi_private_key.pem" && [ "${1:-}" != "--new-key" ]; then
  echo "Kalshi key already set up (run with --new-key to replace it)."
else
  echo
  echo "Make a NEW Kalshi API key just for the Pi (Kalshi > Account > API keys), so you can revoke it on its own."
  echo "Give it read + write access if you want the Pi to do Auto cash-out (read-only is fine for alerts only)."
  read -r -p "Paste its Key ID and press Enter: " KEYID </dev/tty
  echo "Now paste its private key (the whole thing, BEGIN to END lines), then press Enter:"
  pem=""
  while IFS= read -r line </dev/tty; do
    pem+="$line"$'\n'
    [[ "$line" == *"-----END"* ]] && break
  done
  printf '%s' "$pem" | sudo -u combowatch tee "$DIR/kalshi_private_key.pem" >/dev/null
  sudo chmod 600 "$DIR/kalshi_private_key.pem"
  printf '{"kalshi_key_id": "%s", "auto_cash": false}\n' "$KEYID" | sudo -u combowatch tee "$DIR/combo_settings.json" >/dev/null
  sudo chmod 600 "$DIR/combo_settings.json"
fi

if ! sudo test -f "$DIR/watcher.json"; then
  topic="combos-$(python3 -c 'import secrets;print(secrets.token_urlsafe(18).replace("_","x").replace("-","y"))')"
  secret=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
  printf '{"topic": "%s", "secret": "%s"}\n' "$topic" "$secret" | sudo -u combowatch tee "$DIR/watcher.json" >/dev/null
  sudo chmod 600 "$DIR/watcher.json"
fi

sudo tee "$SVC" >/dev/null <<'UNIT'
[Unit]
Description=Kalshi combo planner watcher
After=network-online.target
Wants=network-online.target

[Service]
User=combowatch
Group=combowatch
Environment=COMBOWATCH_HOME=/var/lib/combowatch
WorkingDirectory=/var/lib/combowatch
ExecStart=/usr/bin/python3 /var/lib/combowatch/combo_watcher.py
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/combowatch
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now combowatch >/dev/null
sudo systemctl restart combowatch

topic=$(sudo python3 -c "import json;print(json.load(open('$DIR/watcher.json'))['topic'])")
code=$(sudo python3 -c "import json,base64;c=json.load(open('$DIR/watcher.json'));print(base64.urlsafe_b64encode(json.dumps({'topic':c['topic'],'secret':c['secret']}).encode()).decode().rstrip('='))")
echo
echo "== Done. The watcher is running. =="
echo
echo "1) In the ntfy app on your iPhone, tap + and subscribe to this topic (keep it private):"
echo "     $topic"
echo
echo "2) In the planner on your phone: Settings > Pi watcher, paste this pairing code, tap Save:"
echo "     $code"
echo
echo "Check on it any time:  sudo systemctl status combowatch     Live log:  sudo journalctl -u combowatch -f"
