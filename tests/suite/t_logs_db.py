# CHECK: group=engine
"""The dev Mac's read-only window on the collected data (source=db): SELECT only, one statement, capped, time-limited,
scrubbed, token-protected, and nothing on disk ever changes."""
import sys, os, json, socket, tempfile, importlib.util, time, http.client, hashlib, sqlite3, glob
from urllib.parse import quote
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: None; W.CONF = "run/test_logs_conf.json"; W.HOME = tempfile.mkdtemp(dir="run")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
PEM_TAG = "PRIVATE " + "KEY"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def start(conf):
    conf.setdefault("topic", "t"); conf.setdefault("secret", "s"); conf.setdefault("web_pass", "pass1234")
    conf["hub_port"] = free_port(); conf["https_auto"] = False
    return W.start_hub(conf, M), conf["hub_port"]


def req(port, path, tok=None, method="GET", auth=None):
    h = {}
    if auth is not None:
        h["Authorization"] = auth
    elif tok is not None:
        h["Authorization"] = "Bearer " + tok
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        c.request(method, path, headers=h)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def fresh():
    W.LOG_GATE = W.LogGate()


def snap():
    """Every file in the folder: name -> (size, mtime_ns, sha256). A read-only window must leave all of it alone."""
    out = {}
    for f in sorted(glob.glob(os.path.join(W.HOME, "*"))):
        if f.endswith("-shm"):
            continue                  # sqlite's shared-memory index: any reader legitimately touches it; it holds no data
        b = open(f, "rb").read()
        out[os.path.basename(f)] = (len(b), os.stat(f).st_mtime_ns, hashlib.sha256(b).hexdigest())
    return out


def q(port, tok, **kw):
    fresh()
    return req(port, "/api/logs?source=db&" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in kw.items()), tok=tok)


TOPIC = "zq7-fake-topic-91"
conf = {"topic": TOPIC, "secret": "fakeSharedSecret4471", "web_pass": "pass1234xy"}
tok = W.log_new_token(conf)
srv, port = start(conf)
path = os.path.join(W.HOME, W.LOG_DB_FILE)
fresh()
c, b = req(port, "/api/logs?source=db&tables=1", tok=tok)
ok("no history database yet: 400 with a short reason", c == 400 and json.loads(b)["ok"] is False)

# a WAL database with a live writer connection held open (as the engine's is)
w = sqlite3.connect(path, isolation_level=None)
w.execute("pragma journal_mode=wal")
w.execute("create table ticks(ts real, ticker text, chance real, state text, score text)")
w.execute("create table sell_log(ts real, ticker text, result text, why text, api_token text, detail text)")
w.execute("create table ledger(ticker text primary key, kind text, cost real)")
now = time.time()
for i in range(1500):
    w.execute("insert into ticks values(?,?,?,?,?)", (now - 1500 + i, "KXNBAGAME-26NOV23DENBOS-DEN", 0.5, "live", "Denver Nuggets 54 Boston Celtics 51"))
w.execute("insert into sell_log values(?,?,?,?,?,?)", (now, "KXA-1", "sold", "Denver Nuggets leg won; balance $4,411.20", "SHOULDNOTSHOW1234", "{}"))
w.execute("insert into sell_log values(?,?,?,?,?,?)", (now, "KXA-2", "held", "push to " + TOPIC + " Authorization: Bearer abcdefghijklmnop1234", "x",
          "-----BEGIN RSA " + PEM_TAG + "-----\nMIIEvQIBADANBgkqhkiG9w0\n-----END RSA " + PEM_TAG + "-----"))
w.execute("insert into sell_log values(?,?,?,?,?,?)", (now, "KXA-3", "sold", "blob", "y", None))
w.execute("insert into ledger values('KXA-1','combo',12.5)")
w.execute("insert into ticks values(?,?,?,?,?)", (now, "BLOBROW", 0.1, "x", None))
before = snap()

# ---- reading works
c, b = q(port, tok, tables=1)
a = json.loads(b)
ok("tables: names and columns", c == 200 and {t["name"] for t in a["tables"]} == {"ticks", "sell_log", "ledger"}
   and "ticker" in next(t for t in a["tables"] if t["name"] == "ticks")["columns"])
c, b = q(port, tok, table="sell_log")
a = json.loads(b)
txt = json.dumps(a)
ok("table: 200, newest rows last, columns named", c == 200 and a["columns"][:3] == ["ts", "ticker", "result"] and len(a["rows"]) == 3)
ok("ordinary data flows (team names, dollar balance, tickers)", "Denver Nuggets leg won; balance $4,411.20" in txt and "KXA-1" in txt)
ok("a credential-named column is masked whole", "SHOULDNOTSHOW1234" not in txt)
ok("live topic, bearer token and key block are scrubbed in cells", TOPIC not in txt and "abcdefghijklmnop1234" not in txt and "MIIEvQIBADA" not in txt)
c, b = q(port, tok, table="ticks", limit=5000)
a = json.loads(b)
ok("row cap: limit above 1000 gives 1000 and says truncated", c == 200 and len(a["rows"]) == 1000 and a["truncated"] is True)
c, b = q(port, tok, table="ticks", since=now - 10, limit=50)
a = json.loads(b)
ok("table + since: only recent rows, oldest first", c == 200 and 0 < len(a["rows"]) <= 12 and a["rows"][0][0] <= a["rows"][-1][0] and all(r[0] >= now - 10 for r in a["rows"]))
c, b = q(port, tok, table="ledger", since=1)
ok("since on a table with no ts column: 400", c == 400)
c, b = q(port, tok, sql="select ticker, count(*) n from ticks group by ticker order by n desc")
a = json.loads(b)
ok("sql: a SELECT with GROUP BY works", c == 200 and a["columns"] == ["ticker", "n"] and a["rows"][0][1] == 1500)
c, b = q(port, tok, sql="select ticker, chance from ticks where ticker = 'BLOBROW';")
ok("sql: one trailing semicolon is fine", c == 200 and json.loads(b)["rows"] == [["BLOBROW", 0.1]])
c, b = q(port, tok, sql="with t as (select ticker from ledger) select * from t")
ok("sql: WITH ... SELECT works", c == 200 and json.loads(b)["rows"] == [["KXA-1"]])
c, b = q(port, tok, sql="select length(why), upper(result), sqrt(4) from sell_log where ticker='KXA-1'")
ok("sql: allowlisted functions work", c == 200)
c, b = q(port, tok, sql="select typeof(ts), cast(ts as int) > 0 from ticks limit 1")
ok("sql: typeof / cast work", c == 200)
c, b = q(port, tok, sql="select name, sql from sqlite_master")
ok("sql: the schema is readable", c == 200 and len(json.loads(b)["rows"]) >= 3)
c, b = q(port, tok, sql="select randomblob(16)")
ok("sql: a function not on the list is refused", c == 400)
big = json.loads(q(port, tok, sql="select zeroblob(100)")[1] or b"{}")
ok("sql: zeroblob is not on the list", big.get("ok") is False)
c, b = q(port, tok, sql="select 1 as x")
ok("sql: select 1 works (no table needed)", c == 200 and json.loads(b)["rows"] == [[1]])
c, b = q(port, tok, sql="select " + "'" + "A" * 3000 + "' as x")
ok("a huge cell is cut to 2000 characters", c == 200 and len(json.loads(b)["rows"][0][0]) <= 2003)
c, b = q(port, tok, sql="select ticker, score from ticks where ticker='BLOBROW'")
ok("NULL stays null", c == 200 and json.loads(b)["rows"] == [["BLOBROW", None]])
c, b = q(port, tok, sql="select x'414243' as b")
ok("a blob value is never sent raw", c == 200 and "[blob 3 bytes]" in b.decode())

# ---- everything that is not one plain SELECT is refused, and nothing on disk changes
BAD = [
    "insert into ledger values('X','y',1)", "update ledger set cost=0", "delete from ledger", "drop table ledger",
    "create table z(a)", "create index zi on ledger(cost)", "alter table ledger add column q", "replace into ledger values('X','y',1)",
    "attach database '/tmp/x.db' as x", "attach database ':memory:' as m", "detach database main", "pragma journal_mode=delete",
    "pragma query_only=OFF", "pragma table_info(ledger)", "vacuum", "reindex", "analyze", "begin", "commit", "rollback",
    "savepoint a", "release a", "select 1; select 2", "select 1; drop table ledger", "select 1;;", "select 1; -- x",
    "select 1 -- comment", "select 1 /* c */", "with x as (select 1) insert into ledger select 'Q','q',1 from x",
    "with x as (select 1) delete from ledger", "select load_extension('/tmp/x.dylib')", "select readfile('/etc/passwd')",
    "select * from pragma_table_info('ledger')", "select * from pragma_database_list", "select * from sqlite_sequence",
    "explain select 1", "values (1)", "", "   ", "selectx 1", "/*x*/ select 1", "(select 1)", "\nupdate ledger set cost=1",
    "select 1 where 1=1; attach 'x' as y", "insert into ledger select * from ledger", "create temp table t(a)",
    "create virtual table v using fts5(a)", "select edit('x')", "select fts3_tokenizer('x')", "select sqlite_compileoption_used('x')",
    "select 1\x00; drop table ledger", "select 1;\x0bdrop table ledger"]
allgood = True
for sql in BAD:
    c, b = q(port, tok, sql=sql)
    good = c == 400 and b"error" in b and json.loads(b)["ok"] is False
    if not good:
        allgood = False
        print("FAIL refused:", repr(sql), c, b[:80])
    if snap() != before:
        allgood = False
        print("FAIL files changed after:", repr(sql))
ok("every write / ATTACH / PRAGMA / multi-statement / extension attempt is refused (400) and no file changes", allgood)
c, b = q(port, tok, sql="select count(*) from ledger")
ok("the data is intact after all of that", json.loads(b)["rows"] == [[1]])
for t in ('ticks"; drop table ledger;--', "ticks;", "sqlite_master", "nope", "../x", "ticks where 1", "ledger limit 1", "pragma_table_info", ""):
    c, b = q(port, tok, table=t)
    ok(f"table name {t!r}: 400", c == 400)
ok("a table name that is not in sqlite_master is never put into SQL (files unchanged)", snap() == before)

# the connection itself: even code that skipped every check above cannot write
con = W.log_db_connect(path)
for stmt in ("create table z(a)", "insert into ledger values('X','y',1)", "attach database ':memory:' as m", "pragma query_only=OFF",
             "drop table ledger", "delete from ledger", "update ledger set cost=9", "vacuum"):
    try:
        con.execute(stmt); wrote = True
    except sqlite3.Error:
        wrote = False
    ok(f"the connection refuses: {stmt}", not wrote)
ok("the connection reads", con.execute("select count(*) from ledger").fetchone()[0] == 1)
con.close()
ro = sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True)
try:
    ro.execute("insert into ledger values('X','y',1)"); roerr = None
except sqlite3.Error as e:
    roerr = e
ro.close()
ok("the file is opened mode=ro (sqlite itself refuses a write)", roerr is not None)
ok("after the connection tests, still nothing changed on disk", snap() == before)
import inspect
src = inspect.getsource(W.log_db_connect)
ok("the connection opens with mode=ro, sets query_only, an authorizer and a time limit", "mode=ro" in src and "query_only=ON" in src and "set_authorizer" in src and "set_progress_handler" in src)
ok("the data code never touches the engine's own connection or lock", "STORE" not in inspect.getsource(W.log_db_answer) and "_SLOCK" not in inspect.getsource(W.log_db_answer))

# ---- time limit and one at a time
W.LOG_DB_SECONDS = 0.6
t0 = time.time()
c, b = q(port, tok, sql="with recursive c(x) as (select 1 union all select x+1 from c) select count(*) from c")
ok("a runaway question is stopped (400 'took longer') within a few seconds", c == 400 and b"longer" in b and time.time() - t0 < 6)
W.LOG_DB_SECONDS = 5.0
W._LOG_DB_LOCK.acquire()
c, b = q(port, tok, sql="select 1")
W._LOG_DB_LOCK.release()
ok("a second question while one runs: 429 empty", c == 429 and b == b"")
c, b = q(port, tok, sql="select 1")
ok("and it works again afterwards", c == 200)
c, b = q(port, tok, sql="select 1 " + "-" * 5000)
ok("an over-long question: 400", c == 400)

# ---- who can ask: same gates as the logs
fresh(); c, b = req(port, "/api/logs?source=db&tables=1", tok="wrong" * 8)
ok("wrong code: 401 empty", c == 401 and b == b"")
fresh(); c, b = req(port, "/api/logs?source=db&tables=1")
ok("no code: 401 empty", c == 401 and b == b"")
fresh(); c, b = req(port, "/api/logs?source=db&tables=1", tok=tok, method="POST")
ok("POST: 405, not a write path", c == 405 and b == b"")
for extra in ("&path=/etc/passwd", "&file=x", "&db=/tmp/other.db", "&source=db"):
    fresh(); c, b = req(port, "/api/logs?source=db&table=ledger" + extra, tok=tok)
    ok(f"unknown or repeated parameter {extra}: 400 empty", c == 400 and b == b"")
fresh(); c, b = req(port, "/api/logs?source=db&table=ledger&sql=select+1", tok=tok)
ok("table and sql together: 400", c == 400)
fresh(); c, b = req(port, "/api/logs?source=history", tok=tok)
ok("source=history is still not a thing: 400", c == 400)
fresh(); c, b = req(port, "/api/logs?source=db&limit=abc&table=ledger", tok=tok)
ok("bad limit: 400", c == 400)
# off switch: when off, nothing at all is served, db included
saved = conf.pop("log_access")
fresh(); c, b = req(port, "/api/logs?source=db&table=ledger", tok=tok)
ok("switch off: 404 empty, no data", c == 404 and b == b"")
fresh(); c, b = req(port, "/api/logs?source=db&sql=select+1", tok=tok)
ok("switch off: sql also 404", c == 404 and b == b"")
conf["log_access"] = saved
fresh(); c, b = req(port, "/api/logs?source=db&table=ledger", tok=tok)
ok("switch back on with the same code: served again", c == 200)
tok2 = W.log_new_token(conf)
fresh(); c, b = req(port, "/api/logs?source=db&table=ledger", tok=tok)
ok("a new code stops the old one for data too: 401", c == 401)
fresh(); c, b = req(port, "/api/logs?source=db&table=ledger", tok=tok2)
ok("the new code works", c == 200)
ok("the whole time, no file on disk changed", snap() == before)

# ---- fail closed on a credential that survives scrubbing
_ls, _lr = W.log_safe, W.log_redact
W.log_safe = lambda t, s: t; W.log_redact = lambda t, s: t
c, b = q(port, tok2, table="sell_log")
ok("scrubbing off: the answer-level tripwire gives 503 empty, the secret is not sent", c == 503 and b == b"" and TOPIC.encode() not in b)
W.log_safe, W.log_redact = _ls, _lr
c, b = q(port, tok2, table="sell_log")
ok("and it answers again once scrubbing is back", c == 200)
srv.shutdown()
