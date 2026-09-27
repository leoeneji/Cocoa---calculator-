""" Lag-aware walk-forward backtest for Cocoa Intelligence Hub. Key rule: - ICCO is treated as one trading-day lagged relative to the live market date. - A forecast issued on `as_of_date` may use the latest completed ICCO observation on the immediately preceding ICCO trading observation. - The model origin is therefore `origin_date`; the customer-facing `as_of_date` is the next available ICCO trading date. - Weekends are not counted because dates come from the canonical ICCO trading observations. """

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from backend.ml.xgboost_model import (
    MIN_TRAIN_ROWS,
    TARGET_CONTRACT,
    build_forecasting_dataset,
    calculate_metrics,
    get_feature_columns,
    make_model,
)

HORIZONS = (7, 30)
BACKTEST_STEP = int(os.getenv("BACKTEST_STEP", "5"))
OUTPUT_DIR = Path("data")


def next_available_trading_date(dates: pd.Series, i: int):
    """Return the next observed ICCO trading date after origin i."""
    if i + 1 >= len(dates):
        return pd.NaT
    return dates.iloc[i + 1]


def walk_forward(df: pd.DataFrame, horizon: int, features: list[str]) -> pd.DataFrame:
    target_col = f"target_{horizon}d"
    work = df.sort_values("trade_date").reset_index(drop=True).copy()
    dates = pd.to_datetime(work["trade_date"]).dt.normalize()
    work["trade_date"] = dates

    results = []

    # i is the information origin: everything known at origin i is available.
    # The customer-facing forecast date is the next observed trading date.
    first_origin = max(MIN_TRAIN_ROWS, 0)

    for i in range(first_origin, len(work) - horizon, BACKTEST_STEP):
        origin = work.iloc[i]
        target = work.iloc[i + horizon]

        if pd.isna(origin[TARGET_CONTRACT]) or pd.isna(target[TARGET_CONTRACT]):
            continue

        train = work.iloc[:i].copy()
        train = train[train[target_col].notna() & train[TARGET_CONTRACT].notna()].copy()

        if len(train) < MIN_TRAIN_ROWS:
            continue

        X_train = train[features].apply(pd.to_numeric, errors="coerce")
        X_pred = pd.DataFrame(
            [origin[features].to_dict()], columns=features
        ).apply(pd.to_numeric, errors="coerce")

        # Imputation parameters are learned from the training history only.
        medians = X_train.median()
        X_train = X_train.fillna(medians)
        X_pred = X_pred.fillna(medians)

        model = make_model()
        model.fit(
            X_train,
            train[target_col].astype(float).to_numpy(),
        )

        prediction = float(model.predict(X_pred)[0])
        actual = float(target[TARGET_CONTRACT])
        previous = float(origin[TARGET_CONTRACT])

        error = actual - prediction
        abs_error = abs(error)
        ape = abs(error) / abs(actual) * 100.0 if actual else np.nan

        actual_direction = np.sign(actual - previous)
        predicted_direction = np.sign(prediction - previous)

        results.append(
            {
                "as_of_date": next_available_trading_date(dates, i),
                "origin_date": dates.iloc[i],
                "target_date": dates.iloc[i + horizon],
                "horizon_trading_days": horizon,
                "origin_icco_usd": previous,
                "forecast_usd": prediction,
                "actual_icco_usd": actual,
                "error_usd": error,
                "absolute_error_usd": abs_error,
                "absolute_percentage_error": ape,
                "actual_direction": (
                    "UP" if actual_direction > 0
                    else "DOWN" if actual_direction < 0
                    else "FLAT"
                ),
                "predicted_direction": (
                    "UP" if predicted_direction > 0
                    else "DOWN" if predicted_direction < 0
                    else "FLAT"
                ),
                "direction_correct": (
                    bool(actual_direction == predicted_direction)
                    if actual_direction != 0
                    else np.nan
                ),
                "training_observations": len(train),
            }
        )

    return pd.DataFrame(results)


def summarize(results: pd.DataFrame, horizon: int) -> dict:
    if results.empty:
        return {
            "horizon": horizon,
            "observations": 0,
            "mae": np.nan,
            "rmse": np.nan,
            "mape_pct": np.nan,
            "directional_accuracy_pct": np.nan,
            "baseline_mae": np.nan,
            "baseline_rmse": np.nan,
            "baseline_mape_pct": np.nan,
        }

    actual = results["actual_icco_usd"].to_numpy(float)
    pred = results["forecast_usd"].to_numpy(float)
    previous = results["origin_icco_usd"].to_numpy(float)

    mae, rmse, mape, directional, directional_n = calculate_metrics(
        actual, pred, previous
    )
    b_mae, b_rmse, b_mape, _, _ = calculate_metrics(
        actual, previous, previous
    )

    return {
        "horizon": horizon,
        "observations": len(results),
        "mae": mae,
        "rmse": rmse,
        "mape_pct": mape,
        "directional_accuracy_pct": directional,
        "directional_observations": directional_n,
        "baseline_mae": b_mae,
        "baseline_rmse": b_rmse,
        "baseline_mape_pct": b_mape,
        "mae_improvement_vs_baseline": b_mae - mae,
        "rmse_improvement_vs_baseline": b_rmse - rmse,
    }


def main():
    print("=" * 78)
    print("COCOA INTELLIGENCE HUB — LAG-AWARE WALK-FORWARD BACKTEST")
    print("=" * 78)
    print("ICCO live-date rule: latest available ICCO observation is one")
    print("trading day behind the customer-facing market date.")
    print(f"Backtest step: every {BACKTEST_STEP} trading observations")
    print()

    df = build_forecasting_dataset()
    features = get_feature_columns(df)

    print(f"Canonical observations: {len(df)}")
    print(
        f"ICCO data range: {pd.to_datetime(df['trade_date']).min().date()} "
        f"to {pd.to_datetime(df['trade_date']).max().date()}"
    )
    print(f"Features: {len(features)}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for horizon in HORIZONS:
        print(f"\n--- {horizon}-TRADING-DAY BACKTEST ---")
        results = walk_forward(df, horizon, features)

        output_file = OUTPUT_DIR / f"backtest_lag_aware_{horizon}d.csv"
        results.to_csv(output_file, index=False)

        summary = summarize(results, horizon)
        summary_rows.append(summary)

        print(f"Observations tested: {summary['observations']}")
        if summary["observations"]:
            print(f"MAE: {summary['mae']:.2f}")
            print(f"RMSE: {summary['rmse']:.2f}")
            print(f"MAPE: {summary['mape_pct']:.2f}%")
            print(
                f"Directional accuracy: "
                f"{summary['directional_accuracy_pct']:.2f}%"
            )
            print(f"Persistence MAE: {summary['baseline_mae']:.2f}")
            print(f"Persistence RMSE: {summary['baseline_rmse']:.2f}")
            print(
                f"MAE improvement vs persistence: "
                f"{summary['mae_improvement_vs_baseline']:.2f}"
            )
            print(
                f"RMSE improvement vs persistence: "
                f"{summary['rmse_improvement_vs_baseline']:.2f}"
            )

            print("\nLast 5 test cases:")
            print(
                results[
                    [
                        "as_of_date",
                        "origin_date",
                        "target_date",
                        "origin_icco_usd",
                        "forecast_usd",
                        "actual_icco_usd",
                        "absolute_error_usd",
                        "direction_correct",
                    ]
                ].tail(5).to_string(index=False)
            )

        print(f"Saved: {output_file}")

    summary_file = OUTPUT_DIR / "backtest_lag_aware_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_file, index=False)

    print("\n" + "=" * 78)
    print("BACKTEST COMPLETE")
    print(f"Summary: {summary_file}")
    print("=" * 78)


if __name__ == "__main__":
    main()
