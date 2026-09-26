"""reference.py — RFK Jr.'s face, learned from Wikimedia Commons photographs.

Pulls files from the Commons category and its subcategories, finds every face, and
keeps the faces that agree with each other: in a group photo, the face that matches
the others across files is his. Writes data/ref/rfk.npy (one 128-number SFace
embedding per kept face).

    python vision/reference.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import faces  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ref"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "split-screen-catalog/0.1 (https://github.com/NaNoBotCo; research bot) python-requests"}


def get(s, url, **kw):
    """GET with backoff: this IP is shared, and Commons answers 429 when it is busy."""
    import time
    for i in range(8):
        r = s.get(url, timeout=30, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(120, 5 * 2 ** i))
            continue
        return r
    r.raise_for_status()


CATS = ["Category:Robert F. Kennedy Jr.", "Category:Robert F. Kennedy Jr. in 2024",
        "Category:Robert F. Kennedy Jr. in 2025", "Category:Robert F. Kennedy Jr. in 2023",
        "Category:Robert F. Kennedy Jr. 2024 presidential campaign", "Category:Portraits of Robert F. Kennedy Jr."]


def files(s, cat, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if cat in seen or depth > 2:
        return
    seen.add(cat)
    cont = {}
    while True:
        r = get(s, API, params={"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": 500,
                                "cmtype": "file|subcat", "format": "json", **cont}).json()
        for m in r.get("query", {}).get("categorymembers", []):
            if m["ns"] == 14:
                yield from files(s, m["title"], depth + 1, seen)
            elif m["title"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                yield m["title"]
        if "continue" not in r:
            break
        cont = r["continue"]


def thumb(s, title):
    # Commons serves thumbnails only at standard widths (250, 330, 500, 960, 1280…); 900 answers 400
    r = get(s, API, params={"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url",
                            "iiurlwidth": 960, "format": "json"}).json()
    for p in r["query"]["pages"].values():
        ii = p.get("imageinfo", [{}])[0]
        return ii.get("thumburl") or ii.get("url")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update(UA)
    titles = []
    for c in CATS:
        titles += [t for t in files(s, c) if t not in titles]
    print(len(titles), "files", flush=True)
    per_file = []  # list of lists of embeddings
    for i, t in enumerate(titles[:300]):
        if i % 25 == 0:
            print(i, "looked at", len(per_file), "with faces", flush=True)
        u = thumb(s, t)
        if not u:
            continue
        try:
            im = Image.open(io.BytesIO(get(s, u).content)).convert("RGB")
        except Exception:
            continue
        embs = [f["emb"] for f in faces.find(np.asarray(im)) if f["w"] >= 40]
        if embs:
            per_file.append((t, embs))
    print(len(per_file), "files with faces", flush=True)
    # solo shots seed the centroid; then each file contributes its best-agreeing face
    solos = np.array([e[0] for t, e in per_file if len(e) == 1])
    c = solos.mean(0)
    for _ in range(3):
        c = c / np.linalg.norm(c)
        sims = solos @ c
        c = solos[sims >= np.quantile(sims, 0.25)].mean(0)
    c = c / np.linalg.norm(c)
    keep = []
    for t, embs in per_file:
        E = np.array(embs)
        i = int(np.argmax(E @ c))
        if E[i] @ c >= 0.45:
            keep.append(E[i])
    K = np.array(keep)
    np.save(OUT / "rfk.npy", K)
    print(f"kept {len(K)} faces; mean self-similarity {float((K @ c).mean()):.3f}")


if __name__ == "__main__":
    main()
