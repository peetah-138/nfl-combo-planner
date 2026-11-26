# Wider log and data access for the dev Mac (follow-up to #377)

- **Console log 503 fixed.** The scrubber rebuilt URLs with a parser that raises on a malformed URL (and, on newer Pythons, on its
  own `https://[host]` placeholder), which failed the whole answer. URL handling is now regex-only, scrubbing is idempotent, and one
  bad line is withheld on its own.
- **Only credentials are scrubbed now.** API keys, tokens, private keys, auth headers and passwords are masked and the answer still
  fails closed on them. Team names, tickers, prices, balances, outcomes, emails and hostnames are kept.
- **Auto cash-out records name the legs** (`picks`) instead of only "Combo N".
- **Read-only data window** (`source=db`): SELECT-only questions about the collected data over the same endpoint, same code, same
  Tailscale-only reach, same "Let the dev Mac read logs" switch. Client: `tools/read_prod_logs.py --source db --table X --since ...`
  or `--sql`. The database file is never sent.
- Settings sheet wording: plain English, no Terminal steps.
- CLAUDE.md hard rule 9 reworded: query results over the endpoint are allowed; the database file, key and `~/combowatch` are not.

## Product notes (moved here from CLAUDE.md)

Log access for the dev Mac (#377; hard rule 9). The watcher hub answers `GET /api/logs?source=console|autosell&since=&limit=`
with a redacted tail of `watcher.log` or `combo_autosell_log.jsonl` plus a status line (versions, uptime, Pause, role, auto
cash-out on/off). Off by default; Settings › This Mac › "Let the dev Mac read logs" (only on the Mac itself, `mac_settings` action
`logaccess` → `log_access_set`) makes a `secrets.token_urlsafe(32)` code shown once and stores only its SHA-256 in `watcher.json`
(`log_access`). Gates in order: on + tailnet only (`log_client_ok`: 100.64/10, fd7a:115c:a1e0::/48, the Mac itself, Tailscale serve
with a user; LAN and Funnel refused) → 404; `LogGate` 30/min per client, 5 wrong codes per client / 30 overall per 10 min → 429;
Bearer only, `hmac.compare_digest` on the hash → 401; bad params → 400; any read or redaction error, or a live secret surviving
(`LogLeak` tripwire) → 503 with an empty body. POST → 405 with `Allow: GET` while on, 404 while off. Caps: 200 lines default, 500
max, 200 KB, last 1.5 MB of a file, 2000 chars a line. Scrubbing is for credentials only (`log_redact`, `log_fields`; control and zero-width characters
stripped first, patterns bounded against huge lines): live secret values (and their URL/JSON forms), PEM blocks (any case), auth
headers, JWTs, the `cw` cookie, credential-named `key=value`/JSON pairs, `user:pass@` and secret query values, long random strings.
Ordinary content (team names, tickers, prices, balances, emails, IPs, hostnames) is kept. It is idempotent and regex-only, and one line that
cannot be scrubbed is withheld on its own (`log_safe`) instead of failing the answer (the old 503 came from `urlsplit` raising on a
malformed URL); `log_tripwire` is the last check. Autosell records keep every field except credential-named ones and carry `picks` (leg names).
`source=db` (`log_db_answer`): `tables=1`, `table=X[&since=]` or `sql=<one SELECT>`; fresh `mode=ro` connection, `query_only`, authorizer
(SELECT/READ only, function allowlist, no `pragma_*`), 5 s deadline, 1000 rows, 1.5 MB, one query at a time (429); credential-named columns
masked, blobs not sent; a bad question is a 400 with a short JSON reason. It never takes a lock and never touches a money path; Pause, the Pi and rule 8 are unaffected. Tests: `t_logs_redact.py`,
`t_logs_failclosed.py`, `t_logs_auth.py`, `t_logs_readonly.py`, `t_logs_caps.py`, `t_logs_allowlist.py`, `t_logs_default_off.py`.


Data window hardening: credential-named columns read as NULL (authorizer), rows read one at a time with a byte budget, 64 KB value limit, sql= refused when SQLite limits are unavailable, no printf/format/replace/char/hex/quote; web-push endpoint URLs, topic and endpoint values are masked. The column mask is best-effort (shape-based).
