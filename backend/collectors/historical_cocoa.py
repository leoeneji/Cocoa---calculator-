"""Backfill the official ICCO daily cocoa-price table into PostgreSQL.

The current ICCO statistics page serves its daily table through wpDataTables:
POST /wp-admin/admin-ajax.php?action=get_wdtable&table_id=26
The request requires a dynamic wdtNonce obtained from the statistics page.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

ICCO_STATS_URL = "https://www.icco.org/statistics/"
ICCO_AJAX_URL = "https://www.icco.org/wp-admin/admin-ajax.php"
ICCO_TABLE_ID = "26"
ICCO_SOURCE_ID = "fca90836-0945-4cd2-94f0-f11aa7b5012d"
PAGE_SIZE = 100
REQUEST_TIMEOUT = 45
MAX_PAGES = 20
LAGOS_TZ = ZoneInfo("Africa/Lagos")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
    ),
    "Accept-Language": "en-NG,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set. Load the project .env first.")
    return value


def parse_price(value: Any) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(Decimal(str(value).replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: Any):
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def timestamp_for(date_value):
    return datetime.combine(date_value, time(1, 0), tzinfo=LAGOS_TZ)


def fetch_statistics_page() -> str:
    print("FETCHING ICCO STATISTICS PAGE...")
    response = SESSION.get(ICCO_STATS_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    print(f"PAGE STATUS: {response.status_code}")
    print(f"PAGE BYTES: {len(response.content)}")
    return response.text


def find_table_id(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        headers = " ".join(
            cell.get_text(" ", strip=True).lower()
            for cell in table.find_all("th")
        )
        if all(x in headers for x in ("date", "london futures", "new york futures", "icco daily price")):
            value = table.get("data-wpdatatable_id")
            if value:
                return str(value)
            for cls in table.get("class", []):
                match = re.search(r"wpDataTableID-(\d+)", str(cls))
                if match:
                    return match.group(1)
            return ICCO_TABLE_ID
    # Browser inspection established the current official daily table as ID 26.
    return ICCO_TABLE_ID


def extract_nonce(html: str, table_id: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    expected = f"wdtNonceFrontendServerSide_{table_id}"

    node = soup.find("input", attrs={"name": expected})
    if node and node.get("value"):
        return str(node["value"]).strip()

    for node in soup.find_all("input"):
        name = str(node.get("name", ""))
        value = str(node.get("value", "")).strip()
        if "wdtNonce" in name and value:
            return value

    patterns = [
        rf'{re.escape(expected)}[^A-Za-z0-9]+([A-Za-z0-9]+)',
        r'wdtNonce[^A-Za-z0-9]+([A-Za-z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return match.group(1)

    raise RuntimeError(f"Could not find dynamic ICCO nonce for table {table_id}.")


def request_data(nonce: str, start: int, length: int, draw: int) -> dict[str, Any]:
    columns = [
        "wdt_ID", "date", "prueba", "newyorkfuturesustonne",
        "iccodailypriceustonne", "iccodailypriceeurotonne",
    ]
    data: dict[str, Any] = {
        "draw": draw,
        "order[0][column]": "1",
        "order[0][dir]": "desc",
        "start": start,
        "length": length,
        "search[value]": "",
        "search[regex]": "false",
        "wdtNonce": nonce,
    }
    for i, name in enumerate(columns):
        data[f"columns[{i}][data]"] = str(i)
        data[f"columns[{i}][name]"] = name
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true"
        data[f"columns[{i}][search][value]"] = ""
        data[f"columns[{i}][search][regex]"] = "false"
    return data


def fetch_ajax_page(table_id: str, nonce: str, start: int, length: int, draw: int) -> dict[str, Any]:
    url = f"{ICCO_AJAX_URL}?action=get_wdtable&table_id={table_id}"
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.icco.org",
        "Referer": ICCO_STATS_URL,
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": HEADERS["User-Agent"],
    }
    print(f"AJAX START: {start}")
    print(f"AJAX LENGTH: {length}")
    response = SESSION.post(
        url, headers=headers,
        data=request_data(nonce, start, length, draw),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"AJAX STATUS: {response.status_code}")
    if response.status_code != 200:
        print(response.text[:4000])
        response.raise_for_status()
    text = response.text.lstrip("\ufeff").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        print("AJAX NON-JSON RESPONSE:")
        print(text[:5000])
        raise RuntimeError("ICCO AJAX response was not valid JSON") from exc
    if not isinstance(payload, dict) or "data" not in payload:
        raise RuntimeError(f"Unexpected ICCO AJAX payload: {payload}")
    return payload


def parse_ajax_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("data") or []:
        if isinstance(item, dict):
            values = [
                item.get("wdt_ID"), item.get("date"), item.get("prueba"),
                item.get("newyorkfuturesustonne"), item.get("iccodailypriceustonne"),
                item.get("iccodailypriceeurotonne"),
            ]
        elif isinstance(item, (list, tuple)):
            values = list(item)
        else:
            continue
        if len(values) < 6:
            continue
        date_value = parse_date(values[1])
        if date_value is None:
            continue
        row = {
            "wdt_id": values[0],
            "date": date_value,
            "london_futures": parse_price(values[2]),
            "new_york_futures": parse_price(values[3]),
            "icco_daily_usd": parse_price(values[4]),
            "icco_daily_eur": parse_price(values[5]),
        }
        if any(row[k] is not None for k in ("london_futures", "new_york_futures", "icco_daily_usd", "icco_daily_eur")):
            rows.append(row)
    return rows


def collect_all_rows(html: str) -> list[dict[str, Any]]:
    table_id = find_table_id(html)
    print(f"ICCO TABLE ID: {table_id}")
    if table_id != ICCO_TABLE_ID:
        print(f"WARNING: current page exposed table {table_id}; expected {ICCO_TABLE_ID}")

    nonce = extract_nonce(html, table_id)
    print(f"ICCO NONCE FOUND: {nonce}")

    first = fetch_ajax_page(table_id, nonce, 0, PAGE_SIZE, 1)
    total = int(first.get("recordsFiltered") or first.get("recordsTotal") or 0)
    rows = parse_ajax_rows(first)
    print(f"RECORDS REPORTED BY ICCO: {total}")
    print(f"ROWS RECEIVED: {len(rows)}")

    start, draw = len(rows), 2
    while start < total and draw <= MAX_PAGES + 1:
        page = parse_ajax_rows(fetch_ajax_page(table_id, nonce, start, PAGE_SIZE, draw))
        if not page:
            break
        rows.extend(page)
        start += len(page)
        draw += 1
        print(f"TOTAL COLLECTED: {len(rows)} / {total}")

    unique = {row["date"]: row for row in rows}
    result = sorted(unique.values(), key=lambda r: r["date"])
    if total and len(result) < total:
        print(f"WARNING: ICCO reported {total}, collected {len(result)} unique dates")
    return result


def save_prices(rows: list[dict[str, Any]]) -> int:
    records = []
    for row in rows:
        ts = timestamp_for(row["date"])
        for contract, price, currency in (
            ("LONDON-FUTURES", row["london_futures"], "GBP"),
            ("NEW-YORK-FUTURES", row["new_york_futures"], "USD"),
            ("ICCO-DAILY-USD", row["icco_daily_usd"], "USD"),
            ("ICCO-DAILY-EUR", row["icco_daily_eur"], "EUR"),
        ):
            if price is not None:
                records.append(("ICCO", contract, price, currency, "MT", ts))

    if not records:
        raise RuntimeError("No valid ICCO records prepared")

    sql = """
        INSERT INTO market_prices
            (market, contract, price, currency, unit, timestamp, source_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """
    inserted = 0
    with psycopg2.connect(database_url()) as conn:
        with conn.cursor() as cur:
            for record in records:
                cur.execute(sql, (*record, ICCO_SOURCE_ID))
                inserted += cur.rowcount
        conn.commit()
    print(f"RECORDS PREPARED: {len(records)}")
    print(f"RECORDS INSERTED: {inserted}")
    print(f"FIRST DATE: {rows[0]['date']}")
    print(f"LAST DATE: {rows[-1]['date']}")
    return inserted


def verify_database() -> None:
    sql = """
        SELECT contract, COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM market_prices
        WHERE market='ICCO'
          AND contract IN ('LONDON-FUTURES','NEW-YORK-FUTURES','ICCO-DAILY-USD','ICCO-DAILY-EUR')
        GROUP BY contract ORDER BY contract
    """
    with psycopg2.connect(database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            result = cur.fetchall()
    print("\nDATABASE VERIFICATION")
    print("-" * 72)
    total = 0
    for contract, count, first_ts, last_ts in result:
        total += count
        print(f"{contract:20s} | {count:4d} | {first_ts} | {last_ts}")
    print("-" * 72)
    print(f"TOTAL ICCO CONTRACT ROWS: {total}")


def main() -> None:
    print("=" * 72)
    print("ICCO HISTORICAL COCOA PRICE COLLECTOR")
    print("=" * 72)
    try:
        html = fetch_statistics_page()
        rows = collect_all_rows(html)
        print(f"TOTAL DAILY ROWS FOUND: {len(rows)}")
        if not rows:
            raise RuntimeError("ICCO returned zero historical daily rows")
        save_prices(rows)
        verify_database()
        print("\nICCO HISTORICAL COLLECTOR: PASSED")
    except KeyboardInterrupt:
        print("\nCollector interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
