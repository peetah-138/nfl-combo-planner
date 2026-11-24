# Buy idea with no live fair price: log the reason (issue #255)

**Section:** Fair prices and data

The live-fair pricing of a single-game Buy idea (`idea_single_fair`: a game under way takes only `live_side_fair`, a
sportsbook line read within `LIVE_LINE_AGE` seconds or the live model; with neither the card shows Kalshi's price and a
yellow Buy anyway, never green, no edge) shipped earlier (#288). This adds the one missing piece: `api_act` `idea` now
logs the reason (`fi["nofair"]`) when a game under way falls back to no fair price. Log only; no guard changed, no
automatic path touched, Buy still needs Pete's tap and the IDEA_Q price/size match. Covered by `t_idea_inplay.py`.
