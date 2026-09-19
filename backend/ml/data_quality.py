from datetime import datetime, timezone
from backend.database.connection import get_connection


def _score(value, minimum, maximum):
    """Convert a value to a 0-100 score."""
    if value <= minimum:
        return 0.0
    if value >= maximum:
        return 100.0

    return round(
        ((value - minimum) / (maximum - minimum)) * 100,
        2
    )


def check_market_prices(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT contract),
                COUNT(DISTINCT DATE(timestamp)),
                MIN(timestamp),
                MAX(timestamp),
                COUNT(*) FILTER (WHERE price IS NULL),
                COUNT(*) FILTER (WHERE price <= 0)
            FROM market_prices
        """)

        row = cur.fetchone()

    total = row[0] or 0
    contracts = row[1] or 0
    trading_days = row[2] or 0
    earliest = row[3]
    latest = row[4]
    null_prices = row[5] or 0
    invalid_prices = row[6] or 0

    score = 0.0

    # More observations are better.
    score += min(total / 1000 * 40, 40)

    # Multiple contracts improve market representation.
    score += min(contracts / 4 * 20, 20)

    # More trading days improve time-series usefulness.
    score += min(trading_days / 250 * 30, 30)

    # Data validity.
    if total > 0 and null_prices == 0 and invalid_prices == 0:
        score += 10

    return {
        "rows": total,
        "contracts": contracts,
        "trading_days": trading_days,
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest.isoformat() if latest else None,
        "null_prices": null_prices,
        "invalid_prices": invalid_prices,
        "score": round(min(score, 100), 2),
    }


def check_fx(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT rate_date),
                COUNT(DISTINCT base_currency || '-' || quote_currency),
                MIN(rate_date),
                MAX(rate_date),
                COUNT(*) FILTER (WHERE rate IS NULL),
                COUNT(*) FILTER (WHERE rate <= 0)
            FROM fx_rates
        """)

        row = cur.fetchone()

    total = row[0] or 0
    dates = row[1] or 0
    pairs = row[2] or 0
    earliest = row[3]
    latest = row[4]
    null_rates = row[5] or 0
    invalid_rates = row[6] or 0

    score = 0.0

    score += min(total / 250 * 50, 50)
    score += min(dates / 100 * 30, 30)
    score += min(pairs / 4 * 10, 10)

    if total > 0 and null_rates == 0 and invalid_rates == 0:
        score += 10

    return {
        "rows": total,
        "dates": dates,
        "currency_pairs": pairs,
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest.isoformat() if latest else None,
        "null_rates": null_rates,
        "invalid_rates": invalid_rates,
        "score": round(min(score, 100), 2),
    }


def check_weather(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT location),
                MIN(observation_date),
                MAX(observation_date)
            FROM weather_observations
        """)
        obs = cur.fetchone()

        cur.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT location),
                MIN(forecast_date),
                MAX(forecast_date)
            FROM weather_forecasts
        """)
        forecast = cur.fetchone()

    obs_rows = obs[0] or 0
    obs_locations = obs[1] or 0
    forecast_rows = forecast[0] or 0
    forecast_locations = forecast[1] or 0

    score = 0.0

    # Observation coverage.
    score += min(obs_rows / 100 * 30, 30)

    # Location coverage.
    score += min(obs_locations / 4 * 20, 20)

    # Forecast coverage.
    score += min(forecast_rows / 100 * 20, 20)

    # Forecast location coverage.
    score += min(forecast_locations / 4 * 20, 20)

    if obs_rows > 0 and forecast_rows > 0:
        score += 10

    return {
        "observation_rows": obs_rows,
        "observation_locations": obs_locations,
        "observation_earliest": (
            obs[2].isoformat() if obs[2] else None
        ),
        "observation_latest": (
            obs[3].isoformat() if obs[3] else None
        ),
        "forecast_rows": forecast_rows,
        "forecast_locations": forecast_locations,
        "forecast_earliest": (
            forecast[2].isoformat() if forecast[2] else None
        ),
        "forecast_latest": (
            forecast[3].isoformat() if forecast[3] else None
        ),
        "score": round(min(score, 100), 2),
    }


def check_news(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*),
                COUNT(DISTINCT country_id),
                COUNT(*) FILTER (
                    WHERE title IS NULL OR title = ''
                ),
                MIN(published_at),
                MAX(published_at)
            FROM articles
        """)

        row = cur.fetchone()

    total = row[0] or 0
    countries = row[1] or 0
    missing_titles = row[2] or 0

    score = 0.0

    score += min(total / 500 * 60, 60)
    score += min(countries / 8 * 30, 30)

    if total > 0 and missing_titles == 0:
        score += 10

    return {
        "rows": total,
        "countries": countries,
        "missing_titles": missing_titles,
        "earliest": row[3].isoformat() if row[3] else None,
        "latest": row[4].isoformat() if row[4] else None,
        "score": round(min(score, 100), 2),
    }


def run_data_quality_check():
    conn = get_connection()

    try:
        market = check_market_prices(conn)
        fx = check_fx(conn)
        weather = check_weather(conn)
        news = check_news(conn)

        # Weighted V1.0 score.
        overall = round(
            market["score"] * 0.45
            + fx["score"] * 0.20
            + weather["score"] * 0.20
            + news["score"] * 0.15,
            2
        )

        if overall >= 80:
            status = "READY"
        elif overall >= 50:
            status = "LIMITED"
        else:
            status = "NOT_READY"

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
            "overall_score": overall,
            "status": status,
            "components": {
                "market_prices": market,
                "fx": fx,
                "weather": weather,
                "news": news,
            },
        }

    finally:
        conn.close()


if __name__ == "__main__":
    import json

    result = run_data_quality_check()

    print(json.dumps(result, indent=2, default=str))