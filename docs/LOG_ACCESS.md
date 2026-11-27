# Reading the production Mac's logs from the dev Mac (issue #377)

The production Mac (the one that trades) can let the dev Mac read a **credential-scrubbed, read-only** view of its logs over
Tailscale, so problems can be looked at without SSH and without the dev Mac ever holding the Kalshi key,
`~/combowatch`, a copy of the history database or any `combo_*.json` file (CLAUDE.md hard rule 9, Pete decision
2026-11-23, widened by Pete's wide-access decision: query results over the endpoint, never the file).

It is **off by default**. It can't buy, sell, pause, change settings or move money. Pause is unaffected and the Pi
still never trades.

## What it serves

`GET /api/logs?source=console|autosell&since=<unix seconds>&limit=N` on the watcher hub (port 8765), with
`Authorization: Bearer <code>`.

| source     | file (on the production Mac only)       | what comes back                                         |
|------------|-----------------------------------------|---------------------------------------------------------|
| `console`  | `watcher.log` (stdout + stderr)         | redacted lines, each with its time (`t`) and `text`      |
| `autosell` | `combo_autosell_log.jsonl`              | auto cash-out records, allowlisted fields only (`rec`)  |

Every answer also has `status`: watcher and engine version, uptime, Pause, main/backup, and whether auto cash-out is
on. No other file can be named: the two names above are fixed in the code, and anything else is a 400.

Limits: 200 lines by default, at most 500; at most 200 KB per answer (the oldest lines are dropped first and
`truncated` says so); at most the last 1.5 MB of a file is read; 30 answers a minute per client.

## Who can ask

All of these must hold, or the answer is an empty error:

- **Turned on** on the production Mac (Settings › This Mac › "Let the dev Mac read logs"). Off = 404.
- **From the tailnet**: a Tailscale address (100.64.0.0/10 or fd7a:115c:a1e0::/48), Tailscale's own https front door
  with a signed-in person, or the Mac itself. The home network and Tailscale Funnel get 404.
- **The right code**, in the `Authorization` header only (never the address bar). Wrong = 401. Five wrong codes from
  one client in 10 minutes (or 30 from everyone) turn that client (or everyone) away with 429 for a while.
- **Only GET.** POST is 405 while on (with `Allow: GET`) and 404 while off, like everything else.
  Nothing changes anything.

The code is 32 random bytes made on the production Mac when the switch is turned on, shown **once**. Only its SHA-256
is stored (in `watcher.json`, which is never committed); the check is constant-time. Turning the switch off, or
tapping "New code", stops the old code at once. The code is never logged and never in `/app/mac-info`.

## The data window: `source=db`

`GET /api/logs?source=db&tables=1`, `...&table=<name>[&since=<unix>][&limit=N]` or `...&sql=<one SELECT>`. Same token, same
Tailscale-only reach, same on/off switch (off = nothing served, 404). It reads `combo_history.db` and nothing else; the
file itself is never sent, only query results.

- one fresh read-only connection (`mode=ro`, `query_only`), never the engine's own connection or lock
- an SQLite authorizer allows only SELECT/READ (plus a short list of harmless functions); every write, ATTACH, PRAGMA,
  `load_extension`, `pragma_*` table function and anything else is refused. One statement, no comments, at most 4000 characters
- 5 second limit, 1000 rows (200 default), 1.5 MB, one question at a time (a second one gets 429)
- cells are scrubbed like logs; a column named like a credential is masked whole; blobs are shown as `[blob N bytes]`
- a bad question is a 400 with a short JSON reason (`{"ok":false,"error":...}`); other refusals keep an empty body
- client: `tools/read_prod_logs.py --source db --tables | --table X --since ... | --sql "select ..."`

## Redaction (server-side, before anything is sent)

Only **credentials** are scrubbed. Ordinary content (team names, tickers, prices, balances, order outcomes, emails, IPs,
hostnames, paths) is kept so the logs are useful.

Masked:

- this Mac's live secret values wherever they appear (also URL-encoded or JSON-escaped): the ntfy topic, the pairing
  secret, the Combo Hub passcode, passkey ids, the health-check URL, and the Kalshi key ID, odds key and watcher code
- private key blocks (`-----BEGIN ... PRIVATE KEY-----`, any case), `Authorization`/`Bearer`/`Basic`/`Cookie`/`X-CW`/
  `KALSHI-ACCESS-*`/API-key headers, JWTs, the Combo Hub `cw=` cookie
- colour codes and invisible characters are stripped first, so they can't split a secret and slip it past the masks
- any `name=value` or `"name": value` whose name says secret, token, password, passcode, key id, api key, odds key,
  signature, session, cookie, watcher code, pairing, passkey, credential
- `user:pass@` in URLs and secret query values; long random-looking strings
- auto cash-out records keep every field except credential-named ones, and now carry `picks` (the legs, by name)

**Why the old answer was 503:** redaction rebuilt every URL with a strict parser that raises on a malformed URL (a link
followed by `]`, a bad port) and, on newer Pythons, on its own `https://[host]` placeholder when a console auto cash-out line was
scrubbed a second time. One such line failed the whole answer. Now URL handling is regex-only and never raises, redaction is
idempotent, and a line that still cannot be scrubbed is withheld on its own (`[line withheld: ...]`).

**Fails closed on credentials:** a live secret (or "PRIVATE KEY") surviving in the final answer data means nothing is sent
(503, empty body); only the error's type is logged. The masks are bounded so a huge hostile line can't stall the watcher.

**Known limits:** a secret that was base64-encoded, or split across two lines or cells, isn't recognised; anything a
third-party library prints in a shape not listed above is only caught if it looks like a long random string; a table may
hold sensitive values under an innocent column name (scrubbing is by shape and name); error text in a 400 comes from SQLite.

## Setup (Pete)

On the **production Mac**:

1. Open Combo Hub on that Mac, go to Settings › This Mac and turn on **Let the dev Mac read logs**.
2. A code appears once, with the address (`http://100.x.y.z:8765`). Keep the sheet open.
3. Send the code and the address to the dev Mac in a message to yourself (Messages or Notes; **Copy code** and
   **Copy address** help). Don't post them anywhere else, and delete the message once both are stored.

On the **dev Mac**:

1. Install Tailscale from tailscale.com/download, open it and sign in with the **same account** as the production
   Mac. The menu-bar icon should say Connected.
2. Open Terminal and run the command below. It asks for the code (so it never lands in your shell history): paste
   it and press Return, and press Return again if it asks you to type it a second time. If macOS asks about the
   keychain, click Allow.
   `security add-generic-password -a "$USER" -s nfl-combo-logs-token -w`
   **Faster (#379):** in the code sheet tap **Copy setup command**, then paste it once in Terminal on the dev Mac. It
   stores the address and the code (steps 2 and 3) in one go. It goes only to the clipboard; don't paste it into chat.
   Its leading space keeps it out of shell history where that is switched on.
3. Store the address the same way:
   `security add-generic-password -a "$USER" -s nfl-combo-logs-url -w`
4. Try it: run `cd ~/dev/nfl-combo-planner`, then `python3 tools/read_prod_logs.py --since 30m`. If log lines
   scroll past, it worked.

**Lockout, by design:** another device on the tailnet that keeps sending wrong codes can make everyone wait (the
global limit, 30 wrong codes in 10 minutes). That fails closed (nobody reads logs for a while); it never lets anyone
in. Fix: switch off, find the device in Tailscale, switch on again.

To replace a code later, add `-U` to step 2 (updates the stored one). To stop access, turn the switch off on the
production Mac.

## The client: `tools/read_prod_logs.py`

```
python3 tools/read_prod_logs.py [--source console|autosell|both] [--since 30m|2h|1d|<unix>|<ISO>]
                                [--limit N] [--grep REGEX | --problems] [--follow] [--json]
```

`--problems` is the grep `refused|check|failed|held|Traceback` (case-insensitive) in one word.

It reads `CW_LOGS_URL` / `CW_LOGS_TOKEN` from the environment, else the keychain services above. It never prints the
code. Errors say what to do (401: make a new code; 404: switch off, wrong address or Tailscale down; 429: wait;
503: the Mac couldn't redact safely, so sent nothing). With `--follow` it keeps going through short outages (a
warning, then the next try 15 s later), asks from the production Mac's own clock, and doesn't print the overlap twice.

## Code

`watcher/combo_watcher.py`, the block "dev Mac log reading (issue #377)": `log_route`, `log_answer`, `log_redact`,
`log_fields`, `log_client_ok`, `log_token_ok`, `LogGate`; Settings action `logaccess` (`log_access_set`) and the
`logs` status in `mac_settings`. UI: `watcher/spa/logaccess.js`. Tests: `tests/suite/t_logs_*.py`.
