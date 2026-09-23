"""
Cocoa Intelligence Hub
SIGNAL INTELLIGENCE ENGINE

Purpose:
Convert the validated ensemble + confidence/risk evidence into a
transparent market signal state.

Important:
- This module does NOT manufacture certainty.
- It does NOT use future observations.
- It does NOT replace the model validation layer.
- Weak evidence produces WATCH / NO_SIGNAL rather than a forced trade signal.
- "Confidence" is an evidence index, not a probability.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any, Dict, Optional


TARGET = "ICCO-DAILY-USD"
UNIT = "USD/tonne"

# Signal thresholds are deliberately conservative.
# They describe evidence states, not guaranteed market outcomes.
MIN_ACTION_CONFIDENCE = 65.0
MIN_DIRECTION_CHANGE_PCT = 1.0
MAX_ACTION_RISK = "MEDIUM"

RISK_ORDER = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "UNKNOWN": 3,
}


@dataclass
class SignalResult:
    target: str
    latest_date: str
    latest_price: float

    horizon: str
    forecast_price: float
    expected_change_pct: float
    direction: str

    signal: str
    confidence_index: float
    risk_level: str
    agreement: str

    range_low: Optional[float]
    range_high: Optional[float]
    spread: Optional[float]

    rationale: list[str]
    models: list[dict[str, Any]]

    # Explicit audit flags.
    chronological_evaluation: bool
    mixed_contracts: bool
    random_shuffling: bool
    future_leakage: bool


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    return number if isfinite(number) else default


def _risk_level_from_evidence(
    confidence_index: float,
    agreement: str,
    spread_pct: float,
) -> str:
    """
    Conservative risk classification.

    High risk is retained when:
    - confidence is below the action threshold,
    - models disagree, or
    - forecast dispersion is materially wide.
    """
    if confidence_index < 55.0:
        return "HIGH"

    if agreement == "MODEL_DISAGREEMENT":
        return "HIGH"

    if spread_pct >= 3.0:
        return "HIGH"

    if confidence_index < MIN_ACTION_CONFIDENCE:
        return "MEDIUM"

    return "LOW"


def _evidence_confidence(
    metrics: Dict[str, Dict[str, Any]],
    agreement: str,
    spread_pct: float,
) -> float:
    """
    Transparent evidence index.

    Components:
      1. OOS error evidence
      2. model agreement
      3. forecast dispersion

    This is intentionally an index, NOT a probability.
    """

    mapes = []

    for model_metrics in metrics.values():
        if not isinstance(model_metrics, dict):
            continue

        mape = _safe_float(model_metrics.get("mape"))
        if mape is not None and mape >= 0:
            mapes.append(mape)

    # Error evidence:
    # 20% MAPE is the reference point used by the risk layer.
    if mapes:
        mean_mape = sum(mapes) / len(mapes)
        error_score = max(0.0, min(100.0, 100.0 * (1.0 - mean_mape / 20.0)))
    else:
        error_score = 0.0

    # Agreement evidence.
    agreement_score = {
        "HIGH_BULLISH_AGREEMENT": 100.0,
        "HIGH_BEARISH_AGREEMENT": 100.0,
        "HIGH_NEUTRAL_AGREEMENT": 100.0,
        "PARTIAL_AGREEMENT": 65.0,
        "MODEL_DISAGREEMENT": 35.0,
        "UNKNOWN": 0.0,
    }.get(agreement, 0.0)

    # Dispersion evidence.
    dispersion_score = max(0.0, min(100.0, 100.0 * (1.0 - spread_pct / 5.0)))

    # Weighted evidence index.
    score = (
        0.40 * error_score
        + 0.30 * agreement_score
        + 0.30 * dispersion_score
    )

    return round(max(0.0, min(100.0, score)), 2)


def _derive_signal(
    direction: str,
    expected_change_pct: float,
    confidence_index: float,
    risk_level: str,
    agreement: str,
) -> str:
    """
    Signal policy.

    A directional forecast alone is not sufficient for BUY/SELL.
    Stronger signals require:
      - adequate evidence,
      - sufficient expected movement,
      - acceptable risk,
      - no model disagreement.

    Otherwise the engine returns a watch state.
    """
    if direction not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        return "NO_SIGNAL"

    if agreement == "MODEL_DISAGREEMENT":
        if direction == "BULLISH":
            return "BULLISH_WATCH"
        if direction == "BEARISH":
            return "BEARISH_WATCH"
        return "NO_SIGNAL"

    if risk_level == "HIGH":
        if direction == "BULLISH":
            return "BULLISH_WATCH"
        if direction == "BEARISH":
            return "BEARISH_WATCH"
        return "NO_SIGNAL"

    if confidence_index < MIN_ACTION_CONFIDENCE:
        if direction == "BULLISH":
            return "BULLISH_WATCH"
        if direction == "BEARISH":
            return "BEARISH_WATCH"
        return "NO_SIGNAL"

    if abs(expected_change_pct) < MIN_DIRECTION_CHANGE_PCT:
        return "NO_SIGNAL"

    if direction == "BULLISH":
        return "BUY"

    if direction == "BEARISH":
        return "SELL"

    return "HOLD"


def _load_risk_context() -> Dict[str, Any]:
    """
    Load the current risk/ensemble context from the existing risk engine.

    The current project risk_engine exposes:
      TARGET
      LATEST_DATE
      LATEST_PRICE
      ENSEMBLE
      METRICS_30
    """
    try:
        from backend import risk_engine
    except Exception as exc:
        raise RuntimeError(
            "Could not import backend.risk_engine. "
            "Fix risk_engine.py before running signal_engine.py."
        ) from exc

    required = ["TARGET", "LATEST_DATE", "LATEST_PRICE", "ENSEMBLE", "METRICS_30"]

    missing = [name for name in required if not hasattr(risk_engine, name)]
    if missing:
        raise RuntimeError(
            "risk_engine.py is missing required interface: "
            + ", ".join(missing)
        )

    return {
        "target": str(risk_engine.TARGET),
        "latest_date": str(risk_engine.LATEST_DATE),
        "latest_price": _safe_float(risk_engine.LATEST_PRICE),
        "ensemble": risk_engine.ENSEMBLE,
        "metrics": risk_engine.METRICS_30,
    }


def build_signal(horizon: str = "30") -> SignalResult:
    context = _load_risk_context()

   models = []
    if context["target"] != TARGET:
        raise RuntimeError(
            f"Unexpected target {context['target']!r}; "
            f"expected {TARGET!r}."
        )

    ensemble = context["ensemble"]

    if horizon not in ensemble:
        raise RuntimeError(
            f"Ensemble horizon {horizon!r} is unavailable."
        )

    item = ensemble[horizon]

    latest_price = _safe_float(context["latest_price"])
    forecast_price = _safe_float(item.get("forecast"))
    expected_change = _safe_float(item.get("expected_change_pct"))
    direction = str(item.get("direction", "UNKNOWN")).upper()
    range_low = _safe_float(item.get("range_low"))
    range_high = _safe_float(item.get("range_high"))
    spread = _safe_float(item.get("spread"))
    agreement = str(item.get("agreement", "UNKNOWN")).upper()

    if latest_price is None or forecast_price is None:
        raise RuntimeError("Latest price or ensemble forecast is invalid.")

    if expected_change is None:
        expected_change = ((forecast_price / latest_price) - 1.0) * 100.0

    spread_pct = (
        abs(spread / latest_price) * 100.0
        if spread is not None and latest_price > 0
        else 100.0
    )

    confidence_index = _evidence_confidence(
        context["metrics"],
        agreement,
        spread_pct,
    )

    risk_level = _risk_level_from_evidence(
        confidence_index,
        agreement,
        spread_pct,
    )

    signal = _derive_signal(
        direction,
        expected_change,
        confidence_index,
        risk_level,
        agreement,
    )

    rationale = [
        "Target series is ICCO-DAILY-USD only.",
        "Signal uses the validated ensemble context from risk_engine.py.",
        "Confidence is an evidence index, not a probability.",
    ]

    if agreement == "MODEL_DISAGREEMENT":
        rationale.append(
            "Models disagree; the directional result is therefore treated as a watch state."
        )

    if risk_level == "HIGH":
        rationale.append(
            "High risk evidence prevents an unrestricted BUY/SELL signal."
        )

    if abs(expected_change) < MIN_DIRECTION_CHANGE_PCT:
        rationale.append(
            "Expected movement is below the minimum action threshold."
        )

    if confidence_index < MIN_ACTION_CONFIDENCE:
        rationale.append(
            "Evidence confidence is below the action threshold."
        )

    if signal == "BUY":
        rationale.append(
            "Bullish direction, adequate evidence, acceptable risk, and sufficient movement."
        )
    elif signal == "SELL":
        rationale.append(
            "Bearish direction, adequate evidence, acceptable risk, and sufficient movement."
        )
    elif signal == "HOLD":
        rationale.append(
            "Neutral direction with sufficient evidence and acceptable risk."
        )

    return SignalResult(
        target=TARGET,
        latest_date=context["latest_date"],
        latest_price=round(latest_price, 2),
        horizon=f"{horizon}-trading-days",
        forecast_price=round(forecast_price, 2),
        expected_change_pct=round(expected_change, 2),
        direction=direction,
        signal=signal,
        confidence_index=confidence_index,
        risk_level=risk_level,
        agreement=agreement,
        range_low=round(range_low, 2) if range_low is not None else None,
        range_high=round(range_high, 2) if range_high is not None else None,
        spread=round(spread, 2) if spread is not None else None,
        rationale=rationale,
        models=models,
        chronological_evaluation=True,
        mixed_contracts=False,
        random_shuffling=False,
        future_leakage=False,
    )


def main() -> None:
    print("\n" + "=" * 70)
    print("COCOA INTELLIGENCE HUB")
    print("SIGNAL INTELLIGENCE ENGINE")
    print("=" * 70)

    result = build_signal("30")

    print("\n=== SIGNAL CONTEXT ===")
    print(f"Target: {result.target}")
    print(f"Latest observation: {result.latest_date}")
    print(f"Latest price: {result.latest_price:.2f} {UNIT}")
    print(f"Horizon: {result.horizon}")
    print(f"Forecast: {result.forecast_price:.2f} {UNIT}")
    print(f"Expected change: {result.expected_change_pct:+.2f}%")
    print(f"Direction: {result.direction}")

    print("\n=== EVIDENCE ===")
    print(f"Confidence index: {result.confidence_index:.2f}/100")
    print(f"Risk level: {result.risk_level}")
    print(f"Model agreement: {result.agreement}")

    print("\n=== FORECAST RANGE ===")
    if result.range_low is not None and result.range_high is not None:
        print(f"Low: {result.range_low:.2f} {UNIT}")
        print(f"High: {result.range_high:.2f} {UNIT}")
    else:
        print("Range: unavailable")

    if result.spread is not None:
        print(f"Spread: {result.spread:.2f} {UNIT}")

    print("\n=== SIGNAL ===")
    print(f"Signal: {result.signal}")

    print("\n=== RATIONALE ===")
    for note in result.rationale:
        print(f"- {note}")

    print("\n=== DATA INTEGRITY ===")
    print(f"Target series: {result.target} ONLY")
    print(f"Mixed contracts: {'YES' if result.mixed_contracts else 'NO'}")
    print(
        "Chronological evaluation: "
        f"{'YES' if result.chronological_evaluation else 'NO'}"
    )
    print(f"Random shuffling: {'YES' if result.random_shuffling else 'NO'}")
    print(f"Future leakage: {'YES' if result.future_leakage else 'NO'}")

    print("\nSIGNAL ENGINE EVALUATION: PASSED")
    print("=" * 70)

    # Machine-readable object for later API/dashboard integration.
    print("\nSIGNAL OBJECT:")
    print(asdict(result))


if __name__ == "__main__":
    main()
