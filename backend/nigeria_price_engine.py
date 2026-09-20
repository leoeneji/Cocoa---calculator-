from datetime import date
from decimal import Decimal


def estimate_ngn_price(icco_usd_per_tonne, usd_ngn, local_basis=1.0):
    """
    Nigerian cocoa price benchmark in NGN/tonne.

    This is an estimated reference value, not an official farmgate quote.
    local_basis allows a later calibrated Nigerian farmgate adjustment.
    """
    if icco_usd_per_tonne is None or usd_ngn is None:
        raise ValueError("ICCO price and USD/NGN rate are required")

    icco = Decimal(str(icco_usd_per_tonne))
    fx = Decimal(str(usd_ngn))
    basis = Decimal(str(local_basis))

    return round(icco * fx * basis, 2)


def forecast_ngn_price(current_ngn_price, global_change_pct):
    """
    Translate the modelled global cocoa percentage change
    into the Nigerian NGN/tonne benchmark.
    """
    if current_ngn_price is None or global_change_pct is None:
        return None

    current = Decimal(str(current_ngn_price))
    change = Decimal(str(global_change_pct)) / Decimal("100")

    return round(current * (Decimal("1") + change), 2)
