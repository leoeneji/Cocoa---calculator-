"""
Cocoa Intelligence Hub
Core Historical Price Feature Engine

This module is responsible ONLY for features derived from
cocoa price history.

Multi-factor features such as:
    - FX
    - Weather
    - News
    - Producer prices
    - Macroeconomic data

belong in:
    backend/ml/multifactor_features.py

This separation keeps the ML architecture clean.
"""

from typing import List, Dict, Any, Optional

import numpy as np


# ============================================================
# CORE FEATURE NAMES
# ============================================================

FEATURE_NAMES = [
    "lag_1",
    "lag_2",
    "lag_3",
    "moving_average_3",
    "momentum_1",
    "momentum_3",
]


# ============================================================
# BASIC VALIDATION
# ============================================================

def validate_prices(
    prices: List[float],
) -> List[float]:
    """
    Convert prices to floats and remove invalid values.
    """

    cleaned = []

    for price in prices:

        try:

            value = float(price)

            if np.isfinite(value):
                cleaned.append(value)

        except (TypeError, ValueError):
            continue

    return cleaned


# ============================================================
# SINGLE FEATURE VECTOR
# ============================================================

def make_features(
    prices: List[float],
    index: int,
) -> List[float]:
    """
    Create a leakage-safe feature vector for one observation.

    IMPORTANT:
    The price at `index` is NOT used as an input feature.

    Only prices before `index` are used.

    Features:
        lag_1
        lag_2
        lag_3
        moving_average_3
        momentum_1
        momentum_3
    """

    if index < 4:

        raise ValueError(
            "At least four previous observations "
            "are required to create features."
        )

    lag_1 = float(
        prices[index - 1]
    )

    lag_2 = float(
        prices[index - 2]
    )

    lag_3 = float(
        prices[index - 3]
    )

    moving_average_3 = float(
        np.mean(
            [
                prices[index - 1],
                prices[index - 2],
                prices[index - 3],
            ]
        )
    )

    momentum_1 = float(
        prices[index - 1]
        - prices[index - 2]
    )

    momentum_3 = float(
        prices[index - 1]
        - prices[index - 4]
    )

    return [
        lag_1,
        lag_2,
        lag_3,
        moving_average_3,
        momentum_1,
        momentum_3,
    ]


# ============================================================
# FEATURE DICTIONARY
# ============================================================

def make_feature_dict(
    prices: List[float],
    index: int,
) -> Dict[str, float]:
    """
    Return the same features as a named dictionary.

    Useful for debugging, API responses and future
    feature-importance reporting.
    """

    values = make_features(
        prices,
        index,
    )

    return dict(
        zip(
            FEATURE_NAMES,
            values,
        )
    )


# ============================================================
# BUILD HISTORICAL FEATURE MATRIX
# ============================================================

def build_feature_matrix(
    prices: List[float],
    start_index: int = 4,
):
    """
    Build a complete historical feature matrix.

    Returns:
        X -> 2-D NumPy feature matrix
        y -> target prices
        indices -> original price indices

    Every row uses information available BEFORE its target.
    """

    prices = validate_prices(
        prices
    )

    if len(prices) < start_index + 1:

        raise ValueError(
            "Not enough price observations to build "
            "the feature matrix."
        )

    X = []
    y = []
    indices = []

    for index in range(
        start_index,
        len(prices),
    ):

        features = make_features(
            prices,
            index,
        )

        X.append(features)

        y.append(
            float(prices[index])
        )

        indices.append(index)

    X = np.asarray(
        X,
        dtype=np.float64,
    )

    y = np.asarray(
        y,
        dtype=np.float64,
    )

    # --------------------------------------------------------
    # Safety checks
    # --------------------------------------------------------

    if X.ndim != 2:

        raise ValueError(
            "Feature matrix must be 2-dimensional. "
            f"Received shape: {X.shape}"
        )

    if X.shape[1] != len(
        FEATURE_NAMES
    ):

        raise ValueError(
            "Unexpected feature count. "
            f"Expected {len(FEATURE_NAMES)}, "
            f"received {X.shape[1]}"
        )

    return X, y, indices


# ============================================================
# NEXT-PREDICTION FEATURES
# ============================================================

def build_next_features(
    prices: List[float],
):
    """
    Build the feature vector required to predict
    the next price after the latest observation.
    """

    prices = validate_prices(
        prices
    )

    if len(prices) < 4:

        raise ValueError(
            "At least four price observations "
            "are required."
        )

    features = make_features(
        prices,
        len(prices),
    )

    X_next = np.asarray(
        [features],
        dtype=np.float64,
    )

    if X_next.ndim != 2:

        raise ValueError(
            "Next prediction matrix must "
            "be 2-dimensional."
        )

    return X_next


# ============================================================
# FEATURE AVAILABILITY
# ============================================================

def feature_requirements() -> Dict[str, Any]:
    """
    Describe the requirements for each core feature.
    """

    return {
        "lag_1": {
            "required_history": 1,
            "description": (
                "Previous cocoa price."
            ),
        },

        "lag_2": {
            "required_history": 2,
            "description": (
                "Price two observations ago."
            ),
        },

        "lag_3": {
            "required_history": 3,
            "description": (
                "Price three observations ago."
            ),
        },

        "moving_average_3": {
            "required_history": 3,
            "description": (
                "Three-observation moving average "
                "using only historical prices."
            ),
        },

        "momentum_1": {
            "required_history": 2,
            "description": (
                "One-period price momentum."
            ),
        },

        "momentum_3": {
            "required_history": 4,
            "description": (
                "Three-period price momentum."
            ),
        },
    }


# ============================================================
# DIAGNOSTIC SUMMARY
# ============================================================

def summarize_features(
    prices: List[float],
) -> Dict[str, Any]:
    """
    Return a diagnostic summary of the price feature engine.
    """

    prices = validate_prices(
        prices
    )

    minimum_required = 5

    if len(prices) < minimum_required:

        return {
            "status": "insufficient_data",
            "observations": len(prices),
            "minimum_required": minimum_required,
            "features": FEATURE_NAMES,
        }

    try:

        X, y, indices = build_feature_matrix(
            prices
        )

        return {
            "status": "ok",
            "observations": len(prices),
            "feature_rows": len(X),
            "feature_count": X.shape[1],
            "features": FEATURE_NAMES,
            "matrix_shape": list(
                X.shape
            ),
            "leakage_safe": True,
            "first_target_index": indices[0],
            "last_target_index": indices[-1],
        }

    except ValueError as exc:

        return {
            "status": "error",
            "message": str(exc),
        }


# ============================================================
# SIMPLE TEST
# ============================================================

if __name__ == "__main__":

    # Small synthetic test only.
    # This does NOT touch the database.

    test_prices = [
        2400,
        2450,
        2500,
        2550,
        2600,
        2580,
        2650,
        2700,
    ]

    print(
        "\nCOCOA CORE FEATURE ENGINE"
    )

    print(
        "=========================="
    )

    print(
        f"Observations: {len(test_prices)}"
    )

    print(
        f"Features: {FEATURE_NAMES}"
    )

    X, y, indices = build_feature_matrix(
        test_prices
    )

    print(
        f"Feature matrix shape: {X.shape}"
    )

    print(
        f"Target shape: {y.shape}"
    )

    print(
        "\nFirst feature row:"
    )

    print(
        make_feature_dict(
            test_prices,
            indices[0],
        )
    )

    print(
        "\nNext prediction matrix:"
    )

    print(
        build_next_features(
            test_prices
        )
    )

    print(
        "\nFeature engine test: PASSED"
    )