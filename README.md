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
- `source`: `manual-csv` or `auto-mutual-fund`
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

Manual publish:

```bash
bash tools/publish_prices.sh
```

Default behavior:

```bash
bash tools/publish_prices.sh
```

By default, mutual fund fetch is skipped.

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
FETCH_MUTUAL_FUNDS=1 AUTO_PUBLISH=1 bash tools/publish_prices.sh
```

Daily launchd job:

The daily launchd job runs:

```bash
FETCH_MUTUAL_FUNDS=1 AUTO_PUBLISH=1 bash tools/publish_prices.sh
```

This fetches mutual fund prices before generating and publishing `prices.json`.

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
