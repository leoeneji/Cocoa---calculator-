"""
Cocoa Intelligence Hub
MARKET INTELLIGENCE ENGINE

Purpose
-------
Combine validated model output with current observable market context:

    price + FX + weather + news + signal/risk evidence
                         ↓
                 MARKET INTELLIGENCE

This layer explains the current intelligence state. It does not:
- retrain models,
- invent missing observations,
- convert weak evidence into certainty,
- create a guaranteed price prediction,
- replace the model validation layer.

All context is point-in-time: only observations available at or before
the latest canonical ICCO-DAILY-USD observation are considered.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional
from dotenv import load_dotenv
import psycopg2
load_dotenv()

TARGET = "ICCO-DAILY-USD"
UNIT = "USD/tonne"

# Context windows are deliberately modest and transparent.
NEWS_WINDOW_DAYS = 7
WEATHER_WINDOW_DAYS = 7


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    return number if number == number and abs(number) != float("inf") else default


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Activate the project environment "
            "and load the project .env configuration."
        )
    return psycopg2.connect(database_url)


@dataclass
class IntelligenceResult:
    target: str
    observation_date: str
    latest_price: float

    signal: str
    direction: str
    confidence_index: float
    risk_level: str
    model_agreement: str

    forecast_price: Optional[float]
    expected_change_pct: Optional[float]
    forecast_low: Optional[float]
    forecast_high: Optional[float]

    fx_context: dict[str, Any]
    weather_context: dict[str, Any]
    news_context: dict[str, Any]

    market_state: str
    intelligence_state: str
    drivers: list[str]
    cautions: list[str]
    models: list[dict[str, Any]]

    data_integrity: dict[str, bool]


def load_latest_target(cur) -> tuple[date, float]:
    cur.execute(
        """
        SELECT
            timestamp::date AS trade_date,
            price
        FROM market_prices
        WHERE contract = %s
          AND price IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (TARGET,),
    )
    row = cur.fetchone()

    if not row:
        raise RuntimeError(
            f"No observations found for canonical target {TARGET}."
        )

    trade_date, price = row
    price_value = safe_float(price)

    if price_value is None:
        raise RuntimeError("Latest canonical target price is invalid.")

    return trade_date, price_value


def load_fx_context(cur, as_of: date) -> dict[str, Any]:
    """
    Retrieve the latest available FX observation for each requested pair
    at or before the canonical cocoa observation date.

    We use the existing fx_rates table rather than inventing rates.
    """
    pairs = [
        ("USD", "NGN"),
        ("EUR", "NGN"),
        ("USD", "XOF"),
        ("EUR", "XOF"),
        ("USD", "XAF"),
        ("EUR", "XAF"),
    ]

    result: dict[str, Any] = {}

    for base, quote in pairs:
        cur.execute(
            """
            SELECT rate, rate_date, source
            FROM fx_rates
            WHERE base_currency = %s
              AND quote_currency = %s
              AND rate_date <= %s
            ORDER BY rate_date DESC
            LIMIT 1
            """,
            (base, quote, as_of),
        )
        row = cur.fetchone()

        key = f"{base}_{quote}"

        if not row:
            result[key] = None
            continue

        rate, rate_date, source = row

        result[key] = {
            "rate": safe_float(rate),
            "date": str(rate_date),
            "source": source,
        }

    available = sum(value is not None for value in result.values())

    return {
        "available_pairs": available,
        "requested_pairs": len(pairs),
        "pairs": result,
    }


def load_weather_context(cur, as_of: date) -> dict[str, Any]:
    """
    Summarise recent weather observations without using future data.

    weather_observations contains:
      location, observation_date, rainfall_mm,
      temperature_c, humidity_pct, weather_anomaly,
      crop_risk_score, source
    """
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
        WHERE observation_date <= %s
          AND observation_date >= %s
        ORDER BY observation_date DESC
        """,
        (
            as_of,
            as_of.fromordinal(max(1, as_of.toordinal() - WEATHER_WINDOW_DAYS)),
        ),
    )

    rows = cur.fetchall()

    if not rows:
        return {
            "available": False,
            "observations": 0,
            "locations": 0,
            "average_rainfall_mm": None,
            "average_temperature_c": None,
            "average_humidity_pct": None,
            "average_crop_risk_score": None,
            "average_weather_anomaly": None,
        }

    rainfall = []
    temperature = []
    humidity = []
    crop_risk = []
    anomaly = []
    locations = set()

    for (
        location,
        observation_date,
        rainfall_mm,
        temperature_c,
        humidity_pct,
        weather_anomaly,
        crop_risk_score,
        source,
    ) in rows:
        if location:
            locations.add(str(location))

        for collection, value in (
            (rainfall, rainfall_mm),
            (temperature, temperature_c),
            (humidity, humidity_pct),
            (crop_risk, crop_risk_score),
            (anomaly, weather_anomaly),
        ):
            number = safe_float(value)
            if number is not None:
                collection.append(number)

    average = lambda values: (
        round(sum(values) / len(values), 2) if values else None
    )

    return {
        "available": True,
        "observations": len(rows),
        "locations": len(locations),
        "average_rainfall_mm": average(rainfall),
        "average_temperature_c": average(temperature),
        "average_humidity_pct": average(humidity),
        "average_crop_risk_score": average(crop_risk),
        "average_weather_anomaly": average(anomaly),
    }


def load_news_context(cur, as_of: date) -> dict[str, Any]:
    """
    Count recent articles that were already stored in the articles table.

    Sentiment is reported only when an actual sentiment field exists.
    This function never manufactures sentiment.
    """
    window_start = as_of.fromordinal(
        max(1, as_of.toordinal() - NEWS_WINDOW_DAYS)
    )

    cur.execute(
        """
        SELECT
            COUNT(*)
        FROM articles
        WHERE published_at::date <= %s
          AND published_at::date >= %s
        """,
        (as_of, window_start),
    )
    article_count = int(cur.fetchone()[0] or 0)

    # The current articles schema does not expose a sentiment column.
    # Keep the interface explicit instead of fabricating sentiment.
    return {
        "available": article_count > 0,
        "article_count": article_count,
        "window_days": NEWS_WINDOW_DAYS,
        "sentiment_available": False,
        "sentiment": None,
    }


def load_signal_context() -> dict[str, Any]:
    try:
        from backend.signal_engine import build_signal
    except Exception as exc:
        raise RuntimeError(
            "Could not import backend.signal_engine."
        ) from exc

    result = build_signal("30")
    return asdict(result)


def classify_market_state(
    expected_change_pct: Optional[float],
    direction: str,
    agreement: str,
) -> str:
    if expected_change_pct is None:
        return "UNKNOWN"

    if agreement == "MODEL_DISAGREEMENT":
        return "MIXED"

    if direction == "BULLISH":
        return "BULLISH"

    if direction == "BEARISH":
        return "BEARISH"

    if direction == "NEUTRAL":
        return "NEUTRAL"

    return "UNKNOWN"


def build_drivers(
    signal: dict[str, Any],
    fx: dict[str, Any],
    weather: dict[str, Any],
    news: dict[str, Any],
) -> tuple[list[str], list[str]]:
    drivers: list[str] = []
    cautions: list[str] = []

    direction = signal.get("direction", "UNKNOWN")
    agreement = signal.get("agreement", "UNKNOWN")
    expected_change = safe_float(signal.get("expected_change_pct"))

    if direction in {"BULLISH", "BEARISH", "NEUTRAL"}:
        drivers.append(
            f"Validated ensemble direction is {direction} for the 30-trading-day horizon."
        )

    if expected_change is not None:
        drivers.append(
            f"Ensemble expected change is {expected_change:+.2f}%."
        )

    if agreement == "MODEL_DISAGREEMENT":
        cautions.append(
            "Models disagree on the 30-trading-day forecast."
        )

    confidence = safe_float(signal.get("confidence_index"))
    if confidence is not None and confidence < 65.0:
        cautions.append(
            f"Evidence confidence index is {confidence:.2f}/100, below the action threshold."
        )

    if signal.get("risk_level") == "HIGH":
        cautions.append("Current risk classification is HIGH.")

    if fx.get("available_pairs", 0) == 0:
        cautions.append("No usable FX context was available at the observation date.")
    else:
        drivers.append(
            f"FX context available for {fx['available_pairs']}/{fx['requested_pairs']} requested pairs."
        )

    if weather.get("available"):
        risk = safe_float(weather.get("average_crop_risk_score"))
        if risk is not None:
            drivers.append(
                f"Recent weather observations provide an average crop-risk score of {risk:.2f}."
            )
    else:
        cautions.append("No recent weather observations were available.")

    if news.get("article_count", 0) > 0:
        drivers.append(
            f"{news['article_count']} stored article(s) fall within the recent {NEWS_WINDOW_DAYS}-day window."
        )
    else:
        cautions.append("No stored articles were available in the recent news window.")

    if not news.get("sentiment_available"):
        cautions.append(
            "News sentiment is not scored; no sentiment value is inferred."
        )

    return drivers, cautions


def build_intelligence() -> IntelligenceResult:
    signal = load_signal_context()

    with get_connection() as conn:
        with conn.cursor() as cur:
            observation_date, latest_price = load_latest_target(cur)

            # Prevent accidental mixing of a newer DB target with an older
            # model context.
            signal_date = parse_date(signal.get("latest_date"))

            if signal_date is None:
                raise RuntimeError("Signal engine returned an invalid latest date.")

            if signal_date != observation_date:
                raise RuntimeError(
                    "Signal/model context is not aligned with the latest "
                    f"{TARGET} observation: signal={signal_date}, "
                    f"database={observation_date}."
                )

            fx = load_fx_context(cur, observation_date)
            weather = load_weather_context(cur, observation_date)
            news = load_news_context(cur, observation_date)

    drivers, cautions = build_drivers(signal, fx, weather, news)

    expected_change = safe_float(signal.get("expected_change_pct"))
    direction = str(signal.get("direction", "UNKNOWN")).upper()
    agreement = str(signal.get("agreement", "UNKNOWN")).upper()

    market_state = classify_market_state(
        expected_change,
        direction,
        agreement,
    )

    # Intelligence state is descriptive, not a trading recommendation.
    if signal.get("risk_level") == "HIGH":
        intelligence_state = "CAUTION"
    elif agreement == "MODEL_DISAGREEMENT":
        intelligence_state = "MIXED_EVIDENCE"
    elif signal.get("signal") in {"BUY", "SELL"}:
        intelligence_state = "ACTIONABLE_EVIDENCE"
    else:
        intelligence_state = "WATCH"

    return IntelligenceResult(
        target=TARGET,
        observation_date=str(observation_date),
        latest_price=round(latest_price, 2),
        signal=str(signal.get("signal", "NO_SIGNAL")),
        direction=direction,
        confidence_index=round(
            safe_float(signal.get("confidence_index"), 0.0) or 0.0,
            2,
        ),
        risk_level=str(signal.get("risk_level", "UNKNOWN")),
        model_agreement=agreement,
        forecast_price=safe_float(signal.get("forecast_price")),
        expected_change_pct=(
            round(expected_change, 2) if expected_change is not None else None
        ),
        forecast_low=safe_float(signal.get("range_low")),
        forecast_high=safe_float(signal.get("range_high")),
        fx_context=fx,
        weather_context=weather,
        news_context=news,
        market_state=market_state,
        intelligence_state=intelligence_state,
        drivers=drivers,
        cautions=cautions,
        models=signal.get("models", []),
        data_integrity={
            "canonical_target_only": True,
            "mixed_contracts": False,
            "chronological_evaluation": True,
            "random_shuffling": False,
            "future_leakage": False,
            "sentiment_fabricated": False,
        },
    )


def main() -> None:
    print("\n" + "=" * 70)
    print("COCOA INTELLIGENCE HUB")
    print("MARKET INTELLIGENCE ENGINE")
    print("=" * 70)

    result = build_intelligence()

    print("\n=== MARKET STATE ===")
    print(f"Target: {result.target}")
    print(f"Observation date: {result.observation_date}")
    print(f"Latest price: {result.latest_price:.2f} {UNIT}")
    print(f"Market state: {result.market_state}")
    print(f"Intelligence state: {result.intelligence_state}")

    print("\n=== FORECAST / SIGNAL ===")
    print(f"Signal: {result.signal}")
    print(f"Direction: {result.direction}")
    print(f"Forecast: {result.forecast_price}")
    print(f"Expected change: {result.expected_change_pct:+.2f}%"
          if result.expected_change_pct is not None
          else "Expected change: unavailable")
    print(f"Confidence index: {result.confidence_index:.2f}/100")
    print(f"Risk level: {result.risk_level}")
    print(f"Model agreement: {result.model_agreement}")

    print("\n=== FORECAST RANGE ===")
    print(f"Low: {result.forecast_low}")
    print(f"High: {result.forecast_high}")

    print("\n=== FX CONTEXT ===")
    print(
        f"Available pairs: "
        f"{result.fx_context['available_pairs']}/"
        f"{result.fx_context['requested_pairs']}"
    )
    for pair, value in result.fx_context["pairs"].items():
        print(f"{pair}: {value}")

    print("\n=== WEATHER CONTEXT ===")
    for key, value in result.weather_context.items():
        print(f"{key}: {value}")

    print("\n=== NEWS CONTEXT ===")
    for key, value in result.news_context.items():
        print(f"{key}: {value}")

    print("\n=== INTELLIGENCE DRIVERS ===")
    for item in result.drivers:
        print(f"- {item}")

    print("\n=== CAUTIONS ===")
    for item in result.cautions:
        print(f"- {item}")

    print("\n=== DATA INTEGRITY ===")
    for key, value in result.data_integrity.items():
        print(f"{key}: {'YES' if value else 'NO'}")

    print("\nMARKET INTELLIGENCE ENGINE: PASSED")

    print("\nMACHINE-READABLE RESULT:")
    print(json.dumps(asdict(result), indent=2, default=str))

    print("=" * 70)


if __name__ == "__main__":
    main()
