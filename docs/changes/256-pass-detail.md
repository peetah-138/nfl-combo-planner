# Pass on a Buy idea clears it and keeps it cleared (issue #256)

**Section:** Live page (Buy ideas: ration, dismiss, fold, detail)

Pete: "When I hit pass on this screen, it should just clear that and send me back to live, but it doesn't. It's just like it
resets the ability to check the live price." Then, on the Live card with a fresh price on it and "Reconnecting to your Mac"
showing: "Same problem with this pass button. It should clear it from my screen."

What was wrong, and what Pass does now. Pass is the card's X / Not now: the idea leaves the screen at once, an Undo bar
shows, the Mac remembers it, and it stays gone.

- **The idea came back when the Mac could not be reached.** `ideaSend` took the hide back on any failed dismiss request and
  said "Couldn't hide that just now". With the link down (the "Reconnecting" pill) the card simply stayed. Now the idea
  stays hidden (`S.idHide[key] = true` until the Mac confirms, then the usual 9 s mask), the Undo bar shows right away, and the
  dismiss is retried in the background (`ideaSave`, `IDEA_SAVE_WAIT`: now, 2.5 s, 7 s, 15 s, 30 s, 1 min, 1 min, 2 min). After
  four failed tries it says "Hidden on this phone. Your Mac hasn't got that yet, still trying."; if every try fails it says it
  never got there and that the idea may come back after a refresh. Undo waits for a save still on its way, then tells the Mac,
  so Undo is always the last word. A second tap on the same idea sends nothing.
- **The detail page's Pass reset the card.** It threw the fresh price away first, so the card drew "Get today's price" again
  while the page slid shut. Pass no longer clears the quote itself; the card slides out as it is.
- **The idea could come straight back on its own fresh price.** The dismissal was measured from the old listed price, so the
  price Pete had just looked at (a few cents lower) counted as "price dropped 2 cents" at the next stored quote. The phone
  now sends the fresh price and edge it was showing (`seen`), and the Mac measures the way back from the better of that and the
  listed price (`idea_dismiss(..., seen=)`, `_idea_seen`; the act passes only ids it dismisses, at most 40, numbers checked).
  That only ever makes the bar to come back higher, never lower. A clearly better price (3 points of edge or 2 cents under
  what he saw) still brings the idea back.
- Small: the Undo bar is as wide as its words (`width:max-content`; it wrapped onto four lines on a phone).

Nothing here buys, sells or touches Pause, the caps or rule 8: dismissing only hides. No new setting.

Tests: `test_pass_detail.py` (phone 390, real taps, the real engine's dismiss store): detail Pass closes back to Live, the
idea is gone from the screen and the Mac's list, Undo shows and works, a refresh does not bring it back, a price just above
the one he saw does not re-offer it and a clearly better one does; Pass on the Live card with a fresh price and the dismiss
failing still clears it, retries and lands when the link returns, says so when it never lands; a slow dismiss clears at once
and Undo after it works.

ROADMAP: none
