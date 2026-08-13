from __future__ import annotations

import math

import pytest

from optledger.pricing import black_scholes_price_greeks, crr_american_price_greeks
from optledger.pricing.crr import _crr_price_greeks

# Hull binomial example: 5-month American put, n=5.
# fOptions::CRRBinomialTreeOption reports 4.488459 for T=5/12.
_HULL_CRR = {
    "spot": 50.0,
    "strike": 50.0,
    "time_years": 5.0 / 12.0,
    "rate": 0.10,
    "volatility": 0.40,
    "dividend_yield": 0.0,
}


def test_hull_five_step_american_put() -> None:
    result = crr_american_price_greeks(right="put", steps=5, **_HULL_CRR)
    assert result.price == pytest.approx(4.488459, abs=1e-5)


def test_american_put_at_least_european_put() -> None:
    american = crr_american_price_greeks(right="put", steps=200, **_HULL_CRR)
    european = black_scholes_price_greeks(right="put", **_HULL_CRR)
    assert american.price >= european.price - 1e-10
    assert american.price - european.price > 0.05


def test_american_call_equals_european_when_no_dividends() -> None:
    american = crr_american_price_greeks(right="call", steps=250, **_HULL_CRR)
    european = black_scholes_price_greeks(right="call", **_HULL_CRR)
    assert american.price == pytest.approx(european.price, abs=0.02)


def test_european_crr_converges_to_black_scholes() -> None:
    bs = black_scholes_price_greeks(right="call", **_HULL_CRR)
    tree = _crr_price_greeks(
        right="call",
        steps=400,
        american=False,
        **_HULL_CRR,
    )
    assert tree.price == pytest.approx(bs.price, abs=0.02)


def test_deep_itm_american_put_near_intrinsic() -> None:
    result = crr_american_price_greeks(
        spot=50.0,
        strike=100.0,
        time_years=1.0,
        rate=0.05,
        volatility=0.15,
        right="put",
        steps=150,
    )
    assert result.price >= 50.0
    assert result.price == pytest.approx(50.0, abs=0.05)
    assert result.delta == pytest.approx(-1.0, abs=0.02)


def test_deep_otm_american_call_near_zero() -> None:
    result = crr_american_price_greeks(
        spot=50.0,
        strike=100.0,
        time_years=1.0,
        rate=0.05,
        volatility=0.15,
        right="call",
        steps=150,
    )
    assert result.price < 0.05
    assert result.delta == pytest.approx(0.0, abs=0.02)


def test_atm_american_greeks_signs() -> None:
    result = crr_american_price_greeks(right="put", steps=100, **_HULL_CRR)
    assert -1.0 < result.delta < 0.0
    assert result.gamma > 0.0
    assert result.vega > 0.0
    assert result.theta < 0.0


def test_dividend_yield_can_make_american_call_exceed_european() -> None:
    kwargs = {
        "spot": 100.0,
        "strike": 70.0,
        "time_years": 1.0,
        "rate": 0.03,
        "volatility": 0.20,
        "dividend_yield": 0.12,
    }
    american = crr_american_price_greeks(right="call", steps=200, **kwargs)
    european = black_scholes_price_greeks(right="call", **kwargs)
    assert american.price >= european.price - 1e-10
    assert american.price - european.price > 0.05


def test_expired_matches_intrinsic() -> None:
    result = crr_american_price_greeks(
        spot=40.0,
        strike=50.0,
        time_years=0.0,
        rate=0.1,
        volatility=0.4,
        right="put",
        steps=5,
    )
    assert result.price == pytest.approx(10.0)
    assert result.delta == pytest.approx(-1.0)


def test_two_step_tree_has_finite_greeks() -> None:
    result = crr_american_price_greeks(right="put", steps=2, **_HULL_CRR)
    assert result.price > 0.0
    assert math.isfinite(result.gamma)
    assert result.gamma > 0.0
    assert -1.0 < result.delta < 0.0


def test_rejects_too_few_steps() -> None:
    with pytest.raises(ValueError, match="steps"):
        crr_american_price_greeks(right="put", steps=1, **_HULL_CRR)


def test_rejects_invalid_risk_neutral_probability() -> None:
    with pytest.raises(ValueError, match="risk-neutral probability"):
        crr_american_price_greeks(
            spot=50.0,
            strike=50.0,
            time_years=1.0,
            rate=5.0,
            volatility=0.01,
            right="put",
            steps=2,
        )


def test_european_tree_put_call_parity_limit() -> None:
    call = _crr_price_greeks(right="call", steps=300, american=False, **_HULL_CRR)
    put = _crr_price_greeks(right="put", steps=300, american=False, **_HULL_CRR)
    forward = _HULL_CRR["spot"] * math.exp(
        -_HULL_CRR["dividend_yield"] * _HULL_CRR["time_years"]
    ) - _HULL_CRR["strike"] * math.exp(-_HULL_CRR["rate"] * _HULL_CRR["time_years"])
    assert call.price - put.price == pytest.approx(forward, abs=0.02)
