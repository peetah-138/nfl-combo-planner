# Do-now batch A: small safety and docs tidy-ups (no display change, no money logic)

**Section:** Hub, Selling logs, docs

- **#458 (hub write ids).** The phone-to-Mac hub no longer accepts an id made only of dots (for example
  `DELETE /portfolio/orders/.`). Real ids that contain dots still work. Refs #458.
- **#457 (money stamp).** Failed cash-outs with no bet id no longer share one key, so two different failures cannot hide
  each other's "money moved" stamp for a minute. The `money_note` double-stamp half is not changed. Refs #457.
- **#434 (Pause read).** If the Pause read fails, the app still treats it as paused (nothing sells or buys by itself), and
  now prints one plain console line, at most once a minute. Refs #434.
- **#441 (exit replay one-liner).** `docs/EXIT_REPLAY.md` now downloads a fixed commit of the script and checks its
  fingerprint before running it; a test keeps the doc in step with the script. Refs #441.
