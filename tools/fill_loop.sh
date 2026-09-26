#!/bin/bash
# Move sitemap articles into the classify queue every ten minutes while the walker runs.
cd "$(dirname "$0")/.."
while pgrep -f collect/sitemaps.py >/dev/null; do
  .venv/bin/python collect/sitemaps.py --fill-only
  sleep 600
done
.venv/bin/python collect/sitemaps.py --fill-only
