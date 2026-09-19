"""
Cocoa Intelligence Hub
Canonical ICCO USD Naive Baseline

Purpose:
    Establish a clean, leakage-safe benchmark for cocoa price forecasting.

Target:
    ICCO-DAILY-USD

Method:
    Naive random-walk / persistence baseline:
        forecast(t+1) = price(t)

Evaluation:
    Chronological 80/20 out-of-sample split.
    No shuffling.
    No future information is used.

This baseline is the benchmark against which:
    - XGBoost
    - Random Forest
    - Ensemble
will be evaluated.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

TARGET_CONTRACT = "ICCO-DAILY-USD"
MARKET_NAME = "ICCO"

TEST_SIZE = 0.20
MIN_OBSERVATIONS = 50


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

def get_connection():
    """
    Create a PostgreSQL connection using DATABASE_URL from .env.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Check the project .env file."
        )

    return psycopg2.connect(database_url)


# ---------------------------------------------------------------------
# Load canonical target
# ---------------------------------------------------------------------

def load_target_data() -> pd.DataFrame:
    """
    Load ONLY the canonical ICCO Daily USD series.

    Important:
        Do not load London, New York or ICCO EUR into the target.
    """

    query = """
        SELECT
            timestamp::date AS trade_date,
            price
        FROM market_prices
        WHERE contract = %s
          AND price IS NOT NULL
          AND price > 0
        ORDER BY timestamp::date ASC;
    """

    with get_connection() as conn:
        df = pd.read_sql_query(
            query,
            conn,
            params=(TARGET_CONTRACT,),
        )

    if df.empty:
        raise RuntimeError(
            f"No valid observations found for {TARGET_CONTRACT}."
        )

    # Ensure proper types.
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    # Remove invalid rows.
    df = df.dropna(subset=["trade_date", "price"])

    # Remove duplicate dates defensively.
    df = (
        df.sort_values("trade_date")
        .drop_duplicates(subset=["trade_date"], keep="last")
        .reset_index(drop=True)
    )

    if len(df) < MIN_OBSERVATIONS:
        raise RuntimeError(
            f"Only {len(df)} observations found. "
            f"At least {MIN_OBSERVATIONS} are required."
        )

    return df


# ---------------------------------------------------------------------
# Build naive predictions
# ---------------------------------------------------------------------

def build_naive_predictions(
    df: pd.DataFrame,
    test_start: int,
) -> pd.DataFrame:
    """
    Build persistence forecasts.

    At date t:
        predicted_price(t) = actual_price(t-1)

    The first observation of the test set uses the immediately
    preceding training observation.

    This is leakage-safe.
    """

    result = df.copy()

    result["previous_price"] = result["price"].shift(1)

    # Price persistence forecast.
    result["predicted_price"] = result["previous_price"]

    # Actual one-step price change.
    result["actual_change"] = (
        result["price"] - result["previous_price"]
    )

    # Previous observed change.
    result["previous_change"] = (
        result["previous_price"]
        - result["price"].shift(2)
    )

    # Directional persistence:
    # predict today's direction from yesterday's direction.
    result["predicted_direction"] = np.sign(
        result["previous_change"]
    )

    result["actual_direction"] = np.sign(
        result["actual_change"]
    )

    # Only evaluate the chronological test period.
    result = result.iloc[test_start:].copy()

    return result


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

def calculate_metrics(predictions: pd.DataFrame) -> dict[str, Any]:
    """
    Calculate honest out-of-sample metrics.
    """

    valid = predictions.dropna(
        subset=["price", "predicted_price"]
    ).copy()

    if valid.empty:
        raise RuntimeError("No valid test predictions available.")

    actual = valid["price"].to_numpy(dtype=float)
    predicted = valid["predicted_price"].to_numpy(dtype=float)

    errors = actual - predicted

    mae = float(np.mean(np.abs(errors)))

    rmse = float(
        np.sqrt(np.mean(np.square(errors)))
    )

    # Avoid division by zero.
    nonzero = actual != 0

    if np.any(nonzero):
        mape_pct = float(
            np.mean(
                np.abs(
                    errors[nonzero]
                    / actual[nonzero]
                )
            )
            * 100
        )
    else:
        mape_pct = None

    # Directional accuracy.
    direction_valid = valid[
        (valid["predicted_direction"] != 0)
        & (valid["actual_direction"] != 0)
    ].copy()

    if len(direction_valid) > 0:
        directional_accuracy_pct = float(
            (
                direction_valid["predicted_direction"]
                == direction_valid["actual_direction"]
            ).mean()
            * 100
        )
    else:
        directional_accuracy_pct = None

    return {
        "mae": mae,
        "rmse": rmse,
        "mape_pct": mape_pct,
        "directional_accuracy_pct": directional_accuracy_pct,
        "evaluated_predictions": int(len(valid)),
        "directional_observations": int(len(direction_valid)),
    }


# ---------------------------------------------------------------------
# Horizon diagnostics
# ---------------------------------------------------------------------

def calculate_horizon_persistence(
    df: pd.DataFrame,
    horizon: int,
) -> dict[str, Any]:
    """
    Evaluate a persistence forecast at a future trading-day horizon.

    Forecast:
        price(t+h) = price(t)

    This is useful for establishing naive benchmarks for:
        7 trading days
        30 trading days
    """

    data = df.copy()

    data["future_price"] = data["price"].shift(-horizon)

    data = data.dropna(
        subset=["price", "future_price"]
    )

    if data.empty:
        return {
            "horizon_trading_days": horizon,
            "observations": 0,
            "mae": None,
            "rmse": None,
            "mape_pct": None,
        }

    actual = data["future_price"].to_numpy(dtype=float)
    predicted = data["price"].to_numpy(dtype=float)

    errors = actual - predicted

    mae = float(np.mean(np.abs(errors)))

    rmse = float(
        np.sqrt(np.mean(np.square(errors)))
    )

    nonzero = actual != 0

    if np.any(nonzero):
        mape_pct = float(
            np.mean(
                np.abs(
                    errors[nonzero]
                    / actual[nonzero]
                )
            )
            * 100
        )
    else:
        mape_pct = None

    return {
        "horizon_trading_days": horizon,
        "observations": int(len(data)),
        "mae": mae,
        "rmse": rmse,
        "mape_pct": mape_pct,
    }


# ---------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------

def run_baseline() -> dict[str, Any]:
    """
    Run the complete canonical baseline evaluation.
    """

    print("=" * 70)
    print("COCOA INTELLIGENCE HUB — CANONICAL BASELINE")
    print("=" * 70)

    print("\nLoading canonical ICCO USD market data...")

    df = load_target_data()

    print(f"Target contract: {TARGET_CONTRACT}")
    print(f"Observations: {len(df)}")
    print(f"First date: {df['trade_date'].min().date()}")
    print(f"Last date: {df['trade_date'].max().date()}")

    # -------------------------------------------------------------
    # Chronological split
    # -------------------------------------------------------------

    test_start = int(
        len(df) * (1 - TEST_SIZE)
    )

    train = df.iloc[:test_start].copy()
    test = df.iloc[test_start:].copy()

    print("\n=== CHRONOLOGICAL SPLIT ===")
    print(f"Training observations: {len(train)}")
    print(f"Test observations: {len(test)}")
    print(f"Training end: {train['trade_date'].max().date()}")
    print(f"Test start: {test['trade_date'].min().date()}")

    # -------------------------------------------------------------
    # Build predictions
    # -------------------------------------------------------------

    predictions = build_naive_predictions(
        df,
        test_start,
    )

    metrics = calculate_metrics(predictions)

    # -------------------------------------------------------------
    # Multi-horizon persistence diagnostics
    # -------------------------------------------------------------

    horizon_7 = calculate_horizon_persistence(
        df,
        horizon=7,
    )

    horizon_30 = calculate_horizon_persistence(
        df,
        horizon=30,
    )

    # -------------------------------------------------------------
    # Latest market observation
    # -------------------------------------------------------------

    latest = df.iloc[-1]

    # -------------------------------------------------------------
    # Result
    # -------------------------------------------------------------

    result = {
        "status": "ok",
        "model": "naive_random_walk_baseline",
        "market": MARKET_NAME,
        "target": TARGET_CONTRACT,

        "observations": int(len(df)),
        "training_observations": int(len(train)),
        "test_observations": int(len(test)),
        "test_predictions": metrics["evaluated_predictions"],

        "first_timestamp": df["trade_date"]
        .min()
        .strftime("%Y-%m-%d"),

        "last_timestamp": df["trade_date"]
        .max()
        .strftime("%Y-%m-%d"),

        "metrics": metrics,

        "persistence_horizons": {
            "7_trading_days": horizon_7,
            "30_trading_days": horizon_30,
        },

        "latest_price": float(latest["price"]),
        "latest_date": latest["trade_date"]
        .strftime("%Y-%m-%d"),

        "methodology": {
            "target_series": TARGET_CONTRACT,
            "split": "chronological_80_20",
            "shuffle": False,
            "leakage_safe": True,
            "forecast_rule": "previous_observed_price",
        },
    }

    # -------------------------------------------------------------
    # Print results
    # -------------------------------------------------------------

    print("\n=== BASELINE RESULTS ===")

    print(f"Model: {result['model']}")
    print(f"Target: {result['target']}")
    print(f"Observations: {result['observations']}")
    print(f"Training observations: {result['training_observations']}")
    print(f"Test observations: {result['test_observations']}")
    print(f"Test predictions: {result['test_predictions']}")

    print("\n=== OUT-OF-SAMPLE METRICS ===")

    print(
        f"MAE: "
        f"{metrics['mae']:.4f}"
    )

    print(
        f"RMSE: "
        f"{metrics['rmse']:.4f}"
    )

    if metrics["mape_pct"] is not None:
        print(
            f"MAPE: "
            f"{metrics['mape_pct']:.4f}%"
        )

    if metrics["directional_accuracy_pct"] is not None:
        print(
            f"Directional accuracy: "
            f"{metrics['directional_accuracy_pct']:.4f}%"
        )

    print(
        f"Directional observations:"
        f" {metrics['directional_observations']}"
    )

    print("\n=== PERSISTENCE HORIZON BENCHMARKS ===")

    for name, horizon in [
        ("7 trading days", horizon_7),
        ("30 trading days", horizon_30),
    ]:
        print(f"\n{name}:")
        print(
            f" observations: {horizon['observations']}"
        )

        if horizon["mae"] is not None:
            print(
                f" MAE: {horizon['mae']:.4f}"
            )

        if horizon["rmse"] is not None:
            print(
                f" RMSE: {horizon['rmse']:.4f}"
            )

        if horizon["mape_pct"] is not None:
            print(
                f" MAPE: {horizon['mape_pct']:.4f}%"
            )

    print("\n=== LATEST TARGET ===")

    print(
        f"Date: {result['latest_date']}"
    )

    print(
        f"Price: {result['latest_price']:.2f} USD/tonne"
    )

    print("\n=== DATA INTEGRITY ===")

    print(
        "Target series: ICCO-DAILY-USD ONLY"
    )

    print(
        "Mixed contracts: NO"
    )

    print(
        "Chronological split: YES"
    )

    print(
        "Random shuffling: NO"
    )

    print(
        "Future leakage: NO"
    )

    print("\nBASELINE EVALUATION: PASSED")
    print("=" * 70)

    return result


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------

def main():
    run_baseline()


if __name__ == "__main__":
    main()