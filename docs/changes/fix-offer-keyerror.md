# Auto cash-out no longer aborts on an error-dict offer

Refs #514

When Kalshi answered a real-offer ask with "no offers", the stored offer was an error dict with no `offer` key. The
next `auto_sell_now` pass then raised `KeyError: 'offer'` (the "REAL OFFER not asked" note, and the estimate-vs-bar
checks) and aborted the whole pass, including any stop-loss. Now a stored offer without a numeric `offer` is treated
as the plain estimate (the same as no offer stored): it can never sell, the real-ask throttle and Pause / Rule 8
checks still apply, and the pass carries on to the next combo. No new automatic sale paths.

Test: `tests/suite/t_offer_keyerror.py` (an error-dict combo first, a cut-loss combo and a normal estimate combo after it).
