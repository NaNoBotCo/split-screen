"""db.py — the catalog. One SQLite file, data/catalog.sqlite.

items   one row per (source, image) sighting: where it was posted, when, the words beside it
images  one row per distinct image file (sha1), with its perceptual hash
vision  what the classifier saw in an image
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "catalog.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,          -- bsky | gdelt
  query TEXT,
  post_url TEXT NOT NULL,
  author TEXT,
  posted_at TEXT,                -- ISO 8601 UTC
  text TEXT,                     -- post text or headline
  headline TEXT,                 -- link-card / article title when there is one
  domain TEXT,
  image_url TEXT NOT NULL,
  likes INTEGER, reposts INTEGER, replies INTEGER, quotes INTEGER,
  sha1 TEXT,                     -- filled by fetch
  UNIQUE(post_url, image_url)
);
CREATE INDEX IF NOT EXISTS items_sha ON items(sha1);
CREATE INDEX IF NOT EXISTS items_date ON items(posted_at);
CREATE INDEX IF NOT EXISTS items_img ON items(image_url);   -- the classifier updates by image_url
CREATE INDEX IF NOT EXISTS items_author ON items(author);

CREATE TABLE IF NOT EXISTS images (
  sha1 TEXT PRIMARY KEY,
  path TEXT, w INTEGER, h INTEGER,
  phash TEXT, dhash TEXT
);

CREATE TABLE IF NOT EXISTS fetch_fail (
  image_url TEXT PRIMARY KEY, status TEXT, tried_at TEXT
);

CREATE TABLE IF NOT EXISTS vision (
  sha1 TEXT PRIMARY KEY,
  seam_x REAL,            -- 0..1 position of the strongest vertical seam, NULL if none
  seam_score REAL,
  faces INTEGER,          -- faces found in the whole image
  rfk_left REAL,          -- best RFK face similarity on the left half
  rfk_right REAL,
  rfk_any REAL,
  rfk_x REAL,             -- 0..1 centre x of the best RFK face
  thing_label TEXT,       -- best unhealthy-thing label on the side away from RFK (or whole image)
  thing_score REAL,
  thing_side TEXT,        -- left | right | whole
  labels_json TEXT,       -- top labels with scores
  klass TEXT,             -- rfk_left | rfk_right | thing_only | rfk_only | other
  model TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  collector TEXT, key TEXT, done_at TEXT, n INTEGER,
  PRIMARY KEY(collector, key)
);
"""


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=600)  # collectors and the classifier share the write lock
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def done(con, collector: str, key: str) -> bool:
    return bool(con.execute("SELECT 1 FROM runs WHERE collector=? AND key=?", (collector, key)).fetchall())  # fetchall: an open cursor pins a read snapshot and a later write fails at once


def mark(con, collector: str, key: str, n: int) -> None:
    con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,datetime('now'),?)", (collector, key, n))
    con.commit()
