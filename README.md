# NFL combo planner

A Pythonista (iPhone) script that plans Kalshi NFL combo bets, reads your own
Kalshi account, and (only when you tap Accept) can place combos for you.

This repository holds **code only**. Your API keys, settings and betting history
are stored in separate files on your phone and are never uploaded here.

- `nfl_combo_planner.py` – the planner. Its **Update** button downloads new
  versions from this repo, checks them, keeps a backup, and swaps them in.
- `version.txt` – the latest version number (the planner checks this).
- `install_planner.py` – one-time installer for switching an existing phone
  over to the auto-updating version.

Anyone who can push to this repo controls what the planner on your phone runs,
including with your Kalshi trading key. Keep write access to yourself.
