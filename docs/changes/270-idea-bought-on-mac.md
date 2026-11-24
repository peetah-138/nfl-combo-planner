# The Mac marks a Buy idea bought itself (issue #270)

**Section:** Live page (Buy ideas)

Before: only the phone's follow-up `idea_dismiss why=bought` marked a Buy idea bought, so a lost reply (or a dismiss that
never landed) left the idea live and a second Get price + Buy could buy it twice.

Now `idea_mark_bought(legs)` (planner) writes `st["bought"][idea_key(legs)]` in the idea dismissal file. It is called:
- inside `idea_single_buy` on an ok buy and on an unclear ("check") answer, only when an idea key came with the tap;
- in the web app's combo `buy` handler on an ok buy or a "check", after `accept_offer`, for that combo's tickers.

A definite refusal (Pause, cap, block, nobody selling) marks nothing, so the idea stays live. The mark never raises and
never changes the order's answer; hiding an idea only ever takes it off the list. Nothing here sends, retries or sizes an
order (rule 8: an unclear outcome stays "check" and is never resent).

Phone (`watcher/spa/ideas.js`): a lost reply (`r.lost`, "may have gone through, check Live") now hides the idea like a
check, and `ideaButtons` draws the disabled Pass + "Buying..." row whenever a buy is on its way, not only while the
20-second quote is fresh.

Tests: `t_singlebuy.py` (marks on ok and check, not on a refusal, unwritable file harmless, combo handler order),
`test_ideas2.py` (Buying row with no fresh quote).
