"""bsky.py — Bluesky posts that carry a picture, day by day, for each query.

Public AppView search, sort=latest. The AppView refuses a second page to anonymous
callers, so each day is cut into windows small enough that one page holds them. Keeps every image: attached
photos, and the link-card picture (the article's og:image) on shared links.

    python collect/bsky.py [--since 2023-09-26] [--until 2026-09-26] [--query RFK]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

API = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
# The headlines name the thing, not him ("recall of 1.7 million pounds of sugar"); his face rides in
# the picture. So the search is the things, and the classifier decides whether he is beside them.
TERMS = [
    "sugar", "soda", "food dye", "red dye", "Red 40", "artificial dyes", "candy", "cereal", "Froot Loops",
    "Skittles", "seed oil", "seed oils", "raw milk", "infant formula", "baby formula", "fluoride", "Tylenol",
    "acetaminophen", "ultra-processed", "processed food", "junk food", "fast food", "McDonald's", "hot dogs",
    "ice cream", "energy drink", "Coca-Cola", "Coke", "Pepsi", "Mountain Dew", "Doritos", "aspartame",
    "sweetener", "SNAP soda", "food stamps soda", "school lunch", "FDA recall", "food recall", "recall",
    "FDA ban", "banned", "contamination", "allergen", "listeria", "salmonella", "vaccine", "vaccines",
    "measles", "SSRIs", "antidepressants", "sunscreen", "cell phones", "GRAS", "petroleum", "MAHA",
]
QUERIES = ["RFK", "Robert F. Kennedy", "Secretary Kennedy", "Kennedy HHS", "MAHA"]  # the first pass, by name
UA = {"User-Agent": "split-screen-catalog/0.1 (research; nanobotco)"}


def images_of(post: dict) -> list[tuple[str, str | None, str | None]]:
    """(image_url, headline, link_url) triples from a post view's embed."""
    out = []

    def walk(e):
        if not e:
            return
        t = e.get("$type", "")
        if t.startswith("app.bsky.embed.images"):
            for im in e.get("images", []):
                u = im.get("thumb") or im.get("fullsize")
                if u:
                    out.append((u, None, None))
        elif t.startswith("app.bsky.embed.external"):
            ex = e.get("external") or {}
            if ex.get("thumb"):
                out.append((ex["thumb"], ex.get("title"), ex.get("uri")))
        elif t.startswith("app.bsky.embed.recordWithMedia"):
            walk(e.get("media"))

    walk(post.get("embed"))
    return out


def post_url(p: dict) -> str:
    rkey = p["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{p['author']['handle']}/post/{rkey}"


def day_windows(since: dt.date, until: dt.date):
    """Newest day first, so the recent months fill in before the old ones."""
    e = until
    while e > since:
        d = max(e - dt.timedelta(days=1), since)
        yield d, e
        e = d


def search(s, q, a: dt.datetime, b: dt.datetime):
    """One page for [a, b). Returns (posts, hitsTotal) or None on failure."""
    params = {"q": q, "sort": "latest", "limit": 100,
              "since": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "until": b.strftime("%Y-%m-%dT%H:%M:%SZ")}
    for attempt in range(6):
        try:
            r = s.get(API, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (403, 429) or r.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code != 200:
            print(r.status_code, q, a, r.text[:200], file=sys.stderr)
            return None
        d = r.json()
        return d.get("posts", []), d.get("hitsTotal") or 0
    return None


def harvest(con, s, q, a, b) -> int:
    """Anonymous callers get the first page only, so a window with more than one page
    of hits is halved until each half fits."""
    got = search(s, q, a, b)
    if got is None:
        raise RuntimeError("unreachable")
    posts, hits = got
    if len(posts) >= 90 and hits > len(posts) and (b - a) > dt.timedelta(minutes=2):
        mid = a + (b - a) / 2
        return harvest(con, s, q, a, mid) + harvest(con, s, q, mid, b)
    kept = 0
    for p in posts:
        rec = p.get("record", {})
        for u, title, link in images_of(p):
            dom = urlparse(link).netloc.removeprefix("www.") if link else "bsky.app"
            con.execute(
                "INSERT OR IGNORE INTO items(source,query,post_url,author,posted_at,text,headline,domain,"
                "image_url,likes,reposts,replies,quotes,link_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("bsky", q, post_url(p), p["author"]["handle"], rec.get("createdAt"),
                 rec.get("text"), title, dom, u,
                 p.get("likeCount"), p.get("repostCount"), p.get("replyCount"), p.get("quoteCount"), link))
            kept += 1
    con.commit()  # per window: the write lock is shared with the other workers
    time.sleep(0.15)
    return kept


def run(since: dt.date, until: dt.date, queries: list[str]) -> None:
    con = db.connect()
    s = requests.Session()
    s.headers.update(UA)
    for a, b in day_windows(since, until):
        for q in queries:
            key = f"{q}|{a}"
            if db.done(con, "bsky2", key):
                continue
            try:
                n = harvest(con, s, q, dt.datetime.combine(a, dt.time()), dt.datetime.combine(b, dt.time()))
            except RuntimeError:
                print("unreachable", key, file=sys.stderr, flush=True)
                continue  # stays unmarked; the next run retries it
            db.mark(con, "bsky2", key, n)
            print(f"bsky {q!r} {a} images={n}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2023-09-26")
    ap.add_argument("--until", default=dt.date.today().isoformat())
    ap.add_argument("--query", action="append", help="one query; repeatable (default: every TERM)")
    ap.add_argument("--worker", default="0/1", help="i/n: take every n-th TERM starting at i")
    a = ap.parse_args()
    i, n = (int(x) for x in a.worker.split("/"))
    run(dt.date.fromisoformat(a.since), dt.date.fromisoformat(a.until), a.query or TERMS[i::n])
