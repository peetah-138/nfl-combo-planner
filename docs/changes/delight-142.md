# Plain words on the Promote and cut-losses cards, calmer toast (issues #569 #570 #571 #573)

**Section:** Results page, Live page (notification links)

Display and wording only; no money logic changed.

- **Promote card (#569, #573):** "Ready: say go" is now "Ready to turn on", and the card says how: tell Claude "go" (there is
  deliberately no button; nothing turns on by itself). "Cleared the strict bar" and "Streak 1 of 3" became "passed 3 checks in a
  row, each on games it had not seen before" and "passed 1 of 3 checks on new games so far". The push reads
  "<name> passed its paper test 3 times in a row. Tell Claude "go" to turn it on." (still no urgent words, so it goes in the
  quiet digest). The status chip now always sits under its title, left-aligned, on every row (`results.css` `.prtop`).
- **Cut-losses card (#570):** the long explanation that was repeated per league is said once above the table (`results.js`,
  "Smart sell, tuned by league"), including why NBA / NFL / MLB differ: a league starts on the cautious 12.5% cut, then its own
  number replaces it, and it can learn "never". Each row's Cut losses cell now carries one short reason ("starting value, too few
  results yet", "its own result", "cutting did not help here"); a league's own late-game guards are shown only when it learned them.
- **Toast (#571):** `openClosed`/`closedFill` now return whether the closed bet's page loaded, and `comboFromHash` shows "That bet
  is no longer live" only then, never over "We can't find that bet" or "Couldn't load that bet".

Tests: `t_promote.py` (ready wording and the push text), `test_queue_hygiene_ui.py` (toast only after the page loads, none over
"can't find that bet"), `test_analytics.py` (the once-only cut-losses explanation).
