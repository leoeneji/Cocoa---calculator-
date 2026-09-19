from __future__ import annotations

"""Cocoa Intelligence Hub forecasting dataset builder.

Canonical target: ICCO-DAILY-USD
Horizons: 7 and 30 trading observations.
All external features are point-in-time aligned to trade_date.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

TARGET_CONTRACT = "ICCO-DAILY-USD"
MARKET_CONTRACTS = (
    "ICCO-DAILY-EUR",
    "ICCO-DAILY-USD",
    "LONDON-FUTURES",
    "NEW-YORK-FUTURES",
)
FX_PAIRS = (
    ("USD", "NGN"), ("EUR", "NGN"),
    ("USD", "XOF"), ("EUR", "XOF"),
    ("USD", "XAF"), ("EUR", "XAF"),
)


def get_database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set. Check the project .env file.")
    return value


def get_connection():
    return psycopg2.connect(get_database_url())


def ensure_trade_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "trade_date" not in df.columns:
        raise RuntimeError("Dataset is missing trade_date.")
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df = df.dropna(subset=["trade_date"])
    # Database dates are date-only, so keep them timezone-naive.
    if getattr(df["trade_date"].dt, "tz", None) is not None:
        df["trade_date"] = df["trade_date"].dt.tz_localize(None)
    return df


def load_market_data() -> pd.DataFrame:
    """Load and pivot the four verified ICCO daily market contracts."""
    query = """
        SELECT timestamp::date AS trade_date, contract, price
        FROM market_prices
        WHERE contract IN %s
          AND price IS NOT NULL
          AND price > 0
        ORDER BY timestamp::date, contract;
    """
    with get_connection() as conn:
        raw = pd.read_sql_query(query, conn, params=(MARKET_CONTRACTS,))

    if raw.empty:
        raise RuntimeError("No verified ICCO market data was returned.")

    raw["trade_date"] = pd.to_datetime(raw["trade_date"], errors="coerce")
    raw["price"] = pd.to_numeric(raw["price"], errors="coerce")
    raw = raw.dropna(subset=["trade_date", "price"])
    raw = raw.drop_duplicates(subset=["trade_date", "contract"], keep="last")

    df = raw.pivot(index="trade_date", columns="contract", values="price").reset_index()
    df.columns.name = None

    for contract in MARKET_CONTRACTS:
        if contract not in df.columns:
            df[contract] = np.nan

    return df[["trade_date", *MARKET_CONTRACTS]].sort_values("trade_date").reset_index(drop=True)


def load_fx_data() -> pd.DataFrame:
    """Load historical FX and pivot pairs into columns."""
    query = """
        SELECT rate_date, base_currency, quote_currency, rate
        FROM fx_rates
        WHERE (base_currency, quote_currency) IN (
            ('USD','NGN'), ('EUR','NGN'),
            ('USD','XOF'), ('EUR','XOF'),
            ('USD','XAF'), ('EUR','XAF')
        )
        ORDER BY rate_date;
    """
    with get_connection() as conn:
        raw = pd.read_sql_query(query, conn)

    if raw.empty:
        raise RuntimeError("No historical FX records were returned.")

    raw["rate_date"] = pd.to_datetime(raw["rate_date"], errors="coerce")
    raw["rate"] = pd.to_numeric(raw["rate"], errors="coerce")
    raw = raw.dropna(subset=["rate_date", "rate"])
    raw["pair"] = raw["base_currency"].str.upper() + "_" + raw["quote_currency"].str.upper()
    raw = raw.drop_duplicates(subset=["rate_date", "pair"], keep="last")

    fx = raw.pivot(index="rate_date", columns="pair", values="rate").reset_index()
    fx.columns.name = None
    return fx.sort_values("rate_date").reset_index(drop=True)


def load_weather_data() -> pd.DataFrame:
    """Aggregate historical weather observations across monitored locations."""
    query = """
        SELECT observation_date, location, rainfall_mm,
               temperature_c, humidity_pct, crop_risk_score
        FROM weather_observations
        ORDER BY observation_date, location;
    """
    with get_connection() as conn:
        raw = pd.read_sql_query(query, conn)

    if raw.empty:
        raise RuntimeError("No historical weather observations were returned.")

    raw["observation_date"] = pd.to_datetime(raw["observation_date"], errors="coerce")
    for column in ("rainfall_mm", "temperature_c", "humidity_pct", "crop_risk_score"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw = raw.dropna(subset=["observation_date"])

    weather = raw.groupby("observation_date").agg(
        rainfall_mm=("rainfall_mm", "mean"),
        temperature_c=("temperature_c", "mean"),
        humidity_pct=("humidity_pct", "mean"),
        crop_risk_score=("crop_risk_score", "mean"),
        weather_locations=("location", "nunique"),
    ).reset_index()
    return weather.sort_values("observation_date").reset_index(drop=True)


def add_external_features(market_df: pd.DataFrame) -> pd.DataFrame:
    """Merge only FX/weather information available on or before each market date."""
    df = ensure_trade_date(market_df).sort_values("trade_date").reset_index(drop=True)
    fx = load_fx_data()
    weather = load_weather_data()

    df = pd.merge_asof(
        df, fx.sort_values("rate_date"),
        left_on="trade_date", right_on="rate_date", direction="backward",
    ).drop(columns=["rate_date"])

    df = pd.merge_asof(
        df.sort_values("trade_date"), weather.sort_values("observation_date"),
        left_on="trade_date", right_on="observation_date", direction="backward",
    ).drop(columns=["observation_date"])

    return df.sort_values("trade_date").reset_index(drop=True)


def add_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create leakage-safe historical market and calendar features."""
    df = ensure_trade_date(df)
    for column in MARKET_CONTRACTS:
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")

    target = TARGET_CONTRACT
    for lag in (1, 2, 3, 5, 10, 20):
        df[f"icco_usd_lag_{lag}"] = df[target].shift(lag)
    for window in (3, 5, 10, 20):
        df[f"icco_usd_ma_{window}"] = df[target].rolling(window, min_periods=window).mean()
    for period in (1, 3, 5, 10, 20):
        df[f"icco_usd_return_{period}"] = df[target].pct_change(period)

    df["ny_icco_spread"] = df["NEW-YORK-FUTURES"] - df[target]
    df["london_icco_usd_spread"] = df["LONDON-FUTURES"] - df[target]

    for contract, prefix in (
        ("ICCO-DAILY-EUR", "icco_daily_eur"),
        ("LONDON-FUTURES", "london_futures"),
        ("NEW-YORK-FUTURES", "new_york_futures"),
    ):
        for period in (1, 5):
            df[f"{prefix}_return_{period}"] = df[contract].pct_change(period)

    df["month"] = df["trade_date"].dt.month
    df["quarter"] = df["trade_date"].dt.quarter
    df["day_of_week"] = df["trade_date"].dt.dayofweek
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12.0)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12.0)
    return df


def add_future_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Create forward labels; these are never model inputs."""
    df = ensure_trade_date(df)
    if TARGET_CONTRACT not in df.columns:
        raise RuntimeError(f"Canonical target {TARGET_CONTRACT} is missing.")
    df[TARGET_CONTRACT] = pd.to_numeric(df[TARGET_CONTRACT], errors="coerce")
    df["target_7d"] = df[TARGET_CONTRACT].shift(-7)
    df["target_30d"] = df[TARGET_CONTRACT].shift(-30)
    df["future_return_7d"] = df["target_7d"] / df[TARGET_CONTRACT] - 1.0
    df["future_return_30d"] = df["target_30d"] / df[TARGET_CONTRACT] - 1.0
    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return columns allowed as model inputs."""
    excluded = {
        "trade_date",
        TARGET_CONTRACT,
        "target_7d",
        "target_30d",
        "future_return_7d",
        "future_return_30d",
    }
    return [column for column in df.columns if column not in excluded]


def validate_dataset(df: pd.DataFrame) -> dict:
    """Validate structural integrity and calculate training readiness."""
    required = {"trade_date", *MARKET_CONTRACTS, "target_7d", "target_30d", "future_return_7d", "future_return_30d"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Dataset is missing required columns: {missing}")
    if not df["trade_date"].is_monotonic_increasing:
        raise RuntimeError("trade_date is not sorted chronologically.")
    if df["trade_date"].duplicated().any():
        raise RuntimeError("Duplicate trade_date observations detected.")

    target = pd.to_numeric(df[TARGET_CONTRACT], errors="coerce")
    invalid = target.isna() | ~np.isfinite(target.astype(float)) | (target <= 0)
    features = get_feature_columns(df)
    usable_7d = df[df[features].notna().all(axis=1) & df["target_7d"].notna()]
    usable_30d = df[df[features].notna().all(axis=1) & df["target_30d"].notna()]

    report = {
        "total_observations": len(df),
        "feature_count": len(features),
        "invalid_target_rows": int(invalid.sum()),
        "duplicate_dates": int(df["trade_date"].duplicated().sum()),
        "usable_7d_rows": len(usable_7d),
        "usable_30d_rows": len(usable_30d),
        "dropped_for_7d": len(df) - len(usable_7d),
        "dropped_for_30d": len(df) - len(usable_30d),
        "first_date": df["trade_date"].min().date(),
        "last_date": df["trade_date"].max().date(),
        "latest_price": float(target.iloc[-1]),
    }
    if report["invalid_target_rows"]:
        raise RuntimeError(f"Invalid canonical target rows: {report['invalid_target_rows']}")
    return report


def print_summary(df: pd.DataFrame, report: dict) -> None:
    print("\n=== FORECAST DATASET SUMMARY ===")
    print(f"Total observations: {report['total_observations']}")
    print(f"Feature count: {report['feature_count']}")
    print(f"Latest ICCO USD: {report['latest_price']:.2f}")
    print(f"7-trading-day rows: {report['usable_7d_rows']}")
    print(f"30-trading-day rows: {report['usable_30d_rows']}")
    print(f"Dropped for 7-day: {report['dropped_for_7d']}")
    print(f"Dropped for 30-day: {report['dropped_for_30d']}")
    print(f"Date range: {report['first_date']} -> {report['last_date']}")
    print("\n=== FEATURE COLUMNS ===")
    for feature in get_feature_columns(df):
        print(feature)
    print("\n=== LATEST DATASET ROW ===")
    print(df.tail(1).T.to_string())
    print("\nFORECAST DATASET BUILD: PASSED")


def main() -> None:
    print("Loading verified ICCO market data...")
    market_df = load_market_data()
    print(f"Loaded {len(market_df)} unique trading observations.")
    print("Adding point-in-time FX and historical weather...")
    df = add_external_features(market_df)
    print("Building point-in-time market features...")
    df = add_market_features(df)
    print("Building future forecasting targets...")
    df = add_future_targets(df)
    print("Validating forecasting dataset...")
    report = validate_dataset(df)
    print_summary(df, report)


if __name__ == "__main__":
    main()
