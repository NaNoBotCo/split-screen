"""gdelt.py — news articles naming RFK Jr., with each article's lead image (og:image).

GDELT DOC 2.0 (a free index of world online news, back to 2017) returns at most 250
articles per call, so the window starts at four days and halves until a call comes back
under 250. GDELT asks for one call every 5 seconds; this IP is shared and busy, so
this waits 45 and backs off a minute at a time when told to slow down.

    python collect/gdelt.py [--since 2023-09-26] [--until 2026-09-26]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

API = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = '("Robert F. Kennedy" OR "Kennedy Jr" OR "RFK Jr")'  # GDELT refuses a bare "RFK": too short
GAP = 45.0
_last = [0.0]


def call(s: requests.Session, a: dt.datetime, b: dt.datetime) -> list[dict] | None:
    params = {"query": QUERY, "mode": "artlist", "maxrecords": 250, "format": "json", "sort": "datedesc",
              "startdatetime": a.strftime("%Y%m%d%H%M%S"), "enddatetime": b.strftime("%Y%m%d%H%M%S")}
    for attempt in range(8):
        wait = GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = s.get(API, params=params, timeout=90)
        except requests.RequestException:
            time.sleep(15 * (attempt + 1))
            continue
        body = r.text.strip()
        print(f"  call {a:%Y-%m-%d %H:%M}..{b:%H:%M} {r.status_code} {len(body)}b", file=sys.stderr, flush=True)
        if r.status_code != 200 or body.startswith("Please limit"):
            time.sleep(60 * (attempt + 1))
            continue
        if not body:
            return []
        try:
            return r.json().get("articles", [])
        except ValueError:
            # GDELT sometimes emits bad escapes in titles
            import json, re
            try:
                return json.loads(re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", body)).get("articles", [])
            except ValueError:
                print("bad json", a, file=sys.stderr)
                return None
    return None


class Unreachable(Exception):
    pass


def iso(seen: str) -> str:
    # 20250307T141500Z -> 2025-03-07T14:15:00Z
    return f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}T{seen[9:11]}:{seen[11:13]}:{seen[13:15]}Z"


def harvest(con, s, a: dt.datetime, b: dt.datetime, depth=0) -> int:
    arts = call(s, a, b)
    if arts is None:
        raise Unreachable(a)
    if len(arts) >= 250 and (b - a) > dt.timedelta(minutes=45):
        mid = a + (b - a) / 2
        return harvest(con, s, a, mid, depth + 1) + harvest(con, s, mid, b, depth + 1)
    n = 0
    for x in arts:
        img = x.get("socialimage")
        if not img:
            continue
        con.execute(
            "INSERT OR IGNORE INTO items(source,query,post_url,author,posted_at,text,headline,domain,image_url) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("gdelt", x.get("language"), x["url"], x.get("sourcecountry"), iso(x["seendate"]),
             None, x.get("title"), x.get("domain"), img))
        n += 1
    con.commit()  # now: the next call may wait minutes on GDELT, and an open write would lock out every other process
    return n


def run(since: dt.date, until: dt.date) -> None:
    con = db.connect()
    s = requests.Session()
    s.headers["User-Agent"] = "split-screen-catalog/0.1 (research; nanobotco)"
    d = since
    while d < until:
        e = min(d + dt.timedelta(days=4), until)
        key = d.isoformat()
        if not db.done(con, "gdelt", key):
            a = dt.datetime.combine(d, dt.time())
            try:
                n = harvest(con, s, a, dt.datetime.combine(e, dt.time()))
            except Unreachable:
                con.commit()  # rows so far stay; the window stays unmarked for the next run
                print(f"gdelt {key} unreachable", file=sys.stderr, flush=True)
                d = e
                continue
            con.commit()
            db.mark(con, "gdelt", key, n)
            print(f"gdelt {key}..{e} images={n}", flush=True)
        d = e


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2023-09-26")
    ap.add_argument("--until", default=dt.date.today().isoformat())
    a = ap.parse_args()
    run(dt.date.fromisoformat(a.since), dt.date.fromisoformat(a.until))
