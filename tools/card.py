"""card.py — the share card, 1200×630: a wall of the catalog's own split screens under the title.

    python tools/card.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "build" / "site"
W, H = 1200, 630
BG = (11, 11, 15)
INK = (244, 241, 234)
HOT = (255, 90, 78)
MUTE = (170, 164, 151)
COND = "/System/Library/Fonts/Avenir Next Condensed.ttc"
BODY = "/System/Library/Fonts/Avenir Next.ttc"
THAI = "/System/Library/Fonts/Supplemental/Tahoma.ttf"


def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.load_default()


def tiles(slugs=("left", "right", "thing", "face")):
    out = []
    for slug in slugs:
        p = SITE / "data" / f"{slug}.json"
        if p.exists():
            rows = sorted(json.loads(p.read_text()), key=lambda x: -x["doom"])
            seen = set()
            for x in rows:
                if x["s"] not in seen and (SITE / "img" / f"{x['s']}.jpg").exists():
                    seen.add(x["s"])
                    out.append(SITE / "img" / f"{x['s']}.jpg")
        if len(out) >= 24:
            break
    return out[:24]


def build(out="card.jpg", head="SPLIT SCREEN", lines=None, slugs=("left", "right", "thing", "face"),
          address="nanobotco.github.io/split-screen"):
    """The home card, or one page's: the same wall of tiles, that page's title and line, its address."""
    img = Image.new("RGB", (W, H), BG)
    cw, ch = 200, 126
    for i, p in enumerate(tiles(slugs)):
        t = Image.open(p).convert("RGB")
        r = max(cw / t.width, ch / t.height)
        t = t.resize((int(t.width * r) + 1, int(t.height * r) + 1))
        t = t.crop((0, 0, cw, ch))
        img.paste(t, ((i % 6) * cw, (i // 6) * ch + 60))
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for x in range(W):
        a = int(235 * max(0.25, 1 - x / (W * 0.75)))
        sd.line([(x, 0), (x, H)], fill=BG + (a,))
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")
    d = ImageDraw.Draw(img)
    d.rectangle([64, 150, 124, 190], fill=(201, 184, 166))
    d.rectangle([124, 150, 184, 190], fill=(255, 244, 224))
    d.rectangle([64, 150, 184, 190], outline=HOT, width=4)
    size = 118
    while size > 50 and d.textlength(head, font=font(COND, size, 2)) > W - 128:
        size -= 6
    d.text((60, 205), head, font=font(COND, size, 2), fill=INK)
    lines = lines or [("RFK Jr. on one side. The thing on the other.", BODY, 34, INK),
                      ("Catalog + math, Sept 2023 to today", BODY, 28, MUTE),
                      ("ภาพคู่: หน้า RFK กับของที่ถูกกล่าวหา", THAI, 30, MUTE)]
    y = 340
    for text, face, sz, fill in lines:
        d.text((64, y), text, font=font(face, sz), fill=fill)
        y += 48 if sz >= 34 else 52
    d.text((64, 560), address, font=font(BODY, 24), fill=HOT)
    dest = SITE / out
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=88)
    print("card", dest)


# One card per page, named like the page's folder, saying the page's own title and line (read from the built
# page) over tiles from the wall that page shows.
PAGE_TILES = {
    "left": ("left",), "right": ("right",), "thing": ("thing",), "face": ("face",),
    "math": ("left", "right", "thing", "face"), "data": ("face", "thing", "right", "left"),
}


def build_pages():
    import html
    import re
    for slug, slugs in PAGE_TILES.items():
        page = SITE / slug / "index.html"
        if not page.exists():
            continue
        t = page.read_text(encoding="utf-8")
        title = re.search(r'<meta property="og:title" content="([^"]*)"', t)
        desc = re.search(r'<meta property="og:description" content="([^"]*)"', t)
        head = html.unescape(title.group(1)).split(" — ")[0].upper() if title else slug.upper()
        line = html.unescape(desc.group(1)) if desc else ""
        build(f"cards/{slug}.jpg", head, [(line, BODY, 34, INK)], slugs, f"nanobotco.github.io/split-screen/{slug}")


if __name__ == "__main__":
    build()
    build_pages()
