# Dev Mac can read the production Mac's logs, read-only and redacted (issue #377)

**Section:** "Code map (where to look)" (and hard rule 9, which this PR edits directly as a Pete decision)

The watcher hub answers `GET /api/logs?source=console|autosell&since=&limit=` with a redacted tail of `watcher.log`
or `combo_autosell_log.jsonl` plus a status line (versions, uptime, Pause, role, auto cash-out on/off). Off by
default; Settings › This Mac › "Let the dev Mac read logs" (only on the Mac itself, `mac_settings` action
`logaccess` → `log_access_set`) makes a `secrets.token_urlsafe(32)` code shown once and stores only its SHA-256 in
`watcher.json` (`log_access`). Gates in order: on + tailnet only (`log_client_ok`: 100.64/10, fd7a:115c:a1e0::/48,
the Mac itself, Tailscale serve with a user; LAN and Funnel refused) → 404; `LogGate` 30/min per client, 5 wrong codes
per client / 30 overall per 10 min → 429; Bearer only, `hmac.compare_digest` on the hash → 401; bad params → 400;
any read or redaction error, or a live secret surviving (`LogLeak` tripwire) → 503 with an empty body. Other methods → 405 with `Allow: GET` while on, 404 while off.
Caps: 200 lines default, 500 max, 200 KB, last 1.5 MB of a file, 2000 chars a line. Redaction (`log_redact`,
`log_fields`; control and zero-width characters stripped first, patterns bounded against huge lines): live secret values (and their URL/JSON forms), PEM blocks (any case), auth headers, JWTs, the `cw` cookie, sensitive `key=value`/JSON
pairs, non-allowlisted URL hosts, emails, `*.ts.net`, IPs, UUIDs, home paths, long random strings, balance/pot
amounts; autosell records are field-allowlisted (`LOG_FIELDS`). Tickers and per-trade amounts are kept. Never takes a
lock, never touches a money path; Pause, the Pi and rule 8 are unaffected. Client: `tools/read_prod_logs.py`
(keychain `nfl-combo-logs-url` / `nfl-combo-logs-token`). Docs: `docs/LOG_ACCESS.md`. Tests: `t_logs_redact.py`,
`t_logs_failclosed.py`, `t_logs_auth.py`, `t_logs_readonly.py`, `t_logs_caps.py`, `t_logs_allowlist.py`,
`t_logs_default_off.py`.

ROADMAP: none
