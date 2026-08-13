"""European Black–Scholes–Merton price and first-order Greeks.

Closed-form identities follow Merton (1973) with a continuous dividend yield.
This is supporting math for later book reprice, not a vollib/QuantLib replacement.
"""

from __future__ import annotations

import math

from optledger.pricing._common import (
    DAYS_PER_YEAR,
    VEGA_VOL_POINT,
    OptionRight,
    PriceGreeks,
    expired_greeks,
    is_call,
    norm_cdf,
    norm_pdf,
    validate_inputs,
    zero_vol_european,
)


def black_scholes_price_greeks(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    right: OptionRight,
    dividend_yield: float = 0.0,
) -> PriceGreeks:
    """European BSM price, delta, gamma, calendar-day theta, and 1-vol-point vega."""
    validate_inputs(
        spot=spot,
        strike=strike,
        time_years=time_years,
        rate=rate,
        dividend_yield=dividend_yield,
        volatility=volatility,
    )
    _ = is_call(right)
    if time_years == 0.0:
        return expired_greeks(spot, strike, right)
    if volatility == 0.0:
        return zero_vol_european(
            spot=spot,
            strike=strike,
            time_years=time_years,
            rate=rate,
            dividend_yield=dividend_yield,
            right=right,
        )

    sqrt_t = math.sqrt(time_years)
    vol_sqrt_t = volatility * sqrt_t
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_years
    ) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    disc_spot = math.exp(-dividend_yield * time_years)
    disc_strike = math.exp(-rate * time_years)
    nd1 = norm_cdf(d1)
    nd2 = norm_cdf(d2)
    pdf_d1 = norm_pdf(d1)
    call = is_call(right)

    if call:
        price = disc_spot * spot * nd1 - disc_strike * strike * nd2
        delta = disc_spot * nd1
        theta_year = (
            -disc_spot * spot * pdf_d1 * volatility / (2.0 * sqrt_t)
            - rate * strike * disc_strike * nd2
            + dividend_yield * spot * disc_spot * nd1
        )
    else:
        price = disc_strike * strike * norm_cdf(-d2) - disc_spot * spot * norm_cdf(-d1)
        delta = disc_spot * (nd1 - 1.0)
        theta_year = (
            -disc_spot * spot * pdf_d1 * volatility / (2.0 * sqrt_t)
            + rate * strike * disc_strike * norm_cdf(-d2)
            - dividend_yield * spot * disc_spot * norm_cdf(-d1)
        )

    gamma = disc_spot * pdf_d1 / (spot * vol_sqrt_t)
    vega = disc_spot * spot * pdf_d1 * sqrt_t * VEGA_VOL_POINT
    return PriceGreeks(
        price=price,
        delta=delta,
        gamma=gamma,
        theta=theta_year / DAYS_PER_YEAR,
        vega=vega,
    )
