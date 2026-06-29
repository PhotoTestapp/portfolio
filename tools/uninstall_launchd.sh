#!/usr/bin/env bash
set -euo pipefail

LABEL="com.phototestapp.portfolio-prices"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if [[ -f "$DEST" ]]; then
  launchctl unload "$DEST" 2>/dev/null || true
else
  echo "plist not found:"
  echo "$DEST"
fi

read -r -p "Delete plist? [y/N] " answer
case "$answer" in
  y|Y)
    rm -f "$DEST"
    echo "Deleted plist:"
    echo "$DEST"
    ;;
  *)
    echo "Kept plist:"
    echo "$DEST"
    ;;
esac

echo
echo "launchctl list:"
if launchctl list | grep "$LABEL"; then
  echo "Warning: $LABEL is still registered."
else
  echo "$LABEL is not registered."
fi
