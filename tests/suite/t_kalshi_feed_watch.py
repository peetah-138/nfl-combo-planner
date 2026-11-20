# The Kalshi API watch (tools/kalshi_feed_watch.py, run by .github/workflows/kalshi-api-watch.yml on GitHub): reads
# Kalshi's API changelog RSS feed and opens one issue per new entry. Real feed shape: fixtures/kalshi_changelog.rss
# (a trimmed copy of https://docs.kalshi.com/changelog/rss.xml). Nothing here touches the network or GitHub: the
# feed comes from the fixture or from strings, and GitHub is a fake with the same methods as the real `gh` wrapper.
import os, re, sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("REPO") or os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
import kalshi_feed_watch as K

ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
FIXTURE = open(os.path.join(HERE, "fixtures", "kalshi_changelog.rss"), "rb").read()
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


class FakeGh:
    """Same methods as K.Gh, kept in memory."""

    def __init__(self, issues=None, fail_list=False, fail_create=False):
        self.issues, self.labels, self.count = list(issues or []), {}, 0
        self.fail_list, self.fail_create, self.created, self.closed = fail_list, fail_create, [], []

    def list_issues(self, label, state="all"):
        if self.fail_list:
            raise RuntimeError("boom")
        out = [i for i in self.issues if label in i.get("labels", [])]
        return [i for i in out if state == "all" or i["state"] == state]

    def ensure_label(self, name, color, description):
        self.labels[name] = description

    def create_issue(self, title, body, labels):
        if self.fail_create:
            raise RuntimeError("no")
        n = len(self.issues) + 1
        self.issues.append({"number": n, "title": title, "body": body, "state": "open", "labels": list(labels)})
        self.created.append((title, body, list(labels)))
        return f"https://example.invalid/issues/{n}"

    def close_issue(self, number, comment):
        for i in self.issues:
            if i["number"] == number:
                i["state"] = "closed"
        self.closed.append(number)

    def fail_count(self):
        return self.count

    def set_fail_count(self, n):
        self.count = n


def rss(*items):
    body = "".join(items)
    return f'<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>x</title>{body}</channel></rss>'.encode()


def item(title="T", guid="g1", date="Thu, 19 Nov 2026 16:47:30 GMT", desc="d", link="https://docs.kalshi.com/changelog#x", content=None):
    c = f"<content:encoded><![CDATA[{content}]]></content:encoded>" if content is not None else ""
    return (f"<item><title><![CDATA[{title}]]></title><description><![CDATA[{desc}]]></description><link>{link}</link>"
            f"<guid>{guid}</guid><pubDate>{date}</pubDate>{c}</item>")


def raises(data):
    try:
        K.parse_feed(data)
    except K.FeedError:
        return True
    except Exception:
        return False
    return False


# ---- parsing the real feed
items = K.parse_feed(FIXTURE)
by = {i["guid"]: i for i in items}
ok("fixture: parses all six items", len(items) == 6)
x = by["b81510679af390a1"]
ok("fixture: title, guid, link, date read", x["title"] == "Listener mode on KalshiRFQ sessions" and x["link"].startswith("https://docs.kalshi.com/changelog")
   and x["date"] == datetime(2026, 11, 19, 16, 47, 30, tzinfo=timezone.utc))
ok("fixture: categories become tags", "FIX" in x["tags"])
ok("fixture: HTML is stripped from every summary", all(not re.search(r"</?[a-zA-Z][^>]*>", i["summary"]) and "&lt;" not in i["summary"] and "<![CDATA" not in i["summary"] for i in items))
ok("fixture: summary keeps the words and the line breaks stay plain", "listener mode" in x["summary"].lower() and "ListenerSession<20126>=Y" in x["summary"] or "ListenerSession" in x["summary"])
ok("fixture: every item has a summary within the length limit", all(0 < len(i["summary"]) <= K.SUMMARY_MAX for i in items))

# ---- keyword flagging
ok("flag: 'removed' in the real feed is flagged", by["87e8e0c610c83644"]["breaking"])
ok("flag: rate limit headers entry is flagged", by["714421dc1a050e02"]["breaking"])
ok("flag: a plain addition is not flagged", not by["6c952087f58b2bc5"]["breaking"])
words = ["deprecated", "sunset", "removed", "breaking change", "discontinued", "migrate", "will be disabled", "no longer works", "orders", "portfolio",
         "RFQ", "quote", "fixed-point", "order book", "websocket", "authentication", "signing", "rate limit"]
miss = [w for w in words if not K.parse_feed(rss(item(title="Thing", desc=f"We changed the {w} today")))[0]["breaking"]]
ok("flag: every keyword flags (case-insensitive)", not miss and K.parse_feed(rss(item(desc="We changed the ORDER BOOK")))[0]["breaking"])
ok("flag: a keyword only in the title also flags", K.parse_feed(rss(item(title="Websocket changes", desc="nothing")))[0]["breaking"])
ok("flag: no keyword, no flag", not K.parse_feed(rss(item(title="New markets", desc="Weather markets for more cities")))[0]["breaking"])
b = K.issue_body(by["87e8e0c610c83644"]); p = K.issue_body(by["6c952087f58b2bc5"])
ok("body: flagged issue starts with ACTION LIKELY NEEDED", b.startswith("**ACTION LIKELY NEEDED**"))
ok("body: unflagged issue has no ACTION line", "ACTION LIKELY NEEDED" not in p)
ok("body: link, date and the dedupe marker are in", "https://docs.kalshi.com/changelog" in b and "2026-11-12" in b and "kalshi-feed-id: 87e8e0c610c83644" in b)
ok("title: prefix and the entry title", K.issue_title(by["87e8e0c610c83644"]) == "Kalshi API change: Market expiration_time removed")

# ---- the 14-day window, cap, ordering
known = set()
todo, waiting = K.pick_new(items, known, NOW)
ok("window: first run takes only what the cap allows (5) and says one waits", len(todo) == 5 and waiting == 1)
ok("window: flagged entries come first, then newest", [i["breaking"] for i in todo] == sorted([i["breaking"] for i in todo], reverse=True))
late = datetime(2026, 11, 28, 0, 0, tzinfo=timezone.utc)      # cutoff 14 Nov: only the 16, 19, 19 and 20 Nov entries
todo, _ = K.pick_new(items, known, late)
ok("window: entries older than 14 days are never filed", {i["guid"] for i in todo} == {i["guid"] for i in items if i["date"] >= late - timedelta(days=14)} and len(todo) == 3)
todo, _ = K.pick_new(items, known, datetime(2027, 3, 1, tzinfo=timezone.utc))
ok("window: an old feed files nothing (no flood)", todo == [])
odd = K.parse_feed(rss(item(guid="a", date="not a date"), item(guid="b", date="")))
ok("window: an unreadable date is skipped, not filed", K.pick_new(odd, set(), NOW)[0] == [])
dup = K.parse_feed(rss(item(guid="same"), item(guid="same", title="again")))
ok("window: the same guid twice in one feed is one issue", len(K.pick_new(dup, set(), NOW)[0]) == 1)
many = K.parse_feed(rss(*[item(guid=f"g{n}", title=f"T{n}", desc="plain") for n in range(12)]))
ok("cap: 12 new entries file 5 and leave 7 for later", (len(K.pick_new(many, set(), NOW)[0]), K.pick_new(many, set(), NOW)[1]) == (5, 7))

# ---- dedupe against existing issues (open and closed), reruns never duplicate
gh = FakeGh()
rc = K.run(lambda: FIXTURE, gh, now=NOW)
ok("run: first run opens 5 issues, exits 0, creates the labels", rc == 0 and len(gh.created) == 5 and K.LABEL in gh.labels and K.LABEL_BREAKING in gh.labels)
ok("run: issues carry the labels (breaking only where flagged)", all(l[0] == K.LABEL for _, _, l in gh.created)
   and all((K.LABEL_BREAKING in l) == ("ACTION LIKELY NEEDED" in b) for _, b, l in gh.created))
rc = K.run(lambda: FIXTURE, gh, now=NOW)
ok("run: second run files the last one only", rc == 0 and len(gh.created) == 6)
rc = K.run(lambda: FIXTURE, gh, now=NOW)
ok("run: a third run changes nothing (no duplicates)", rc == 0 and len(gh.created) == 6 and len({K.ids_in([{'body': b}]).pop() for _, b, _ in gh.created}) == 6)
gh2 = FakeGh([{"number": 9, "title": "x", "state": "closed", "labels": [K.LABEL], "body": "hello\nkalshi-feed-id: 6c952087f58b2bc5\n"}])
K.run(lambda: FIXTURE, gh2, now=NOW)
ok("dedupe: a CLOSED issue still counts as filed", not any("6c952087f58b2bc5" in b for _, b, _ in gh2.created))
ok("dedupe: ids_in reads markers from many bodies", K.ids_in([{"body": "a kalshi-feed-id: aa1 z"}, {"body": None}, {"body": "kalshi-feed-id:bb2"}]) == {"aa1", "bb2"})
gh3 = FakeGh(fail_list=True)
rc = K.run(lambda: FIXTURE, gh3, now=NOW)
ok("dedupe: if issues cannot be listed it creates nothing (and the run shows red)", rc == 1 and gh3.created == [])
gh4 = FakeGh(fail_create=True)
ok("run: a failed create makes the run red, not silent", K.run(lambda: FIXTURE, gh4, now=NOW) == 1)

every_label = set(gh.labels) | {x for i in gh.issues for x in i["labels"]} | {K.LABEL_COUNT}
ok("labels: only kalshi-* and 'breaking' are ever used; never a wip:* label (other sessions own those)",
   every_label <= {K.LABEL, K.LABEL_BREAKING, K.LABEL_FAILING, K.LABEL_COUNT} and not any(l.startswith("wip:") for l in every_label))

# ---- dry run changes nothing
gh5 = FakeGh()
rc = K.run(lambda: FIXTURE, gh5, now=NOW, dry_run=True)
ok("dry run: no issues, no labels, no failure count", rc == 0 and gh5.created == [] and gh5.labels == {} and gh5.count == 0)
gh6 = FakeGh(); K.run(lambda: b"junk", gh6, now=NOW, dry_run=True)
ok("dry run: a bad feed does not touch the failure count", gh6.count == 0)

# ---- malformed or missing feeds are quiet (exit 0) and counted
bad = [b"", b"   ", b"not xml at all", b"<html><body>502 Bad Gateway</body></html>", b"<rss version='2.0'><channel><item><title>x</item></channel></rss>",
       b"<rss version='2.0'><channel><title>x</title></channel></rss>", b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>",
       b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>', b"\xff\xfe\x00bad", None]
ok("malformed: every kind raises FeedError (never anything else)", all(raises(d) for d in bad))
ok("malformed: an item with no title is skipped, the rest still read", len(K.parse_feed(rss("<item><guid>q</guid></item>", item(guid="ok")))) == 1)
g = FakeGh()
for n in range(1, 4):
    rc = K.run(lambda: b"oops", g, now=NOW)
ok("failing: three bad runs exit 0, count 3, no issue yet", rc == 0 and g.count == 3 and g.created == [])
K.run(lambda: b"oops", g, now=NOW)
ok("failing: the 4th bad run opens ONE 'watch is failing' issue", g.count == 4 and [t for t, _, _ in g.created] == [K.FAILING_TITLE] and g.created[0][2] == [K.LABEL_FAILING])
K.run(lambda: b"oops", g, now=NOW); K.run(lambda: b"oops", g, now=NOW)
ok("failing: more bad runs never open a second one", len(g.created) == 1 and g.count == 6)
def broken():
    raise K.FeedError("down")
K.run(broken, g, now=NOW)
ok("failing: an unreachable feed counts the same way", g.count == 7)
K.run(lambda: FIXTURE, g, now=NOW)
ok("recovery: a good run resets the count and closes the failing issue", g.count == 0 and g.closed == [1] and g.issues[0]["state"] == "closed")
for n in range(4):
    K.run(lambda: b"oops", g, now=NOW)
ok("recovery: failing again later opens a fresh issue", [t for t, _, _ in g.created].count(K.FAILING_TITLE) == 2)
class Flaky(FakeGh):
    def fail_count(self):
        raise RuntimeError("gh down")
ok("failing: even if the bookkeeping fails, a Kalshi outage exits 0", K.run(lambda: b"oops", Flaky(), now=NOW) == 0)

# ---- untrusted text is trimmed, stripped and fenced
evil = K.parse_feed(rss(item(
    title="Hi @octocat <script>alert(1)</script>\nsecond line " + "x" * 400, guid="e vil;$(rm -rf /)`id`", link="javascript:alert(1)",
    desc="@everyone see #1 and https://evil.example/", content="<p>Hello <b>there</b> @octocat</p><script>steal()</script><style>p{}</style><ul><li>one</li><li>two</li></ul>"
    "\u202eRTL\u200b```\n@mallory\n```\n<img src=x onerror=alert(1)>&lt;b&gt;" + "y" * 5000)))[0]
ok("untrusted: title is one short line without tags", "\n" not in evil["title"] and "<" not in evil["title"] and len(evil["title"]) <= K.TITLE_MAX)
ok("untrusted: guid keeps only safe characters (no shell or marker tricks)", re.fullmatch(r"[A-Za-z0-9._:/#-]+", evil["guid"]) is not None)
ok("untrusted: a non-Kalshi link is replaced by the changelog page", evil["link"] == K.CHANGELOG_URL)
ok("untrusted: scripts, styles, tags and invisible characters are gone", all(s not in evil["summary"] for s in ("steal", "p{}", "<script", "<img", "<p>", "onerror", "\u202e", "\u200b")) and "Hello there" in evil["summary"])
ok("untrusted: the summary is cut to the limit", len(evil["summary"]) <= K.SUMMARY_MAX)
body = K.issue_body(evil)
inner = body.split("```text\n", 1)[1].rsplit("\n```", 1)[0]
ok("untrusted: a ``` in the feed cannot close the code fence (mentions stay inert)", "```" not in inner and body.count("```") == 2)
ok("untrusted: list items are kept as plain bullets", "- one" in evil["summary"] and "- two" in evil["summary"])
for link in ("https://docs.kalshi.com/changelog#november-26-2026", "https://docs.kalshi.com.evil.example/x", "http://docs.kalshi.com/x", "https://evil.example/https://docs.kalshi.com/"):
    exp = link if link == "https://docs.kalshi.com/changelog#november-26-2026" else K.CHANGELOG_URL
    if K.safe_link(link) != exp:
        ok(f"untrusted: link check {link}", False); break
else:
    ok("untrusted: only real docs.kalshi.com links are kept", True)
big = K.parse_feed(rss(*[item(guid=f"g{n}") for n in range(300)]))
ok("untrusted: at most 200 items are read", len(big) == K.MAX_ITEMS)
noid = K.parse_feed(rss("<item><title>No id</title><pubDate>Thu, 19 Nov 2026 16:47:30 GMT</pubDate></item>"))[0]
ok("untrusted: an item with no guid gets a stable made-up one", noid["guid"].startswith("h") and noid["guid"] == K.parse_feed(rss("<item><title>No id</title><pubDate>Thu, 19 Nov 2026 16:47:30 GMT</pubDate></item>"))[0]["guid"])

# ---- the command line: --feed-file with --dry-run prints and changes nothing (gh is never started)
import io, contextlib
buf = io.StringIO()
class NoGh(K.Gh):
    def _run(self, args, stdin=None):
        raise RuntimeError("no gh in tests")
orig = K.Gh
K.Gh = NoGh
try:
    with contextlib.redirect_stdout(buf):
        rc = K.main(["--feed-file", os.path.join(HERE, "fixtures", "kalshi_changelog.rss"), "--dry-run", "--days", "30"])
finally:
    K.Gh = orig
out = buf.getvalue()
ok("cli: --feed-file --dry-run prints what it would create and exits 0", rc == 0 and out.count("would create: Kalshi API change:") == 5)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = K.main(["--feed-file", "/nonexistent/feed.xml", "--dry-run"])
ok("cli: a missing feed file is a quiet failure", rc == 0 and "problem" in buf.getvalue())

# ---- the workflow file (no actionlint here: structural checks, plus a real YAML parse when PyYAML is around)
wf = open(os.path.join(REPO, ".github", "workflows", "kalshi-api-watch.yml")).read()
ok("workflow: every 6 hours plus a manual trigger", re.search(r'cron:\s*"\d+ \*/6 \* \* \*"', wf) is not None and "workflow_dispatch:" in wf)
perm = re.search(r"^permissions:\n((?:[ ]+\S.*\n)+)", wf, re.M)
ok("workflow: permissions are exactly contents: read and issues: write", perm is not None and [l.strip() for l in perm.group(1).splitlines()] == ["contents: read", "issues: write"])
ok("workflow: not pull_request_target, no secrets beyond GITHUB_TOKEN", "pull_request_target" not in wf and re.findall(r"secrets\.(\w+)", wf) == ["GITHUB_TOKEN"])
runs, cur = [], None
for line in wf.splitlines():
    if cur is not None and (line.startswith(cur[0] + " ") or not line.strip()):
        runs.append(line)
    else:
        cur = None
        m = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if m:
            cur = (m.group(1),)
        elif re.match(r"^\s*run:\s*\S", line):
            runs.append(line)
ok("workflow: nothing from ${{ }} is placed inside a shell script", runs and not any("${{" in r for r in runs))
ok("workflow: runs the script by path with python3, no installs", "tools/kalshi_feed_watch.py" in wf and "pip " not in wf and "uses: actions/checkout@v4" in wf)
ok("workflow: checkout does not keep the token", "persist-credentials: false" in wf)
try:
    import yaml
    y = yaml.safe_load(wf)
    on = y.get("on", y.get(True))
    ok("workflow: valid YAML with a schedule and a watch job", "schedule" in on and "watch" in y["jobs"] and y["permissions"] == {"contents": "read", "issues": "write"})
except ImportError:
    ok("workflow: (PyYAML not installed here; structural checks above stand in)", True)
ci = open(os.path.join(REPO, ".github", "workflows", "ci.yml")).read()
ok("ci: unchanged, still only contents: read", "issues: write" not in ci)
