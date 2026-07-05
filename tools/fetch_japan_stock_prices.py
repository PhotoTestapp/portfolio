#!/usr/bin/env python3
"""Fetch four Japan stock prices and update data/prices_input.csv.

This script is manual-only. It is not called by publish_prices.sh or launchd.
"""

from __future__ import annotations

import csv
import html
import math
import re
import subprocess
import sys
import tempfile
import urllib.error
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
class StockTarget:
    code: str
    name: str
    url: str


@dataclass(frozen=True)
class StockPrice:
    price: int | float
    price_date: str
    date_from_page: bool
    previous_day_change: str | None = None
    price_time: str | None = None


STOCK_TARGETS = [
    StockTarget(code="9432", name="NTT", url="https://finance.yahoo.co.jp/quote/9432.T"),
    StockTarget(code="8410", name="セブン銀行", url="https://finance.yahoo.co.jp/quote/8410.T"),
    StockTarget(code="6857", name="アドバンテスト", url="https://finance.yahoo.co.jp/quote/6857.T"),
    StockTarget(code="7741", name="HOYA", url="https://finance.yahoo.co.jp/quote/7741.T"),
]


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_price(value: str) -> int | float:
    text = strip_tags(value)
    match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        raise ValueError("株価を数値として解析できません")
    price = float(match.group(1).replace(",", ""))
    return int(price) if price.is_integer() else price


def valid_price(value: int | float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0


def format_price(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.10f}".rstrip("0").rstrip(".")


def parse_date(value: str, today: date | None = None) -> str:
    today = today or date.today()
    text = strip_tags(value)

    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()

    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()

    match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text)
    if match:
        inferred = date(today.year, int(match.group(1)), int(match.group(2)))
        if inferred > today:
            inferred = date(today.year - 1, inferred.month, inferred.day)
        return inferred.isoformat()

    raise ValueError("日付を解析できません")


def extract_price_board(html_text: str) -> str:
    match = re.search(
        r'<div class="[^"]*BasePriceBoard__priceInfo[^"]*">(.*?)(?:<ul class="[^"]*PriceBoardNav|<section class="[^"]*Chart)',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1)

    start = html_text.find("BasePriceBoard__priceInfo")
    if start == -1:
        start = html_text.find("CommonPriceBoard__price")
    if start == -1:
        raise ValueError("Yahoo Finance: 株価ボードが見つかりません")
    return html_text[start : start + 8000]


def parse_yahoo_finance(html_text: str) -> StockPrice:
    board = extract_price_board(html_text)
    price_match = re.search(
        r"CommonPriceBoard__price[^>]*>.*?StyledNumber__value[^>]*>\s*([0-9,]+(?:\.[0-9]+)?)\s*</span>",
        board,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not price_match:
        price_match = re.search(
            r"StyledNumber--vertical[^>]*>.*?StyledNumber__value[^>]*>\s*([0-9,]+(?:\.[0-9]+)?)\s*</span>",
            board,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not price_match:
        raise ValueError("Yahoo Finance: 株価が見つかりません")

    previous_day_change = None
    change_match = re.search(
        r"<dt[^>]*>\s*前日比\s*</dt>.*?<dd[^>]*>(.*?)</dd>",
        board,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if change_match:
        previous_day_change = strip_tags(change_match.group(1))

    price_time = None
    time_match = re.search(r"<time[^>]*>\s*([^<]+)\s*</time>", board, flags=re.IGNORECASE)
    if time_match:
        price_time = strip_tags(time_match.group(1))

    date_patterns = [
        r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日",
        r"\d{4}[/-]\d{1,2}[/-]\d{1,2}",
        r"(?<!\d)\d{1,2}/\d{1,2}(?!\d)",
    ]
    price = parse_price(price_match.group(1))
    if not valid_price(price):
        raise ValueError("invalid price <= 0")

    for pattern in date_patterns:
        date_match = re.search(pattern, board)
        if date_match:
            return StockPrice(
                price=price,
                price_date=parse_date(date_match.group(0)),
                date_from_page=True,
                previous_day_change=previous_day_change,
                price_time=price_time,
            )

    return StockPrice(
        price=price,
        price_date=date.today().isoformat(),
        date_from_page=False,
        previous_day_change=previous_day_change,
        price_time=price_time,
    )


def fetch_stock_price(target: StockTarget) -> tuple[StockPrice | None, str | None]:
    print(f"{target.code} {target.name}")
    print("Source: Yahoo Finance")
    try:
        price = parse_yahoo_finance(fetch_html(target.url))
        print("Result: success")
        print(f"Price: {format_price(price.price)}")
        print(f"PriceDate: {price.price_date}")
        if not price.date_from_page:
            print("Price date not found. Using today.")
        print("Market calendar check is not implemented. Using displayed/latest available price.")
        print()
        return price, None
    except (OSError, urllib.error.URLError, ValueError) as exc:
        reason = str(exc)
        print("Result: failed")
        print(f"Reason: {reason}")
        print()
        return None, reason


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


def csv_price(row: dict[str, str]) -> float | None:
    try:
        value = float(row.get("price", ""))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def log_failure_actions(failures: dict[str, str], existing_rows: dict[str, dict[str, str]]) -> None:
    for target in STOCK_TARGETS:
        reason = failures.get(target.code)
        if reason is None:
            continue

        print(f"{target.code} {target.name}")
        if target.code in existing_rows:
            existing_price = existing_rows[target.code].get("price", "")
            print("Action: kept existing row")
            print(f"Existing price: {existing_price}")
        else:
            print("Action: skipped")
        print()


def update_csv(successes: dict[str, StockPrice]) -> None:
    rows = load_csv_rows()
    targets_by_code = {target.code: target for target in STOCK_TARGETS}
    existing_target_codes = {
        row["code"]
        for row in rows
        if row.get("assetType") == "japanStock" and row.get("code") in targets_by_code
    }

    for row in rows:
        code = row.get("code", "")
        if code not in successes:
            continue
        if row.get("assetType") != "japanStock":
            raise ValueError(f"{code}: target row is not japanStock")
        fetched = successes[code]
        if not valid_price(fetched.price):
            raise ValueError(f"{code}: invalid fetched price before CSV write")
        row["price"] = format_price(fetched.price)
        row["source"] = "auto-japan-stock"
        row["priceDate"] = fetched.price_date
        row["memo"] = "株価 自動取得"

    for code, fetched in successes.items():
        if code in existing_target_codes:
            continue
        if not valid_price(fetched.price):
            raise ValueError(f"{code}: invalid fetched price before CSV append")
        target = targets_by_code[code]
        rows.append(
            {
                "code": target.code,
                "name": target.name,
                "assetType": "japanStock",
                "price": format_price(fetched.price),
                "currency": "JPY",
                "source": "auto-japan-stock",
                "priceDate": fetched.price_date,
                "memo": "株価 自動取得",
            }
        )

    for row in rows:
        if row.get("assetType") == "japanStock" and row.get("code") in targets_by_code:
            price = csv_price(row)
            if price is None or price <= 0:
                raise ValueError(f"{row.get('code', '')}: invalid Japan stock price in CSV")

    write_csv_rows(rows)


def generate_prices_json() -> None:
    subprocess.run([sys.executable, str(GENERATE_SCRIPT)], cwd=ROOT, check=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("Fetching Japan stock prices...")
    print()

    existing_rows = {
        row.get("code", ""): row
        for row in load_csv_rows()
        if row.get("assetType") == "japanStock"
    }
    successes: dict[str, StockPrice] = {}
    failures: dict[str, str] = {}
    for target in STOCK_TARGETS:
        fetched, reason = fetch_stock_price(target)
        if fetched:
            successes[target.code] = fetched
        else:
            failures[target.code] = reason or "unknown error"
    log_failure_actions(failures, existing_rows)

    if not successes:
        print("All Japan stock fetches failed.")
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
