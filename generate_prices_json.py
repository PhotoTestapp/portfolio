#!/usr/bin/env python3
"""Generate prices.json for Portfolio App from data/prices_input.csv.

Local check:

    python3 -m http.server 8000

Portfolio App URL:

    http://localhost:8000/prices.json

For an iPhone device, use the Mac's LAN IP address:

    http://192.168.x.x:8000/prices.json
"""

from __future__ import annotations

import json
import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


INPUT_PATH = Path("data/prices_input.csv")
OUTPUT_PATH = Path("prices.json")
EXPECTED_COLUMNS = ["code", "name", "assetType", "price", "currency", "source"]
ALLOWED_ASSET_TYPES = {"mutualFund", "japanStock", "crypto"}
EXPECTED_COUNTS = {"mutualFund": 6, "japanStock": 4, "crypto": 5}


def current_tokyo_timestamp() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).replace(microsecond=0).isoformat()


def normalize_code(value: str) -> str:
    half_width = value.strip().translate(str.maketrans({
        "　": " ",
    }))
    half_width = half_width.encode("utf-8").decode("utf-8")
    import unicodedata

    normalized = unicodedata.normalize("NFKC", half_width)
    return "".join(normalized.split()).upper()


def parse_price(value: str, line_number: int):
    try:
        price = float(value)
    except ValueError as exc:
        raise ValueError(f"line {line_number}: price must be numeric") from exc
    if price <= 0:
        raise ValueError(f"line {line_number}: price must be greater than 0")
    return int(price) if price.is_integer() else price


def load_price_rows() -> list[dict]:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"{INPUT_PATH} not found")

    rows: list[dict] = []
    seen_raw_codes: set[str] = set()
    seen_normalized_codes: set[str] = set()
    with INPUT_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"CSV header must be: {','.join(EXPECTED_COLUMNS)}")
        for line_number, row in enumerate(reader, start=2):
            raw_code = (row.get("code") or "").strip()
            normalized_code = normalize_code(raw_code)
            name = (row.get("name") or "").strip()
            asset_type = (row.get("assetType") or "").strip()
            currency = (row.get("currency") or "").strip()
            source = (row.get("source") or "").strip()

            if not raw_code:
                raise ValueError(f"line {line_number}: code is required")
            if not normalized_code:
                raise ValueError(f"line {line_number}: normalized code is empty")
            if not name:
                raise ValueError(f"line {line_number}: name is required")
            if asset_type not in ALLOWED_ASSET_TYPES:
                raise ValueError(f"line {line_number}: assetType must be mutualFund / japanStock / crypto")
            if currency != "JPY":
                raise ValueError(f"line {line_number}: currency must be JPY")
            if not source:
                raise ValueError(f"line {line_number}: source is required")
            if raw_code in seen_raw_codes:
                raise ValueError(f"line {line_number}: duplicate code {raw_code}")
            if normalized_code in seen_normalized_codes:
                raise ValueError(f"line {line_number}: duplicate normalized code {normalized_code}")

            seen_raw_codes.add(raw_code)
            seen_normalized_codes.add(normalized_code)
            rows.append({
                "code": normalized_code,
                "name": name,
                "assetType": asset_type,
                "price": parse_price(row.get("price") or "", line_number),
                "currency": currency,
                "source": source,
            })
    return rows


def build_payload(rows: list[dict]) -> dict:
    prices = {
        row["code"]: {
            "name": row["name"],
            "price": row["price"],
            "currency": row["currency"],
            "source": row["source"],
        }
        for row in rows
    }
    return {
        "asOf": current_tokyo_timestamp(),
        "prices": prices,
    }


def validate_payload(payload: dict, rows: list[dict]) -> dict[str, int]:
    if not payload.get("asOf"):
        raise ValueError("asOf is required")
    prices = payload.get("prices")
    if not isinstance(prices, dict):
        raise ValueError("prices must be a dict")
    for code, item in prices.items():
        if not item.get("name"):
            raise ValueError(f"{code}: name is required")
        price = item.get("price")
        if not isinstance(price, (int, float)):
            raise ValueError(f"{code}: price must be numeric")
        if price <= 0:
            raise ValueError(f"{code}: price must be greater than 0")
        if item.get("currency") != "JPY":
            raise ValueError(f"{code}: currency must be JPY")
        if not item.get("source"):
            raise ValueError(f"{code}: source is required")
    counts = {asset_type: 0 for asset_type in EXPECTED_COUNTS}
    for row in rows:
        counts[row["assetType"]] += 1
    if len(rows) != 15:
        print(f"Warning: expected total 15 records, got {len(rows)}")
    for asset_type, expected in EXPECTED_COUNTS.items():
        if counts[asset_type] != expected:
            print(f"Warning: expected {asset_type} {expected} records, got {counts[asset_type]}")
    return counts


def main() -> None:
    rows = load_price_rows()
    payload = build_payload(rows)
    counts = validate_payload(payload, rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("prices.json generated")
    print()
    print("Input:")
    print(INPUT_PATH)
    print()
    print("Output:")
    print(OUTPUT_PATH)
    print()
    print("asOf:")
    print(payload["asOf"])
    print()
    print("Total:")
    print(len(payload["prices"]))
    print()
    print("mutualFund:")
    print(counts["mutualFund"])
    print()
    print("japanStock:")
    print(counts["japanStock"])
    print()
    print("crypto:")
    print(counts["crypto"])


if __name__ == "__main__":
    main()
