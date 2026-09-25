#!/usr/bin/env python3
"""
Cocoa Intelligence Hub — automatic daily refresh pipeline.

Flow:
0. Ensure the PostgreSQL table required to persist ensemble results exists.
1. Pull the latest official ICCO observations into PostgreSQL.
2. Refresh historical FX / NGN data.
3. Refresh live weather data.
4. Rebuild/evaluate the dynamic ML ensemble and persist its results.
5. Leave FastAPI running; the API reads the current intelligence at request time.

This script intentionally does not hard-code market prices or forecasts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = Path(sys.executable)


def ensure_ensemble_results_table() -> None:
    """Create the ensemble_results table if it does not already exist."""
    import os
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")

    print("\n" + "=" * 70)
    print("STEP 0 - ENSURE ENSEMBLE RESULTS TABLE")
    print("=" * 70)

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ensemble_results (
                    horizon TEXT PRIMARY KEY,
                    latest_date DATE NOT NULL,
                    result JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    print("ensemble_results table is ready.")


def run(label: str, *args: str) -> None:
    """Run one refresh stage and stop the pipeline if it fails."""
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")

    result = subprocess.run(
        [str(PYTHON), *args],
        cwd=str(ROOT),
        text=True,
    )

    if result.returncode != 0:
        raise SystemExit(
            f"\nREFRESH FAILED: {label} (exit code {result.returncode})"
        )


def main() -> None:
    """Run the complete automatic refresh pipeline."""
    ensure_ensemble_results_table()

    if not PYTHON.exists():
        raise SystemExit(f"Python environment not found: {PYTHON}")

    run(
        "STEP 1 — REFRESH OFFICIAL ICCO DATA",
        "backend/collectors/historical_cocoa.py",
    )

    run(
        "STEP 2 — REFRESH HISTORICAL FX / NGN DATA",
        "-m",
        "backend.collectors.historical_fx",
    )

    run(
        "STEP 3 — REFRESH LIVE WEATHER DATA",
        "-m",
        "backend.collectors.weather",
    )

    run(
        "STEP 4 — REBUILD DYNAMIC MODEL ENSEMBLE",
        "-m",
        "backend.model_ensemble",
    )

    print("\n" + "=" * 70)
    print("COCOA INTELLIGENCE HUB AUTOMATIC REFRESH: PASSED")
    print("ICCO, FX, weather, database, model forecasts, and ensemble are refreshed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
