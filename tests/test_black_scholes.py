from __future__ import annotations

import math

import pytest

from optledger.pricing import black_scholes_price_greeks

# Hull, Options, Futures, and Other Derivatives: S=42, K=40, r=10%, σ=20%, T=0.5.
_HULL_EUROPEAN = {
    "spot": 42.0,
    "strike": 40.0,
    "time_years": 0.5,
    "rate": 0.10,
    "volatility": 0.20,
    "dividend_yield": 0.0,
}


def test_hull_european_call_and_put_prices() -> None:
    call = black_scholes_price_greeks(right="call", **_HULL_EUROPEAN)
    put = black_scholes_price_greeks(right="put", **_HULL_EUROPEAN)
    assert call.price == pytest.approx(4.759, abs=0.005)
    assert put.price == pytest.approx(0.808, abs=0.005)


def test_put_call_parity() -> None:
    call = black_scholes_price_greeks(right="call", **_HULL_EUROPEAN)
    put = black_scholes_price_greeks(right="put", **_HULL_EUROPEAN)
    forward = _HULL_EUROPEAN["spot"] * math.exp(
        -_HULL_EUROPEAN["dividend_yield"] * _HULL_EUROPEAN["time_years"]
    ) - _HULL_EUROPEAN["strike"] * math.exp(-_HULL_EUROPEAN["rate"] * _HULL_EUROPEAN["time_years"])
    assert call.price - put.price == pytest.approx(forward, abs=1e-12)


def test_put_call_parity_with_dividend_yield() -> None:
    kwargs = {**_HULL_EUROPEAN, "dividend_yield": 0.03}
    call = black_scholes_price_greeks(right="call", **kwargs)
    put = black_scholes_price_greeks(right="put", **kwargs)
    forward = kwargs["spot"] * math.exp(-kwargs["dividend_yield"] * kwargs["time_years"]) - kwargs[
        "strike"
    ] * math.exp(-kwargs["rate"] * kwargs["time_years"])
    assert call.price - put.price == pytest.approx(forward, abs=1e-12)


def test_atm_call_matches_brenner_subrahmanyam_approx() -> None:
    spot = 100.0
    vol = 0.20
    time_years = 1.0
    result = black_scholes_price_greeks(
        spot=spot,
        strike=spot,
        time_years=time_years,
        rate=0.0,
        volatility=vol,
        right="call",
        dividend_yield=0.0,
    )
    approx = 0.4 * spot * vol * math.sqrt(time_years)
    assert result.price == pytest.approx(approx, abs=0.15)
    put = black_scholes_price_greeks(
        spot=spot,
        strike=spot,
        time_years=time_years,
        rate=0.0,
        volatility=vol,
        right="put",
        dividend_yield=0.0,
    )
    assert result.price == pytest.approx(put.price, abs=1e-12)


def test_deep_itm_call_near_discounted_intrinsic() -> None:
    result = black_scholes_price_greeks(
        spot=100.0,
        strike=50.0,
        time_years=1.0,
        rate=0.05,
        volatility=0.15,
        right="call",
    )
    discounted = 100.0 - 50.0 * math.exp(-0.05)
    assert result.price == pytest.approx(discounted, abs=0.05)
    assert result.delta == pytest.approx(1.0, abs=0.01)
    assert result.gamma == pytest.approx(0.0, abs=0.01)


def test_deep_otm_call_near_zero() -> None:
    result = black_scholes_price_greeks(
        spot=50.0,
        strike=100.0,
        time_years=1.0,
        rate=0.05,
        volatility=0.15,
        right="call",
    )
    assert result.price < 0.02
    assert result.delta == pytest.approx(0.0, abs=0.01)


def test_deep_itm_put_near_discounted_intrinsic() -> None:
    result = black_scholes_price_greeks(
        spot=50.0,
        strike=100.0,
        time_years=1.0,
        rate=0.05,
        volatility=0.15,
        right="put",
    )
    discounted = 100.0 * math.exp(-0.05) - 50.0
    assert result.price == pytest.approx(discounted, abs=0.05)
    assert result.delta == pytest.approx(-1.0, abs=0.01)


def test_first_order_greeks_signs_and_call_put_relations() -> None:
    call = black_scholes_price_greeks(right="call", **_HULL_EUROPEAN)
    put = black_scholes_price_greeks(right="put", **_HULL_EUROPEAN)
    assert 0.0 < call.delta < 1.0
    assert -1.0 < put.delta < 0.0
    assert call.delta - put.delta == pytest.approx(
        math.exp(-_HULL_EUROPEAN["dividend_yield"] * _HULL_EUROPEAN["time_years"]),
        abs=1e-12,
    )
    assert call.gamma == pytest.approx(put.gamma, abs=1e-12)
    assert call.vega == pytest.approx(put.vega, abs=1e-12)
    assert call.gamma > 0.0
    assert call.vega > 0.0
    assert call.theta < 0.0


def test_expired_spot_is_intrinsic() -> None:
    call = black_scholes_price_greeks(
        spot=110.0,
        strike=100.0,
        time_years=0.0,
        rate=0.05,
        volatility=0.2,
        right="call",
    )
    put = black_scholes_price_greeks(
        spot=110.0,
        strike=100.0,
        time_years=0.0,
        rate=0.05,
        volatility=0.2,
        right="put",
    )
    assert call.price == pytest.approx(10.0)
    assert put.price == pytest.approx(0.0)
    assert call.delta == pytest.approx(1.0)
    assert put.delta == pytest.approx(0.0)
    assert call.vega == 0.0
    assert call.gamma == 0.0


def test_zero_vol_is_discounted_forward_intrinsic() -> None:
    call = black_scholes_price_greeks(
        spot=100.0,
        strike=90.0,
        time_years=1.0,
        rate=0.05,
        volatility=0.0,
        right="call",
    )
    expected = 100.0 - 90.0 * math.exp(-0.05)
    assert call.price == pytest.approx(expected, abs=1e-12)
    assert call.vega == 0.0
    assert call.gamma == 0.0


def test_greeks_match_finite_differences() -> None:
    kwargs = dict(_HULL_EUROPEAN)
    base = black_scholes_price_greeks(right="call", **kwargs)
    d_spot = 1e-4
    up = black_scholes_price_greeks(right="call", **{**kwargs, "spot": kwargs["spot"] + d_spot})
    down = black_scholes_price_greeks(right="call", **{**kwargs, "spot": kwargs["spot"] - d_spot})
    assert base.delta == pytest.approx((up.price - down.price) / (2.0 * d_spot), rel=1e-5)
    assert base.gamma == pytest.approx((up.delta - down.delta) / (2.0 * d_spot), rel=1e-4)

    d_vol = 1e-5
    vol_up = black_scholes_price_greeks(
        right="call", **{**kwargs, "volatility": kwargs["volatility"] + d_vol}
    )
    vol_down = black_scholes_price_greeks(
        right="call", **{**kwargs, "volatility": kwargs["volatility"] - d_vol}
    )
    fd_vega = (vol_up.price - vol_down.price) / (2.0 * d_vol) * 0.01
    assert base.vega == pytest.approx(fd_vega, rel=1e-5)

    d_t = 1e-6
    later = black_scholes_price_greeks(
        right="call", **{**kwargs, "time_years": kwargs["time_years"] - d_t}
    )
    fd_theta = (later.price - base.price) / d_t / 365.0
    assert base.theta == pytest.approx(fd_theta, rel=1e-4)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spot", 0.0),
        ("strike", -1.0),
        ("time_years", -0.1),
        ("volatility", -0.01),
    ],
)
def test_rejects_invalid_inputs(field: str, value: float) -> None:
    kwargs = dict(_HULL_EUROPEAN)
    kwargs[field] = value
    with pytest.raises(ValueError):
        black_scholes_price_greeks(right="call", **kwargs)


def test_rejects_unknown_right() -> None:
    with pytest.raises(ValueError, match="right"):
        black_scholes_price_greeks(right="straddle", **_HULL_EUROPEAN)  # type: ignore[arg-type]
