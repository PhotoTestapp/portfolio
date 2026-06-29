#!/usr/bin/env python3
"""Fetch US stock prices from data/price_universe.csv and update prices_input.csv.

This script is manual-only. It is not called by publish_prices.sh or launchd.
"""

from __future__ import annotations

import csv
import gzip
import html
import math
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "prices_input.csv"
UNIVERSE_PATH = ROOT / "data" / "price_universe.csv"
GENERATE_SCRIPT = ROOT / "tools" / "generate_prices_json.py"
EXPECTED_COLUMNS = ["code", "name", "assetType", "price", "currency", "source", "priceDate", "memo"]
UNIVERSE_COLUMNS = ["code", "name", "assetType", "currency", "fetchEnabled", "sourceHint", "notes"]
USER_AGENT = "Mozilla/5.0"
TIMEOUT_SECONDS = 15
REQUEST_SLEEP_SECONDS = 0.6


@dataclass(frozen=True)
class StockTarget:
    code: str
    name: str
    url: str


@dataclass(frozen=True)
class StockPrice:
    price: int | float
    price_date: str
    date_from_page: bool


def yahoo_symbol(code: str) -> str:
    return code.replace(".", "-")


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    if body.startswith(b"\x1f\x8b"):
        body = gzip.decompress(body)
    return body.decode(charset, errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_price(value: str) -> int | float:
    text = strip_tags(value)
    match = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        raise ValueError("Stock price could not be parsed")
    price = float(match.group(1).replace(",", ""))
    if not math.isfinite(price):
        raise ValueError("Stock price must be finite")
    if price <= 0:
        raise ValueError("Stock price must be greater than 0")
    return int(price) if price.is_integer() else price


def format_price(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.10f}".rstrip("0").rstrip(".")


def parse_yahoo_finance(html_text: str) -> StockPrice:
    price_patterns = [
        r'data-testid="qsp-price"[^>]*>(.*?)<',
        r'data-symbol="[^"]+"[^>]*data-field="regularMarketPrice"[^>]*data-value="([0-9,]+(?:\.[0-9]+)?)"',
        r'"regularMarketPrice"\s*:\s*\{\s*"raw"\s*:\s*([0-9,]+(?:\.[0-9]+)?)',
    ]
    for pattern in price_patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return StockPrice(
                price=parse_price(match.group(1)),
                price_date=date.today().isoformat(),
                date_from_page=False,
            )
    raise ValueError("Yahoo Finance: stock price was not found")


def fetch_stock_price(target: StockTarget) -> tuple[StockPrice | None, str | None]:
    print(f"{target.code} {target.name}")
    print("Source: Yahoo Finance")
    try:
        price = parse_yahoo_finance(fetch_html(target.url))
        print("Result: success")
        print(f"Price: {format_price(price.price)}")
        print("Currency: USD")
        print(f"PriceDate: {price.price_date}")
        if not price.date_from_page:
            print("Price date not found. Using today.")
        print()
        return price, None
    except (OSError, urllib.error.URLError, ValueError) as exc:
        reason = str(exc)
        print("Result: failed")
        print("Fetch failed")
        print("Code:")
        print(target.code)
        print("Reason:")
        print(reason)
        print()
        return None, reason


def load_targets_from_universe() -> list[StockTarget]:
    if not UNIVERSE_PATH.exists():
        raise FileNotFoundError(f"{UNIVERSE_PATH} not found")
    targets: list[StockTarget] = []
    with UNIVERSE_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != UNIVERSE_COLUMNS:
            raise ValueError(f"price_universe.csv header must be: {','.join(UNIVERSE_COLUMNS)}")
        for line_number, row in enumerate(reader, start=2):
            if row.get("assetType") != "usStock":
                continue
            if (row.get("fetchEnabled") or "").strip().lower() != "true":
                continue
            if row.get("sourceHint") != "yahoo-us":
                continue
            code = (row.get("code") or "").strip()
            name = (row.get("name") or "").strip()
            if not code or not name:
                print(f"Skipping universe line {line_number}: code or name is empty")
                continue
            symbol = urllib.parse.quote(yahoo_symbol(code), safe="")
            targets.append(StockTarget(
                code=code,
                name=name,
                url=f"https://finance.yahoo.com/quote/{symbol}",
            ))
    return targets


def load_csv_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"CSV header must be: {','.join(EXPECTED_COLUMNS)}")
        return list(reader)


def write_csv_rows(rows: list[dict[str, str]]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=CSV_PATH.parent) as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temp_path = Path(handle.name)
    temp_path.replace(CSV_PATH)


def update_csv(successes: dict[str, StockPrice], targets_by_code: dict[str, StockTarget]) -> tuple[int, int]:
    rows = load_csv_rows()
    rows_by_code = {row.get("code", ""): row for row in rows}
    updated = 0
    added = 0

    for code, fetched in successes.items():
        row = rows_by_code.get(code)
        if row is None:
            target = targets_by_code[code]
            rows.append({
                "code": target.code,
                "name": target.name,
                "assetType": "usStock",
                "price": format_price(fetched.price),
                "currency": "USD",
                "source": "auto-us-stock",
                "priceDate": fetched.price_date,
                "memo": "株価 自動取得",
            })
            added += 1
            continue
        if row.get("assetType") != "usStock":
            raise ValueError(f"{code}: target row is not usStock")
        row["price"] = format_price(fetched.price)
        row["currency"] = "USD"
        row["source"] = "auto-us-stock"
        row["priceDate"] = fetched.price_date
        row["memo"] = "株価 自動取得"
        updated += 1

    write_csv_rows(rows)
    return updated, added


def generate_prices_json() -> None:
    subprocess.run([sys.executable, str(GENERATE_SCRIPT)], cwd=ROOT, check=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("Fetching US stock prices from price_universe.csv...")
    print()
    print("Universe:")
    print(UNIVERSE_PATH.relative_to(ROOT))
    print()

    targets = load_targets_from_universe()
    targets_by_code = {target.code: target for target in targets}
    existing_codes = {row["code"] for row in load_csv_rows()}

    print("Target:")
    print(len(targets))
    print()

    successes: dict[str, StockPrice] = {}
    failures: dict[str, str] = {}
    kept_existing = 0
    for index, target in enumerate(targets):
        fetched, reason = fetch_stock_price(target)
        if fetched:
            successes[target.code] = fetched
            action = "updated existing row" if target.code in existing_codes else "added new row"
            print(f"Action: {action}")
            print()
        else:
            failures[target.code] = reason or "unknown error"
            if target.code in existing_codes:
                kept_existing += 1
                print("Existing CSV value kept.")
                print("Action: kept existing row")
            else:
                print("Action: skipped")
            print()
        if index < len(targets) - 1:
            time.sleep(REQUEST_SLEEP_SECONDS)

    if not successes:
        print("All US stock fetches failed.")
        return 1

    updated, added = update_csv(successes, targets_by_code)
    print("CSV updated:")
    print(CSV_PATH.relative_to(ROOT))
    print()

    generate_prices_json()
    print()
    print("Success:")
    print(len(successes))
    print()
    print("Failed:")
    print(len(failures))
    print()
    print("Added:")
    print(added)
    print()
    print("Updated:")
    print(updated)
    print()
    print("Kept existing:")
    print(kept_existing)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
