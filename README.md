# split-screen

Pictures posted beside RFK Jr. since 2023-09-26, sorted by what sits next to his face.

| Wall | Class | Rule |
|---|---|---|
| RFK left | `rfk_left` | vertical cut; his face left of it; a thing right of it |
| RFK right | `rfk_right` | the same, flipped |
| The thing | `thing_only` | a thing, no face of his |
| RFK | `rfk_only` | his face, no thing |

## Run

```
tools/bsky_fleet.sh                       # Bluesky, 12 workers, resumable
.venv/bin/python collect/gdelt.py         # GDELT news images, slow (shared IP is throttled)
tools/classify_loop.sh                    # fetch + score new images until the collectors stop
./publish.sh                              # numbers → pages → card → docs/
```

`data/catalog.sqlite` holds every row: `items` (sightings), `images` (files, perceptual
hashes), `vision` (scores, class), `runs` (which days each collector finished). Pictures
outside the four walls are scored and then deleted.

## Parts

- `collect/bsky.py` — public AppView search. Anonymous callers get page one only, so each
  day is halved until each window fits in one page of 100.
- `collect/gdelt.py` — GDELT DOC 2.0 artlist; lead image per article.
- `vision/reference.py` — his reference faces from Wikimedia Commons (`data/ref/rfk.npy`).
- `vision/faces.py` — YuNet detector, SFace embeddings (OpenCV model zoo, `models/`).
- `vision/things.py` — CLIP ViT-B/32 (LAION-2B) labels; thing groups and scene negatives.
- `vision/classify.py` — seam finder, face match, thing check; thresholds at the top.
- `vision/doom.py` — weighted alarm-word score for headlines and post text.
- `tools/tally.py` — `data/math.json`: Wilson intervals, binomial and Beta tests on left
  against right, perceptual-hash families, power-law fits, Gini, PELT change points, Hawkes
  fits, Shannon entropy, Jensen–Shannon divergence, Mann–Whitney, Kruskal–Wallis,
  Spearman, Rayleigh test on hour of day, news–social cross-correlation.
- `tools/site.py`, `tools/card.py` — the site and its share card.
- `tools/sheet.py` — contact sheets for checking thresholds by eye.

Code MIT. Words and numbers CC BY 4.0. Pictures belong to their owners.
