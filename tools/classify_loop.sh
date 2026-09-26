#!/bin/bash
# Classify new rows as the collectors add them; stop after an hour with nothing new while no collector runs.
cd "$(dirname "$0")/.."
idle=0
while true; do
  n=$(sqlite3 data/catalog.sqlite "SELECT count(DISTINCT image_url) FROM items WHERE sha1 IS NULL AND image_url NOT IN (SELECT image_url FROM fetch_fail)")
  if [ "$n" -gt 0 ]; then
    for i in 0 1 2; do
      .venv/bin/python vision/classify.py --workers 12 --limit 8000 --shard $i/3 2>&1 | grep --line-buffered -v -E "WARN|HF Hub" | sed -u "s/^/[$i] /" &
    done
    wait
    idle=0
  else
    pgrep -f "collect/(bsky|gdelt).py" >/dev/null || idle=$((idle+1))
    [ $idle -ge 12 ] && break
    sleep 300
  fi
done
echo "classify loop finished"
