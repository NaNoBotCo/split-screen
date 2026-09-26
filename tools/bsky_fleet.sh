#!/bin/bash
# Bluesky collection over the unhealthy TERMS in collect/bsky.py, ten workers, newest days first.
cd "$(dirname "$0")/.."
mkdir -p logs
for i in $(seq 0 9); do
  nohup .venv/bin/python collect/bsky.py --worker $i/10 > logs/bsky-terms-$i.log 2> logs/bsky-terms-$i.err &
done
