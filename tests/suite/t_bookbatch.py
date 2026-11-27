# CHECK: group=engine
# #225: books_now reads many order books with Kalshi's batch endpoint (GET /markets/orderbooks) instead of one call per
# book. Same numbers as the single read (BOOK_DEPTH, BOOK_LADDER), and any error, odd answer or missing book falls back
# to the single read. Reads only. requests.get is faked.
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
calls = []
MODE = {"batch": "ok", "drop": set(), "bad": set()}


def ob(t):
    n = sum(map(ord, t)) % 7
    return {"yes_dollars": [["0.40", "50"], [f"0.4{n % 5}", "300"]], "no_dollars": [["0.50", "120"], ["0.5%d" % (n % 4), "80"]]}


class R:
    def __init__(self, js, good=True):
        self.js, self.ok = js, good

    def json(self):
        if isinstance(self.js, Exception):
            raise self.js
        return self.js


def fake_get(url, params=None, **kw):
    calls.append((url, params))
    if url.endswith("/markets/orderbooks"):
        if MODE["batch"] == "500":
            return R({}, False)
        if MODE["batch"] == "raise":
            raise E.requests.RequestException("down")
        if MODE["batch"] == "junk":
            return R({"orderbooks": "nope"})
        rows = [{"ticker": t, "orderbook_fp": ob(t)} for t in params["tickers"] if t not in MODE["drop"]]
        rows += [{"ticker": t, "orderbook_fp": "garbage"} for t in MODE["bad"]]
        rows.append({"ticker": "NOT-ASKED", "orderbook_fp": ob("x")})
        return R({"orderbooks": rows})
    return R({"orderbook_fp": ob(url.split("/markets/")[1].split("/")[0])})


E.requests.get = fake_get
T = [f"KXT-{i}" for i in range(5)]


def reset():
    E.BOOK_DEPTH.clear(); E.BOOK_LADDER.clear(); calls.clear()


# the reference: individual reads
reset()
single = {t: (E.book_depth(t, max_age=0), E.BOOK_LADDER[t][1]) for t in T}
ok("reference: one call per book", len(calls) == 5)

reset()
got = E.books_now(T)
ok("batch: one call for five books", len(calls) == 1 and calls[0][0].endswith("/markets/orderbooks"), calls)
ok("batch: same asks as the single reads", all(got[t] == single[t][1] for t in T))
ok("batch: same depth info as the single reads", all(E.BOOK_DEPTH[t][1] == single[t][0] for t in T))
ok("batch: nobody extra kept (a ticker we didn't ask for)", "NOT-ASKED" not in E.BOOK_DEPTH)
calls.clear()
E.books_now(T)
ok("books read in the last minute are not read again", not calls)

for mode in ("500", "raise", "junk"):
    reset(); MODE["batch"] = mode
    got = E.books_now(T)
    ok(f"fail closed ({mode}): falls back to single reads, same answer",
       all(got[t] == single[t][1] for t in T) and sum(c[0].endswith("/orderbook") for c in calls) == 5, len(calls))
MODE["batch"] = "ok"

reset(); MODE["drop"] = {"KXT-2", "KXT-3"}; MODE["bad"] = {"KXT-3"}
got = E.books_now(T)
single_calls = [c[0] for c in calls if not c[0].endswith("/markets/orderbooks")]
ok("a book the batch leaves out or garbles is read singly, the rest are not",
   len(single_calls) == 2 and any("KXT-2" in u for u in single_calls) and any("KXT-3" in u for u in single_calls), single_calls)
ok("...and every answer still matches", all(got[t] == single[t][1] for t in T))
MODE["drop"], MODE["bad"] = set(), set()

reset()
E.books_now(["KXT-0"])
ok("one book: the single read (no batch call)", len(calls) == 1 and calls[0][0].endswith("/markets/KXT-0/orderbook"))

reset()
many = [f"KXM-{i}" for i in range(230)]
E.books_batch(many)
ok("more than 100 books: split into calls of at most 100", [len(c[1]["tickers"]) for c in calls] == [100, 100, 30])
src = open("wahome/engine.py").read()
ok("only the read-only books_now uses the batch read; no buy, sale or hedge path", src.count("books_batch(") == 2, src.count("books_batch("))
