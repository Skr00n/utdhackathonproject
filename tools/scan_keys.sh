#!/usr/bin/env bash
# Scan the repo for leaked API keys. Prints file:line and a MASKED match only (never the key).
# Usage: tools/scan_keys.sh [--history]   (--history also scans every git commit)
# Exit 1 if anything is found. Run it before every push.
set -uo pipefail
cd "$(dirname "$0")/.."
PAT='AIza[0-9A-Za-z_-]{30,}|AQ\.Ab8[0-9A-Za-z_-]{20,}|(GEMINI|GOOGLE|SERP|PLACES)_API_KEY[[:space:]]*[=:][[:space:]]*["'"'"']?[A-Za-z0-9_.-]{16,}'
ALLOW='your-key-here|PASTE_KEY|test-not-a-real-key|FAKEFAKE'
mask() { sed -E 's/((AIza|AQ\.Ab8|API_KEY[[:space:]]*[=:][[:space:]]*["'"'"']?)[A-Za-z0-9_.-]{0,2})[A-Za-z0-9_.-]+/\1…[MASKED]/g'; }
found=0
hits=$(grep -rInE "$PAT" . \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude-dir=__pycache__ --exclude-dir=var \
  --exclude-dir=out --exclude-dir=.pytest_cache --exclude='*.zip' --exclude='scan_keys.sh' 2>/dev/null | grep -vE "$ALLOW" || true)
if [ -n "$hits" ]; then echo "✗ Possible keys in working tree:"; echo "$hits" | cut -c1-200 | mask; found=1; fi
for f in .env .env.local .env.production; do
  if [ -f "$f" ] && git ls-files --error-unmatch "$f" >/dev/null 2>&1; then echo "✗ $f is tracked by git"; found=1; fi
done
if git rev-parse --git-dir >/dev/null 2>&1; then
  if git check-ignore -q .env && git check-ignore -q .env.local; then :; else echo "✗ .gitignore does not cover .env*"; found=1; fi
elif ! grep -qxF '.env.*' .gitignore 2>/dev/null || ! grep -qxF '.env' .gitignore; then echo "✗ .gitignore does not cover .env*"; found=1; fi
if [ -f page_one_builder.ipynb ]; then
  python3 - <<'PY' || found=1
import json, sys
nb = json.load(open("page_one_builder.ipynb"))
bad = [i for i, c in enumerate(nb["cells"]) if c.get("cell_type") == "code" and (c.get("outputs") or c.get("execution_count"))]
if bad:
    print(f"✗ notebook has saved outputs in cells {bad}"); sys.exit(1)
PY
fi
if [ "${1:-}" = "--history" ] && [ -d .git ]; then
  h=$(git log -p --all 2>/dev/null | grep -nE "$PAT" | grep -vE "$ALLOW" || true)
  if [ -n "$h" ]; then echo "✗ Possible keys in git history:"; echo "$h" | cut -c1-200 | mask; found=1; fi
fi
if [ $found -eq 0 ]; then echo "✓ No keys found (working tree$( [ "${1:-}" = "--history" ] && echo ' + git history'))"; fi
exit $found
