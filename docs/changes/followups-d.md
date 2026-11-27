# Follow-ups D

- Results > Smart sell, tuned by league: the "Cut losses" column used to say "never" for a league with no loss cut of its own, even though combos there are on the 12.5% starting cut (#556). It now says "Default 12.5%" (late, confirmed; combos only). Still "never" when the switch is off or the league's own tuning chose no cut. Display only; no bet, sell or setting changes. It does not know about self-tuning's brake (which can hold the default off for a league).
- t_orderbook "caps at the whole contracts on sale": see the PR for what was found.
