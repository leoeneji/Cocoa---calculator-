"""
Read-only context adapter for the CIH AI analyst.

This module formats existing market-intelligence outputs.
It does not fetch data, make forecasts, or execute trades.
"""

from dataclasses import asdict
from typing import Any


def build_analyst_context(intelligence: Any) -> dict[str, Any]:
    """Convert an IntelligenceResult (or compatible object) to analyst context."""
    if hasattr(intelligence, "model_dump"):
        data = intelligence.model_dump()
    elif hasattr(intelligence, "__dataclass_fields__"):
        data = asdict(intelligence)
    elif isinstance(intelligence, dict):
        data = dict(intelligence)
    else:
        raise TypeError("Unsupported market-intelligence result type.")

    # Keep the analyst focused on established CIH outputs.
    allowed_fields = (
        "target",
        "observation_date",
        "latest_price",
        "signal",
        "direction",
        "confidence_index",
        "risk_level",
        "model_agreement",
        "forecast_price",
        "expected_change_pct",
        "forecast_low",
        "forecast_high",
        "forecast_7_price",
        "expected_change_7_pct",
        "forecast_7_low",
        "forecast_7_high",
        "direction_7",
        "model_agreement_7",
        "fx_context",
        "weather_context",
        "news_context",
        "market_state",
        "intelligence_state",
        "drivers",
        "cautions",
        "nigeria_price_ngn",
        "nigeria_forecast_ngn",
        "ensemble_7",
        "ensemble_30",
        "data_integrity",
    )

    context = {field: data.get(field) for field in allowed_fields}

    context["interpretation_rules"] = [
        "The latest_price is the CIH canonical ICCO benchmark, not a verified physical spot quote.",
        "The Nigerian naira benchmark is an estimate derived from the ICCO benchmark and FX context, not a guaranteed farm-gate price.",
        "Forecasts are model estimates, not guaranteed outcomes.",
        "Use observation_date to identify the date of the underlying canonical benchmark.",
        "If a value is missing or a forecast horizon is unavailable, say so rather than inventing it.",
    ]

    return context
