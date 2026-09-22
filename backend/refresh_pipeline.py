#!/usr/bin/env python3
"""
Cocoa Intelligence Hub — automatic daily refresh pipeline.

Flow:
1. Pull the latest official ICCO observations into PostgreSQL.
2. Rebuild/evaluate the dynamic ensemble from the refreshed database.
3. Leave FastAPI running; the API reads the current intelligence at request time.

This script intentionally does not hard-code market prices or forecasts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = Path(sys.executable)

def run(label: str, *args: str) -> None:
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
