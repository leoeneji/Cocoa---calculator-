import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from psycopg import connect

from backend.database.config import settings


BEAC_URL = "https://webadmin.beac.int/"


TARGET_CURRENCIES = {
    "EUR/XAF": "EUR",
    "USD/XAF": "USD",
}


def fetch_beac_page():
    response = httpx.get(
        BEAC_URL,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.encoding = "utf-8"
    response.raise_for_status()

    return response.text


def parse_beac_rates(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    date_match = re.search(
        r"Date de valeur\s*:\s*(\d{2}/\d{2}/\d{4})",
        text,
    )

    if not date_match:
        raise RuntimeError(
            "BEAC value date not found."
        )

    rate_date = datetime.strptime(
        date_match.group(1),
        "%d/%m/%Y",
    ).date()

    rates = []

    for document in soup.find_all(
        "div",
        class_="document",
    ):

        code_element = document.find(
            class_="code_valeur"
        )

        if not code_element:
            continue

        pair = code_element.get_text(
            " ",
            strip=True,
        )

        if pair not in TARGET_CURRENCIES:
            continue

        middle = document.find(
            id="middle"
        )

        right = document.find(
            id="right"
        )

        if not middle or not right:
            continue

        try:
            buy_rate = float(
                middle.get_text(
                    " ",
                    strip=True,
                ).replace(",", ".")
            )

            sell_rate = float(
                right.get_text(
                    " ",
                    strip=True,
                ).replace(",", ".")
            )

        except ValueError:
            continue

        midpoint = (
            buy_rate + sell_rate
        ) / 2

        rates.append(
            {
                "base_currency": TARGET_CURRENCIES[pair],
                "quote_currency": "XAF",
                "buy_rate": buy_rate,
                "sell_rate": sell_rate,
                "rate": midpoint,
                "rate_date": rate_date,
            }
        )

    return rates


def save_beac_rates(rates):
    conn = connect(
        settings.database_url
    )

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM sources
                WHERE name = 'BEAC FX'
                LIMIT 1
            """)

            source = cur.fetchone()

            if not source:
                raise RuntimeError(
                    "BEAC FX source not found."
                )

            for item in rates:

                cur.execute(
                    """
                    INSERT INTO fx_rates (
                        base_currency,
                        quote_currency,
                        rate,
                        rate_date,
                        source
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    ON CONFLICT (
                        base_currency,
                        quote_currency,
                        rate_date
                    )
                    DO UPDATE SET
                        rate = EXCLUDED.rate,
                        source = EXCLUDED.source
                    """,
                    (
                        item["base_currency"],
                        item["quote_currency"],
                        item["rate"],
                        item["rate_date"],
                        "BEAC",
                    ),
                )

        conn.commit()

    finally:
        conn.close()


if __name__ == "__main__":

    html = fetch_beac_page()

    rates = parse_beac_rates(
        html
    )

    print(
        "BEAC FX CONNECTION: OK"
    )

    print(
        f"RATES FOUND: {len(rates)}"
    )

    for item in rates:

        print(
            item["rate_date"],
            "|",
            item["base_currency"],
            "→",
            item["quote_currency"],
            "| BUY:",
            item["buy_rate"],
            "| SELL:",
            item["sell_rate"],
            "| MID:",
            round(item["rate"], 6),
        )

    save_beac_rates(rates)

    print(
        "BEAC FX RATES SAVED TO DATABASE"
    )