"""rescore.py — score the stored pictures again with the current classifier, without refetching.

Pictures filed 'other' were never stored, so only the four walls are rescored.

    python tools/rescore.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "vision"))
import classify as C  # noqa: E402


def main():
    con = sqlite3.connect(ROOT / "data" / "catalog.sqlite", timeout=600)
    rows = con.execute("SELECT v.sha1, g.path FROM vision v JOIN images g ON g.sha1 = v.sha1 WHERE g.path IS NOT NULL").fetchall()
    moved = {}
    for sha, path in rows:
        p = ROOT / path
        if not p.exists():
            continue
        row, _ = C.look(p.read_bytes())
        con.execute("UPDATE vision SET seam_x=?, seam_score=?, faces=?, rfk_left=?, rfk_right=?, rfk_any=?, rfk_x=?, "
                    "thing_label=?, thing_score=?, thing_side=?, labels_json=?, klass=?, model=? WHERE sha1=?",
                    (row["seam_x"], row["seam_score"], row["faces"], row["rfk_left"], row["rfk_right"], row["rfk_any"],
                     row["rfk_x"], row["thing_label"], row["thing_score"], row["thing_side"], row["labels_json"],
                     row["klass"], C.MODEL, sha))
        con.commit()
        moved[row["klass"]] = moved.get(row["klass"], 0) + 1
    print(moved)


if __name__ == "__main__":
    main()
