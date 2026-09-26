"""bsky_authors.py — every picture post from the accounts that run the format, back to the window start.

Search stops at page one for anonymous callers; an account's own feed pages all the way back.
Seeds are in ACCOUNTS; --snowball adds every account whose posts the classifier has filed
RFK-left or RFK-right, and every account those posts quote or link.

    python collect/bsky_authors.py [--snowball] [--since 2023-09-26]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
from bsky import images_of, post_url  # noqa: E402

API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
UA = {"User-Agent": "split-screen-catalog/0.1 (research; nanobotco)"}
# aggregators first, then outlets: an outlet account shares each article with its card picture
ACCOUNTS = [
    "factpostnews.bsky.social", "leadingreports.bsky.social", "visegrad24real.bsky.social", "disclosetv.bsky.social",
    "thespectatorindex.bsky.social", "globeeyenews.bsky.social", "popbase.tv", "popcrave.com", "unusualwhales.bsky.social",
    "kalshiofficial.bsky.social", "polymarket.com", "thedailyloud.bsky.social", "insiderpaper.com", "bnonews.com",
    "health.bnonews.com", "marionawfal.bsky.social", "rawsalerts.bsky.social",
    "newsmax.com", "nypost.com", "newsweek.com", "dailymail.co.uk", "the-independent.com", "foxnews.com.web.brid.gy",
    "huffpost.com", "thehill.com", "dailydot.com", "mediaite.com", "rawstory.com", "irishstar.com", "themirror.com",
    "yahoonews.com", "cbsnews.com", "nbcnews.com", "usatoday.com", "nytimes.com", "washingtonpost.com", "cnn.com",
    "apnews.com", "reuters.com", "npr.org", "politico.com", "axios.com", "abcnews.bsky.social", "thedailybeast.com",
    "salon.com", "motherjones.com", "theguardian.com", "latimes.com", "businessinsider.com", "forbes.com",
    "statnews.com", "people.com", "today.com", "newsnation.bsky.social", "independent.co.uk", "time.com",
    "theatlantic.com", "vox.com", "slate.com", "newrepublic.com", "thedailyshow.com", "msnbc.com",
]
HANDLE_IN_URL = re.compile(r"bsky\.app/profile/([^/]+)/post/")


def feed(s, con, actor: str, since: dt.date) -> int:
    cursor, kept, pages = None, 0, 0
    while True:
        params = {"actor": actor, "limit": 100, "filter": "posts_with_media"}
        if cursor:
            params["cursor"] = cursor
        for i in range(6):
            try:
                r = s.get(API, params=params, timeout=30)
            except requests.RequestException:
                time.sleep(5 * (i + 1))
                continue
            if r.status_code in (429,) or r.status_code >= 500:
                time.sleep(15 * (i + 1))
                continue
            break
        if r.status_code != 200:
            print(f"  {actor} {r.status_code} {r.text[:120]}", file=sys.stderr, flush=True)
            return kept
        d = json.loads(r.content.decode("utf-8", "replace"), strict=False)
        items = d.get("feed", [])
        oldest = None
        for it in items:
            if it.get("reason"):          # a repost of someone else
                continue
            p = it["post"]
            rec = p.get("record", {})
            when = rec.get("createdAt") or p.get("indexedAt")
            oldest = when
            if when and when[:10] < since.isoformat():
                continue
            for u, title, link in images_of(p):
                dom = urlparse(link).netloc.removeprefix("www.") if link else "bsky.app"
                con.execute(
                    "INSERT OR IGNORE INTO items(source,query,post_url,author,posted_at,text,headline,domain,"
                    "image_url,likes,reposts,replies,quotes,link_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("bsky", "account", post_url(p), p["author"]["handle"], when, rec.get("text"), title, dom, u,
                     p.get("likeCount"), p.get("repostCount"), p.get("replyCount"), p.get("quoteCount"), link))
                kept += 1
        con.commit()
        pages += 1
        cursor = d.get("cursor")
        if not cursor or not items or (oldest and oldest[:10] < since.isoformat()):
            break
        time.sleep(0.3)
    return kept


def snowball(con) -> list[str]:
    rows = con.execute("""SELECT DISTINCT i.author, i.link_url FROM items i JOIN vision v ON v.sha1 = i.sha1
                          WHERE v.klass IN ('rfk_left','rfk_right') AND i.source = 'bsky'""").fetchall()
    out = set()
    for author, link in rows:
        if author and author != "handle.invalid":
            out.add(author)
        m = HANDLE_IN_URL.search(link or "")
        if m:
            out.add(m.group(1))
    return sorted(out)


def main(since: dt.date, snow: bool):
    con = db.connect()
    s = requests.Session()
    s.headers.update(UA)
    actors = list(dict.fromkeys(list(ACCOUNTS) + (snowball(con) if snow else [])))

    def one(a):
        c = db.connect()
        ss = requests.Session()
        ss.headers.update(UA)
        key = f"{a}|{dt.date.today()}"
        if db.done(c, "bsky_author", key):
            return
        n = feed(ss, c, a, since)
        db.mark(c, "bsky_author", key, n)
        print(f"account {a} images={n}", flush=True)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, actors))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2023-09-26")
    ap.add_argument("--snowball", action="store_true")
    a = ap.parse_args()
    main(dt.date.fromisoformat(a.since), a.snowball)
