"""Optional cross-checks against vollib (optledger[ref]) and QuantLib.

Vollib tests skip when the ref extra is missing. The QuantLib American CRR
check skips unless QuantLib is installed separately; it is not a declared extra.
Core tests never require these packages.
"""

from __future__ import annotations

from typing import Any

import pytest

from optledger.pricing import black_scholes_price_greeks, crr_american_price_greeks

_CASES = (
    {"spot": 42.0, "strike": 40.0, "time_years": 0.5, "rate": 0.10, "volatility": 0.20},
    {"spot": 100.0, "strike": 100.0, "time_years": 1.0, "rate": 0.01, "volatility": 0.25},
    {"spot": 90.0, "strike": 110.0, "time_years": 0.25, "rate": 0.05, "volatility": 0.35},
)


def _vollib_flag(right: str) -> str:
    return "c" if right == "call" else "p"


def _load_bs() -> Any:
    pytest.importorskip("vollib")
    from vollib.black_scholes import black_scholes
    from vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega

    return black_scholes, delta, gamma, theta, vega


@pytest.mark.parametrize("right", ["call", "put"])
@pytest.mark.parametrize("case", _CASES)
def test_european_bs_matches_vollib(right: str, case: dict[str, float]) -> None:
    black_scholes, delta, gamma, theta, vega = _load_bs()
    ours = black_scholes_price_greeks(right=right, dividend_yield=0.0, **case)
    flag = _vollib_flag(right)
    args = (
        flag,
        case["spot"],
        case["strike"],
        case["time_years"],
        case["rate"],
        case["volatility"],
    )
    assert ours.price == pytest.approx(black_scholes(*args), abs=1e-8)
    assert ours.delta == pytest.approx(delta(*args), abs=1e-8)
    assert ours.gamma == pytest.approx(gamma(*args), abs=1e-8)
    assert ours.theta == pytest.approx(theta(*args), abs=1e-8)
    assert ours.vega == pytest.approx(vega(*args), abs=1e-8)


@pytest.mark.parametrize("right", ["call", "put"])
def test_bsm_with_yield_matches_vollib_merton(right: str) -> None:
    pytest.importorskip("vollib")
    from vollib.black_scholes_merton import black_scholes_merton
    from vollib.black_scholes_merton.greeks.analytical import delta, gamma, theta, vega

    kwargs = {
        "spot": 100.0,
        "strike": 95.0,
        "time_years": 0.75,
        "rate": 0.06,
        "volatility": 0.22,
        "dividend_yield": 0.03,
    }
    ours = black_scholes_price_greeks(right=right, **kwargs)
    flag = _vollib_flag(right)
    args = (
        flag,
        kwargs["spot"],
        kwargs["strike"],
        kwargs["time_years"],
        kwargs["rate"],
        kwargs["volatility"],
        kwargs["dividend_yield"],
    )
    assert ours.price == pytest.approx(black_scholes_merton(*args), abs=1e-8)
    assert ours.delta == pytest.approx(delta(*args), abs=1e-8)
    assert ours.gamma == pytest.approx(gamma(*args), abs=1e-8)
    assert ours.theta == pytest.approx(theta(*args), abs=1e-8)
    assert ours.vega == pytest.approx(vega(*args), abs=1e-8)


def test_crr_american_put_matches_quantlib_binomial() -> None:
    """Skip-if-installed oracle. QuantLib is not part of optledger[ref] (vollib only)."""
    ql = pytest.importorskip("QuantLib")
    spot = 50.0
    strike = 50.0
    rate = 0.10
    vol = 0.40
    steps = 100
    ours = crr_american_price_greeks(
        spot=spot,
        strike=strike,
        time_years=1.0,
        rate=rate,
        volatility=vol,
        right="put",
        dividend_yield=0.0,
        steps=steps,
    )

    today = ql.Date(1, 1, 2024)
    ql.Settings.instance().evaluationDate = today
    daycount = ql.Actual365Fixed()
    calendar = ql.NullCalendar()
    maturity = today + 365
    process = ql.BlackScholesProcess(
        ql.QuoteHandle(ql.SimpleQuote(spot)),
        ql.YieldTermStructureHandle(ql.FlatForward(today, rate, daycount)),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, calendar, vol, daycount)),
    )
    option = ql.VanillaOption(
        ql.PlainVanillaPayoff(ql.Option.Put, strike),
        ql.AmericanExercise(today, maturity),
    )
    option.setPricingEngine(ql.BinomialVanillaEngine(process, "crr", steps))
    assert ours.price == pytest.approx(option.NPV(), rel=1e-4, abs=1e-3)
