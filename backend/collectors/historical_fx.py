"""
Cocoa Intelligence Hub
Historical FX Backfill

Purpose:
    Build historical FX observations required by the
    Cocoa Intelligence Hub feature engine.

Sources:
    CBN
        Historical NGN rates.

    BCEAO
        Historical XOF rates.

    ECB
        Historical EUR/USD reference rate used to derive
        USD/XAF from the fixed EUR/XAF CFA franc peg.

Important:
    This collector is separate from the existing live
    BCEAO and BEAC collectors.

Database:
    PostgreSQL via backend.database.connection.get_connection()
"""

from datetime import date
from decimal import Decimal

import requests

from backend.database.connection import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

API_BASE = "https://api.frankfurter.dev/v2/providers"

START_DATE = date(2024, 10, 1)
END_DATE = date.today()

TIMEOUT = 60

USER_AGENT = "Cocoa-Intelligence-Hub/1.0"

# Central African CFA franc is fixed to the euro.
EUR_XAF_PEG = Decimal("655.957")


# ============================================================
# FETCH PROVIDER DATA
# ============================================================

def fetch_provider_rates(
    provider,
    base,
    quotes,
    start_date,
    end_date,
):
    """
    Fetch historical rates from one specific Frankfurter
    provider.

    Frankfurter v2 returns flat rows such as:

        {
            "date": "2024-10-01",
            "base": "NGN",
            "quote": "USD",
            "rate": 0.0006
        }

    Only rows inside the requested date range are returned.
    """

    url = f"{API_BASE}/{provider}/rates"

    params = {
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "base": base,
        "quotes": ",".join(quotes),
    }

    response = requests.get(
        url,
        params=params,
        timeout=TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected response from {provider}: "
            f"{type(data).__name__}"
        )

    # --------------------------------------------------------
    # Enforce the requested date boundary.
    # --------------------------------------------------------

    filtered = []

    minimum_date = start_date.isoformat()
    maximum_date = end_date.isoformat()

    for row in data:

        row_date = row.get("date")

        if not row_date:
            continue

        if minimum_date <= row_date <= maximum_date:
            filtered.append(row)

    return filtered


# ============================================================
# RATE INVERSION
# ============================================================

def invert_rate(rate):
    """
    Convert:

        NGN -> USD

    into:

        USD -> NGN
    """

    value = Decimal(str(rate))

    if value == 0:
        return None

    return Decimal("1") / value


# ============================================================
# CBN
# ============================================================

def collect_cbn():

    print()
    print("FETCHING CBN HISTORICAL FX...")

    rows = fetch_provider_rates(
        provider="cbn",
        base="NGN",
        quotes=["USD", "EUR"],
        start_date=START_DATE,
        end_date=END_DATE,
    )

    print(f"CBN RAW ROWS: {len(rows)}")

    output = []

    for row in rows:

        rate = row.get("rate")

        if rate is None:
            continue

        base = str(
            row.get("base", "")
        ).upper()

        quote = str(
            row.get("quote", "")
        ).upper()

        if base != "NGN":
            continue

        if quote not in {"USD", "EUR"}:
            continue

        converted = invert_rate(rate)

        if converted is None:
            continue

        output.append(
            {
                "rate_date": row["date"],
                "base_currency": quote,
                "quote_currency": "NGN",
                "rate": converted,
                "source": "FRANKFURTER_CBN",
            }
        )

    print(
        f"CBN TRANSFORMED ROWS: {len(output)}"
    )

    return output


# ============================================================
# BCEAO
# ============================================================

def collect_bceao():

    print()
    print("FETCHING BCEAO HISTORICAL FX...")

    rows = fetch_provider_rates(
        provider="bceao",
        base="XOF",
        quotes=["USD", "EUR"],
        start_date=START_DATE,
        end_date=END_DATE,
    )

    print(
        f"BCEAO RAW ROWS: {len(rows)}"
    )

    output = []

    for row in rows:

        rate = row.get("rate")

        if rate is None:
            continue

        base = str(
            row.get("base", "")
        ).upper()

        quote = str(
            row.get("quote", "")
        ).upper()

        if base != "XOF":
            continue

        if quote not in {"USD", "EUR"}:
            continue

        converted = invert_rate(rate)

        if converted is None:
            continue

        output.append(
            {
                "rate_date": row["date"],
                "base_currency": quote,
                "quote_currency": "XOF",
                "rate": converted,
                "source": "FRANKFURTER_BCEAO",
            }
        )

    print(
        f"BCEAO TRANSFORMED ROWS: {len(output)}"
    )

    return output


# ============================================================
# ECB
# ============================================================

def collect_ecb():

    print()
    print("FETCHING ECB HISTORICAL EUR/USD...")

    rows = fetch_provider_rates(
        provider="ecb",
        base="EUR",
        quotes=["USD"],
        start_date=START_DATE,
        end_date=END_DATE,
    )

    print(
        f"ECB RAW ROWS: {len(rows)}"
    )

    output = []

    for row in rows:

        rate = row.get("rate")

        if rate is None:
            continue

        base = str(
            row.get("base", "")
        ).upper()

        quote = str(
            row.get("quote", "")
        ).upper()

        if base != "EUR":
            continue

        if quote != "USD":
            continue

        eur_usd = Decimal(str(rate))

        if eur_usd == 0:
            continue

        # ----------------------------------------------------
        # EUR -> XAF
        #
        # XAF is fixed to EUR at:
        #
        # 1 EUR = 655.957 XAF
        # ----------------------------------------------------

        output.append(
            {
                "rate_date": row["date"],
                "base_currency": "EUR",
                "quote_currency": "XAF",
                "rate": EUR_XAF_PEG,
                "source": "EUR_XAF_PEG",
            }
        )

        # ----------------------------------------------------
        # USD -> XAF
        #
        # EUR/XAF
        # -------------
        # EUR/USD
        #
        # gives USD/XAF
        # ----------------------------------------------------

        usd_xaf = (
            EUR_XAF_PEG / eur_usd
        )

        output.append(
            {
                "rate_date": row["date"],
                "base_currency": "USD",
                "quote_currency": "XAF",
                "rate": usd_xaf,
                "source": "ECB_EURUSD_XAF_PEG_DERIVED",
            }
        )

    print(
        f"ECB/XAF TRANSFORMED ROWS: {len(output)}"
    )

    return output


# ============================================================
# DATABASE SAVE
# ============================================================

def save_rates(rows):

    if not rows:

        print()
        print("NO FX RECORDS TO SAVE.")

        return 0

    conn = get_connection()

    saved = 0

    try:

        with conn.cursor() as cur:

            for row in rows:

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
                        row["base_currency"],
                        row["quote_currency"],
                        row["rate"],
                        row["rate_date"],
                        row["source"],
                    ),
                )

                saved += 1

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    return saved


# ============================================================
# MAIN
# ============================================================

def run():

    print("=" * 70)
    print("COCOA INTELLIGENCE HUB")
    print("HISTORICAL FX BACKFILL")
    print("=" * 70)

    print(
        f"DATE RANGE: "
        f"{START_DATE.isoformat()} -> "
        f"{END_DATE.isoformat()}"
    )

    all_rows = []

    # --------------------------------------------------------
    # CBN
    # --------------------------------------------------------

    try:

        all_rows.extend(
            collect_cbn()
        )

    except Exception as exc:

        print()
        print("CBN COLLECTION ERROR:")
        print(
            f"{type(exc).__name__}: {exc}"
        )

    # --------------------------------------------------------
    # BCEAO
    # --------------------------------------------------------

    try:

        all_rows.extend(
            collect_bceao()
        )

    except Exception as exc:

        print()
        print("BCEAO COLLECTION ERROR:")
        print(
            f"{type(exc).__name__}: {exc}"
        )

    # --------------------------------------------------------
    # ECB / XAF
    # --------------------------------------------------------

    try:

        all_rows.extend(
            collect_ecb()
        )

    except Exception as exc:

        print()
        print("ECB COLLECTION ERROR:")
        print(
            f"{type(exc).__name__}: {exc}"
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print(
        f"TOTAL TRANSFORMED FX RECORDS: "
        f"{len(all_rows)}"
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    if all_rows:

        saved = save_rates(
            all_rows
        )

        print()
        print(
            f"FX RECORDS SAVED/UPDATED: "
            f"{saved}"
        )

    else:

        print()
        print(
            "NO HISTORICAL FX DATA WAS AVAILABLE."
        )

    print()
    print(
        "HISTORICAL FX BACKFILL COMPLETE"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run()