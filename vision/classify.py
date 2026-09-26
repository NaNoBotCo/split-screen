"""classify.py — fetch each catalogued image once, look at it, file it.

For each distinct image:
  1. seam   — a straight vertical cut between two pictures pasted side by side
  2. faces  — every face, matched against RFK Jr.'s reference faces
  3. thing  — CLIP labels on the side away from his face (or the whole picture)

The seam is recorded, not required: a card like the FactPost sugar recall has no clean cut.

Classes (a picture gets one):
  rfk_left    RFK's face left of centre, a thing on the far side of it
  rfk_right   RFK's face right of centre, a thing on the far side of it
  rfk_only    RFK's face, no thing beside it
  thing_only  a thing, no RFK face
  other       the rest

Every picture keeps its hashes and scores. Pictures in the first four classes are kept
on disk at 640 px; the rest are dropped after scoring.

    python vision/classify.py [--workers 16] [--limit N] [--shard 0/3]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imagehash
import numpy as np
import requests
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
import db  # noqa: E402
import faces  # noqa: E402
import things  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "data" / "img"
REF = np.load(ROOT / "data" / "ref" / "rfk.npy")
MODEL = "yunet+sface/clip-vit-b32-laion2b/v5"

RFK_T = 0.50        # top-5 mean cosine to the reference faces; scores fall in two humps, <0.35 and >0.55
THING_T = 0.50      # share of CLIP mass on thing labels
SEAM_T = 5.0        # seam contrast over the band's median column contrast
SEAM_ROWS = 0.75    # the cut runs unbroken down this share of the height inside any border (0.45 if dead straight)
SEAM_STRAIGHT = 0.80  # share of band rows whose sharpest nearby change sits on the cut
THING_COS = 0.24    # raw CLIP cosine of the best thing label

AGGREGATORS = ["factpostnews.bsky.social", "leadingreports.bsky.social", "visegrad24real.bsky.social",
               "disclosetv.bsky.social", "thespectatorindex.bsky.social", "globeeyenews.bsky.social",
               "unusualwhales.bsky.social", "kalshiofficial.bsky.social", "polymarket.com",
               "thedailyloud.bsky.social", "insiderpaper.com", "bnonews.com", "health.bnonews.com",
               "marionawfal.bsky.social", "rawsalerts.bsky.social"]
TOPIC = re.compile(
    r"(sugar|soda|dye|candy|cereal|seed.oil|raw.milk|formula|fluorid|tylenol|acetaminophen|processed|junk.food|"
    r"fast.food|mcdonald|hot.dog|ice.cream|energy.drink|coca.cola|coke|pepsi|doritos|aspartame|sweetener|snap|"
    r"school.lunch|recall|fda|ban|contamina|allergen|listeria|salmonella|vaccin|measles|ssri|antidepress|sunscreen|"
    r"maha|rfk|kennedy|hhs|food|drink|milk|cancer|autism|toxic|chemical|additive|diet|snack|health|cdc|drug)", re.I)

_local = threading.local()


def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) split-screen-catalog/0.1"
    return _local.s


def fetch(url: str):
    try:
        r = session().get(url, timeout=25)
        if r.status_code != 200 or len(r.content) < 1500:
            return url, None, f"http {r.status_code}"
        return url, r.content, None
    except Exception as e:  # noqa: BLE001
        return url, None, type(e).__name__


def trim(g: np.ndarray) -> tuple[int, int, int, int]:
    """Rows and columns of g inside any flat border (letterbox bars, a white frame)."""
    rs, cs = g.std(1) > 3, g.std(0) > 3
    r = np.nonzero(rs)[0]
    c = np.nonzero(cs)[0]
    if r.size < 16 or c.size < 16:
        return 0, g.shape[0], 0, g.shape[1]
    return int(r[0]), int(r[-1]) + 1, int(c[0]), int(c[-1]) + 1


def seam(g: np.ndarray):
    """The strongest straight vertical cut in the middle 40%, over the longest band of rows it runs.

    Returns (x 0..1, contrast, band share of height, y0 0..1, y1 0..1, straightness 0..1). The band lets a composite
    inside a screenshot (text above, letterbox bars) still count: the cut need only run down the
    picture part."""
    d = np.abs(np.diff(g, axis=1))                 # H x (W-1)
    H, W = d.shape
    lo, hi = int(W * 0.3), int(W * 0.7)
    base_col = float(np.median(d.mean(0))) + 1.0
    thr = max(12.0, 3 * base_col)
    # a cut may wobble a pixel after resizing: take the max over x-1..x+1
    dd = np.maximum(np.maximum(d[:, lo - 1:hi - 1], d[:, lo:hi]), d[:, lo + 1:hi + 1]) > thr
    best = (None, 0.0, 0.0, 0.0, 1.0, 0.0)
    for j in np.argsort(-dd.mean(0))[:6]:
        col = dd[:, j]
        # longest run of strong rows, bridging gaps of up to 3 rows
        run = gap = 0
        start = best_len = best_start = 0
        for r in range(H):
            if col[r]:
                if run == 0:
                    start = r
                run += 1 + gap
                gap = 0
            elif run:
                gap += 1
                if gap > 3:
                    if run > best_len:
                        best_len, best_start = run, start
                    run = gap = 0
        if run > best_len:
            best_len, best_start = run, start
        share = best_len / H
        if share > best[2]:
            y0, y1 = best_start, best_start + best_len
            x = lo + int(j)
            band = d[y0:y1]
            # straight: in most band rows the sharpest change within ±4 columns sits on one column (±1),
            # the same column row after row; a body outline drifts
            am = np.argmax(band[:, max(0, x - 4):x + 5], axis=1)
            c = np.convolve(np.bincount(am, minlength=9), [1, 1, 1], "same")
            straight = float(c.max() / max(1, am.size))
            contrast = float(band[:, x].mean()) / (float(np.median(band.mean(0))) + 1.0)
            best = ((x + 0.5) / W, contrast, share, y0 / H, y1 / H, straight)
    return best


def rfk_sim(e: np.ndarray) -> float:
    s = np.sort(REF @ e)[::-1]
    return float(s[:5].mean())


def look(raw: bytes) -> tuple[dict, Image.Image]:
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    im.thumbnail((960, 960))
    a = np.asarray(im)
    H, W = a.shape[:2]
    g = np.asarray(im.convert("L").resize((512, max(64, int(512 * H / W)))), dtype=np.float32)
    t0, t1, l0, l1 = trim(g)
    gh, gw = g.shape
    sx, sc, sr, y0, y1, st = seam(g[t0:t1, l0:l1])
    has_seam = sx is not None and sc >= SEAM_T and st >= SEAM_STRAIGHT and (
        sr >= SEAM_ROWS or (st >= 0.95 and sr >= 0.45))
    sx = sx if sx is not None else 0.5
    # back to whole-picture coordinates
    sx = (l0 + sx * (l1 - l0)) / gw
    y0, y1 = (t0 + y0 * (t1 - t0)) / gh, (t0 + y1 * (t1 - t0)) / gh
    fs = [f for f in faces.find(a) if f["w"] >= 24]
    best = None
    for f in fs:
        f["rfk"] = rfk_sim(f["emb"])
        f["cx"] = (f["x"] + f["w"] / 2) / W
        if best is None or f["rfk"] > best["rfk"]:
            best = f
    rfk = best is not None and best["rfk"] >= RFK_T
    left_sims = [f["rfk"] for f in fs if f["cx"] < 0.5]
    right_sims = [f["rfk"] for f in fs if f["cx"] >= 0.5]
    # the thing is looked for on the side away from his face: from the face's outer edge (or the seam,
    # or the midline, whichever is farthest from him) to the picture's edge
    if rfk:
        fx0, fx1 = best["x"] / W, (best["x"] + best["w"]) / W
        if best["cx"] < 0.5:
            side = "right"
            x0 = max(0.5, fx1, sx if has_seam else 0)
            crop = im.crop((int(x0 * W), 0, W, H)) if x0 < 0.92 else None
        else:
            side = "left"
            x1 = min(0.5, fx0, sx if has_seam else 1)
            crop = im.crop((0, 0, int(x1 * W), H)) if x1 > 0.08 else None
    else:
        side, crop = "whole", im
    t = things.score([crop])[0] if crop is not None else {"groups": {"scene": 1.0}, "best": None, "thing_mass": 0.0,
                                                          "thing_cos": 0.0, "top": []}
    # beside his face the share decides; a whole picture with no face of his must also clear the cosine
    thing = t["thing_mass"] >= THING_T and (rfk or t["thing_cos"] >= THING_COS)
    if rfk and thing:
        klass = "rfk_left" if side == "right" else "rfk_right"
    elif rfk:
        klass = "rfk_only"
    elif thing:
        klass = "thing_only"
    else:
        klass = "other"
    row = {
        "seam_x": sx if has_seam else None, "seam_score": sc, "seam_rows": sr, "faces": len(fs),
        "rfk_left": max(left_sims, default=None), "rfk_right": max(right_sims, default=None),
        "rfk_any": best["rfk"] if best else None, "rfk_x": best["cx"] if best else None,
        "thing_label": t["best"], "thing_score": t["thing_mass"], "thing_side": side,
        "labels_json": json.dumps({"groups": {k: round(v, 4) for k, v in t["groups"].items()}, "top": t["top"],
                                   "thing_cos": round(t["thing_cos"], 4), "seam_rows": round(sr, 3), "seam_straight": round(st, 3),
                                   "band": [round(y0, 3), round(y1, 3)]}),
        "klass": klass,
    }
    return row, im


def main(workers: int, limit: int | None, shard: int = 0, shards: int = 1):
    con = db.connect()
    # accounts that run the format, then news, then Bluesky link cards, then photos on term posts, then the first pass by name; newest first
    q = ("SELECT image_url FROM items WHERE sha1 IS NULL "
         "AND image_url NOT IN (SELECT image_url FROM fetch_fail) "
         "GROUP BY image_url ORDER BY max(CASE WHEN query = 'account' THEN 4 WHEN source != 'bsky' THEN 3 WHEN link_url IS NOT NULL THEN 2 "
         "WHEN query NOT IN ('RFK','Robert F. Kennedy','Secretary Kennedy','Kennedy HHS') THEN 1 ELSE 0 END) DESC, "
         "max(posted_at) DESC")
    # outlet accounts share everything; look only at their posts that name a thing, him, or health
    skip = {r[0] for r in con.execute(
        "SELECT image_url FROM items WHERE sha1 IS NULL AND query='account' AND author NOT IN (%s)"
        % ",".join("?" * len(AGGREGATORS)), AGGREGATORS)
        if True} - {r[0] for r in con.execute(
        "SELECT image_url, coalesce(headline,'') || ' ' || coalesce(text,'') || ' ' || coalesce(link_url,'') FROM items "
        "WHERE sha1 IS NULL AND query='account'") if TOPIC.search(r[1])}
    urls = [r[0] for r in con.execute(q) if r[0] not in skip
            and int(hashlib.md5(r[0].encode()).hexdigest(), 16) % shards == shard]
    urls = urls[:limit] if limit else urls
    print(f"{len(urls)} images to fetch", flush=True)
    n = kept = 0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for url, raw, err in ex.map(fetch, urls):
            n += 1
            if raw is None:
                con.execute("INSERT OR REPLACE INTO fetch_fail VALUES (?,?,datetime('now'))", (url, err))
                con.commit()
                continue
            sha = hashlib.sha1(raw).hexdigest()
            if not con.execute("SELECT 1 FROM vision WHERE sha1=?", (sha,)).fetchall():
                try:
                    row, im = look(raw)
                except Exception as e:  # noqa: BLE001
                    con.execute("INSERT OR REPLACE INTO fetch_fail VALUES (?,?,datetime('now'))",
                                (url, "decode " + type(e).__name__))
                    continue
                path = None
                if row["klass"] != "other":
                    p = IMG / sha[:2] / f"{sha}.jpg"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    small = im.copy()
                    small.thumbnail((640, 640))
                    small.save(p, "JPEG", quality=82)
                    path = str(p.relative_to(ROOT))
                    kept += 1
                con.execute("INSERT OR REPLACE INTO images VALUES (?,?,?,?,?,?)",
                            (sha, path, im.width, im.height, str(imagehash.phash(im)), str(imagehash.dhash(im))))
                con.execute("INSERT OR REPLACE INTO vision VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (sha, row["seam_x"], row["seam_score"], row["faces"], row["rfk_left"], row["rfk_right"],
                             row["rfk_any"], row["rfk_x"], row["thing_label"], row["thing_score"], row["thing_side"],
                             row["labels_json"], row["klass"], MODEL))
            con.execute("UPDATE items SET sha1=? WHERE image_url=?", (sha, url))
            con.commit()  # per image: the collectors write to the same file
            if n % 200 == 0:
                rate = n / (time.time() - t0)
                print(f"{n}/{len(urls)} kept={kept} {rate:.1f}/s", flush=True)
    con.commit()
    print(f"done {n} kept={kept}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--shard", default="0/1", help="i/n: take the URLs whose hash mod n is i")
    a = ap.parse_args()
    i, n = (int(x) for x in a.shard.split("/"))
    main(a.workers, a.limit, i, n)
