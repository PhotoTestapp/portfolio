#!/usr/bin/env bash
set -euo pipefail

LABEL="com.phototestapp.portfolio-prices"
TEMPLATE="tools/launchd/${LABEL}.plist"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
OUT_LOG="${HOME}/Library/Logs/portfolio-prices.out.log"
ERR_LOG="${HOME}/Library/Logs/portfolio-prices.err.log"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "Error: not inside a git repository."
  exit 1
fi

cd "$ROOT"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Error: plist template not found: $TEMPLATE"
  exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/Library/Logs"
touch "$OUT_LOG" "$ERR_LOG"

TMP_PLIST="$(mktemp)"
python3 - "$TEMPLATE" "$TMP_PLIST" "$ROOT" "$HOME" <<'PY'
from pathlib import Path
import sys

template, output, root, home = sys.argv[1:5]
text = Path(template).read_text(encoding="utf-8")
text = text.replace("__REPO_ROOT__", root)
text = text.replace("__HOME__", home)
Path(output).write_text(text, encoding="utf-8")
PY

cp "$TMP_PLIST" "$DEST"
rm -f "$TMP_PLIST"

echo "Installed plist:"
echo "$DEST"
echo

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "launchctl list:"
launchctl list | grep "$LABEL" || true
echo
echo "Next run:"
echo "Every day at 09:05 JST"
echo
echo "Logs:"
echo "$OUT_LOG"
echo "$ERR_LOG"
