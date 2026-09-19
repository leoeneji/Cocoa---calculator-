"""
Cocoa Intelligence Hub
Model -> Signal Service

Connects:
    XGBoost forecasting
        ↓
    Signal Engine
        ↓
    PostgreSQL signals table
"""

from backend.ml.xgboost_model import run_xgboost
from backend.ml.signal_engine import generate_signal
from backend.database.connection import get_connection


# ============================================================
# GENERATE CURRENT COCOA SIGNAL
# ============================================================

def generate_current_signal(market="ICCO"):
    """
    Run the XGBoost model and convert its forecast
    into a decision signal.
    """

    model_result = run_xgboost(market)

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    if model_result.get("status") != "ok":
        return {
            "status": "unavailable",
            "model": "xgboost",
            "market": market,
            "model_result": model_result,
        }

    # --------------------------------------------------------
    # Extract model results
    # --------------------------------------------------------

    latest_price = float(
        model_result["latest_price"]
    )

    predicted_price = float(
        model_result["next_prediction"]
    )

    expected_change_pct = float(
        model_result["expected_change_pct"]
    )

    metrics = model_result["metrics"]

    directional_accuracy_pct = float(
        metrics["directional_accuracy_pct"]
    )

    mape_pct = float(
        metrics["mape_pct"]
    )

    validation_observations = int(
        model_result["validation_observations"]
    )

    # --------------------------------------------------------
    # Generate decision signal
    # --------------------------------------------------------

    signal = generate_signal(
        market=market,
        latest_price=latest_price,
        predicted_price=predicted_price,
        expected_change_pct=expected_change_pct,
        directional_accuracy_pct=directional_accuracy_pct,
        mape_pct=mape_pct,
        validation_observations=validation_observations,
    )

    # --------------------------------------------------------
    # Attach model information
    # --------------------------------------------------------

    signal["model"] = "xgboost"

    signal["model_metrics"] = metrics

    signal["validation_observations"] = (
        validation_observations
    )

    signal["latest_timestamp"] = (
        model_result["latest_timestamp"]
    )

    return signal


# ============================================================
# SAVE SIGNAL
# ============================================================

def save_signal(signal):
    """
    Save a generated model signal to PostgreSQL.
    """

    conn = get_connection()

    try:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO signals (
                    article_id,
                    country_id,
                    category,
                    event,
                    summary,
                    market_direction,
                    impact_score,
                    confidence_score,
                    severity,
                    detected_at
                )
                VALUES (
                    NULL,
                    NULL,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id
                """,
                (
                    signal["category"],
                    signal["event"],
                    signal["summary"],
                    signal["market_direction"],
                    signal["impact_score"],
                    signal["confidence_score"],
                    signal["severity"],
                    signal["detected_at"],
                ),
            )

            signal_id = cur.fetchone()[0]

        conn.commit()

        signal["signal_id"] = str(
            signal_id
        )

        return signal

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# COMPLETE PIPELINE
# ============================================================

def create_current_signal(market="ICCO"):
    """
    Generate and persist the current model signal.
    """

    signal = generate_current_signal(
        market=market
    )

    if signal.get("status") == "unavailable":
        return signal

    return save_signal(signal)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = create_current_signal(
        market="ICCO"
    )

    print(result))