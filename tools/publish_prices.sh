#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "Error: not inside a git repository."
  exit 1
fi

cd "$ROOT"

FILES=(
  data/prices_input.csv
  prices.json
  README.md
  index.html
  tools/generate_prices_json.py
  tools/fetch_mutual_fund_prices.py
  tools/fetch_japan_stock_prices.py
  tools/fetch_us_stock_prices.py
  tools/fetch_crypto_prices.py
  tools/publish_prices.sh
  tools/launchd/com.phototestapp.portfolio-prices.plist
  tools/install_launchd.sh
  tools/uninstall_launchd.sh
)

if [[ "${FETCH_MUTUAL_FUNDS:-0}" == "1" ]]; then
  echo "FETCH_MUTUAL_FUNDS=1: fetching mutual fund prices before generating prices.json"
  python3 tools/fetch_mutual_fund_prices.py
else
  echo "FETCH_MUTUAL_FUNDS is not enabled. Skipping mutual fund fetch."
fi

if [[ "${FETCH_JAPAN_STOCKS:-0}" == "1" ]]; then
  echo "FETCH_JAPAN_STOCKS=1: fetching Japan stock prices before generating prices.json"
  python3 tools/fetch_japan_stock_prices.py
else
  echo "FETCH_JAPAN_STOCKS is not enabled. Skipping Japan stock fetch."
fi

if [[ "${FETCH_US_STOCKS:-0}" == "1" ]]; then
  echo "FETCH_US_STOCKS=1: fetching US stock prices before generating prices.json"
  python3 tools/fetch_us_stock_prices.py
else
  echo "FETCH_US_STOCKS is not enabled. Skipping US stock fetch."
fi

if [[ "${FETCH_CRYPTO:-0}" == "1" ]]; then
  echo "FETCH_CRYPTO=1: fetching crypto prices before generating prices.json"
  python3 tools/fetch_crypto_prices.py
else
  echo "FETCH_CRYPTO is not enabled. Skipping crypto fetch."
fi

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
git diff -- "${FILES[@]}"

STATUS_OUTPUT="$(git status --short -- "${FILES[@]}")"
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
echo "- tools/fetch_mutual_fund_prices.py"
echo "- tools/fetch_japan_stock_prices.py"
echo "- tools/fetch_us_stock_prices.py"
echo "- tools/fetch_crypto_prices.py"
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

for file in "${FILES[@]}"; do
  if [[ -e "$file" ]]; then
    git add "$file"
  fi
done

COMMIT_MESSAGE="Update prices.json $(TZ=Asia/Tokyo date "+%Y-%m-%d %H:%M JST")"
git commit -m "$COMMIT_MESSAGE"
git push
