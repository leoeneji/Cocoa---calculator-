import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from psycopg import connect

from backend.database.config import settings


BCEAO_URL = (
    "https://www.bceao.int/en/cours/"
    "cours-de-reference-des-principales-devises-contre-Franc-CFA"
)


CURRENCY_MAP = {
    "Euro": "EUR",
    "Dollar us": "USD",
}


def fetch_bceao_page():

    response = httpx.get(
        BCEAO_URL,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.encoding = "utf-8"
    response.raise_for_status()

    return response.text


def parse_bceao_rates(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    date_match = re.search(
        r"Exchange rates of "
        r"\w+ (\d{1,2}) "
        r"(\w+) (\d{4})",
        text,
    )

    if not date_match:
        raise RuntimeError(
            "BCEAO rate date not found."
        )

    day = date_match.group(1)
    month = date_match.group(2)
    year = date_match.group(3)

    rate_date = datetime.strptime(
        f"{day} {month} {year}",
        "%d %B %Y",
    ).date()

    rates = []

    for row in soup.find_all("tr"):

        cells = row.find_all(
            ["td", "th"]
        )

        if len(cells) < 2:
            continue

        currency = cells[0].get_text(
            " ",
            strip=True
        )

        value = cells[1].get_text(
            " ",
            strip=True
        )

        if currency not in CURRENCY_MAP:
            continue

        value = value.replace(
            ",",
            "."
        )

        try:
            rate = float(value)
        except ValueError:
            continue

        rates.append(
            {
                "base_currency":
                    CURRENCY_MAP[currency],

                "quote_currency":
                    "XOF",

                "rate":
                    rate,

                "rate_date":
                    rate_date,
            }
        )

    return rates


def save_bceao_rates(rates):

    conn = connect(
        settings.database_url
    )

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM sources
                WHERE name = 'BCEAO FX'
                LIMIT 1
            """)

            source = cur.fetchone()

            if not source:
                raise RuntimeError(
                    "BCEAO FX source not found."
                )

            source_id = source[0]

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
                        "BCEAO",
                    ),
                )

        conn.commit()

    finally:
        conn.close()


if __name__ == "__main__":

    html = fetch_bceao_page()

    rates = parse_bceao_rates(html)

    print(
        "BCEAO FX CONNECTION: OK"
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
            "|",
            item["rate"],
        )

    save_bceao_rates(rates)

    print(
        "BCEAO FX RATES SAVED TO DATABASE"
    )