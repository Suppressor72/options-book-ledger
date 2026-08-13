"""Cox–Ross–Rubinstein binomial tree for American (and European) options.

``u = exp(σ √Δt)``, ``d = 1/u``. Early exercise is taken as the max of intrinsic
and discounted risk-neutral continuation at every node. Vega is a central
finite difference in volatility; other Greeks come from the first two tree
steps (Haug / standard binomial identities).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from optledger.pricing._common import (
    DAYS_PER_YEAR,
    VEGA_VOL_POINT,
    OptionRight,
    PriceGreeks,
    expired_greeks,
    intrinsic,
    is_call,
    validate_inputs,
    zero_vol_european,
)


class _CrrNodes(NamedTuple):
    price: float
    value_up: float
    value_down: float
    value_uu: float
    value_ud: float
    value_dd: float
    dt: float
    up: float
    down: float


_VEGA_BUMP = 1.0e-4
# Below this, sigma * sqrt(dt) cannot resolve drift from zero, so the tree is
# routed to the deterministic (zero-vol) forward instead of a frozen all-up/down tree.
_DEGEN_EPS = 1e-10


def crr_american_price_greeks(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    right: OptionRight,
    dividend_yield: float = 0.0,
    steps: int = 100,
) -> PriceGreeks:
    """American CRR price, delta, gamma, calendar-day theta, and 1-vol-point vega."""
    return _crr_price_greeks(
        spot=spot,
        strike=strike,
        time_years=time_years,
        rate=rate,
        volatility=volatility,
        right=right,
        dividend_yield=dividend_yield,
        steps=steps,
        american=True,
    )


def _crr_price_greeks(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    right: OptionRight,
    dividend_yield: float,
    steps: int,
    american: bool,
) -> PriceGreeks:
    validate_inputs(
        spot=spot,
        strike=strike,
        time_years=time_years,
        rate=rate,
        dividend_yield=dividend_yield,
        volatility=volatility,
    )
    _ = is_call(right)
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 2:
        raise ValueError(f"steps must be an int >= 2, got {steps!r}")
    if time_years == 0.0:
        return expired_greeks(spot, strike, right)
    if volatility == 0.0 or volatility * math.sqrt(time_years / steps) < _DEGEN_EPS:
        european = zero_vol_european(
            spot=spot,
            strike=strike,
            time_years=time_years,
            rate=rate,
            dividend_yield=dividend_yield,
            right=right,
        )
        if not american:
            return european
        exercise_now = intrinsic(spot, strike, right)
        if exercise_now <= european.price:
            return european
        call = is_call(right)
        if spot > strike:
            delta = 1.0 if call else 0.0
        elif spot < strike:
            delta = 0.0 if call else -1.0
        else:
            delta = european.delta
        return PriceGreeks(
            price=exercise_now,
            delta=delta,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
        )

    nodes = _roll(
        spot=spot,
        strike=strike,
        time_years=time_years,
        rate=rate,
        dividend_yield=dividend_yield,
        volatility=volatility,
        right=right,
        steps=steps,
        american=american,
    )
    su = spot * nodes.up
    sd = spot * nodes.down
    suu = spot * nodes.up * nodes.up
    sud = spot * nodes.up * nodes.down
    sdd = spot * nodes.down * nodes.down
    delta = (nodes.value_up - nodes.value_down) / (su - sd)
    delta_up = (nodes.value_uu - nodes.value_ud) / (suu - sud)
    delta_down = (nodes.value_ud - nodes.value_dd) / (sud - sdd)
    gamma = (delta_up - delta_down) / (0.5 * (suu - sdd))
    theta = (nodes.value_ud - nodes.price) / (2.0 * nodes.dt) / DAYS_PER_YEAR
    vega = _vega_finite_difference(
        spot=spot,
        strike=strike,
        time_years=time_years,
        rate=rate,
        dividend_yield=dividend_yield,
        volatility=volatility,
        right=right,
        steps=steps,
        american=american,
    )
    return PriceGreeks(
        price=nodes.price,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
    )


def _vega_finite_difference(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    right: OptionRight,
    steps: int,
    american: bool,
) -> float:
    bump = _VEGA_BUMP
    up_vol = volatility + bump
    down_vol = volatility - bump
    if down_vol <= 0.0:
        up_price = _roll(
            spot=spot,
            strike=strike,
            time_years=time_years,
            rate=rate,
            dividend_yield=dividend_yield,
            volatility=up_vol,
            right=right,
            steps=steps,
            american=american,
        ).price
        base = _roll(
            spot=spot,
            strike=strike,
            time_years=time_years,
            rate=rate,
            dividend_yield=dividend_yield,
            volatility=volatility,
            right=right,
            steps=steps,
            american=american,
        ).price
        raw = (up_price - base) / bump
    else:
        up_price = _roll(
            spot=spot,
            strike=strike,
            time_years=time_years,
            rate=rate,
            dividend_yield=dividend_yield,
            volatility=up_vol,
            right=right,
            steps=steps,
            american=american,
        ).price
        down_price = _roll(
            spot=spot,
            strike=strike,
            time_years=time_years,
            rate=rate,
            dividend_yield=dividend_yield,
            volatility=down_vol,
            right=right,
            steps=steps,
            american=american,
        ).price
        raw = (up_price - down_price) / (2.0 * bump)
    return raw * VEGA_VOL_POINT


def _roll(
    *,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    right: OptionRight,
    steps: int,
    american: bool,
) -> _CrrNodes:
    n = steps
    dt = time_years / n
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    growth = math.exp((rate - dividend_yield) * dt)
    denom = up - down
    if denom == 0.0:
        raise ValueError("CRR up/down collapsed; volatility and step size are invalid")
    risk_neutral_p = (growth - down) / denom
    # Low vol / near-expiry / high drift can push the naive p just outside
    # [0, 1]. Clamp to the deterministic limit rather than raise: the tree is
    # then continuous with the zero-vol path, and reachable prices stay
    # reachable (e.g. vol=0.0026, r=0.05 used to raise). This is standard
    # production CRR practice.
    risk_neutral_p = min(max(risk_neutral_p, 0.0), 1.0)
    discount = math.exp(-rate * dt)
    call = is_call(right)
    values = [0.0] * (n + 1)
    for downs in range(n + 1):
        terminal_spot = spot * (up ** (n - downs)) * (down**downs)
        values[downs] = (
            max(terminal_spot - strike, 0.0) if call else max(strike - terminal_spot, 0.0)
        )

    # When n == 2 the expiry layer is also the t=2 layer used for gamma.
    layer2 = (values[0], values[1], values[2]) if n == 2 else (0.0, 0.0, 0.0)
    layer1 = (0.0, 0.0)
    price = 0.0
    for step in range(n - 1, -1, -1):
        for downs in range(step + 1):
            continuation = discount * (
                risk_neutral_p * values[downs] + (1.0 - risk_neutral_p) * values[downs + 1]
            )
            if american:
                node_spot = spot * (up ** (step - downs)) * (down**downs)
                exercise = max(node_spot - strike, 0.0) if call else max(strike - node_spot, 0.0)
                values[downs] = max(continuation, exercise)
            else:
                values[downs] = continuation
        if step == 2:
            layer2 = (values[0], values[1], values[2])
        elif step == 1:
            layer1 = (values[0], values[1])
        elif step == 0:
            price = values[0]

    return _CrrNodes(
        price=price,
        value_up=layer1[0],
        value_down=layer1[1],
        value_uu=layer2[0],
        value_ud=layer2[1],
        value_dd=layer2[2],
        dt=dt,
        up=up,
        down=down,
    )
