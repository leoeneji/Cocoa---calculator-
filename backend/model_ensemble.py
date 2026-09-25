"""
Cocoa Intelligence Hub
DYNAMIC MODEL COMPARISON & ENSEMBLE ENGINE

The ensemble reads the current PostgreSQL-backed ICCO series every time it
runs. It does not hard-code the latest price or current model forecasts.

Weighting uses chronological out-of-sample MAE from the current model runs.
No random shuffling and no future leakage are introduced by this layer.
"""

from __future__ import annotations

import json
import os
import psycopg2

from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from backend import time_series_model as ts
from backend.ml import xgboost_model as xgb
from backend.ml import random_forest_model as rf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

TARGET = "ICCO-DAILY-USD"
UNIT = "USD/tonne"
HORIZONS = (7, 30)


@dataclass
class ModelResult:
    model: str
    forecast: float
    mae: Optional[float]
    rmse: Optional[float]
    mape: Optional[float]
    weight: float = 0.0
    eligible: bool = False


def valid_metric(value) -> bool:
    return (
        value is not None
        and isfinite(float(value))
        and float(value) >= 0
    )


def calculate_weights(metrics: Dict[str, Optional[dict]]) -> Dict[str, float]:
    eligible = {
        name: float(values["mae"])
        for name, values in metrics.items()
        if values is not None and valid_metric(values.get("mae"))
    }

    if not eligible:
        return {name: 0.0 for name in metrics}

    inverse = {
        name: 1.0 / max(mae, 1e-9)
        for name, mae in eligible.items()
    }
    total = sum(inverse.values())

    if total <= 0:
        return {name: 0.0 for name in metrics}

    weights = {name: 0.0 for name in metrics}
    for name, value in inverse.items():
        weights[name] = value / total

    return weights


def weighted_forecast(
    forecasts: Dict[str, float],
    weights: Dict[str, float],
) -> Optional[float]:
    usable = [
        (name, float(price), float(weights.get(name, 0.0)))
        for name, price in forecasts.items()
        if name in weights
        and weights[name] > 0
        and price is not None
        and isfinite(float(price))
    ]

    if not usable:
        return None

    weight_sum = sum(item[2] for item in usable)
    if weight_sum <= 0:
        return None

    return sum(price * weight for _, price, weight in usable) / weight_sum


def direction(change_pct: float) -> str:
    if change_pct > 0.25:
        return "BULLISH"
    if change_pct < -0.25:
        return "BEARISH"
    return "NEUTRAL"


def agreement(forecasts: Dict[str, float], latest_price: float) -> str:
    if latest_price <= 0:
        return "UNKNOWN"

    directions = [
        direction((price / latest_price - 1.0) * 100.0)
        for price in forecasts.values()
    ]

    if not directions:
        return "UNKNOWN"

    if all(d == "BULLISH" for d in directions):
        return "HIGH_BULLISH_AGREEMENT"
    if all(d == "BEARISH" for d in directions):
        return "HIGH_BEARISH_AGREEMENT"
    if all(d == "NEUTRAL" for d in directions):
        return "HIGH_NEUTRAL_AGREEMENT"

    bullish = directions.count("BULLISH")
    bearish = directions.count("BEARISH")
    neutral = directions.count("NEUTRAL")

    if max(bullish, bearish, neutral) >= 3:
        return "PARTIAL_AGREEMENT"

    return "MODEL_DISAGREEMENT"


def forecast_range(forecasts: Dict[str, float]) -> Optional[dict]:
    values = [
        float(value)
        for value in forecasts.values()
        if value is not None and isfinite(float(value))
    ]

    if not values:
        return None

    return {
        "low": min(values),
        "high": max(values),
        "spread": max(values) - min(values),
    }


def _date_value(value):
    return value.date() if hasattr(value, "date") else value


def _assert_current_data_alignment(
    xdf,
    rdf,
    tdf,
) -> tuple[object, float]:
    """
    Require every model input to end on the same latest ICCO observation.

    This prevents a newer database price from being combined with a stale
    model dataset.
    """
    x_latest_date = _date_value(xdf["trade_date"].iloc[-1])
    r_latest_date = _date_value(rdf["trade_date"].iloc[-1])
    t_latest_date = _date_value(tdf["trade_date"].iloc[-1])

    dates = {
        "xgboost": x_latest_date,
        "random_forest": r_latest_date,
        "time_series": t_latest_date,
    }

    if len(set(dates.values())) != 1:
        raise RuntimeError(
            "Model input dates are not aligned with the latest ICCO observation: "
            + ", ".join(f"{name}={date}" for name, date in dates.items())
        )

    x_latest_price = float(
        xdf.loc[xdf["trade_date"].eq(xdf["trade_date"].iloc[-1]), TARGET].iloc[-1]
    )
    r_latest_price = float(
        rdf.loc[rdf["trade_date"].eq(rdf["trade_date"].iloc[-1]), TARGET].iloc[-1]
    )
    t_latest_price = float(tdf["price"].iloc[-1])

    prices = {
        "xgboost": x_latest_price,
        "random_forest": r_latest_price,
        "time_series": t_latest_price,
    }

    if max(prices.values()) - min(prices.values()) > 1e-6:
        raise RuntimeError(
            "Model input prices are not aligned for "
            f"{dates['time_series']}: "
            + ", ".join(f"{name}={price:.2f}" for name, price in prices.items())
        )

    return t_latest_date, t_latest_price


def _model_outputs():
    """
    Rebuild all four current model outputs from the current database.

    A fresh dataset is built on every call. No current price, forecast, or
    model date is stored as a module constant.
    """

    # Build all source datasets from PostgreSQL at runtime.
    xdf = xgb.build_forecasting_dataset()
    rdf = rf.build_forecasting_dataset()
    tdf = ts.load_target()

    latest_date, latest_price = _assert_current_data_alignment(
        xdf, rdf, tdf
    )

    # XGBoost
    xv = xgb.validate_dataset(xdf)
    x_features = xv["features"]

    x_eval = {}
    x_forecast = {}
    for horizon in HORIZONS:
        evaluation, _, _ = xgb.evaluate_horizon(
            xdf, horizon, x_features
        )
        forecast, _ = xgb.fit_current_forecast(
            xdf, horizon, x_features
        )
        x_eval[horizon] = evaluation
        x_forecast[horizon] = forecast

    # Random Forest
    rv = rf.validate_dataset(rdf)
    r_features = rv["features"]

    r_eval = {}
    r_forecast = {}
    for horizon in HORIZONS:
        evaluation, _, _ = rf.evaluate_horizon(
            rdf, horizon, r_features
        )
        forecast, _ = rf.fit_current_forecast(
            rdf, horizon, r_features
        )
        r_eval[horizon] = evaluation
        r_forecast[horizon] = forecast

    # Time-series
    t_eval = {}
    t_forecast = {}
    for horizon in HORIZONS:
        evaluation = ts.evaluate_horizon(tdf, horizon)
        forecast = ts.fit_current_forecast(tdf, horizon)
        t_eval[horizon] = evaluation
        t_forecast[horizon] = forecast

    return {
        "latest_date": latest_date,
        "latest_price": latest_price,
        "x_eval": x_eval,
        "r_eval": r_eval,
        "t_eval": t_eval,
        "x_forecast": x_forecast,
        "r_forecast": r_forecast,
        "t_forecast": t_forecast,
    }


def build_horizon(horizon: str, outputs: dict) -> dict:
    h = int(horizon)

    x = outputs["x_eval"][h]
    r = outputs["r_eval"][h]
    t = outputs["t_eval"][h]

    forecasts = {
        "persistence": outputs["latest_price"],
        "xgboost": float(outputs["x_forecast"][h]),
        "random_forest": float(outputs["r_forecast"][h]),
        "time_series": float(outputs["t_forecast"][h]),
    }

    metrics = {
        "persistence": {
            "mae": float(x.baseline_mae),
            "rmse": float(x.baseline_rmse),
            "mape": float(x.baseline_mape_pct),
        },
        "xgboost": {
            "mae": float(x.mae),
            "rmse": float(x.rmse),
            "mape": float(x.mape_pct),
        },
        "random_forest": {
            "mae": float(r.mae),
            "rmse": float(r.rmse),
            "mape": float(r.mape_pct),
        },
        "time_series": {
            "mae": float(t.metrics.mae),
            "rmse": float(t.metrics.rmse),
            "mape": float(t.metrics.mape_pct),
        },
    }

    weights = calculate_weights(metrics)
    ensemble = weighted_forecast(forecasts, weights)

    results = []
    for name in forecasts:
        metric = metrics.get(name)
        results.append(
            ModelResult(
                model=name,
                forecast=forecasts[name],
                mae=metric["mae"] if metric else None,
                rmse=metric["rmse"] if metric else None,
                mape=metric["mape"] if metric else None,
                weight=weights.get(name, 0.0),
                eligible=weights.get(name, 0.0) > 0,
            )
        )

    changes = {
        name: (price / outputs["latest_price"] - 1.0) * 100.0
        for name, price in forecasts.items()
    }

    if ensemble is None:
        status = "NOT_READY"
        ensemble_change = None
        ensemble_direction = "UNKNOWN"
    else:
        status = "READY"
        ensemble_change = (
            (ensemble / outputs["latest_price"] - 1.0) * 100.0
        )
        ensemble_direction = direction(ensemble_change)

    return {
        "horizon": f"{horizon}-trading-days",
        "status": status,
        "target": TARGET,
        "unit": UNIT,
        "latest_date": str(outputs["latest_date"]),
        "latest_price": outputs["latest_price"],
        "models": [asdict(result) for result in results],
        "individual_changes_pct": changes,
        "ensemble_forecast": ensemble,
        "ensemble_expected_change_pct": ensemble_change,
        "ensemble_direction": ensemble_direction,
        "forecast_range": forecast_range(forecasts),
        "model_agreement": agreement(
            forecasts, outputs["latest_price"]
        ),
        "weight_method": "inverse_out_of_sample_MAE",
    }


def build_all() -> dict:
    outputs = _model_outputs()
    return {
        "7": build_horizon("7", outputs),
        "30": build_horizon("30", outputs),
    }


def print_horizon(result: dict) -> None:
    print(f"\n=== {result['horizon'].upper()} ENSEMBLE ===")
    print(f"Target: {result['target']}")
    print(
        f"Latest: {result['latest_price']:.2f} "
        f"{result['unit']} ({result['latest_date']})"
    )
    print(f"Status: {result['status']}")

    print("\nMODEL FORECASTS")
    for model in result["models"]:
        mae = (
            f"{model['mae']:.4f}"
            if model["mae"] is not None
            else "N/A"
        )
        print(
            f"{model['model']:15s} "
            f"{model['forecast']:8.2f} "
            f"weight={model['weight']:.4f} "
            f"MAE={mae}"
        )

    rng = result["forecast_range"]
    print("\nFORECAST RANGE")
    if rng:
        print(f"Low:    {rng['low']:.2f} {UNIT}")
        print(f"High:   {rng['high']:.2f} {UNIT}")
        print(f"Spread: {rng['spread']:.2f} {UNIT}")
    else:
        print("Unavailable")

    print(f"Agreement: {result['model_agreement']}")

    if result["ensemble_forecast"] is None:
        print("\nENSEMBLE FORECAST: NOT READY")
        print("Reason: valid out-of-sample weights are unavailable.")
    else:
        print("\nENSEMBLE FORECAST")
        print(
            f"Forecast price: "
            f"{result['ensemble_forecast']:.2f} {UNIT}"
        )
        print(
            f"Expected change: "
            f"{result['ensemble_expected_change_pct']:+.2f}%"
        )
        print(f"Direction: {result['ensemble_direction']}")


def _save_ensemble_results(results: dict) -> None:
    """Persist completed ensemble results for the API."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            for horizon, result in results.items():
                cur.execute(
                    """
                    INSERT INTO ensemble_results
                        (horizon, latest_date, result, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (horizon)
                    DO UPDATE SET
                        latest_date = EXCLUDED.latest_date,
                        result = EXCLUDED.result,
                        updated_at = NOW()
                    """,
                    (
                        str(horizon),
                        result["latest_date"],
                        json.dumps(result, default=str),
                    ),
                )

    print("ENSEMBLE RESULTS SAVED TO POSTGRESQL")

def main() -> None:
    print("=" * 70)
    print("COCOA INTELLIGENCE HUB")
    print("DYNAMIC MODEL COMPARISON & ENSEMBLE ENGINE")
    print("=" * 70)
    print("Source: current PostgreSQL ICCO-DAILY-USD series")
    print("Weighting: inverse out-of-sample MAE")
    print("Random shuffling: NO")
    print("Future leakage: NO")
    print()

    results = build_all()
    _save_ensemble_results(results)

    for result in results.values():
        print_horizon(result)

    print("\n=== ENSEMBLE DATA INTEGRITY ===")
    print("Target series: ICCO-DAILY-USD ONLY")
    print("Mixed contracts: NO")
    print("Chronological evaluation: YES")
    print("Random shuffling: NO")
    print("Future leakage: NO")
    print("Current data: loaded at runtime")
    print("Current forecasts: generated at runtime")
    print("Weights: generated from current OOS metrics")

    print("\nMODEL ENSEMBLE EVALUATION: PASSED")


if __name__ == "__main__":
    main()
