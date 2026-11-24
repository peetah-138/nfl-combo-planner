# t_cover no longer depends on the real date or time zone (issue #370)

**Section:** Tests / cover test

`t_cover.py` failed on CI (UTC) whenever the UTC date was a day ahead of Pacific: the test chose the week's Sunday from
the machine's local `date.today()`, while `_cover_pass` chose it from the real Pacific date. Not a production bug (the
engine was consistently Pacific). The Sunday rule is now `_cover_sunday(now)` (Pacific date of the pass's own clock,
identical result in production); the test pins its week (Sunday 2026-11-22) and checks all 7 weekdays map to it.
