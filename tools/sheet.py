"""sheet.py — a contact sheet of stored pictures for eyeballing thresholds.

    python tools/sheet.py "SQL WHERE clause on vision v" out.jpg [limit]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def main(where, out, limit=48):
    con = sqlite3.connect(ROOT / "data" / "catalog.sqlite")
    rows = con.execute(f"""SELECT g.path, v.seam_score, json_extract(v.labels_json,'$.seam_rows'), v.rfk_any, v.rfk_x,
                           v.thing_label, v.thing_score, v.klass, v.seam_x
                           FROM vision v JOIN images g ON g.sha1=v.sha1 WHERE g.path IS NOT NULL AND ({where})
                           ORDER BY random() LIMIT {int(limit)}""").fetchall()
    cols, W, H = 6, 300, 230
    sheet = Image.new("RGB", (cols * W, ((len(rows) + cols - 1) // cols) * H), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (p, sc, sr, rfk, rx, tl, ts, k, sx) in enumerate(rows):
        im = Image.open(ROOT / p).convert("RGB")
        im.thumbnail((W - 6, H - 40))
        x, y = (i % cols) * W, (i // cols) * H
        sheet.paste(im, (x + 3, y + 3))
        if sx is not None:
            d.line([(x + 3 + sx * im.width, y + 3), (x + 3 + sx * im.width, y + 3 + im.height)], fill=(255, 0, 0), width=1)
        d.text((x + 4, y + H - 36), f"#{i} {k} seam {sc:.1f}/{(sr or 0):.2f} rfk {rfk or 0:.2f}", fill=(255, 255, 255))
        d.text((x + 4, y + H - 20), f"{tl} {ts:.2f}", fill=(255, 210, 120))
    sheet.save(out, quality=85)
    print(out, len(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:]))
