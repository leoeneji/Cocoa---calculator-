"""
Cocoa Intelligence Hub
Model Evaluation Engine

Purpose:
    Evaluate cocoa price forecasting models against a
    leakage-safe naive/random-walk baseline.

Metrics:
    MAE
    RMSE
    MAPE
    Directional Accuracy

Baseline:
    Today's observed price is used as tomorrow's forecast.

Important:
    The random-walk baseline directional accuracy is calculated
    using direction persistence:

        If the market rose previously,
        the baseline expects another rise.

        If the market fell previously,
        the baseline expects another fall.
"""

import json
import math

from backend.database.connection import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_MARKET = "ICCO"


# ============================================================
# LOAD MARKET PRICES
# ============================================================

def load_prices(market=DEFAULT_MARKET):
    """
    Load historical market prices from PostgreSQL.

    Returns:
        List of:
            (timestamp, price)
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    timestamp,
                    price
                FROM market_prices
                WHERE market = %s
                  AND price IS NOT NULL
                ORDER BY timestamp ASC
                """,
                (market,),
            )

            return cur.fetchall()

    finally:
        conn.close()


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(actual, predicted):
    """
    Calculate forecasting metrics.

    Metrics:

        MAE
            Mean Absolute Error.

        RMSE
            Root Mean Squared Error.

        MAPE
            Mean Absolute Percentage Error.

        Directional Accuracy
            Percentage of correctly predicted price directions.

    Directional accuracy compares the predicted movement with
    the actual movement using the previous actual price as the
    reference point.
    """

    if not actual or not predicted:

        return {
            "mae": None,
            "rmse": None,
            "mape_pct": None,
            "directional_accuracy_pct": None,
        }

    if len(actual) != len(predicted):

        raise ValueError(
            "actual and predicted must have the same length"
        )

    # --------------------------------------------------------
    # ERROR CALCULATION
    # --------------------------------------------------------

    errors = [
        prediction - reality
        for prediction, reality
        in zip(predicted, actual)
    ]

    absolute_errors = [
        abs(error)
        for error in errors
    ]

    squared_errors = [
        error ** 2
        for error in errors
    ]

    # --------------------------------------------------------
    # MAE
    # --------------------------------------------------------

    mae = (
        sum(absolute_errors)
        / len(absolute_errors)
    )

    # --------------------------------------------------------
    # RMSE
    # --------------------------------------------------------

    rmse = math.sqrt(
        sum(squared_errors)
        / len(squared_errors)
    )

    # --------------------------------------------------------
    # MAPE
    # --------------------------------------------------------

    mape_values = [
        abs(
            (reality - prediction)
            / reality
        ) * 100

        for prediction, reality
        in zip(predicted, actual)

        if reality != 0
    ]

    mape = (
        sum(mape_values)
        / len(mape_values)

        if mape_values

        else None
    )

    # --------------------------------------------------------
    # DIRECTIONAL ACCURACY
    # --------------------------------------------------------
    #
    # For each forecast:
    #
    # actual direction:
    # actual[i] > actual[i-1]
    #
    # predicted direction:
    # predicted[i] > actual[i-1]
    #
    # This is the correct formulation for a one-step-ahead
    # forecasting model because the previous actual price is
    # the information available when the prediction is made.
    #
    # --------------------------------------------------------

    correct_direction = 0
    direction_total = 0

    for i in range(len(actual)):

        # The first observation has no previous actual price.
        if i == 0:
            continue

        actual_direction = (
            actual[i] > actual[i - 1]
        )

        predicted_direction = (
            predicted[i] > actual[i - 1]
        )

        if actual_direction == predicted_direction:

            correct_direction += 1

        direction_total += 1

    directional_accuracy = (

        correct_direction
        / direction_total
        * 100

        if direction_total

        else None
    )

    return {
        "mae": mae,
        "rmse": rmse,
        "mape_pct": mape,
        "directional_accuracy_pct": (
            directional_accuracy
        ),
    }


# ============================================================
# RANDOM-WALK BASELINE
# ============================================================

def evaluate_random_walk(
    market=DEFAULT_MARKET
):
    """
    Evaluate the naive/random-walk baseline.

    Price rule:

        next predicted price = current observed price

    Direction rule:

        next predicted direction =
        most recent observed direction

    This model is intentionally simple.

    Its purpose is to establish a benchmark that more advanced
    models such as XGBoost must beat.
    """

    rows = load_prices(market)

    # --------------------------------------------------------
    # DATA VALIDATION
    # --------------------------------------------------------

    if len(rows) < 2:

        return {
            "status": "insufficient_data",
            "model": "naive_random_walk_baseline",
            "market": market,
            "observations": len(rows),
            "message": (
                "At least 2 observations are required."
            ),
        }

    actual = []
    predicted = []

    # --------------------------------------------------------
    # PRICE FORECASTS
    # --------------------------------------------------------
    #
    # Prediction at time t:
    #
    # predicted[t] = actual[t-1]
    #
    # --------------------------------------------------------

    for i in range(1, len(rows)):

        previous_price = float(
            rows[i - 1][1]
        )

        current_price = float(
            rows[i][1]
        )

        predicted.append(
            previous_price
        )

        actual.append(
            current_price
        )

    # --------------------------------------------------------
    # STANDARD ERROR METRICS
    # --------------------------------------------------------

    metrics = calculate_metrics(
        actual,
        predicted,
    )

    # --------------------------------------------------------
    # RANDOM-WALK DIRECTIONAL ACCURACY
    # --------------------------------------------------------
    #
    # The random-walk price forecast is:
    #
    # y_hat(t) = y(t-1)
    #
    # That forecast itself is flat relative to the previous
    # actual price, so using:
    #
    # predicted[t] > actual[t-1]
    #
    # would incorrectly classify every forecast as "down".
    #
    # Instead, the directional baseline uses persistence:
    #
    # Previous movement:
    #
    # y(t-1) > y(t-2)
    #
    # Predicted movement:
    #
    # same direction
    #
    # Actual movement:
    #
    # y(t) > y(t-1)
    #
    # --------------------------------------------------------

    correct_direction = 0
    direction_total = 0

    for i in range(2, len(rows)):

        previous_price = float(
            rows[i - 1][1]
        )

        price_before_previous = float(
            rows[i - 2][1]
        )

        current_price = float(
            rows[i][1]
        )

        previous_direction = (
            previous_price
            > price_before_previous
        )

        actual_direction = (
            current_price
            > previous_price
        )

        if (
            previous_direction
            == actual_direction
        ):

            correct_direction += 1

        direction_total += 1

    baseline_directional_accuracy = (

        correct_direction
        / direction_total
        * 100

        if direction_total

        else None
    )

    metrics[
        "directional_accuracy_pct"
    ] = baseline_directional_accuracy

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "status": "ok",

        "model": (
            "naive_random_walk_baseline"
        ),

        "market": market,

        "observations": len(rows),

        "test_predictions": len(predicted),

        "first_timestamp": rows[0][0],

        "last_timestamp": rows[-1][0],

        "metrics": metrics,
    }


# ============================================================
# MODEL COMPARISON
# ============================================================

def compare_models(
    baseline,
    candidate
):
    """
    Compare a candidate forecasting model against a baseline.

    Lower is better:
        MAE
        RMSE
        MAPE

    Higher is better:
        Directional Accuracy

    Improvement for error metrics:

        (
            baseline - candidate
        )
        /
        baseline
        * 100

    Improvement for directional accuracy:

        (
            candidate - baseline
        )
        /
        baseline
        * 100
    """

    comparison = {}

    # --------------------------------------------------------
    # ERROR METRICS
    # --------------------------------------------------------

    for metric in [
        "mae",
        "rmse",
        "mape_pct",
    ]:

        baseline_value = (
            baseline["metrics"].get(metric)
        )

        candidate_value = (
            candidate["metrics"].get(metric)
        )

        # ----------------------------------------------------
        # Missing values
        # ----------------------------------------------------

        if (
            baseline_value is None
            or candidate_value is None
        ):

            comparison[metric] = None

            continue

        # ----------------------------------------------------
        # Zero baseline protection
        # ----------------------------------------------------

        if baseline_value == 0:

            comparison[metric] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "improvement_pct": None,
            }

            continue

        # ----------------------------------------------------
        # Improvement
        # ----------------------------------------------------

        improvement_pct = (

            (
                baseline_value
                - candidate_value
            )

            / baseline_value

        ) * 100

        comparison[metric] = {
            "baseline": baseline_value,
            "candidate": candidate_value,
            "improvement_pct": (
                improvement_pct
            ),
        }

    # --------------------------------------------------------
    # DIRECTIONAL ACCURACY
    # --------------------------------------------------------

    baseline_direction = (
        baseline["metrics"].get(
            "directional_accuracy_pct"
        )
    )

    candidate_direction = (
        candidate["metrics"].get(
            "directional_accuracy_pct"
        )
    )

    if (
        baseline_direction is not None
        and candidate_direction is not None
    ):

        improvement_pct = None

        if baseline_direction != 0:

            improvement_pct = (

                (
                    candidate_direction
                    - baseline_direction
                )

                / baseline_direction

            ) * 100

        comparison[
            "directional_accuracy_pct"
        ] = {

            "baseline": (
                baseline_direction
            ),

            "candidate": (
                candidate_direction
            ),

            "improvement_pct": (
                improvement_pct
            ),
        }

    else:

        comparison[
            "directional_accuracy_pct"
        ] = None

    return comparison


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    result = evaluate_random_walk(
        DEFAULT_MARKET
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )