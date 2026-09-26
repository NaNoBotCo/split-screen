"""sitemaps.py — news outlets' own sitemaps: every article, its date, its lead image.

An outlet's sitemap index points at dated child sitemaps (by year, month or day); this
walks the ones inside the window, keeps articles whose URL slug names one of the things
(or him), and takes the lead image from the sitemap's image:loc, or from the article's
og:image when the sitemap carries none.

    python collect/sitemaps.py [--outlet nypost.com] [--since 2023-09-26]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}

# sitemap index per outlet; the walker follows children whose URL dates fall in the window
OUTLETS = {
    "nypost.com": ["https://nypost.com/sitemap-{y}.xml"],
    "newsweek.com": ["https://www.newsweek.com/sitemap-{y}.xml?v={y}"],
    "dailymail.co.uk": ["https://www.dailymail.co.uk/sitemap-articles-year~{y}.xml"],
    "express.co.uk": ["https://www.express.co.uk/sitemap.xml"],
    "usatoday.com": ["https://www.usatoday.com/web-sitemap-index.xml"],
    "thehill.com": ["https://thehill.com/sitemap.xml"],
    "foxnews.com": ["https://www.foxnews.com/sitemap.xml?type=articles"],
    "mirror.co.uk": ["https://www.mirror.co.uk/sitemaps/sitemap_index.xml"],
    "independent.co.uk": ["https://www.independent.co.uk/sitemaps/sitemap-index.xml"],
    "washingtonexaminer.com": ["https://www.washingtonexaminer.com/sitemap.xml"],
    "thestreet.com": ["https://www.thestreet.com/sitemaps.xml"],
    "parade.com": ["https://parade.com/sitemaps.xml"],
    "huffpost.com": ["https://www.huffpost.com/static-assets/isolated/huffpostsitemapgeneratorjob-prod-public/us/sitemaps/sitemap-v1.xml"],
    "mediaite.com": ["https://www.mediaite.com/sitemap.xml"],
    "rawstory.com": ["https://www.rawstory.com/sitemap.xml"],
    "cbsnews.com": ["https://www.cbsnews.com/xml-sitemap/index.xml"],
    "nbcnews.com": ["https://www.nbcnews.com/sitemap/nbcnews/sitemap-index"],
    "dailycaller.com": ["https://dailycaller.com/sitemap"],
    "allrecipes.com": ["https://www.allrecipes.com/sitemap.xml"],
    "foodandwine.com": ["https://www.foodandwine.com/sitemap.xml"],
    "eatingwell.com": ["https://www.eatingwell.com/sitemap.xml"],
    "people.com": ["https://people.com/sitemap.xml"],
    "today.com": ["https://www.today.com/sitemap/today/sitemap-index"],
    "irishstar.com": ["https://www.irishstar.com/sitemaps/sitemap_index.xml"],
    "the-sun.com": ["https://www.the-sun.com/sitemap.xml"],
    "newsmax.com": ["https://www.newsmax.com/sitemap.xml"],
    "thedailybeast.com": ["https://www.thedailybeast.com/sitemap.xml"],
    "salon.com": ["https://www.salon.com/sitemap.xml"],
    "forbes.com": ["https://www.forbes.com/sitemaps/sitemap-index.xml"],
    "businessinsider.com": ["https://www.businessinsider.com/sitemap/index.xml"],
    "statnews.com": ["https://www.statnews.com/sitemap_index.xml"],
    "delish.com": ["https://www.delish.com/sitemap_index.xml"],
    "mensjournal.com": ["https://www.mensjournal.com/sitemaps.xml"],
    "dailydot.com": ["https://www.dailydot.com/sitemap_index.xml"],
    "unilad.com": ["https://www.unilad.com/sitemap.xml"],
    "ladbible.com": ["https://www.ladbible.com/sitemap.xml"],
    "dexerto.com": ["https://www.dexerto.com/sitemap_index.xml"],
    "yahoo.com": ["https://www.yahoo.com/sitemap-index.xml"],
}

SLUG = re.compile(
    r"(sugar|soda|dye|candy|candies|cereal|froot|skittle|seed-oil|raw-milk|formula|fluorid|tylenol|acetaminophen|"
    r"processed|junk-food|fast-food|mcdonald|hot-dog|ice-cream|energy-drink|coca-cola|coke|pepsi|mountain-dew|"
    r"doritos|aspartame|sweetener|snap|food-stamp|school-lunch|recall|fda|banned|-ban-|bans-|contamina|allergen|"
    r"listeria|salmonella|e-coli|vaccin|measles|ssri|antidepress|sunscreen|maha|rfk|kennedy|hhs|food|drink|milk|"
    r"cancer|autism|toxic|chemical|additive|preservative|microplastic|pesticide|glyphosate|obesity|diet|snack)", re.I)
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "image": "http://www.google.com/schemas/sitemap-image/1.1",
      "news": "http://www.google.com/schemas/sitemap-news/0.9"}
DATE_IN_URL = [
    re.compile(r"yyyy=(20\d\d)&(?:amp;)?mm=(\d\d)(?:&(?:amp;)?dd=(\d\d))?"),
    re.compile(r"(20\d\d)[-/_]?(\d\d)[-/_]?(\d\d)(?!\d)"),
    re.compile(r"(20\d\d)[-/_](\d\d)(?!\d)"),
    re.compile(r"(20\d\d)(\d\d)\.xml"),
    re.compile(r"sitemap-(20\d\d)\.xml\?mm=(\d\d)&(?:amp;)?dd=(\d\d)"),
    re.compile(r"(20\d\d)(?!\d)"),
]


def url_span(u: str):
    """(first day, last day) a child sitemap covers, from dates in its URL; None if undated."""
    for pat in DATE_IN_URL:
        m = pat.search(u)
        if not m:
            continue
        g = [x for x in m.groups() if x]
        y = int(g[0])
        if not (2000 <= y <= 2100):
            continue
        if len(g) >= 3:
            try:
                d = dt.date(y, int(g[1]), int(g[2]))
                return d, d
            except ValueError:
                continue
        if len(g) == 2 and 1 <= int(g[1]) <= 12:
            a = dt.date(y, int(g[1]), 1)
            b = (a + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
            return a, b
        return dt.date(y, 1, 1), dt.date(y, 12, 31)
    return None


class Walker:
    def __init__(self, con, outlet, since, until):
        self.con, self.outlet, self.since, self.until = con, outlet, since, until
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.seen = set()
        self.kept = 0
        self.last = 0.0

    def get(self, u):
        wait = 0.6 - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        for i in range(4):
            try:
                r = self.s.get(u, timeout=40)
            except requests.RequestException:
                time.sleep(5 * (i + 1))
                continue
            if r.status_code in (429, 503):
                time.sleep(20 * (i + 1))
                continue
            return r
        return None

    def walk(self, u, depth=0):
        if u in self.seen or depth > 4:
            return
        self.seen.add(u)
        if db.done(self.con, "sitemap", u):
            return
        r = self.get(u)
        if r is None or r.status_code != 200:
            print(f"  {self.outlet} {r.status_code if r is not None else 'x'} {u}", file=sys.stderr, flush=True)
            return
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            print(f"  {self.outlet} unparsable {u}", file=sys.stderr, flush=True)
            return
        tag = root.tag.split("}")[-1]
        if tag == "sitemapindex":
            kids = [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]
            for k in kids:
                span = url_span(k)
                if span and (span[1] < self.since or span[0] > self.until):
                    continue
                self.walk(k.replace("&amp;", "&"), depth + 1)
            return
        n = 0
        for url in root.findall("s:url", NS):
            loc = (url.findtext("s:loc", default="", namespaces=NS) or "").strip()
            if not loc or not SLUG.search(urlparse(loc).path):
                continue
            when = (url.findtext("news:news/news:publication_date", default="", namespaces=NS)
                    or url.findtext("s:lastmod", default="", namespaces=NS) or "").strip()
            day = when[:10]
            try:
                if not (self.since <= dt.date.fromisoformat(day) <= self.until):
                    continue
            except ValueError:
                span = url_span(loc)
                if not span or span[0] > self.until or span[1] < self.since:
                    continue
                when = span[0].isoformat()
            title = url.findtext("news:news/news:title", default=None, namespaces=NS)
            img = url.findtext("image:image/image:loc", default=None, namespaces=NS)
            self.con.execute(
                "INSERT OR IGNORE INTO articles(url, outlet, published, title, image_url) VALUES (?,?,?,?,?)",
                (loc, self.outlet, when, title, img.strip() if img else None))
            n += 1
        self.con.commit()
        span = url_span(u)
        # a finished past-dated child sitemap never changes; mark it so a rerun skips it
        if span and span[1] < dt.date.today() - dt.timedelta(days=2):
            db.mark(self.con, "sitemap", u, n)
        self.kept += n


SCHEMA = """CREATE TABLE IF NOT EXISTS articles (
  url TEXT PRIMARY KEY, outlet TEXT, published TEXT, title TEXT, image_url TEXT,
  og_done INTEGER DEFAULT 0
);"""
OG_IMG = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\'][^>]*content=["\']([^"\']+)', re.I)
OG_IMG2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)["\']', re.I)
OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]*content=["\']([^"\']+)', re.I)


def og(url):
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except requests.RequestException:
        return url, None, None
    if r.status_code != 200:
        return url, None, None
    h = r.text[:300000]
    m = OG_IMG.search(h) or OG_IMG2.search(h)
    t = OG_TITLE.search(h)
    import html as H
    return url, H.unescape(m.group(1)) if m else None, H.unescape(t.group(1)) if t else None


def queue(con):
    con.execute("""INSERT OR IGNORE INTO items(source, query, post_url, author, posted_at, text, headline, domain, image_url, link_url)
                   SELECT 'site', 'sitemap', url, outlet, published, NULL, title, outlet, image_url, url
                   FROM articles WHERE image_url IS NOT NULL""")
    con.commit()


def fill(con):
    """Queue articles that have an image; read og:image and og:title for the rest; queue again."""
    queue(con)
    rows = con.execute("SELECT url FROM articles WHERE og_done=0 AND (image_url IS NULL OR title IS NULL)").fetchall()
    with ThreadPoolExecutor(8) as ex:
        for url, img, title in ex.map(og, [r[0] for r in rows]):
            con.execute("UPDATE articles SET image_url=coalesce(image_url, ?), title=coalesce(title, ?), og_done=1 WHERE url=?",
                        (img, title, url))
            con.commit()
    queue(con)


def main(outlets, since, until):
    con = db.connect()
    con.executescript(SCHEMA)

    def one(o):
        c = db.connect()
        w = Walker(c, o, since, until)
        for tmpl in OUTLETS[o]:
            for y in range(since.year, until.year + 1):
                w.walk(tmpl.format(y=y))
                if "{y}" not in tmpl:
                    break
        print(f"sitemap {o} kept={w.kept}", flush=True)

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, outlets))
    fill(con)
    print("articles with images:", con.execute("SELECT count(*) FROM articles WHERE image_url IS NOT NULL").fetchone()[0])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outlet", action="append")
    ap.add_argument("--since", default="2023-09-26")
    ap.add_argument("--until", default=dt.date.today().isoformat())
    ap.add_argument("--fill-only", action="store_true", help="read og:images for articles found so far, then stop")
    a = ap.parse_args()
    if a.fill_only:
        c = db.connect()
        c.executescript(SCHEMA)
        fill(c)
        sys.exit()
    main(a.outlet or list(OUTLETS), dt.date.fromisoformat(a.since), dt.date.fromisoformat(a.until))
