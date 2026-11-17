#!/bin/bash
# Double-click to set up (or update, check, or remove) the combo planner's watcher and hub on this Mac.
# It downloads the latest setup script and walks you through it with dialogs.
REPO=https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main
clear
echo "Combo Watcher Setup"
echo "Follow the dialogs. This window shows progress; you can close it when setup says All set."
echo
tmp=$(mktemp -d)
if ! curl -fsSL "$REPO/watcher/install_mac.sh?t=$(date +%s)" -o "$tmp/install_mac.sh"; then
  osascript -e 'display alert "Combo Watcher Setup" message "Could not download the setup. Check the connection and try again."' >/dev/null
  exit 1
fi
bash "$tmp/install_mac.sh" --gui
rc=$?
rm -rf "$tmp"
echo
[ $rc = 0 ] && echo "Done. You can close this window." || echo "Setup stopped (code $rc). Run this file again to retry."
