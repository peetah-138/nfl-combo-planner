# Kalshi combo planner (iPhone)

Builds Kalshi sports combos (NFL, NBA, NHL), tracks them live with scores and
cash-out offers, and tells you when a combo is worth cashing out. Runs in **Pythonista 3**
on iPhone.

## Set up (about 10 minutes)

1. **Install Pythonista 3** from the App Store and open it once.
2. **Make a Kalshi API key**: kalshi.com → Account → API keys → Create key.
   Choose read + write (the planner places and cashes out combos only when you
   tap to confirm). Copy the Key ID and the whole private key. Kalshi shows the
   private key only once.
3. **Install the planner**: in Pythonista open the console (swipe left from the
   editor, or tap `>_`), paste this line and tap Return:

   ```
   import requests; exec(requests.get('https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/install_planner.py').text)
   ```

4. **Run it**: open `nfl_combo_planner.py` and tap ▶. A Welcome screen asks for
   your Key ID and private key, an optional free odds key (the-odds-api.com), and
   offers to add a Home Screen icon. Don't open `combo_planner_engine.py` in the
   editor. It's large and updates replace it.

New versions arrive through **Settings → Check for updates**.

## Optional: the Raspberry Pi watcher

A Pi at home watches your combos around the clock, sends alerts through the ntfy app and, if you turn
it on, does Auto cash-out by the same rules as the phone. Install it with `watcher/install_pi.sh`
(it prints a pairing code for Settings → Pi watcher). It installs a new version only after your phone
has updated to that exact version.

**Dead-man alert.** Make a free check at healthchecks.io (period 5 minutes, grace 5 minutes), copy its
ping URL, then on the Pi run:

    bash install_pi.sh --healthcheck https://hc-ping.com/<your check's id>

healthchecks.io emails or texts you if the Pi stops checking in.

**Reach the Pi from anywhere (Tailscale).** On the Pi:

    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up --ssh

Open the link it prints and sign in. Install Tailscale on your Mac and iPhone with the same account.
Then `ssh <you>@combowatch` works from anywhere, with nothing opened to the internet. In the Tailscale
admin page, turn off key expiry for the Pi so it stays connected.

## Optional: the watcher on a Mac (instead of a Pi)

A Mac that stays plugged in can run the same watcher. In Terminal:

```
curl -fsSLO https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/watcher/install_mac.sh
bash install_mac.sh
```

It asks for a new Kalshi API key just for the Mac, and for your phone's pairing code (Settings > Pi watcher)
so the existing ntfy topic keeps working. It runs in the background whenever you're logged in, restarts
itself, keeps the Mac awake while plugged in (leave the lid open), and only installs updates your phone approved.
`bash install_mac.sh --status` shows whether it's running. Run only one watcher at a time (Pi or Mac).

**Mac hub.** With Tailscale on the Mac and your iPhone, the installer prints a pairing code that includes the
Mac's address. Paste it into the phone (Settings > Pi watcher) and the phone gets its Kalshi data from the Mac
(kept fresh all the time) and sends trades there to be placed with the Mac's key. Everything between them is
encrypted and signed with the pairing secret. If the Mac can't be reached, the phone checks Kalshi itself and
uses its own backup key, after a second tap. `bash install_mac.sh --code` prints the code again.

## Files

- `nfl_combo_planner.py`: the planner (installed on the phone as `combo_planner_engine.py`).
- `install_planner.py`: installer and repair tool.
- `version.txt`: latest version number.
- `watcher/`: optional always-on watcher for a Raspberry Pi (`install_pi.sh`).

This repository holds **code only**. API keys, settings and betting history stay
in separate files on your phone and are never uploaded.

**Trust:** anyone who can push to this repository controls what the planner runs
on your phone, including with your Kalshi trading key. Only install from someone
you trust, or use a read-only Kalshi key and place bets yourself.

Bet responsibly: the planner estimates chances and can't promise outcomes.
