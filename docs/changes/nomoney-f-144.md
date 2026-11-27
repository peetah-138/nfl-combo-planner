# Leftover small items: lost-reply note, cap wording, quick accessibility wins (issues #453, #112, #140)

**Section:** Build page / Live page (buy results), Settings wording, whole app (look)

Display and wording only. Nothing here touches buy, sell or sizing logic, the caps themselves, Pause or smart sell.

- **#453 Lost-reply buy:** when a buy's reply is lost (the phone could not reach the Mac) or comes back unclear, Build
  cards, Long shots and Live buy ideas now leave a sheet that stays until tapped ("Check Live" for a lost reply,
  "Check Kalshi" for an unclear one) instead of a 6 to 9 second toast. If another sheet is already open it falls back
  to a long toast. New `checkLive(msg, title)` in `moments.js`; the three buy paths flag a lost reply with `lost:true`.
  The straight-bet sheet already behaved this way.
- **#112 cap message:** the "over your cap" message now says to raise the cap to the next $10 step (what the Settings
  slider can actually be set to, up to $200), e.g. "at least $60" for a $54 total. `cap_msg` only; the check
  `spent + stake > budget` is unchanged.
- **#140 quick wins:** the toast is a polite live region (`role=status`), buttons, links and fields get a keyboard focus
  ring (`chrome.css`), and the grey "mute" text is a little darker in light mode (`#6f7890`) and lighter in dark mode
  (`#8790a3`) for contrast.

Checked and left to the other branch: nomoney-d-144 only touches the Best bets heading and housekeeping, no overlap.
Left out: #431 (open PR #465, money wording decision), #494 (research outside the repo), #512 (adds new quote pulls
and a recorder; not a small add-on), #63 #64 #69 #72 #78 #148 #187 (large, or need Pete's call on design), the rest of
#140 (hold-to-buy and celebration changes alter the buy tap), and the other #112 items (paper test and hero estimate
sit near the sell path).

Tests: `t_nomoney_f.py` (source checks), `t_capmsg.py` (new $10-step wording).
