# CHECK: group=engine
# #500: book_depth(max_age=0) stays a truly fresh read for buy, sell and hedge checks; only a caller that says
#  (the selling guards) may reuse a fetch a few seconds old. No Kalshi call: requests.get is faked.
import os, re, time, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
calls = []


class R:
    ok = True

    def json(self):
        return {"orderbook_fp": {"yes_dollars": [["0.48", "300"]], "no_dollars": [["0.50", "300"]]}}


def fake_get(url, **kw):
    calls.append(url)
    return R()


E.requests.get = fake_get
E.BOOK_DEPTH.clear()
a = E.book_depth("KXT-1", max_age=0)
ok("max_age=0: fetches", len(calls) == 1 and a and a["bid"] == 0.48)
E.book_depth("KXT-1", max_age=0)
E.book_depth("KXT-1", max_age=0)
ok("max_age=0 with no share: every call is a fresh fetch (money paths unchanged)", len(calls) == 3, len(calls))
E.book_depth_shared("KXT-1")
ok("a guard that shares reuses the fetch from a moment ago", len(calls) == 3, len(calls))
E.book_depth_shared("KXT-1")
ok("...as often as it asks inside the window", len(calls) == 3)
E.book_depth_shared("KXT-2")
ok("a different ticker is its own fetch", len(calls) == 4)
t, v = E.BOOK_DEPTH["KXT-1"]
E.BOOK_DEPTH["KXT-1"] = (time.time() - E.BOOK_SHARE_SECS - 1, v)
E.book_depth_shared("KXT-1")
ok("an older fetch than the window is refetched even for a sharing caller", len(calls) == 5)
E.book_depth_shared("KXT-1")
E.BOOK_DEPTH["KXT-1"] = (time.time() - 10, v)
E.book_depth_shared("KXT-1")
ok("a 10-second-old book is refetched", len(calls) == 6)
E.book_depth("KXT-1", max_age=0)
ok("a fresh max_age=0 caller right after a sharing one still gets a real fetch", len(calls) == 7)
E.book_depth("KXT-1")
ok("the default 60 s caller is unchanged (served from the cache)", len(calls) == 7)
src = open("wahome/engine.py").read()
uses = re.findall(r"(\w+) = book_depth_shared\(", src)
ok("only the two selling guards share a book; no buy, sale or hedge path does", len(uses) == 2 and len(re.findall(r"book_depth_shared\(", src)) == 3, uses)
