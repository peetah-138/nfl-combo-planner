#!/usr/bin/env python3
"""Tell Pete the moment Kalshi changes its API.

Runs on GitHub (.github/workflows/kalshi-api-watch.yml, every 6 hours), never on the Mac. It reads Kalshi's API
changelog RSS feed and opens one GitHub issue for each new entry from the last 14 days (at most 5 per run). GitHub
then notifies the repo owner by email / the app. Entries that retire or remove something in an area the app uses
(a removal/deprecation word AND orders, order book, market fields, signing, rate limits...) get the `breaking` label
and an "ACTION LIKELY NEEDED" first line; every other entry is filed as a plain "FYI" issue.

Standard library only (plus the `gh` CLI that GitHub runners already have). The feed is untrusted text: it is parsed
as data, stripped of HTML, trimmed, put inside a code fence in the issue (so no @mentions, links or markdown are
live), and never run or placed in a shell command (`gh` gets an argument list and the body on stdin).

  python3 tools/kalshi_feed_watch.py                 # normal run (needs GH_TOKEN and GH_REPO or a git remote)
  python3 tools/kalshi_feed_watch.py --dry-run       # prints the issues it would create; changes nothing
  python3 tools/kalshi_feed_watch.py --feed-file f.xml --dry-run     # same, from a saved feed

If the feed is unreachable or malformed the run still exits 0 (a Kalshi outage must not spam failures). After 4
failed runs in a row it opens ONE issue, "Kalshi API watch is failing", and closes it when the feed works again.
The consecutive-failure count lives in the description of a label (`kalshi-watch-failures`), which needs no extra
permissions and sends no notification.
"""
import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

FEED_URL = "https://docs.kalshi.com/changelog/rss.xml"
USER_AGENT = "kalshi-api-watch/1.0"
CHANGELOG_URL = "https://docs.kalshi.com/changelog"
WINDOW_DAYS = 14
MAX_NEW = 5                # new issues per run: the first run (and any burst) can never flood
FAIL_LIMIT = 4             # failed runs in a row before the "watch is failing" issue
MAX_FEED_BYTES = 2_000_000
MAX_ITEMS = 200
TITLE_MAX = 120
SUMMARY_MAX = 1500
LABEL = "kalshi-api-change"
LABEL_BREAKING = "breaking"
LABEL_FAILING = "kalshi-watch-failing"
LABEL_COUNT = "kalshi-watch-failures"
FAILING_TITLE = "Kalshi API watch is failing"
MARKER = "kalshi-feed-id:"          # a line in each issue body: the dedupe key
# Two tiers. "breaking" (label + ACTION LIKELY NEEDED) needs BOTH a strong removal/deprecation word AND something this
# app uses, found in the entry's title or description. Everything else is still filed, as a plain "FYI" issue.
STRONG_RE = re.compile(r"deprecat|sunset|remov|no longer|discontinu|will be disabled|migrat|\b410\b", re.I)
AREA_RE = re.compile(
    r"\borders?\b|portfolio|\brfq|\bquotes?\b|communications|order ?book|market[_ ]?id|market (?:objects?|fields?)"
    r"|expiration_time|authentication|\bsigning\b|signature|rate[- ]limit|websocket|\bfills?\b", re.I)
CTRL_RE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f\\u200b-\\u200f\\u202a-\\u202e\\u2066-\\u2069\\ufeff]")
GUID_BAD = re.compile(r"[^A-Za-z0-9._:/#-]")
TAG_BAD = re.compile(r"[^A-Za-z0-9 ._/+-]")                 # tags sit outside the code fence: plain characters only
CDATA_RE = re.compile(rb"<!\[CDATA\[.*?\]\]>", re.S)


class FeedError(Exception):
    """The feed could not be fetched or understood (quiet: counted, never a red run)."""


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- reading the feed

def fetch_feed(url=FEED_URL, timeout=20, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})
            with urllib.request.urlopen(req, timeout=timeout) as r:   # nosec: fixed https URL
                data = r.read(MAX_FEED_BYTES + 1)
            if len(data) > MAX_FEED_BYTES:
                raise FeedError("feed is too large")
            return data
        except FeedError:
            raise
        except Exception as e:   # network trouble of any kind
            last = e
            if i + 1 < tries:
                time.sleep(5)
    raise FeedError(f"could not fetch the feed: {type(last).__name__}")


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def clean_text(raw, limit):
    """Untrusted HTML/text -> short plain text: no tags, no control or invisible characters, trimmed."""
    raw = (raw or "")[:50_000]
    p = _Text()
    try:
        p.feed(raw)
        p.close()
        text = "".join(p.out)
    except Exception:   # a parser the markup confuses: fall back to crude tag removal
        text = re.sub(r"<[^>]*>", " ", raw)
    text = html.unescape(text) if "&" in text else text
    text = CTRL_RE.sub("", text.replace("\r", "\n").replace("\t", " "))
    lines = [re.sub(r"[  ]+", " ", ln).strip() for ln in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def one_line(raw, limit):
    return clean_text(raw, limit * 4).replace("\n", " ").strip()[:limit].strip()


def safe_link(link):
    """Only a Kalshi docs address is shown as a link; anything else becomes the changelog page."""
    link = (link or "").strip()
    if re.fullmatch(r"https://docs\.kalshi\.com/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{0,300}", link):
        return link
    return CHANGELOG_URL


def parse_date(s):
    try:
        d = parsedate_to_datetime((s or "").strip())
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def is_breaking(text):
    return bool(STRONG_RE.search(text) and AREA_RE.search(text))


def parse_feed(data):
    """RSS bytes -> list of items (newest feed order kept). Raises FeedError if it is not an RSS feed with items."""
    if not isinstance(data, (bytes, bytearray)) or not data.strip():
        raise FeedError("empty feed")
    head = CDATA_RE.sub(b"", bytes(data)).lower()          # entry text lives in CDATA and may quote anything
    if b"<!doctype" in head or b"<!entity" in head:        # no DTDs: nothing here needs entities (and it blocks entity bombs)
        raise FeedError("feed has a DTD; refusing it")
    try:
        root = ET.fromstring(bytes(data))
    except ET.ParseError as e:
        raise FeedError(f"feed is not valid XML: {e}")
    if not root.tag.lower().endswith("rss") or root.find("channel") is None:
        raise FeedError("feed is not an RSS feed")
    ns = "{http://purl.org/rss/1.0/modules/content/}encoded"
    items = []
    for it in root.find("channel").findall("item")[:MAX_ITEMS]:
        title = one_line(it.findtext("title"), TITLE_MAX)
        if not title:
            continue
        desc = (it.findtext("description") or "")
        body = (it.findtext(ns) or "")
        link0 = (it.findtext("link") or "").strip()
        guid0 = GUID_BAD.sub("", (it.findtext("guid") or "").strip())[:100]
        pub = (it.findtext("pubDate") or "").strip()
        if not guid0:      # no usable id: a stable one made from what the entry says
            guid0 = "h" + hashlib.sha1(f"{title}|{link0}|{pub}".encode()).hexdigest()[:16]
        summary = clean_text(body or desc, SUMMARY_MAX)
        short = clean_text(desc, 600)
        items.append({
            "title": title, "guid": guid0, "link": safe_link(link0), "pub": pub, "date": parse_date(pub),
            "summary": summary or short or "(no summary in the feed)",
            "tags": [t for t in (TAG_BAD.sub("", one_line(c.text, 30)).strip() for c in it.findall("category")) if t][:6],
            "breaking": is_breaking(title + " " + clean_text(desc, 2000)),
        })
    if not items:
        raise FeedError("feed has no items")
    if not any(i["date"] for i in items):       # dates we cannot read would silently hide every entry: count it as a failure
        raise FeedError("no item has a readable date")
    return items


# ---------------------------------------------------------------- deciding what is new

def pick_new(items, known_ids, now, days=WINDOW_DAYS, cap=MAX_NEW):
    """Items inside the window with no issue yet: breaking ones first, then newest. Returns (to_file, waiting)."""
    cutoff = now - timedelta(days=days)
    fresh = [i for i in items if i["date"] is not None and i["date"] >= cutoff and i["guid"] not in known_ids]
    seen, uniq = set(), []
    for i in fresh:                      # the same guid twice in one feed is still one issue
        if i["guid"] not in seen:
            seen.add(i["guid"])
            uniq.append(i)
    uniq.sort(key=lambda i: (not i["breaking"], -i["date"].timestamp()))
    return uniq[:cap], len(uniq) - min(cap, len(uniq))


def issue_title(item):
    return f"Kalshi API change: {item['title']}"


def issue_body(item):
    fence = "```"
    summary = item["summary"].replace("```", "'''")
    lines = []
    if item["breaking"]:
        lines += ["**ACTION LIKELY NEEDED**: this entry removes or retires something in an area the app uses (orders, "
                  "order book, market fields, signing, rate limits, websocket...). Read it and check the app against it.", ""]
    else:
        lines += ["**FYI**: nothing here looks like it removes anything the app relies on. Skim it and close it.", ""]
    when = item["date"].strftime("%Y-%m-%d %H:%M UTC") if item["date"] else item["pub"][:40]
    lines += ["Kalshi posted a change to its API.", "",
              f"- Link: {item['link']}",
              f"- Published: {when}"]
    if item["tags"]:
        lines.append("- Tags: " + ", ".join(item["tags"]))
    lines += ["", "What the feed says (copied as plain text; it is Kalshi's wording, not ours):", "",
              fence + "text", summary, fence, "",
              f"{MARKER} {item['guid']}", "",
              "Opened automatically by the Kalshi API watch (`.github/workflows/kalshi-api-watch.yml`). "
              "Close this when the app is checked against the change."]
    return "\n".join(lines)


def ids_in(issues):
    out = set()
    for it in issues or []:
        found = re.findall(r"^" + re.escape(MARKER) + r"[ ]*([A-Za-z0-9._:/#-]+)[ ]*$", it.get("body") or "", re.M)
        if found:
            out.add(found[-1])      # ours is the last marker line; text quoted from the feed comes earlier
    return out


# ---------------------------------------------------------------- GitHub (through the gh CLI)

class Gh:
    """Thin wrapper over `gh`. Every call is an argument list (no shell); bodies go in on stdin."""

    def __init__(self, repo=None):
        self.repo = repo

    def _run(self, args, stdin=None):
        cmd = ["gh"] + args + (["--repo", self.repo] if self.repo else [])
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=120)
        if r.returncode:
            raise RuntimeError(f"gh {args[0]} {args[1]} failed: {(r.stderr or r.stdout).strip()[:300]}")
        return r.stdout

    def list_issues(self, label, state="all"):
        out = self._run(["issue", "list", "--label", label, "--state", state, "--limit", "1000",
                         "--json", "number,title,body,state"])
        return json.loads(out or "[]")

    def ensure_label(self, name, color, description):
        self._run(["label", "create", name, "--color", color, "--description", description, "--force"])

    def create_issue(self, title, body, labels):
        args = ["issue", "create", "--title", title, "--body-file", "-"]
        for lb in labels:
            args += ["--label", lb]
        return self._run(args, stdin=body).strip()

    def close_issue(self, number, comment):
        self._run(["issue", "close", str(number), "--comment", comment])

    def fail_count(self):
        out = self._run(["label", "list", "--search", LABEL_COUNT, "--json", "name,description", "--limit", "50"])
        for lb in json.loads(out or "[]"):
            if lb.get("name") == LABEL_COUNT:
                m = re.search(r"(\d+)\s*$", lb.get("description") or "")
                return int(m.group(1)) if m else 0
        return 0

    def set_fail_count(self, n):
        self.ensure_label(LABEL_COUNT, "ededed", f"consecutive feed failures: {int(n)}")


# ---------------------------------------------------------------- one run

def record_failure(gh, why, dry_run):
    log(f"Kalshi feed problem (quiet, exiting 0): {why}")
    if dry_run:
        return
    n = gh.fail_count() + 1
    gh.set_fail_count(n)
    log(f"consecutive failures: {n}")
    # Once per outage: at the 4th failure, or later only if that one never got made. A hand-closed issue is not reopened.
    if n >= FAIL_LIMIT and not gh.list_issues(LABEL_FAILING, "open") and (n == FAIL_LIMIT or not gh.list_issues(LABEL_FAILING, "all")):
        gh.ensure_label(LABEL_FAILING, "b60205", "the Kalshi API watch cannot read Kalshi's changelog feed")
        url = gh.create_issue(
            FAILING_TITLE,
            f"The Kalshi API watch could not read Kalshi's changelog feed ({FEED_URL}) on {n} runs in a row.\n\n"
            f"Last problem: `{why[:200]}`\n\nUntil it works again, Kalshi API changes will not be reported. "
            "Check the feed address in `tools/kalshi_feed_watch.py`. This closes itself when the feed works again.",
            [LABEL_FAILING])
        log(f"opened {url}")


def record_success(gh, dry_run):
    if dry_run:
        return
    if gh.fail_count():
        gh.set_fail_count(0)
    for it in gh.list_issues(LABEL_FAILING, "open"):
        gh.close_issue(it["number"], "The feed is readable again.")


def run(feed_loader, gh, now=None, dry_run=False, days=WINDOW_DAYS, cap=MAX_NEW):
    """Returns the process exit code: 0 for a clean run or a quiet feed problem, 1 if GitHub calls failed."""
    now = now or datetime.now(timezone.utc)
    try:
        items = parse_feed(feed_loader())
    except FeedError as e:
        try:
            record_failure(gh, str(e), dry_run)
        except Exception as e2:    # even the failure bookkeeping must not make a Kalshi outage look like a bug
            log(f"(could not record the failure: {e2})")
        return 0
    try:
        record_success(gh, dry_run)
    except Exception as e:
        log(f"(could not update the failure state: {e})")
    try:
        known = ids_in(gh.list_issues(LABEL, "all"))
    except Exception as e:
        if not dry_run:
            log(f"cannot list existing issues, so creating nothing (it could duplicate): {e}")
            return 1
        known = set()
        log(f"(dry run: could not list existing issues, assuming none: {e})")
    todo, waiting = pick_new(items, known, now, days, cap)
    log(f"{len(items)} items in the feed, {len(known)} already filed, {len(todo)} to file now"
        + (f", {waiting} more next run" if waiting else ""))
    if not todo:
        return 0
    if not dry_run:
        try:
            gh.ensure_label(LABEL, "1d76db", "a change Kalshi announced in its API changelog")
            if any(i["breaking"] for i in todo):
                gh.ensure_label(LABEL_BREAKING, "d73a4a", "likely needs a change in the app")
        except Exception as e:
            log(f"cannot create the labels: {e}")
            return 1
    bad = 0
    for it in todo:
        labels = [LABEL] + ([LABEL_BREAKING] if it["breaking"] else [])
        if dry_run:
            log(f"\n--- would create: {issue_title(it)}\n    labels: {', '.join(labels)}\n{issue_body(it)}")
            continue
        try:
            log(f"created {gh.create_issue(issue_title(it), issue_body(it), labels)}")
        except Exception as e:
            bad += 1
            log(f"could not create an issue for {it['guid']}: {e}")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the issues it would create; change nothing")
    ap.add_argument("--feed-file", help="read the feed from this file instead of fetching it")
    ap.add_argument("--days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--repo", help="owner/name (default: GH_REPO or the current git remote)")
    a = ap.parse_args(argv)

    def loader():
        if a.feed_file:
            try:
                with open(a.feed_file, "rb") as f:
                    return f.read(MAX_FEED_BYTES + 1)[:MAX_FEED_BYTES]
            except OSError as e:
                raise FeedError(f"cannot read {a.feed_file}: {e.strerror}")
        return fetch_feed()
    return run(loader, Gh(a.repo), dry_run=a.dry_run, days=a.days)


if __name__ == "__main__":
    sys.exit(main())
