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
