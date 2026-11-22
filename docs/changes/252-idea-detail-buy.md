# Buy idea Buy button: never green and dead, always an answer (issue #252)

**Section:** Live page (Buy ideas: ration, dismiss, fold, detail)

**What was wrong.** For a single-game idea, `ideaButtons` drew the Buy as a green countdown button ("Buy · 11s", with
the draining bar) but added `disabled` when the fresh price had no edge after Kalshi's fee (`q.edge <= 0`). A disabled
button is just `opacity:.5; pointer-events:none`, so Pete saw a green (or "faded") Buy that did nothing when tapped,
with no reason. Separately, every Buy answer was a toast at `z-index:50`, under the detail page (`.modal`, 60), so a
refusal on the detail page was invisible too. A network error threw out of `buyIdea`/`buySingle` silently, and a tap
after the quote ran out returned silently.

**Now (display only; the Mac's buy paths and guards are unchanged).**
- `ideaVerdict(x, q)` reads the fresh price: single with no edge left after the fee = **"No longer a good bet. Kalshi
  wants 60¢ and the fair chance is now 40% (it was 54% when this idea was found), so there's no edge left after the
  fee."**, no Buy, a **Get a new price** button instead; a single whose fair chance fell 5+ points since it was found, or
  under the bar (`clears` false), and a combo under the bar (`clears` false, the green bar of #142) = a yellow **Buy
  anyway** with the reason; otherwise the green Buy. The Buy is never `disabled` except while that buy is on its way
  ("Buying…").
- `ideaBuyGo` (behind `buyIdea`/`buySingle`): every tap ends with a plain answer, stored in `S.ideaAns[id]` and drawn on
  the card and the detail page (`.ians`): bought, Kalshi's or the guard's own refusal words, unclear ("check"), "That
  price ran out before your tap, so nothing was sent", or "Couldn't reach your Mac, so this may or may not have gone
  through" (a failed request). A second tap while one is on its way sends nothing. On the detail page a refusal shows
  on the page (no toast covering its buttons); a buy or "check" closes the page as before and shows a toast. The toast
  is now drawn above sheets and pages (`z-index:70`).
- Once a fresh price is on screen, the numbers from when the idea was found are dimmed under "When this idea was found
  · 3m old · older than the price below" (`ideaOld`), so the old +20% edge never sits beside a −4.9¢ fresh one
  unexplained. The fresh single block names its parts: Price now, Fair chance, Edge after fee, **Buy now: 4 contracts ·
  $2.47**, **Pays if it wins: $4**. The suggested stake reads "Stake → if it wins".
- "At the ask 94080" is now **Contracts at the ask: 94k** (`ideaCount`).

Never touched: Pause, caps (fail closed), rule 8 ("check" never resent), one order per idea/market per 2 min, the fresh
book re-read, the Mac's `IDEA_Q` check of size and price. Test: `test_idea_detail_buy.py` (phone 390, real taps through
the see-through haptic switch).

Doubt left for Pete: the single idea's fresh quote takes its fair chance from the Build board's side for that game
(`api_act` "idea"); the board is what said 40% for the in-play Memphis game.

ROADMAP: none
