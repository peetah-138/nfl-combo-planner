# Bet-card chip "AT THE BAR" renamed "Ready to sell" (wording only)

**Section:** Live page

The grey chip on a Live bet card that shows the estimate has reached smart sell's line, but something is stopping the
sale right now (`smart_state` "reached"), now reads **Ready to sell** instead of "AT THE BAR". The green **SET TO SELL**
chip (`smart_state` "go") is unchanged. Changed in `watcher/spa/live.js` and the page check in
`tests/suite/t_mom_shadow.py`. No logic, setting, push text or money path is touched; the push text never used the old
words (the chip text the engine sends, `smart_chip`, is unchanged).
