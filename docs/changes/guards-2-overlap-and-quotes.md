# Overlap re-grey after Add anyway, overlap log, own request kept (issues #366, #367, #350)

**Section:** Build page / Fair prices and data

- **#366, never looser.** "Add anyway" now carries the game's exposure at the tap (`KEY~n~risk`, `overlap.js` `S.ovAllow`
  is a Map). `overlap_allow` returns a set subclass with the exposure; `overlap_games` greys the game again when more bets
  (`n`) or more dollars at risk than at the tap are riding. Exposure that fell never greys by itself. An older page that
  sends a plain key is let through as before. Malformed or negative values are dropped; duplicates keep the stricter one.
- **#367, measurement.** `overlap_log(kind, game, n, risk, why)` writes greyed games ("grey", once per 30 minutes per
  game and exposure) and Add anyway taps ("add") to the `overlap_log` table. It never raises and never changes the answer.
- **#350.** `carry_quote` no longer withdraws Pete's own open "Get price" request on the same combo: if any request is open
  (or the list cannot be read) it makes no quote instead of calling `clear_my_rfqs`.

Tests: `t_guards2.py`.
