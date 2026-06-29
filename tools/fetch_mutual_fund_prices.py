#!/usr/bin/env python3
"""Fetch six mutual fund prices and update data/prices_input.csv.

This script is intentionally manual-only. It is not called by publish_prices.sh
or launchd.
"""

from __future__ import annotations

import csv
import html
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "prices_input.csv"
GENERATE_SCRIPT = ROOT / "tools" / "generate_prices_json.py"
EXPECTED_COLUMNS = ["code", "name", "assetType", "price", "currency", "source", "priceDate", "memo"]
USER_AGENT = "Mozilla/5.0"
TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class FundTarget:
    code: str
    name: str
    primary_url: str
    fallback_url: str


@dataclass(frozen=True)
class FundPrice:
    price: int
    price_date: str
    previous_day_change: str | None = None
    net_assets: str | None = None


FUND_TARGETS = [
    FundTarget(
        code="03311187",
        name="eMAXIS Slim 米国株式（S&P500）",
        primary_url="https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/snp/snp_03311187.html",
        fallback_url="https://finance.yahoo.co.jp/quote/03311187",
    ),
    FundTarget(
        code="0331418A",
        name="eMAXIS Slim 全世界株式（オール・カントリー）",
        primary_url="https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/snp/snp_0331418A.html",
        fallback_url="https://finance.yahoo.co.jp/quote/0331418A",
    ),
    FundTarget(
        code="29313233",
        name="ニッセイNASDAQ100インデックスファンド",
        primary_url="https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/snp/snp_29313233.html",
        fallback_url="https://finance.yahoo.co.jp/quote/29313233",
    ),
    FundTarget(
        code="01313098",
        name="野村世界業種別投資シリーズ（世界半導体株投資）",
        primary_url="https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/snp/snp_01313098.html",
        fallback_url="https://finance.yahoo.co.jp/quote/01313098",
    ),
    FundTarget(
        code="4731299C",
        name="DLIBJ公社債オープン（中期コース）",
        primary_url="https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/snp/snp_4731299C.html",
        fallback_url="https://finance.yahoo.co.jp/quote/4731299C",
    ),
    FundTarget(
        code="AJ312217",
        name="Smart-i ゴールドファンド（為替ヘッジあり）",
        primary_url="https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/snp/snp_AJ312217.html",
        fallback_url="https://finance.yahoo.co.jp/quote/AJ312217",
    ),
]


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read()
        charset = response.headers.get_content_charset()
    if not charset:
        match = re.search(br"charset=['\"]?([A-Za-z0-9_-]+)", body[:2000], re.IGNORECASE)
        charset = match.group(1).decode("ascii", "replace") if match else "utf-8"
    return body.decode(charset, errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_price(value: str) -> int:
    text = strip_tags(value)
    match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)", text)
    if not match:
        raise ValueError("基準価額を数値として解析できません")
    return int(match.group(1).replace(",", ""))


def parse_date(value: str, today: date | None = None) -> str:
    today = today or date.today()
    text = strip_tags(value)

    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()

    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()

    match = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if match:
        inferred = date(today.year, int(match.group(1)), int(match.group(2)))
        if inferred > today:
            inferred = date(today.year - 1, inferred.month, inferred.day)
        return inferred.isoformat()

    raise ValueError("基準日を解析できません")


def parse_wealthadvisor(html_text: str) -> FundPrice:
    date_match = re.search(r"基準日\s*[:：]\s*([^<]+)", html_text)
    if not date_match:
        raise ValueError("WealthAdvisor: 基準日が見つかりません")

    table_match = re.search(
        r"<th>\s*基準価額\s*</th>\s*<th>\s*前日比\s*</th>\s*<th>\s*純資産\s*</th>\s*</tr>\s*<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        raise ValueError("WealthAdvisor: 基準価額テーブルが見つかりません")

    return FundPrice(
        price=parse_price(table_match.group(1)),
        price_date=parse_date(date_match.group(1)),
        previous_day_change=strip_tags(table_match.group(2)),
        net_assets=strip_tags(table_match.group(3)),
    )


def parse_yahoo_finance(html_text: str) -> FundPrice:
    price_match = re.search(
        r"PriceBoard__priceInfo.*?PriceBoard__price__[^>]*>.*?StyledNumber__value__[^>]*>\s*([0-9,]+)\s*</span>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not price_match:
        price_match = re.search(
            r"PriceBoard__priceBlock.*?StyledNumber__value__[^>]*>\s*([0-9,]+)\s*</span>",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not price_match:
        raise ValueError("Yahoo Finance: 基準価額が見つかりません")

    date_match = re.search(r"<time[^>]*>\s*([0-9]{1,2}/[0-9]{1,2})\s*</time>", html_text, flags=re.IGNORECASE)
    if not date_match:
        raise ValueError("Yahoo Finance: 基準日が見つかりません")

    return FundPrice(
        price=parse_price(price_match.group(1)),
        price_date=parse_date(date_match.group(1)),
    )


def fetch_fund_price(target: FundTarget) -> tuple[FundPrice | None, str | None]:
    print(f"{target.code} {target.name}")
    print("Primary: WealthAdvisor")
    try:
        price = parse_wealthadvisor(fetch_html(target.primary_url))
        print("Result: success")
        print(f"Price: {price.price}")
        print(f"PriceDate: {price.price_date}")
        print()
        return price, None
    except (OSError, urllib.error.URLError, ValueError) as exc:
        primary_reason = str(exc)
        print("Result: failed")
        print("Fallback: Yahoo Finance")

    try:
        price = parse_yahoo_finance(fetch_html(target.fallback_url))
        print("Result: success")
        print(f"Price: {price.price}")
        print(f"PriceDate: {price.price_date}")
        print()
        return price, None
    except (OSError, urllib.error.URLError, ValueError) as exc:
        reason = f"Primary failed: {primary_reason}; Fallback failed: {exc}"
        print("Result: failed")
        print("Fetch failed")
        print("Code:")
        print(target.code)
        print("Reason:")
        print(reason)
        print("Existing CSV value kept.")
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


def update_csv(successes: dict[str, FundPrice]) -> None:
    rows = load_csv_rows()
    target_codes = {target.code for target in FUND_TARGETS}
    csv_codes = {row["code"] for row in rows if row.get("assetType") == "mutualFund"}
    missing_codes = sorted(target_codes - csv_codes)
    if missing_codes:
        raise ValueError(f"CSV missing target mutual fund rows: {', '.join(missing_codes)}")

    for row in rows:
        code = row.get("code", "")
        if code not in successes:
            continue
        if row.get("assetType") != "mutualFund":
            raise ValueError(f"{code}: target row is not mutualFund")
        fetched = successes[code]
        row["price"] = str(fetched.price)
        row["source"] = "auto-mutual-fund"
        row["priceDate"] = fetched.price_date
        row["memo"] = "基準価額 自動取得"

    write_csv_rows(rows)


def generate_prices_json() -> None:
    subprocess.run([sys.executable, str(GENERATE_SCRIPT)], cwd=ROOT, check=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("Fetching mutual fund prices...")
    print()

    successes: dict[str, FundPrice] = {}
    failures: dict[str, str] = {}
    for target in FUND_TARGETS:
        fetched, reason = fetch_fund_price(target)
        if fetched:
            successes[target.code] = fetched
        else:
            failures[target.code] = reason or "unknown error"

    if not successes:
        print("All mutual fund fetches failed.")
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
