#!/usr/bin/env python3
"""Read the production Mac's logs from the dev Mac (issue #377, docs/LOG_ACCESS.md).

Read-only: it asks the watcher's /api/logs for a credential-scrubbed tail of watcher.log or the auto cash-out log, or
(--source db) for rows of the collected data (history database: ticks, offers, sell_log, ledger, price_path ...) by table
or by one SELECT. It can't buy, sell, pause or change anything, and never gets the Kalshi key, ~/combowatch, the database
file itself or combo_*.json.

Where it finds the address and code (nothing secret is in this file):
  1. the environment: CW_LOGS_URL (e.g. http://100.x.y.z:8765) and CW_LOGS_TOKEN
  2. else the macOS keychain: services "nfl-combo-logs-url" and "nfl-combo-logs-token"

Examples:
  python3 tools/read_prod_logs.py                       # last 200 console lines
  python3 tools/read_prod_logs.py --source autosell --since 2h
  python3 tools/read_prod_logs.py --since 30m --grep "cash-out|Traceback"
  python3 tools/read_prod_logs.py --follow              # keep printing new lines (Ctrl-C to stop)
  python3 tools/read_prod_logs.py --source db --tables  # the tables and their columns
  python3 tools/read_prod_logs.py --source db --table sell_log --since 1d --limit 50
  python3 tools/read_prod_logs.py --source db --sql "select ticker, count(*) from offers group by 1 limit 20" --json
"""
import argparse
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

URL_SVC, TOKEN_SVC = "nfl-combo-logs-url", "nfl-combo-logs-token"


def keychain(service):
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def settings():
    url = os.environ.get("CW_LOGS_URL") or keychain(URL_SVC)
    tok = os.environ.get("CW_LOGS_TOKEN") or keychain(TOKEN_SVC)
    if not url:
        sys.exit(f"No address for the production Mac. Set CW_LOGS_URL, or store it in the keychain:\n"
                 f"  security add-generic-password -a \"$USER\" -s {URL_SVC} -w")
    if not tok:
        sys.exit(f"No log code. Set CW_LOGS_TOKEN, or store it in the keychain (it asks for the code, so it stays "
                 f"out of your shell history):\n  security add-generic-password -a \"$USER\" -s {TOKEN_SVC} -w")
    if not re.match(r"^https?://", url):
        url = "http://" + url
    return url.rstrip("/"), tok


def parse_since(s):
    """30m, 2h, 1d, a unix time, or an ISO date/time (local)."""
    if s is None:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd])", s.strip())
    if m:
        return time.time() - float(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
    if re.fullmatch(r"\d{9,11}(?:\.\d+)?", s.strip()):
        return float(s)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(s.strip(), fmt))
        except ValueError:
            pass
    sys.exit(f"Couldn't read --since {s!r}. Use 30m, 2h, 1d, a unix time or 2026-11-23 14:00.")


WHY = {401: "The code was refused (it was replaced, or access was switched off). On the production Mac open Settings "
            "› This Mac, turn on 'Let the dev Mac read logs' (or tap New code), copy the new code, then run:\n"
            f"  security add-generic-password -U -a \"$USER\" -s {TOKEN_SVC} -w",
       404: "The production Mac said 'not found'. Either 'Let the dev Mac read logs' is off in its Settings, the "
            "address is wrong, or this Mac isn't reaching it over Tailscale (open Tailscale and check it's Connected). "
            "See docs/LOG_ACCESS.md.",
       429: "Too many requests (or too many wrong codes). Wait a few minutes and try again.",
       400: "The production Mac didn't understand the question (check --source / --limit / --since).",
       405: "Only reading is allowed.",
       503: "The production Mac couldn't safely scrub that answer (a credential was still in it), so it sent nothing. "
            "Try again shortly; if it persists, look at the logs on that Mac itself."}


class Failed(Exception):
    """A request that got no usable answer; `again` = worth retrying in --follow."""

    def __init__(self, msg, again):
        super().__init__(msg)
        self.again = again


def fetch(url, tok, source, since, limit, extra=None):
    q = {"source": source, "limit": str(limit)}
    if since is not None:
        q["since"] = f"{since:.0f}"
    q.update(extra or {})
    req = urllib.request.Request(f"{url}/api/logs?{urllib.parse.urlencode(q)}",
                                 headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 400 and source == "db":                      # the Mac says why (short fixed wording)
            try:
                raise Failed("Refused: " + str(json.loads(err.read().decode("utf-8")).get("error")), False)
            except (ValueError, OSError):
                pass
        raise Failed(f"Error {err.code}: {WHY.get(err.code, 'unexpected answer.')}", err.code in (429, 503) or err.code >= 500)
    except urllib.error.URLError as err:
        raise Failed(f"Couldn't reach {urllib.parse.urlsplit(url).netloc}: {err.reason}. Is Tailscale connected on both "
                     f"Macs, and is the production Mac awake?", True)
    except (TimeoutError, socket.timeout):
        raise Failed("The production Mac didn't answer in 20 seconds. Is it awake and on Tailscale?", True)
    except (OSError, http.client.HTTPException) as err:
        raise Failed(f"The connection broke ({type(err).__name__}). Is the production Mac awake and on Tailscale?", True)
    except ValueError:
        raise Failed("The answer wasn't readable. Is the address the watcher's (port 8765)?", False)


def fetch_db(url, tok, table=None, sql=None, since=None, limit=200, tables=False):
    """Rows of the collected data (read-only on the Mac). Returns the answer: {columns, rows, truncated} or {tables}.
    Other tools (e.g. a --remote mode) call this instead of opening the database file."""
    extra = {"sql": sql} if sql else {"table": table} if table else {}
    return fetch(url, tok, "db", since if table else None, limit, extra)


def show_db(ans, as_json):
    if "tables" in ans:
        for t in ans["tables"]:
            print(f"{t['name']}: {', '.join(t['columns'])}")
        return
    cols = ans.get("columns") or []
    if as_json:
        for r in ans.get("rows") or []:
            print(json.dumps(dict(zip(cols, r)), ensure_ascii=False))
    else:
        print("\t".join(cols))
        for r in ans.get("rows") or []:
            print("\t".join("" if v is None else str(v).replace("\t", " ").replace("\n", " ") for v in r))
    if ans.get("truncated"):
        print("# more rows exist than were sent: narrow the question or raise --limit (the Mac caps it at 1000)", file=sys.stderr)


def show(ans, rx, as_json, seen):
    """Print new rows. `seen` holds only the previous answer's rows (so --follow's overlap isn't printed twice, and
    two identical lines in one answer both are); returns this answer's rows for the next call."""
    now = {}
    for row in ans.get("lines") or []:
        text = row.get("text") if "text" in row else json.dumps(row.get("rec"), ensure_ascii=False)
        key = (row.get("t"), text)
        now[key] = now.get(key, 0) + 1
        if now[key] <= seen.get(key, 0):
            continue
        if rx and not rx.search(text or ""):
            continue
        if as_json:
            print(json.dumps(row, ensure_ascii=False))
        elif "text" in row:
            print(text)
        else:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["t"])) if row.get("t") else "?"
            print(f"{t} [{ans.get('source')}] {text}")
    return now


def main():
    ap = argparse.ArgumentParser(description="Read the production Mac's redacted logs (read-only).")
    ap.add_argument("--source", choices=("console", "autosell", "both", "db"), default="console")
    ap.add_argument("--table", help="with --source db: a table's newest rows (--since limits by its ts column)")
    ap.add_argument("--sql", help="with --source db: one SELECT (the Mac refuses anything else, and stops it after 5 s)")
    ap.add_argument("--tables", action="store_true", help="with --source db: list the tables and their columns")
    ap.add_argument("--since", help="30m, 2h, 1d, unix time, or ISO date/time")
    ap.add_argument("--limit", type=int, default=200, help="lines per source (the Mac caps it at 500; rows for --source db: 1000)")
    ap.add_argument("--grep", help="only lines matching this regular expression (case-insensitive)")
    ap.add_argument("--follow", action="store_true", help="keep checking every 15 seconds")
    ap.add_argument("--json", action="store_true", help="one JSON object per line")
    a = ap.parse_args()
    rx = re.compile(a.grep, re.I) if a.grep else None
    url, tok = settings()
    since = parse_since(a.since)
    if a.source == "db":
        if not (a.table or a.sql or a.tables):
            sys.exit("With --source db give --tables, --table NAME or --sql \"select ...\".")
        if a.follow:
            sys.exit("--follow is only for the logs.")
        try:
            ans = fetch_db(url, tok, a.table, a.sql, since, a.limit)
        except Failed as err:
            sys.exit(str(err))
        show_db(ans, a.json)
        return
    sources = ("console", "autosell") if a.source == "both" else (a.source,)
    seen, first, nxt = {s: {} for s in sources}, True, since
    while True:
        for src in sources:
            try:
                ans = fetch(url, tok, src, since, a.limit)
            except Failed as err:
                if not a.follow or not err.again:
                    sys.exit(str(err))
                print(f"# {err} (trying again in 15 s)", file=sys.stderr)
                continue
            if first and not a.json:
                st = ans.get("status") or {}
                up = int(st.get("up") or 0)
                print(f"# {src}: watcher {st.get('watcher')} · engine {st.get('engine')} · up {up // 3600}h{up % 3600 // 60:02d}m"
                      f" · {st.get('role')} · {'PAUSED' if st.get('paused') else 'running'}"
                      f" · auto cash-out {'on' if st.get('auto_sell') else 'off'}"
                      + (" · (oldest lines cut to fit)" if ans.get("truncated") else ""), file=sys.stderr)
            seen[src] = show(ans, rx, a.json, seen[src])
            now = (ans.get("status") or {}).get("now")
            if isinstance(now, (int, float)):
                nxt = now - 60                                 # the Mac's own clock: this one may be off
        first = False
        if not a.follow:
            return
        since = nxt if nxt is not None else time.time() - 60
        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
