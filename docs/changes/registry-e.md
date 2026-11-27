# Registry E: the numbers card folds up (display only)

**Section:** Results › Selling › "The numbers smart sell and Smart Buy run on" and "What self-tuning changed"

Nothing about when or whether a sale, hedge or buy happens changed, and no number the app tunes changed. Only how the card looks.

- **#261 (done here):** opened, the card was about 60 rows. Each group (Taking a profit, Selling at a loss, Hedging, Selling: limits
  and checks, Smart Buy) is now its own fold, shut by default, with a one-line summary like "12 numbers · 2 learned". Both self-tuning
  cards now share one header that shows a keyboard focus ring, and the little arrow turns when you open or shut them. When the Mac
  can't read the numbers the card says "Couldn't read the numbers right now." instead of vanishing. A number that learns league by
  league carries a small "by league" tag when you pick a league chip. The three numbers that also sit in the table above
  (profit floor, risk weight, cut losses) say so inside their group.
- **#261, not done:** values do not roll when you switch league (they are written as words like "1.4x what you paid", not a plain
  number), and the three duplicate rows are noted rather than deleted, because the card is the only place that shows their starting
  point and range.
- **Already done on develop, no change here:** #214 (closed; the stale-page reload was finished in #535, checked again by #552) and
  the #246 items that landed in #535 and #552 (panel header numbers roll, toast ticks like a button, settled #c= link toast, sell sheet
  wording). Left in #246 and untouched here because they live on the server's sell path: stake rounding, "expected +$" format, the
  raw get_offer exception, and the .sacts hint taps.
