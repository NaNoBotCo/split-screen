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


def tiles():
    out = []
    for slug in ("left", "right", "thing", "face"):
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


def build():
    img = Image.new("RGB", (W, H), BG)
    cw, ch = 200, 126
    for i, p in enumerate(tiles()):
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
    d.text((60, 205), "SPLIT SCREEN", font=font(COND, 118, 2), fill=INK)
    d.text((64, 340), "RFK Jr. on one side. The thing on the other.", font=font(BODY, 34), fill=INK)
    d.text((64, 388), "Catalog + math, Sept 2023 to today", font=font(BODY, 28), fill=MUTE)
    d.text((64, 440), "ภาพคู่: หน้า RFK กับของที่ถูกกล่าวหา", font=font(THAI, 30), fill=MUTE)
    d.text((64, 560), "nanobotco.github.io/split-screen", font=font(BODY, 24), fill=HOT)
    img.save(SITE / "card.jpg", quality=88)
    print("card", SITE / "card.jpg")


if __name__ == "__main__":
    build()
