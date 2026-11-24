# Game card score-pulse test no longer races the page (issue #240)

**Section:** Tests

`test_gamecard_opp.py` bumped the opponent's score, slept 0.15 s, then looked for the `.gc.scored` pulse. The page clears that pulse
after 1.7 s (`scoreWatch` in `watcher/spa/games.js`) and a background poll can repaint the card, so on a loaded Mac the read lost the
race ("the score pulse broke: None"). The test now renders and reads in one `evaluate`, which cannot be interleaved. No product code
changed. Issues #189 (fixed by #234: hermetic engine tests, netguard), #331 (fixed by #330: `_clear_of_starts` pins the test clock),
#298 (run_checks.sh counts a non-zero exit status as FAIL) and #159 (`_SID` counter in `store_suggestion`, #220) were already fixed on develop.

ROADMAP: none
