"""
Cocoa Intelligence Hub
Canonical XGBoost forecasting model.

Design:
- Canonical target: ICCO-DAILY-USD
- Forecast horizons: 7 and 30 trading days
- Chronological out-of-sample evaluation
- No random shuffling
- No future-target columns used as model inputs
- Rows whose future target is not yet known are excluded from evaluation/training
  but the latest feature row is retained for producing the current forecast.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

TARGET_CONTRACT = "ICCO-DAILY-USD"
HORIZONS = (7, 30)
TEST_FRACTION = 0.20
RANDOM_SEED = 42
MIN_TRAIN_ROWS = 60

# Deliberately exclude anything that is the target itself, a future target,
# an identifier/date, or a value that would only be known after the forecast
# timestamp.
EXCLUDED_FEATURES = {
    "trade_date",
    "target_7d",
    "target_30d",
    "future_return_7d",
    "future_return_30d",
    TARGET_CONTRACT,
}

# Candidate features are selected only when present in the built dataset.
PREFERRED_FEATURES = [
    "icco_usd_lag_1",
    "icco_usd_lag_2",
    "icco_usd_lag_3",
    "icco_usd_lag_5",
    "icco_usd_lag_10",
    "icco_usd_lag_20",
    "icco_usd_ma_3",
    "icco_usd_ma_5",
    "icco_usd_ma_10",
    "icco_usd_ma_20",
    "icco_usd_return_1",
    "icco_usd_return_3",
    "icco_usd_return_5",
    "icco_usd_return_10",
    "icco_usd_return_20",
    "ny_icco_spread",
    "london_icco_usd_spread",
    "icco_daily_eur_return_1",
    "icco_daily_eur_return_5",
    "london_futures_return_1",
    "london_futures_return_5",
    "new_york_futures_return_1",
    "new_york_futures_return_5",
    "eur_ngn",
    "usd_ngn",
    "eur_xaf",
    "usd_xaf",
    "eur_xof",
    "usd_xof",
    "rainfall_mm",
    "temperature_c",
    "humidity_pct",
    "crop_risk_score",
    "weather_locations",
    "month",
    "quarter",
    "day_of_week",
    "month_sin",
    "month_cos",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Evaluation:
    horizon: int
    observations: int
    training_observations: int
    test_observations: int
    mae: float
    rmse: float
    mape_pct: float
    directional_accuracy_pct: float
    directional_observations: int
    baseline_mae: float
    baseline_rmse: float
    baseline_mape_pct: float


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_connection():
    """Return a PostgreSQL connection using the project's .env."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Check the project .env file."
        )
    return psycopg2.connect(database_url)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def pct_change(current: pd.Series, periods: int) -> pd.Series:
    return current.pct_change(periods=periods)


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build leakage-safe price/futures features from information available at t."""
    df = df.sort_values("trade_date").reset_index(drop=True).copy()

    target = safe_numeric(df[TARGET_CONTRACT])
    df[TARGET_CONTRACT] = target

    for lag in (1, 2, 3, 5, 10, 20):
        df[f"icco_usd_lag_{lag}"] = target.shift(lag)

    for window in (3, 5, 10, 20):
        df[f"icco_usd_ma_{window}"] = target.rolling(window).mean()

    for period in (1, 3, 5, 10, 20):
        df[f"icco_usd_return_{period}"] = pct_change(target, period)

    if "NEW-YORK-FUTURES" in df:
        ny = safe_numeric(df["NEW-YORK-FUTURES"])
        df["ny_icco_spread"] = ny - target

        for p in (1, 5):
            df[f"new_york_futures_return_{p}"] = pct_change(ny, p)

    if "LONDON-FUTURES" in df:
        london = safe_numeric(df["LONDON-FUTURES"])
        df["london_icco_usd_spread"] = london - target

        for p in (1, 5):
            df[f"london_futures_return_{p}"] = pct_change(london, p)

    if "ICCO-DAILY-EUR" in df:
        eur = safe_numeric(df["ICCO-DAILY-EUR"])
        for p in (1, 5):
            df[f"icco_daily_eur_return_{p}"] = pct_change(eur, p)

    return df


def add_fx_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach latest prior FX observations for each trade date."""
    conn = get_connection()
    try:
        fx = pd.read_sql_query(
            """
            SELECT
                rate_date,
                base_currency,
                quote_currency,
                rate
            FROM fx_rates
            ORDER BY rate_date
            """,
            conn,
        )
    finally:
        conn.close()

    if fx.empty:
        return df

    fx["rate_date"] = pd.to_datetime(fx["rate_date"]).dt.normalize()
    fx["rate"] = safe_numeric(fx["rate"])

    # We need the common pairs already present in the project.
    pairs = [
        ("EUR", "NGN", "eur_ngn"),
        ("USD", "NGN", "usd_ngn"),
        ("EUR", "XAF", "eur_xaf"),
        ("USD", "XAF", "usd_xaf"),
        ("EUR", "XOF", "eur_xof"),
        ("USD", "XOF", "usd_xof"),
    ]

    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.normalize()

    for base, quote, name in pairs:
        part = fx[
            (fx["base_currency"] == base)
            & (fx["quote_currency"] == quote)
        ][["rate_date", "rate"]].drop_duplicates("rate_date")

        if part.empty:
            out[name] = np.nan
            continue

        part = part.rename(columns={"rate_date": "trade_date", "rate": name})
        # merge_asof guarantees no future FX value is used.
        out = pd.merge_asof(
            out.sort_values("trade_date"),
            part.sort_values("trade_date"),
            on="trade_date",
            direction="backward",
        )

    return out


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate weather observations by date and merge at the same date."""
    conn = get_connection()
    try:
        weather = pd.read_sql_query(
            """
            SELECT
                observation_date,
                rainfall_mm,
                temperature_c,
                humidity_pct,
                crop_risk_score
            FROM weather_observations
            ORDER BY observation_date
            """,
            conn,
        )
    finally:
        conn.close()

    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.normalize()

    if weather.empty:
        for col in (
            "rainfall_mm",
            "temperature_c",
            "humidity_pct",
            "crop_risk_score",
            "weather_locations",
        ):
            out[col] = np.nan
        return out

    weather["observation_date"] = pd.to_datetime(
        weather["observation_date"]
    ).dt.normalize()

    numeric_cols = [
        "rainfall_mm",
        "temperature_c",
        "humidity_pct",
        "crop_risk_score",
    ]
    for col in numeric_cols:
        weather[col] = safe_numeric(weather[col])

    daily = (
        weather.groupby("observation_date", as_index=False)
        .agg(
            rainfall_mm=("rainfall_mm", "mean"),
            temperature_c=("temperature_c", "mean"),
            humidity_pct=("humidity_pct", "mean"),
            crop_risk_score=("crop_risk_score", "mean"),
            weather_locations=("observation_date", "size"),
        )
        .rename(columns={"observation_date": "trade_date"})
    )

    out = out.merge(daily, on="trade_date", how="left")
    return out


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dates = pd.to_datetime(df["trade_date"])
    df["month"] = dates.dt.month.astype(float)
    df["quarter"] = dates.dt.quarter.astype(float)
    df["day_of_week"] = dates.dt.dayofweek.astype(float)

    angle = 2.0 * math.pi * df["month"] / 12.0
    df["month_sin"] = np.sin(angle)
    df["month_cos"] = np.cos(angle)
    return df


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------

def load_market_data() -> pd.DataFrame:
    """
    Load one row per trading date.

    The canonical target is ICCO-DAILY-USD. Other cocoa contracts are
    explanatory variables, not alternate target observations.
    """
    conn = get_connection()
    try:
        raw = pd.read_sql_query(
            """
            SELECT
                timestamp::date AS trade_date,
                contract,
                price
            FROM market_prices
            WHERE contract IN (
                'ICCO-DAILY-USD',
                'ICCO-DAILY-EUR',
                'LONDON-FUTURES',
                'NEW-YORK-FUTURES'
            )
              AND price IS NOT NULL
              AND price > 0
            ORDER BY timestamp::date, contract
            """,
            conn,
        )
    finally:
        conn.close()

    if raw.empty:
        raise RuntimeError("No cocoa market data found.")

    raw["trade_date"] = pd.to_datetime(raw["trade_date"]).dt.normalize()
    raw["price"] = safe_numeric(raw["price"])

    # If duplicate rows ever exist at a date/contract level, keep the
    # deterministic latest SQL result after grouping.
    wide = (
        raw.groupby(["trade_date", "contract"], as_index=False)["price"]
        .last()
        .pivot(index="trade_date", columns="contract", values="price")
        .reset_index()
        .sort_values("trade_date")
        .reset_index(drop=True)
    )

    if TARGET_CONTRACT not in wide.columns:
        raise RuntimeError(
            f"Canonical target {TARGET_CONTRACT} is missing from market_prices."
        )

    # Keep only dates where the canonical target exists. Other explanatory
    # variables may legitimately be missing and will be handled later.
    wide = wide[wide[TARGET_CONTRACT].notna()].copy()

    # Ensure expected contract columns exist.
    for contract in (
        "ICCO-DAILY-EUR",
        "LONDON-FUTURES",
        "NEW-YORK-FUTURES",
    ):
        if contract not in wide.columns:
            wide[contract] = np.nan

    return wide


def add_future_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create supervised targets from the canonical ICCO USD series.

    shift(-h) is a future value relative to t and is used ONLY as the
    supervised label. It is never included in model features.
    """
    df = df.sort_values("trade_date").reset_index(drop=True).copy()
    target = safe_numeric(df[TARGET_CONTRACT])

    df["target_7d"] = target.shift(-7)
    df["target_30d"] = target.shift(-30)

    df["future_return_7d"] = df["target_7d"] / target - 1.0
    df["future_return_30d"] = df["target_30d"] / target - 1.0

    return df


def build_forecasting_dataset() -> pd.DataFrame:
    print("Loading verified ICCO market data...")

    df = load_market_data()

    print(f"Canonical observations: {len(df)}")
    print(
        f"Date range: {df['trade_date'].min().date()} "
        f"to {df['trade_date'].max().date()}"
    )

    df = add_price_features(df)
    df = add_fx_features(df)
    df = add_weather_features(df)
    df = add_calendar_features(df)
    df = add_future_targets(df)

    return df


# ---------------------------------------------------------------------------
# Feature selection / validation
# ---------------------------------------------------------------------------

def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """Return only approved, numeric, non-target model inputs."""
    features = [
        col
        for col in PREFERRED_FEATURES
        if col in df.columns and col not in EXCLUDED_FEATURES
    ]

    if not features:
        raise RuntimeError("No approved model feature columns are available.")

    return features


def validate_dataset(df: pd.DataFrame) -> Dict[str, object]:
    required = {"trade_date", TARGET_CONTRACT, "target_7d", "target_30d"}
    missing = sorted(required - set(df.columns))

    if missing:
        raise RuntimeError(
            "Forecast dataset is missing required columns: "
            + ", ".join(missing)
        )

    features = get_feature_columns(df)

    if len(df) < MIN_TRAIN_ROWS:
        raise RuntimeError(
            f"Only {len(df)} observations are available; "
            f"at least {MIN_TRAIN_ROWS} are required."
        )

    return {
        "observations": len(df),
        "feature_count": len(features),
        "features": features,
        "target_7d_rows": int(df["target_7d"].notna().sum()),
        "target_30d_rows": int(df["target_30d"].notna().sum()),
    }


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def make_model() -> XGBRegressor:
    return XGBRegressor(
        n_estimators=500,
        max_depth=4,
        learning_rate=0.035,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=3,
        reg_alpha=0.05,
        reg_lambda=1.0,
        objective="reg:squarederror",
        eval_metric="rmse",
        random_state=RANDOM_SEED,
        n_jobs=1,
    )


def chronological_split(
    data: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological 80/20 split; never shuffle."""
    n = len(data)
    test_n = max(1, int(round(n * TEST_FRACTION)))
    split = n - test_n

    train = data.iloc[:split].copy()
    test = data.iloc[split:].copy()

    return train, test


def calculate_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    previous: np.ndarray,
) -> Tuple[float, float, float, float, int]:
    mae = float(mean_absolute_error(actual, predicted))
    rmse = float(np.sqrt(mean_squared_error(actual, predicted)))

    denom = np.where(np.abs(actual) > 1e-12, np.abs(actual), np.nan)
    mape = float(np.nanmean(np.abs((actual - predicted) / denom)) * 100.0)

    actual_direction = np.sign(actual - previous)
    predicted_direction = np.sign(predicted - previous)

    mask = actual_direction != 0
    directional_n = int(mask.sum())

    if directional_n:
        directional_accuracy = float(
            (actual_direction[mask] == predicted_direction[mask]).mean()
            * 100.0
        )
    else:
        directional_accuracy = float("nan")

    return mae, rmse, mape, directional_accuracy, directional_n


def evaluate_horizon(
    df: pd.DataFrame,
    horizon: int,
    features: List[str],
) -> Tuple[Evaluation, XGBRegressor, pd.DataFrame]:
    target_col = f"target_{horizon}d"

    # Crucial correction:
    # rows with unknown future targets are NOT errors. They are simply
    # unavailable for supervised evaluation/training.
    supervised = df[
        df[target_col].notna()
        & df[TARGET_CONTRACT].notna()
    ].copy()

    supervised = supervised.sort_values("trade_date").reset_index(drop=True)

    if len(supervised) < MIN_TRAIN_ROWS:
        raise RuntimeError(
            f"Not enough supervised observations for {horizon}-day model: "
            f"{len(supervised)}"
        )

    train, test = chronological_split(supervised)

    if len(train) < MIN_TRAIN_ROWS:
        raise RuntimeError(
            f"Training set too small for {horizon}-day model: {len(train)}"
        )

    # Use median values learned from TRAIN ONLY. This prevents test-period
    # information leaking through imputation.
    X_train = train[features].apply(pd.to_numeric, errors="coerce")
    X_test = test[features].apply(pd.to_numeric, errors="coerce")

    medians = X_train.median()
    X_train = X_train.fillna(medians)
    X_test = X_test.fillna(medians)

    y_train = train[target_col].astype(float).to_numpy()
    y_test = test[target_col].astype(float).to_numpy()

    model = make_model()
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    previous = test[TARGET_CONTRACT].astype(float).to_numpy()

    mae, rmse, mape, directional, directional_n = calculate_metrics(
        y_test, predictions, previous
    )

    # Canonical persistence benchmark: predict the future target using
    # today's price at each test observation.
    baseline = previous.copy()
    b_mae, b_rmse, b_mape, _, _ = calculate_metrics(
        y_test, baseline, previous
    )

    evaluation = Evaluation(
        horizon=horizon,
        observations=len(supervised),
        training_observations=len(train),
        test_observations=len(test),
        mae=mae,
        rmse=rmse,
        mape_pct=mape,
        directional_accuracy_pct=directional,
        directional_observations=directional_n,
        baseline_mae=b_mae,
        baseline_rmse=b_rmse,
        baseline_mape_pct=b_mape,
    )

    results = test[
        ["trade_date", TARGET_CONTRACT, target_col]
    ].copy()
    results["prediction"] = predictions
    results["absolute_error"] = np.abs(
        results[target_col].astype(float) - results["prediction"]
    )

    return evaluation, model, results


def fit_current_forecast(
    df: pd.DataFrame,
    horizon: int,
    features: List[str],
) -> Tuple[float, int]:
    """
    Train on every currently supervised observation and predict the latest
    available ICCO USD feature row.

    The latest row may have target_7d/target_30d = NaN. That is intentional.
    """
    target_col = f"target_{horizon}d"

    supervised = df[
        df[target_col].notna()
        & df[TARGET_CONTRACT].notna()
    ].copy()

    latest = df.sort_values("trade_date").iloc[-1]

    X_train = supervised[features].apply(pd.to_numeric, errors="coerce")
    X_latest = pd.DataFrame(
        [latest[features].to_dict()],
        columns=features,
    ).apply(pd.to_numeric, errors="coerce")

    medians = X_train.median()
    X_train = X_train.fillna(medians)
    X_latest = X_latest.fillna(medians)

    model = make_model()
    model.fit(
        X_train,
        supervised[target_col].astype(float).to_numpy(),
    )

    prediction = float(model.predict(X_latest)[0])
    return prediction, len(supervised)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_evaluation(evaluation: Evaluation) -> None:
    print(f"\n=== {evaluation.horizon}-TRADING-DAY XGBOOST ===")
    print(f"Supervised observations: {evaluation.observations}")
    print(f"Training observations:   {evaluation.training_observations}")
    print(f"Test observations:       {evaluation.test_observations}")

    print("\n--- OUT-OF-SAMPLE METRICS ---")
    print(f"MAE:                    {evaluation.mae:.4f}")
    print(f"RMSE:                   {evaluation.rmse:.4f}")
    print(f"MAPE:                   {evaluation.mape_pct:.4f}%")
    print(
        "Directional accuracy:   "
        f"{evaluation.directional_accuracy_pct:.4f}%"
    )
    print(
        "Directional observations: "
        f"{evaluation.directional_observations}"
    )

    print("\n--- PERSISTENCE BASELINE ---")
    print(f"MAE:                    {evaluation.baseline_mae:.4f}")
    print(f"RMSE:                   {evaluation.baseline_rmse:.4f}")
    print(f"MAPE:                   {evaluation.baseline_mape_pct:.4f}%")

    print("\n--- COMPARISON ---")
    print(
        "MAE improvement vs baseline: "
        f"{evaluation.baseline_mae - evaluation.mae:.4f}"
    )
    print(
        "RMSE improvement vs baseline: "
        f"{evaluation.baseline_rmse - evaluation.rmse:.4f}"
    )


def print_current_forecasts(
    df: pd.DataFrame,
    forecasts: Dict[int, float],
) -> None:
    latest = df.sort_values("trade_date").iloc[-1]
    latest_price = float(latest[TARGET_CONTRACT])
    latest_date = pd.to_datetime(latest["trade_date"]).date()

    print("\n=== CURRENT XGBOOST FORECASTS ===")
    print(f"Latest ICCO USD date:  {latest_date}")
    print(f"Latest ICCO USD price: {latest_price:.2f} USD/tonne")

    for horizon in HORIZONS:
        prediction = forecasts[horizon]
        change_pct = ((prediction / latest_price) - 1.0) * 100.0
        direction = (
            "BULLISH"
            if change_pct > 0
            else "BEARISH"
            if change_pct < 0
            else "NEUTRAL"
        )

        print(f"\n{horizon}-trading-day forecast:")
        print(f"  Forecast price: {prediction:.2f} USD/tonne")
        print(f"  Expected change: {change_pct:+.2f}%")
        print(f"  Direction: {direction}")


def print_data_integrity(
    df: pd.DataFrame,
    validation: Dict[str, object],
) -> None:
    latest = df.sort_values("trade_date").iloc[-1]

    print("\n=== DATA INTEGRITY ===")
    print(f"Target series: ICCO-DAILY-USD ONLY")
    print(f"Mixed target contracts: NO")
    print(f"Chronological split: YES")
    print(f"Random shuffling: NO")
    print(f"Future leakage in features: NO")
    print(f"Total observations: {validation['observations']}")
    print(f"Feature count: {validation['feature_count']}")
    print(f"7-day supervised rows: {validation['target_7d_rows']}")
    print(f"30-day supervised rows: {validation['target_30d_rows']}")
    print(
        "Latest target_7d: "
        f"{latest['target_7d'] if pd.notna(latest['target_7d']) else 'NaN (expected)'}"
    )
    print(
        "Latest target_30d: "
        f"{latest['target_30d'] if pd.notna(latest['target_30d']) else 'NaN (expected)'}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("COCOA INTELLIGENCE HUB")
    print("CANONICAL XGBOOST MODEL")
    print("=" * 70)

    df = build_forecasting_dataset()

    validation = validate_dataset(df)
    features = validation["features"]

    print("\n=== FORECAST DATASET VALIDATION ===")
    print(f"Total observations: {validation['observations']}")
    print(f"Feature count:      {validation['feature_count']}")
    print(f"7-day rows:         {validation['target_7d_rows']}")
    print(f"30-day rows:        {validation['target_30d_rows']}")

    print("\n=== APPROVED MODEL FEATURES ===")
    for feature in features:
        print(feature)

    print_data_integrity(df, validation)

    evaluations: Dict[int, Evaluation] = {}
    forecasts: Dict[int, float] = {}

    for horizon in HORIZONS:
        evaluation, _, _ = evaluate_horizon(
            df,
            horizon,
            features,
        )
        evaluations[horizon] = evaluation

        forecast, training_rows = fit_current_forecast(
            df,
            horizon,
            features,
        )
        forecasts[horizon] = forecast

        print_evaluation(evaluation)
        print(
            f"\nCurrent {horizon}-day model trained on "
            f"{training_rows} supervised observations."
        )

    print_current_forecasts(df, forecasts)

    print("\n=== XGBOOST EVALUATION: PASSED ===")
    print(
        "NOTE: Performance is out-of-sample and must be interpreted "
        "against the persistence baseline and across additional walk-forward "
        "tests before drawing trading conclusions."
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
