#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "Error: not inside a git repository."
  exit 1
fi

cd "$ROOT"

echo "Generating prices.json..."
python3 tools/generate_prices_json.py

echo "Validating prices.json..."
python3 -m json.tool prices.json > /dev/null
echo "JSON validation succeeded"

if [[ ! -f prices.json ]]; then
  echo "Error: prices.json does not exist."
  exit 1
fi

if [[ ! -f data/prices_input.csv ]]; then
  echo "Error: data/prices_input.csv does not exist."
  exit 1
fi

echo
echo "git status --short"
git status --short

echo
echo "git diff"
git diff -- prices.json data/prices_input.csv README.md index.html tools/generate_prices_json.py tools/publish_prices.sh tools/launchd/com.phototestapp.portfolio-prices.plist tools/install_launchd.sh tools/uninstall_launchd.sh

STATUS_OUTPUT="$(git status --short -- data/prices_input.csv prices.json README.md index.html tools/generate_prices_json.py tools/publish_prices.sh tools/launchd/com.phototestapp.portfolio-prices.plist tools/install_launchd.sh tools/uninstall_launchd.sh)"
if [[ -z "$STATUS_OUTPUT" ]]; then
  echo "No changes to publish."
  exit 0
fi

echo
echo "About to commit and push price JSON update."
echo
echo "Files:"
echo "- data/prices_input.csv"
echo "- prices.json"
echo "- README.md"
echo "- index.html"
echo "- tools/generate_prices_json.py"
echo "- tools/publish_prices.sh"
echo "- tools/launchd/com.phototestapp.portfolio-prices.plist"
echo "- tools/install_launchd.sh"
echo "- tools/uninstall_launchd.sh"
echo
if [[ "${AUTO_PUBLISH:-0}" == "1" ]]; then
  echo "AUTO_PUBLISH=1: skipping confirmation prompt."
else
  read -r -p "Continue? [y/N] " answer

  case "$answer" in
    y|Y)
      ;;
    *)
      echo "Cancelled."
      exit 0
      ;;
  esac
fi

git add data/prices_input.csv prices.json README.md index.html tools/generate_prices_json.py tools/publish_prices.sh tools/launchd/com.phototestapp.portfolio-prices.plist tools/install_launchd.sh tools/uninstall_launchd.sh

COMMIT_MESSAGE="Update prices.json $(TZ=Asia/Tokyo date "+%Y-%m-%d %H:%M JST")"
git commit -m "$COMMIT_MESSAGE"
git push
