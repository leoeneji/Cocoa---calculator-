"""
Cocoa Intelligence Hub
DYNAMIC CONFIDENCE + RISK ENGINE

Reads the current model ensemble at runtime. No hard-coded market price,
forecast, date, or model metrics are stored in this module.
"""

from __future__ import annotations

from math import isfinite
from typing import Dict, Optional
import time

from backend.database.connection import get_connection

TARGET = "ICCO-DAILY-USD"
UNIT = "USD/tonne"

REFERENCE_MAPE = 20.0
REFERENCE_SPREAD_PCT = 5.0

_CONTEXT_CACHE = None
_CONTEXT_TIME = 0.0
_CONTEXT_TTL_SECONDS = 60.0


def _normalise_ensemble(result: dict) -> dict:
    """Convert dynamic model_ensemble output to the interface expected by
    signal_engine and market_intelligence_engine."""
    forecast_range = result.get("forecast_range") or {}

    return {
        "status": result.get("status", "NOT_READY"),
        "forecast": result.get("ensemble_forecast"),
        "expected_change_pct": result.get("ensemble_expected_change_pct"),
        "direction": result.get("ensemble_direction", "UNKNOWN"),
        "range_low": forecast_range.get("low"),
        "range_high": forecast_range.get("high"),
        "spread": forecast_range.get("spread"),
        "agreement": result.get("model_agreement", "UNKNOWN"),
        "models": result.get("models", []),
    }


def _context() -> dict:
    """Read the latest persisted ensemble from PostgreSQL."""
    global _CONTEXT_CACHE, _CONTEXT_TIME

    now = time.monotonic()

    if _CONTEXT_CACHE is None or now - _CONTEXT_TIME >= _CONTEXT_TTL_SECONDS:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT horizon, latest_date, result
                    FROM ensemble_results
                    ORDER BY horizon
                    """
                )
                rows = cur.fetchall()

        results = {str(row[0]): row[2] for row in rows}

        if "30" not in results:
            raise RuntimeError(
                "No persisted 30-day ensemble result found. "
                "Run the automatic refresh first."
            )

        horizon_30 = results["30"]

        metrics = {
            item["model"]: {
                "mae": item["mae"],
                "rmse": item["rmse"],
                "mape": item["mape"],
            }
            for item in horizon_30.get("models", [])
        }

        _CONTEXT_CACHE = {
            "latest_date": horizon_30["latest_date"],
            "latest_price": float(horizon_30["latest_price"]),
            "ensemble": {
                "7": _normalise_ensemble(results.get("7", {})),
                "30": _normalise_ensemble(horizon_30),
            },
            "metrics": metrics,
        }

        _CONTEXT_TIME = now

    return _CONTEXT_CACHE


def __getattr__(name: str):
    """Preserve the existing signal_engine interface dynamically."""
    context = _context()

    if name == "LATEST_DATE":
        return context["latest_date"]

    if name == "LATEST_PRICE":
        return context["latest_price"]

    if name == "ENSEMBLE":
        return context["ensemble"]

    if name == "METRICS_30":
        return context["metrics"]

    raise AttributeError(name)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def mean_mape(metrics: Dict[str, dict]) -> Optional[float]:
    values = [
        float(v["mape"])
        for v in metrics.values()
        if v.get("mape") is not None and isfinite(float(v["mape"]))
    ]
    return sum(values) / len(values) if values else None


def agreement_score(agreement: str) -> float:
    return {
        "HIGH_BULLISH_AGREEMENT": 100.0,
        "HIGH_BEARISH_AGREEMENT": 100.0,
        "HIGH_NEUTRAL_AGREEMENT": 100.0,
        "PARTIAL_AGREEMENT": 65.0,
        "MODEL_DISAGREEMENT": 35.0,
        "UNKNOWN": 0.0,
    }.get(agreement, 0.0)


def dispersion_score(spread: float, current_price: float) -> float:
    if current_price <= 0:
        return 0.0

    spread_pct = abs(spread / current_price) * 100.0
    return clamp(100.0 * (1.0 - spread_pct / REFERENCE_SPREAD_PCT))


def validation_score(metrics: Dict[str, dict]) -> float:
    required = {"mae", "rmse", "mape"}
    complete = 0

    for values in metrics.values():
        if required.issubset(values.keys()) and all(
            v is not None and isfinite(float(v)) and float(v) >= 0
            for v in values.values()
        ):
            complete += 1

    return 100.0 * complete / 4.0


def model_error_score(metrics: Dict[str, dict]) -> float:
    avg = mean_mape(metrics)

    if avg is None:
        return 0.0

    return clamp(100.0 * (1.0 - avg / REFERENCE_MAPE))


def classify_risk(
    confidence: Optional[float],
    dispersion: Optional[float],
    agreement: str,
) -> str:
    if confidence is None:
        return "UNASSESSED"

    if agreement == "MODEL_DISAGREEMENT" or (
        dispersion is not None and dispersion < 50
    ):
        return "HIGH"

    if confidence >= 75:
        return "LOW"

    if confidence >= 55:
        return "MODERATE"

    return "HIGH"


def build_30_day_result() -> dict:
    context = _context()
    ensemble = context["ensemble"]["30"]
    metrics = context["metrics"]
    latest_price = context["latest_price"]

    v_score = validation_score(metrics)
    a_score = agreement_score(ensemble["agreement"])
    d_score = dispersion_score(
        ensemble["spread"],
        latest_price,
    )
    e_score = model_error_score(metrics)

    confidence = round(
        clamp(
            0.25 * v_score
            + 0.35 * e_score
            + 0.25 * a_score
            + 0.15 * d_score
        ),
        2,
    )

    return {
        "horizon": "30-trading-days",
        "status": ensemble["status"],
        "confidence_index": confidence,
        "risk_level": classify_risk(
            confidence,
            d_score,
            ensemble["agreement"],
        ),
        "validation_score": round(v_score, 2),
        "agreement_score": round(a_score, 2),
        "dispersion_score": round(d_score, 2),
        "model_error_score": round(e_score, 2),
        "expected_change_pct": ensemble["expected_change_pct"],
        "forecast_range": {
            "low": ensemble["range_low"],
            "high": ensemble["range_high"],
            "spread": ensemble["spread"],
        },
        "notes": [
            "Confidence is an evidence index, not a probability.",
            "The ensemble direction is generated from the current PostgreSQL-backed data.",
            "The forecast spread is measured across the current model forecasts.",
            "OOS metrics are chronological and use the canonical ICCO-DAILY-USD target.",
            "This layer does not issue a buy, hold or sell recommendation.",
        ],
    }


def main() -> None:
    result = build_30_day_result()
    context = _context()

    print("\n=== COCOA CONFIDENCE + RISK ENGINE ===")
    print(f"Target: {TARGET}")
    print(f"Latest observation: {context['latest_date']}")
    print(f"Latest price: {context['latest_price']:.2f} {UNIT}")
    print(f"Horizon: {result['horizon']}")
    print(f"Status: {result['status']}")
    print(f"Confidence index: {result['confidence_index']:.2f}/100")
    print(f"Risk level: {result['risk_level']}")
    print(f"Expected change: {result['expected_change_pct']:+.2f}%")

    rng = result["forecast_range"]
    print(
        f"Range: {rng['low']:.2f} - {rng['high']:.2f} {UNIT}"
    )
    print(f"Spread: {rng['spread']:.2f} {UNIT}")
    print("\nCONFIDENCE + RISK ENGINE: PASSED")


if __name__ == "__main__":
    main()
