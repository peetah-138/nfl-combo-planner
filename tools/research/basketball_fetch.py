#!/usr/bin/env python3
"""Download the hoopR / sportsdataverse basketball files used by basketball_discovery.py.  OFFLINE RESEARCH ONLY.

Data stays OUTSIDE the repo (default ~/dev/research/basketball/raw).  Nothing here touches the app, its keys or
its history.  The files are CC-BY-4.0 on the sportsdataverse repos, but the content is ESPN-derived, so the data's
own terms may be stricter than the repo licence: keep it local, never commit or redistribute it.

Polite: one file at a time, a pause between files, a descriptive User-Agent, files already on disk are never
fetched again (use --force to refresh the newest season).  stats.nba.com / cdn.nba.com are never used.

Run with the research venv:   ~/dev/research/venv/bin/python tools/research/basketball_fetch.py
"""
import argparse, os, sys, time, urllib.request, urllib.error

REL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
RAW = "https://github.com/sportsdataverse/hoopR-nba-data/raw/main/nba/betting_lines/closing_lines_odds_api.parquet"
UA = "offline-research-cache/0.1 (personal research; polite, cached)"
# (league, local prefix, release tag, file pattern)
KINDS = {
    "pbp": ("{lg}_pbp", "play_by_play_{y}.parquet"),
    "sched": ("{lg}_schedules", "{lg}_schedule_{y}.parquet"),
    "off": ("{lg}_officials", "officials_{y}.parquet"),
}
TAGS = {"nba": "espn_nba", "mbb": "espn_mens_college_basketball"}
SLUG = {"nba": "nba", "mbb": "mbb"}


def default_root():
    return os.path.expanduser("~/dev/research/basketball/raw")


def url_for(league, kind, year):
    tagfmt, filefmt = KINDS[kind]
    tag = {"nba": "espn_nba", "mbb": "espn_mens_college_basketball"}[league] + "_" + tagfmt.split("_", 1)[1]
    return "%s/%s/%s" % (REL, tag, filefmt.format(lg=SLUG[league], y=year))


def fetch(url, dest, force=False, pause=2.0, tries=3):
    """Download url to dest unless cached.  Returns 'cached', 'ok' or 'missing'."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return "cached"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r, open(dest + ".part", "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            os.replace(dest + ".part", dest)
            time.sleep(pause)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "missing"
            time.sleep(5 * (i + 1))
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(5 * (i + 1))
    return "failed"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=default_root())
    ap.add_argument("--first", type=int, default=2019)
    ap.add_argument("--last", type=int, default=2026)
    ap.add_argument("--leagues", default="nba,mbb")
    ap.add_argument("--force-last", action="store_true", help="re-download the last season (still in progress)")
    a = ap.parse_args(argv)
    for lg in a.leagues.split(","):
        for y in range(a.first, a.last + 1):
            for kind in KINDS:
                dest = os.path.join(a.root, lg, "%s_%d.parquet" % (kind, y))
                st = fetch(url_for(lg, kind, y), dest, force=a.force_last and y == a.last)
                print("%-6s %-5s %d %s" % (lg, kind, y, st), flush=True)
    st = fetch(RAW, os.path.join(a.root, "nba_closing_lines.parquet"))
    print("nba closing_lines", st)


if __name__ == "__main__":
    sys.exit(main())
