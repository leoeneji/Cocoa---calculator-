"""
Cocoa Intelligence Hub
Decision Intelligence / Signal Engine

Purpose:
    Convert validated model forecasts into transparent
    market decision signals.

Signal types:
    BUY
    HOLD
    SELL

Important:
    Signals are generated from model evidence.
    They are not guaranteed trading outcomes.
"""

from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

BUY_THRESHOLD_PCT = 2.0
SELL_THRESHOLD_PCT = -2.0

# Confidence is intentionally capped because our current
# validation sample is still relatively small.
MAX_CONFIDENCE = 75.0


# ============================================================
# SIGNAL DIRECTION
# ============================================================

def determine_signal(expected_change_pct):
    """
    Convert expected percentage change into BUY / HOLD / SELL.
    """

    if expected_change_pct >= BUY_THRESHOLD_PCT:
        return "BUY"

    if expected_change_pct <= SELL_THRESHOLD_PCT:
        return "SELL"

    return "HOLD"


# ============================================================
# MARKET DIRECTION
# ============================================================

def determine_market_direction(expected_change_pct):
    """
    Convert expected price movement into market direction.
    """

    if expected_change_pct > 0:
        return "BULLISH"

    if expected_change_pct < 0:
        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# IMPACT SCORE
# ============================================================

def calculate_impact_score(expected_change_pct):
    """
    Estimate the significance of the expected move.

    Scale:
        0 - 100
    """

    magnitude = abs(float(expected_change_pct))

    score = min(
        magnitude * 20.0,
        100.0,
    )

    return round(score, 2)


# ============================================================
# SEVERITY
# ============================================================

def determine_severity(expected_change_pct):
    """
    Classify the magnitude of the expected movement.
    """

    magnitude = abs(float(expected_change_pct))

    if magnitude >= 5.0:
        return "HIGH"

    if magnitude >= 2.0:
        return "MEDIUM"

    return "LOW"


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(
    directional_accuracy_pct,
    mape_pct,
    validation_observations,
):
    """
    Calculate a conservative confidence score.

    Inputs:
        directional_accuracy_pct
        mape_pct
        validation_observations

    The score is deliberately capped because a small
    validation sample should not produce excessive confidence.
    """

    directional_accuracy = float(
        directional_accuracy_pct
    )

    mape = float(mape_pct)

    observations = int(
        validation_observations
    )

    # --------------------------------------------------------
    # Direction component
    # --------------------------------------------------------

    direction_score = max(
        0.0,
        min(
            directional_accuracy,
            100.0,
        ),
    )

    # --------------------------------------------------------
    # Error component
    #
    # Lower MAPE = stronger confidence.
    # --------------------------------------------------------

    if mape <= 2.0:
        error_score = 100.0

    elif mape <= 5.0:
        error_score = 90.0

    elif mape <= 10.0:
        error_score = 75.0

    elif mape <= 20.0:
        error_score = 55.0

    else:
        error_score = 30.0

    # --------------------------------------------------------
    # Combine direction and error.
    # --------------------------------------------------------

    raw_confidence = (
        direction_score * 0.60
        + error_score * 0.40
    )

    # --------------------------------------------------------
    # Small-sample protection.
    # --------------------------------------------------------

    if observations < 20:
        confidence = min(
            raw_confidence,
            MAX_CONFIDENCE,
        )

    else:
        confidence = min(
            raw_confidence,
            90.0,
        )

    return round(
        confidence,
        2,
    )


# ============================================================
# SIGNAL SUMMARY
# ============================================================

def build_summary(
    signal,
    market_direction,
    latest_price,
    predicted_price,
    expected_change_pct,
):
    """
    Create a concise human-readable explanation.
    """

    return (
        f"{signal} signal for cocoa. "
        f"Model direction is {market_direction}. "
        f"Latest price: {latest_price:.2f}. "
        f"Forecast: {predicted_price:.2f}. "
        f"Expected change: {expected_change_pct:+.2f}%."
    )


# ============================================================
# COMPLETE SIGNAL
# ============================================================

def generate_signal(
    market,
    latest_price,
    predicted_price,
    expected_change_pct,
    directional_accuracy_pct,
    mape_pct,
    validation_observations,
):
    """
    Generate a complete decision signal.
    """

    expected_change_pct = float(
        expected_change_pct
    )

    latest_price = float(
        latest_price
    )

    predicted_price = float(
        predicted_price
    )

    signal = determine_signal(
        expected_change_pct
    )

    market_direction = determine_market_direction(
        expected_change_pct
    )

    impact_score = calculate_impact_score(
        expected_change_pct
    )

    severity = determine_severity(
        expected_change_pct
    )

    confidence_score = calculate_confidence(
        directional_accuracy_pct=directional_accuracy_pct,
        mape_pct=mape_pct,
        validation_observations=validation_observations,
    )

    summary = build_summary(
        signal=signal,
        market_direction=market_direction,
        latest_price=latest_price,
        predicted_price=predicted_price,
        expected_change_pct=expected_change_pct,
    )

    return {
        "market": market,
        "category": "model_forecast",
        "event": signal,
        "summary": summary,
        "market_direction": market_direction,
        "impact_score": impact_score,
        "confidence_score": confidence_score,
        "severity": severity,
        "detected_at": datetime.now(
            timezone.utc
        ),
        "latest_price": latest_price,
        "predicted_price": predicted_price,
        "expected_change_pct": expected_change_pct,
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = generate_signal(
        market="ICCO",
        latest_price=5140.17,
        predicted_price=5009.59375,
        expected_change_pct=-2.5403699508382034,
        directional_accuracy_pct=87.5,
        mape_pct=3.949052277898461,
        validation_observations=16,
    )

    print(result)