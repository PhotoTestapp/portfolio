# Portfolio Prices JSON

Portfolio App price JSON hosting files.

`prices.json` is generated from `data/prices_input.csv`.

CSV format:

```csv
code,name,assetType,price,currency,source,priceDate,memo
```

Rules:

- `assetType`: `mutualFund`, `japanStock`, or `crypto`
- `price`: numeric and greater than 0
- `currency`: `JPY`
- `source`: `manual-csv`, `auto-mutual-fund`, `auto-japan-stock`, or `auto-crypto`
- `priceDate`: `YYYY-MM-DD`
- `memo`: optional

Generate:

```bash
python3 tools/generate_prices_json.py
```

Fetch mutual fund prices manually:

```bash
python3 tools/fetch_mutual_fund_prices.py
```

This updates only `mutualFund` rows in `data/prices_input.csv`.

Primary source:

```text
WealthAdvisor Yahoo fund snapshot
```

Fallback:

```text
Yahoo! Finance quote page
```

Successful rows use:

```text
source=auto-mutual-fund
memo=基準価額 自動取得
```

If a fund fetch fails, the existing CSV value is kept.

Fetch Japan stock prices manually:

```bash
python3 tools/fetch_japan_stock_prices.py
```

This updates only `japanStock` rows in `data/prices_input.csv`.

Source:

```text
Yahoo! Finance Japan quote pages
```

Successful rows use:

```text
source=auto-japan-stock
memo=株価 自動取得
```

If a stock fetch fails, the existing CSV value is kept.

Fetch crypto prices manually:

```bash
python3 tools/fetch_crypto_prices.py
```

This updates only `crypto` rows in `data/prices_input.csv`.

Source:

```text
CoinGecko Simple Price API
```

Successful rows use:

```text
source=auto-crypto
memo=JPY価格 自動取得
```

If a crypto fetch fails, the existing CSV value is kept.

Manual publish:

```bash
bash tools/publish_prices.sh
```

Publish with optional price fetch:

Mutual funds:

```bash
FETCH_MUTUAL_FUNDS=1 bash tools/publish_prices.sh
```

Japan stocks:

```bash
FETCH_JAPAN_STOCKS=1 bash tools/publish_prices.sh
```

Crypto:

```bash
FETCH_CRYPTO=1 bash tools/publish_prices.sh
```

All supported prices:

```bash
FETCH_MUTUAL_FUNDS=1 FETCH_JAPAN_STOCKS=1 FETCH_CRYPTO=1 bash tools/publish_prices.sh
```

All supported prices without confirmation:

```bash
FETCH_MUTUAL_FUNDS=1 FETCH_JAPAN_STOCKS=1 FETCH_CRYPTO=1 AUTO_PUBLISH=1 bash tools/publish_prices.sh
```

Default behavior:

```bash
bash tools/publish_prices.sh
```

By default, all fetch steps are skipped.

Publish with mutual fund auto fetch:

```bash
FETCH_MUTUAL_FUNDS=1 bash tools/publish_prices.sh
```

Auto publish without confirmation:

```bash
FETCH_MUTUAL_FUNDS=1 AUTO_PUBLISH=1 bash tools/publish_prices.sh
```

Auto publish on Mac mini:

```bash
bash tools/install_launchd.sh
```

This installs `com.phototestapp.portfolio-prices` to `~/Library/LaunchAgents` and runs:

```bash
FETCH_MUTUAL_FUNDS=1 FETCH_JAPAN_STOCKS=1 FETCH_CRYPTO=1 AUTO_PUBLISH=1 bash tools/publish_prices.sh
```

Daily launchd job:

The daily launchd job runs:

```bash
FETCH_MUTUAL_FUNDS=1 FETCH_JAPAN_STOCKS=1 FETCH_CRYPTO=1 AUTO_PUBLISH=1 bash tools/publish_prices.sh
```

This fetches:

- mutual fund prices
- Japan stock prices
- crypto JPY prices

Then it generates `prices.json` and publishes it to GitHub Pages.

Schedule:

```text
Every day at 09:05 JST
```

Logs:

```text
~/Library/Logs/portfolio-prices.out.log
~/Library/Logs/portfolio-prices.err.log
```

Uninstall:

```bash
bash tools/uninstall_launchd.sh
```

GitHub Pages URL:

```text
https://phototestapp.github.io/portfolio/prices.json
```
