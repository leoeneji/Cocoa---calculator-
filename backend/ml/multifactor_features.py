"""
Cocoa Intelligence Hub
Multi-Factor Point-in-Time Feature Engine

Combines:
    - Cocoa market price history
    - FX
    - Weather observations
    - News/article activity
    - Seasonality

IMPORTANT:
Every feature is point-in-time safe.
Historical observations are NEVER allowed to use future information.
"""

from datetime import datetime, date, timezone, timedelta

import numpy as np

from backend.database.connection import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

MARKET = "ICCO"

FX_MAX_AGE_DAYS = 7
WEATHER_MAX_AGE_DAYS = 7
NEWS_LOOKBACK_DAYS = 30


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_table_columns(table_name):
    """
    Return available columns for a PostgreSQL table.
    """

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )

        columns = {
            row[0]
            for row in cur.fetchall()
        }

        cur.close()

        return columns

    finally:
        conn.close()


# ============================================================
# MARKET PRICES
# ============================================================

def load_market_prices(market=MARKET):
    """
    Load historical cocoa prices.
    """

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT timestamp, price
            FROM market_prices
            WHERE market = %s
              AND price IS NOT NULL
            ORDER BY timestamp ASC
            """,
            (market,),
        )

        rows = cur.fetchall()

        cur.close()

        return rows

    finally:
        conn.close()


# ============================================================
# FX
# ============================================================

def load_fx():
    """
    Load available FX observations.

    Confirmed project columns:
        rate_date
        base_currency
        quote_currency
        rate
        source
    """

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                rate_date,
                base_currency,
                quote_currency,
                rate,
                source
            FROM fx_rates
            WHERE rate IS NOT NULL
            ORDER BY rate_date ASC
            """
        )

        rows = cur.fetchall()

        cur.close()

        return rows

    finally:
        conn.close()


# ============================================================
# WEATHER
# ============================================================

def load_weather():
    """
    Load historical weather observations.

    Confirmed project columns:
        location
        observation_date
        rainfall_mm
        temperature_c
        humidity_pct
        weather_anomaly
        crop_risk_score
        source
    """

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                location,
                observation_date,
                rainfall_mm,
                temperature_c,
                humidity_pct,
                weather_anomaly,
                crop_risk_score,
                source
            FROM weather_observations
            ORDER BY observation_date ASC
            """
        )

        rows = cur.fetchall()

        cur.close()

        return rows

    finally:
        conn.close()


# ============================================================
# NEWS / ARTICLES
# ============================================================

def detect_article_columns():
    """
    Detect the available article date/sentiment columns.

    This prevents the feature engine from breaking if the
    article schema uses a slightly different column name.
    """

    columns = get_table_columns("articles")

    date_candidates = [
        "published_at",
        "published_date",
        "publication_date",
        "article_date",
        "created_at",
        "date",
        "timestamp",
    ]

    sentiment_candidates = [
        "sentiment_score",
        "sentiment",
        "score",
    ]

    date_column = next(
        (
            column
            for column in date_candidates
            if column in columns
        ),
        None,
    )

    sentiment_column = next(
        (
            column
            for column in sentiment_candidates
            if column in columns
        ),
        None,
    )

    return date_column, sentiment_column


def load_articles():
    """
    Load article publication times and sentiment if available.
    """

    date_column, sentiment_column = (
        detect_article_columns()
    )

    if date_column is None:
        return []

    conn = get_connection()

    try:
        cur = conn.cursor()

        if sentiment_column:

            query = f"""
                SELECT
                    "{date_column}",
                    "{sentiment_column}"
                FROM articles
                WHERE "{date_column}" IS NOT NULL
                ORDER BY "{date_column}" ASC
            """

        else:

            query = f"""
                SELECT
                    "{date_column}"
                FROM articles
                WHERE "{date_column}" IS NOT NULL
                ORDER BY "{date_column}" ASC
            """

        cur.execute(query)

        rows = cur.fetchall()

        cur.close()

        return rows

    finally:
        conn.close()


# ============================================================
# DATE NORMALIZATION
# ============================================================
def normalize_datetime(value):
    """
    Convert database date/time values to timezone-aware datetime.

    Handles:
        - datetime
        - date
        - ISO datetime strings
        - ISO date strings

    All returned values are timezone-aware UTC datetimes.
    """

    if value is None:
        return None

    # Already a datetime
    if isinstance(value, datetime):

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value

    # PostgreSQL DATE
    if isinstance(value, date):

        return datetime(
            value.year,
            value.month,
            value.day,
            tzinfo=timezone.utc,
        )

    text = str(value).strip()

    if not text:
        return None

    # ISO datetime
    try:

        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    except ValueError:
        pass

    # ISO date
    try:

        parsed = datetime.strptime(
            text,
            "%Y-%m-%d",
        )

        return parsed.replace(
            tzinfo=timezone.utc
        )

    except ValueError:

        return None

# ============================================================
# SAFE PREVIOUS VALUE
# ============================================================

def latest_prior_value(
    observations,
    target_time,
    date_index,
    value_index,
    max_age_days,
):
    """
    Return the latest observation available BEFORE the
    target timestamp.

    Future observations are never used.
    """

    target_time = normalize_datetime(
        target_time
    )

    if target_time is None:
        return None

    best_time = None
    best_value = None

    maximum_age = timedelta(
        days=max_age_days
    )

    for observation in observations:

        observation_time = normalize_datetime(
            observation[date_index]
        )

        if observation_time is None:
            continue

        # -----------------------------------------------
        # NEVER use future information
        # -----------------------------------------------

        if observation_time > target_time:
            continue

        age = target_time - observation_time

        if age > maximum_age:
            continue

        if (
            best_time is None
            or observation_time > best_time
        ):

            best_time = observation_time
            best_value = observation[value_index]

    if best_value is None:
        return None

    try:
        return float(best_value)

    except (TypeError, ValueError):
        return None


# ============================================================
# FX FEATURES
# ============================================================

def build_fx_features(
    target_time,
    fx_rows,
):
    """
    Build FX features using only the latest available
    historical observations.
    """

    usd_ngn = None
    eur_ngn = None
    usd_xof = None
    eur_xof = None
    usd_xaf = None
    eur_xaf = None

    target_time = normalize_datetime(
        target_time
    )

    if target_time is None:
        return {
            "usd_ngn": None,
            "eur_ngn": None,
            "usd_xof": None,
            "eur_xof": None,
            "usd_xaf": None,
            "eur_xaf": None,
        }

    latest = {}

    maximum_age = timedelta(
        days=FX_MAX_AGE_DAYS
    )

    for row in fx_rows:

        observation_time = normalize_datetime(
            row[0]
        )

        if observation_time is None:
            continue

        observation_time = normalize_datetime(observation_time)
        target_time = normalize_datetime(target_time)

        if observation_time is None or target_time is None:
           continue
        observation_time = normalize_datetime(observation_time)
        target_time = normalize_datetime(target_time)

        if observation_time is None or target_time is None:
           continue
        if observation_time > target_time:
           continue
        if (
            target_time - observation_time
            > maximum_age
        ):
            continue

        base = str(row[1]).upper()
        quote = str(row[2]).upper()

        try:
            rate = float(row[3])
        except (TypeError, ValueError):
            continue

        key = f"{base}_{quote}"

        if (
            key not in latest
            or observation_time > latest[key][0]
        ):

            latest[key] = (
                observation_time,
                rate,
            )

    values = {
        "usd_ngn": latest.get(
            "USD_NGN",
            (None, None)
        )[1],

        "eur_ngn": latest.get(
            "EUR_NGN",
            (None, None)
        )[1],

        "usd_xof": latest.get(
            "USD_XOF",
            (None, None)
        )[1],

        "eur_xof": latest.get(
            "EUR_XOF",
            (None, None)
        )[1],

        "usd_xaf": latest.get(
            "USD_XAF",
            (None, None)
        )[1],

        "eur_xaf": latest.get(
            "EUR_XAF",
            (None, None)
        )[1],
    }

    return values


# ============================================================
# WEATHER FEATURES
# ============================================================

def build_weather_features(
    target_time,
    weather_rows,
):
    """
    Aggregate the latest available weather observations
    from the cocoa-region locations.

    No future observations are used.
    """

    target_time = normalize_datetime(
        target_time
    )

    if target_time is None:
        return {
            "rainfall_mm": None,
            "temperature_c": None,
            "humidity_pct": None,
            "weather_anomaly": None,
            "crop_risk_score": None,
            "weather_locations": 0,
        }

    maximum_age = timedelta(
        days=WEATHER_MAX_AGE_DAYS
    )

    latest_by_location = {}

    for row in weather_rows:

        location = row[0]

        observation_time = normalize_datetime(
            row[1]
        )

        normalized_target_time = normalize_datetime(
            target_time
        )

        if observation_time is None:
            continue

        if normalized_target_time is None:
            continue

        # Never use future observations.
        if observation_time > normalized_target_time:
            continue

        # Ignore observations that are too old.
        if (
            normalized_target_time - observation_time
            > maximum_age
        ):
            continue

        # Keep the newest valid observation for each location.
        if location not in latest_by_location:

            latest_by_location[location] = row

        else:

            latest_time = normalize_datetime(
                latest_by_location[location][1]
            )

            if (
                latest_time is None
                or observation_time > latest_time
            ):

                latest_by_location[location] = row

    if not latest_by_location:

        return {
            "rainfall_mm": None,
            "temperature_c": None,
            "humidity_pct": None,
            "weather_anomaly": None,
            "crop_risk_score": None,
            "weather_locations": 0,
        }

    rainfall = []
    temperature = []
    humidity = []
    anomaly = []
    crop_risk = []

    for row in latest_by_location.values():

        values = [
            (rainfall, row[2]),
            (temperature, row[3]),
            (humidity, row[4]),
            (anomaly, row[5]),
            (crop_risk, row[6]),
        ]

        for destination, value in values:

            try:
                if value is not None:
                    destination.append(
                        float(value)
                    )
            except (TypeError, ValueError):
                pass

    def safe_mean(values):

        if not values:
            return None

        return float(
            np.mean(values)
        )

    return {
        "rainfall_mm": safe_mean(rainfall),
        "temperature_c": safe_mean(temperature),
        "humidity_pct": safe_mean(humidity),
        "weather_anomaly": safe_mean(anomaly),
        "crop_risk_score": safe_mean(crop_risk),
        "weather_locations": len(
            latest_by_location
        ),
    }


# ============================================================
# NEWS FEATURES
# ============================================================

def build_news_features(
    target_time,
    article_rows,
):
    """
    Build point-in-time news activity features.

    Features:
        - articles in last 7 days
        - articles in last 30 days
        - average sentiment when available

    Articles published after target_time are ignored.
    """

    target_time = normalize_datetime(
        target_time
    )

    if target_time is None:
        return {
            "news_count_7d": 0,
            "news_count_30d": 0,
            "news_sentiment_avg": None,
        }

    seven_days = timedelta(days=7)
    thirty_days = timedelta(days=30)

    count_7d = 0
    count_30d = 0

    sentiments = []

    for row in article_rows:

        article_time = normalize_datetime(
            row[0]
        )

        if article_time is None:
            continue

        # -----------------------------------------------
        # Point-in-time protection
        # -----------------------------------------------

        if article_time > target_time:
            continue

        age = target_time - article_time

        if age <= thirty_days:

            count_30d += 1

            if age <= seven_days:
                count_7d += 1

            if len(row) > 1:

                try:

                    sentiment = float(
                        row[1]
                    )

                    if np.isfinite(
                        sentiment
                    ):
                        sentiments.append(
                            sentiment
                        )

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

    sentiment_average = None

    if sentiments:

        sentiment_average = float(
            np.mean(sentiments)
        )

    return {
        "news_count_7d": count_7d,
        "news_count_30d": count_30d,
        "news_sentiment_avg": (
            sentiment_average
        ),
    }


# ============================================================
# SEASONALITY
# ============================================================

def build_seasonality_features(
    target_time,
):
    """
    Calendar/seasonality features.

    These are deterministic and therefore available at
    prediction time.
    """

    target_time = normalize_datetime(
        target_time
    )

    if target_time is None:
        return {
            "month": None,
            "month_sin": None,
            "month_cos": None,
            "quarter": None,
        }

    month = target_time.month

    angle = (
        2.0
        * np.pi
        * (month - 1)
        / 12.0
    )

    return {
        "month": month,

        "month_sin": float(
            np.sin(angle)
        ),

        "month_cos": float(
            np.cos(angle)
        ),

        "quarter": (
            (month - 1) // 3
        ) + 1,
    }


# ============================================================
# MAIN FEATURE MATRIX
# ============================================================

def build_multifactor_features(
    market=MARKET,
):
    """
    Build the complete point-in-time feature matrix.

    Every market observation is processed independently.
    """

    market_rows = load_market_prices(
        market
    )

    fx_rows = load_fx()
    weather_rows = load_weather()
    article_rows = load_articles()

    if not market_rows:
        return []

    feature_rows = []

    price_history = []

    for timestamp, price in market_rows:

        timestamp = normalize_datetime(
            timestamp
        )

        if timestamp is None:
            continue

        price = float(price)

        price_history.append(
            price
        )

        row = {
            "timestamp": timestamp,
            "price": price,
        }

        # ----------------------------------------------------
        # Price history
        # ----------------------------------------------------

        if len(price_history) >= 2:

            row["lag_1"] = float(
                price_history[-2]
            )

        else:

            row["lag_1"] = None

        if len(price_history) >= 3:

            row["lag_2"] = float(
                price_history[-3]
            )

        else:

            row["lag_2"] = None

        if len(price_history) >= 4:

            row["lag_3"] = float(
                price_history[-4]
            )

        else:

            row["lag_3"] = None

        if len(price_history) >= 4:

            previous_three = (
                price_history[-2:]
                + [price_history[-4]]
            )

            row["moving_average_3"] = (
                float(
                    np.mean(
                        previous_three
                    )
                )
            )

        else:

            row["moving_average_3"] = None

        if len(price_history) >= 3:

            row["momentum_1"] = (
                price_history[-2]
                - price_history[-3]
            )

        else:

            row["momentum_1"] = None

        if len(price_history) >= 5:

            row["momentum_3"] = (
                price_history[-2]
                - price_history[-5]
            )

        else:

            row["momentum_3"] = None

        # ----------------------------------------------------
        # FX
        # ----------------------------------------------------

        row.update(
            build_fx_features(
                timestamp,
                fx_rows,
            )
        )

        # ----------------------------------------------------
        # Weather
        # ----------------------------------------------------

        row.update(
            build_weather_features(
                timestamp,
                weather_rows,
            )
        )

        # ----------------------------------------------------
        # News
        # ----------------------------------------------------

        row.update(
            build_news_features(
                timestamp,
                article_rows,
            )
        )

        # ----------------------------------------------------
        # Seasonality
        # ----------------------------------------------------

        row.update(
            build_seasonality_features(
                timestamp,
            )
        )

        feature_rows.append(row)

    return feature_rows


# ============================================================
# FEATURE SUMMARY
# ================

# ============================================================
# FEATURE SUMMARY
# ============================================================

def summarize_features(rows):
    """
    Return a compact diagnostic summary of the
    multi-factor feature matrix.
    """

    if not rows:
        return {
            "status": "empty",
            "rows": 0,
            "features": [],
            "availability": {},
        }

    feature_names = [
        key
        for key in rows[0].keys()
        if key not in {
            "timestamp",
            "price",
        }
    ]

    availability = {}

    for feature in feature_names:

        available = sum(
            1
            for row in rows
            if row.get(feature) is not None
        )

        total = len(rows)

        coverage_pct = (
            available / total
        ) * 100 if total else 0

        availability[feature] = {
            "available": available,
            "total": total,
            "coverage_pct": round(
                coverage_pct,
                2,
            ),
        }

    return {
        "status": "ok",
        "rows": len(rows),
        "features": feature_names,
        "availability": availability,
    }


# ============================================================
# LATEST ROW DISPLAY
# ============================================================

def print_latest_row(rows):
    """
    Display the latest multi-factor observation.
    """

    if not rows:
        print(
            "\nNo feature rows were generated."
        )
        return

    latest = rows[-1]

    print(
        "\nLatest multi-factor feature row:"
    )

    print(
        "----------------------------------"
    )

    for key, value in latest.items():

        print(
            f"{key}: {value}"
        )


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "\nCOCOA MULTI-FACTOR FEATURE ENGINE"
    )

    print(
        "===================================="
    )

    print(
        f"Market: {MARKET}"
    )

    print(
        "\nLoading historical market, FX, "
        "weather and news data..."
    )

    try:

        rows = build_multifactor_features(
            MARKET
        )

        summary = summarize_features(
            rows
        )

        print(
            f"\nRows generated: "
            f"{summary.get('rows', 0)}"
        )

        print(
            "\nFeature coverage:"
        )

        print(
            "------------------"
        )

        for feature, info in summary.get(
            "availability",
            {}
        ).items():

            print(
                f"{feature}: "
                f"{info['available']}/"
                f"{info['total']} "
                f"({info['coverage_pct']}%)"
            )

        print_latest_row(
            rows
        )

        print(
            "\nMulti-factor feature engine: PASSED"
        )

    except Exception as exc:

        print(
            "\nMulti-factor feature engine: FAILED"
        )

        print(
            f"Error: {type(exc).__name__}: {exc}"
        )

        raise