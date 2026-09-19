import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from psycopg import connect

from backend.database.config import settings


ICCO_URL = "https://www.icco.org/"
ICCO_SOURCE_ID = "fca90836-0945-4cd2-94f0-f11aa7b5012d"


def fetch_icco_page():
    response = httpx.get(ICCO_URL, timeout=30)
    response.raise_for_status()
    return response.text


def parse_icco_prices(html):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        raise ValueError("No tables found on ICCO page")

    table = tables[0]
    rows = []

    for tr in table.find_all("tr"):
        cells = [
            cell.get_text(" ", strip=True)
            for cell in tr.find_all(["th", "td"])
        ]
        
        if len(cells) < 5:
            continue

        date_index = None
        for i, value in enumerate(cells):
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
                date_index = i
                break


        if date_index is None or len(cells) < date_index + 5:
            continue

        try:
            date = datetime.strptime(
                cells[date_index],
                "%d/%m/%Y"
            ).date()

            london = float(
                cells[date_index + 1].replace(",", "")
            )

            new_york = float(
                cells[date_index + 2].replace(",", "")
            )

            icco_usd = float(
                cells[date_index + 3].replace(",", "")
            )

            icco_eur = float(
                cells[date_index + 4].replace(",", "")
            )

            rows.append(
                {
                    "date": date.isoformat(),
                    "london_futures_gbp": london,
                    "new_york_futures_usd": new_york,
                    "icco_daily_price_usd": icco_usd,
                    "icco_daily_price_eur": icco_eur,
                }
            )

        except ValueError:
            continue

    return rows


def save_icco_prices(prices):
    conn = connect(settings.database_url)

    try:
        with conn.cursor() as cur:

            for price in prices:
                timestamp = datetime.fromisoformat(
                    price["date"]
                ).replace(tzinfo=timezone.utc)

                records = [
                    (
                        "ICCO",
                        "LONDON-FUTURES",
                        price["london_futures_gbp"],
                        "GBP",
                        "MT",
                        timestamp,
                        ICCO_SOURCE_ID,
                    ),
                    (
                        "ICCO",
                        "NEW-YORK-FUTURES",
                        price["new_york_futures_usd"],
                        "USD",
                        "MT",
                        timestamp,
                        ICCO_SOURCE_ID,
                    ),
                    (
                        "ICCO",
                        "ICCO-DAILY-USD",
                        price["icco_daily_price_usd"],
                        "USD",
                        "MT",
                        timestamp,
                        ICCO_SOURCE_ID,
                    ),
                    (
                        "ICCO",
                        "ICCO-DAILY-EUR",
                        price["icco_daily_price_eur"],
                        "EUR",
                        "MT",
                        timestamp,
                        ICCO_SOURCE_ID,
                    ),
                ]

                cur.executemany(
                    """
                    INSERT INTO market_prices
                    (market, contract, price, currency, unit, timestamp, source_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (market, contract, timestamp) DO NOTHING
                    """,
                    records,
                )

        conn.commit()

    finally:
        conn.close()


if __name__ == "__main__":
    html = fetch_icco_page()
    prices = parse_icco_prices(html)

    print("ICCO CONNECTION: OK")
    print(f"PRICE RECORDS FOUND: {len(prices)}")

    save_icco_prices(prices)

    print("ICCO PRICES SAVED TO DATABASE")