"""Shared types and identities for the thin BS / CRR layer."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

type OptionRight = Literal["call", "put"]

DAYS_PER_YEAR = 365.0
VEGA_VOL_POINT = 0.01

_SQRT_TWO = math.sqrt(2.0)
_SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


@dataclass(frozen=True, slots=True)
class PriceGreeks:
    """Model price and first-order Greeks (plus gamma).

    Conventions:
    - ``theta`` is calendar-day (``∂V/∂t / 365``), typically negative for a long option.
    - ``vega`` is the price change for a +1 percentage-point move in volatility
      (``∂V/∂σ / 100``).
    """

    price: float
    delta: float
    gamma: float
    theta: float
    vega: float


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT_TWO))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_TWO_PI


def is_call(right: OptionRight) -> bool:
    if right == "call":
        return True
    if right == "put":
        return False
    raise ValueError(f"right must be 'call' or 'put', got {right!r}")


def validate_inputs(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
) -> None:
    for name, value in (
        ("spot", spot),
        ("strike", strike),
        ("time_years", time_years),
        ("rate", rate),
        ("dividend_yield", dividend_yield),
        ("volatility", volatility),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value!r}")
    if spot <= 0.0:
        raise ValueError(f"spot must be positive, got {spot!r}")
    if strike <= 0.0:
        raise ValueError(f"strike must be positive, got {strike!r}")
    if time_years < 0.0:
        raise ValueError(f"time_years must be >= 0, got {time_years!r}")
    if volatility < 0.0:
        raise ValueError(f"volatility must be >= 0, got {volatility!r}")


def intrinsic(spot: float, strike: float, right: OptionRight) -> float:
    if is_call(right):
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def expired_greeks(spot: float, strike: float, right: OptionRight) -> PriceGreeks:
    """Payoff and binary delta at expiry (gamma/theta/vega are zero)."""
    call = is_call(right)
    if spot > strike:
        delta = 1.0 if call else 0.0
    elif spot < strike:
        delta = 0.0 if call else -1.0
    else:
        delta = 0.5 if call else -0.5
    return PriceGreeks(
        price=intrinsic(spot, strike, right),
        delta=delta,
        gamma=0.0,
        theta=0.0,
        vega=0.0,
    )


def zero_vol_european(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend_yield: float,
    right: OptionRight,
) -> PriceGreeks:
    """Deterministic forward: discounted intrinsic of ``S e^{(r-q)T}``."""
    disc_spot = spot * math.exp(-dividend_yield * time_years)
    disc_strike = strike * math.exp(-rate * time_years)
    call = is_call(right)
    if disc_spot > disc_strike:
        price = disc_spot - disc_strike if call else 0.0
        delta = math.exp(-dividend_yield * time_years) if call else 0.0
    elif disc_spot < disc_strike:
        price = 0.0 if call else disc_strike - disc_spot
        delta = 0.0 if call else -math.exp(-dividend_yield * time_years)
    else:
        price = 0.0
        delta = 0.5 * math.exp(-dividend_yield * time_years) * (1.0 if call else -1.0)
    return PriceGreeks(price=price, delta=delta, gamma=0.0, theta=0.0, vega=0.0)
