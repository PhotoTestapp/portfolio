#!/usr/bin/env python3
"""Fetch five crypto JPY prices and update data/prices_input.csv.

This script is manual-only. It is not called by publish_prices.sh or launchd.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "prices_input.csv"
GENERATE_SCRIPT = ROOT / "tools" / "generate_prices_json.py"
EXPECTED_COLUMNS = ["code", "name", "assetType", "price", "currency", "source", "priceDate", "memo"]
USER_AGENT = "Mozilla/5.0"
TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class CryptoTarget:
    code: str
    name: str
    coingecko_id: str


@dataclass(frozen=True)
class CryptoPrice:
    price: int | float
    price_date: str


CRYPTO_TARGETS = [
    CryptoTarget(code="BTC", name="Bitcoin", coingecko_id="bitcoin"),
    CryptoTarget(code="ETH", name="Ethereum", coingecko_id="ethereum"),
    CryptoTarget(code="XRP", name="XRP", coingecko_id="ripple"),
    CryptoTarget(code="SOL", name="Solana", coingecko_id="solana"),
    CryptoTarget(code="DOGE", name="Dogecoin", coingecko_id="dogecoin"),
]


def format_price(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.10f}".rstrip("0").rstrip(".")


def parse_price(value: object, code: str) -> int | float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{code}: jpy is not numeric")
    price = float(value)
    if not math.isfinite(price):
        raise ValueError(f"{code}: jpy must be finite")
    if price <= 0:
        raise ValueError(f"{code}: jpy must be greater than 0")
    return int(price) if price.is_integer() else price


def build_url() -> str:
    ids = ",".join(target.coingecko_id for target in CRYPTO_TARGETS)
    query = urllib.parse.urlencode({
        "ids": ids,
        "vs_currencies": "jpy",
    })
    return f"https://api.coingecko.com/api/v3/simple/price?{query}"


def fetch_prices() -> dict:
    request = urllib.request.Request(build_url(), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


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


def update_csv(successes: dict[str, CryptoPrice]) -> None:
    rows = load_csv_rows()
    target_codes = {target.code for target in CRYPTO_TARGETS}
    csv_codes = {row["code"] for row in rows if row.get("assetType") == "crypto"}
    missing_codes = sorted(target_codes - csv_codes)
    if missing_codes:
        raise ValueError(f"CSV missing target crypto rows: {', '.join(missing_codes)}")

    for row in rows:
        code = row.get("code", "")
        if code not in successes:
            continue
        if row.get("assetType") != "crypto":
            raise ValueError(f"{code}: target row is not crypto")
        fetched = successes[code]
        row["price"] = format_price(fetched.price)
        row["source"] = "auto-crypto"
        row["priceDate"] = fetched.price_date
        row["memo"] = "JPY価格 自動取得"

    write_csv_rows(rows)


def generate_prices_json() -> None:
    subprocess.run([sys.executable, str(GENERATE_SCRIPT)], cwd=ROOT, check=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("Fetching crypto prices...")
    print()
    print("Source:")
    print("CoinGecko Simple Price API")
    print()

    price_date = date.today().isoformat()
    print("Price date is set to fetch date because API does not provide official priceDate.")
    print()

    try:
        payload = fetch_prices()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        payload = {}
        fetch_error = str(exc)
    else:
        fetch_error = None

    successes: dict[str, CryptoPrice] = {}
    failures: dict[str, str] = {}
    for target in CRYPTO_TARGETS:
        print(f"{target.code} {target.name}")
        try:
            if fetch_error:
                raise ValueError(fetch_error)
            item = payload.get(target.coingecko_id)
            if not isinstance(item, dict):
                raise ValueError(f"{target.coingecko_id}: response item is missing")
            if "jpy" not in item:
                raise ValueError(f"{target.coingecko_id}: jpy is missing")
            price = parse_price(item["jpy"], target.code)
        except ValueError as exc:
            reason = str(exc)
            failures[target.code] = reason
            print("Result: failed")
            print("Fetch failed")
            print("Code:")
            print(target.code)
            print("Reason:")
            print(reason)
            print("Existing CSV value kept.")
            print()
            continue

        successes[target.code] = CryptoPrice(price=price, price_date=price_date)
        print("Result: success")
        print(f"Price: {format_price(price)}")
        print(f"PriceDate: {price_date}")
        print()

    if not successes:
        print("All crypto fetches failed.")
        return 1

    update_csv(successes)
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
