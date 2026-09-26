#!/bin/bash
# Numbers, pages, card, checks; then build/site → docs/. GitHub Pages serves docs/ from main.
#
#   ./publish.sh
#
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUTF8=1
PY=.venv/bin/python
SITE_URL="${SITE_URL:-https://nanobotco.github.io/split-screen}"
STYLE="$HOME/.claude/bin/stylecheck.py"

$PY tools/tally.py
SITE_URL="$SITE_URL" $PY tools/site.py
$PY tools/card.py
if [ -f "$STYLE" ]; then
  python3 "$STYLE" build/site README.md || { echo "REFUSED: style. See ~/.claude/STYLE.md"; exit 4; }
fi
if grep -rl "/Users/" build/site >/dev/null 2>&1; then
  echo "REFUSED: host paths found in build/site"; exit 2
fi
rm -rf docs
cp -R build/site docs
touch docs/.nojekyll
echo "docs/ ← $(find docs -name 'index.html' | wc -l | tr -d ' ') pages, $(du -sh docs | cut -f1)"
