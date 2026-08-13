from __future__ import annotations

import pytest

from optledger.book import (
    DEFAULT_SCENARIO_MOVES,
    BookSnapshot,
    OptionPosition,
    example_xyz_call_spread,
    mark_book,
    reprice_book,
    scenario_pnl_grid,
)
from optledger.pricing import black_scholes_price_greeks, crr_american_price_greeks

_STEPS = 80


def _independent_leg_value(
    book: BookSnapshot,
    position: OptionPosition,
    *,
    spot: float,
    volatility: float,
) -> float:
    if position.style == "european":
        unit = black_scholes_price_greeks(
            spot=spot,
            strike=position.strike,
            time_years=position.time_years,
            rate=book.rate,
            volatility=volatility,
            right=position.right,
            dividend_yield=book.dividend_yield,
        ).price
    else:
        unit = crr_american_price_greeks(
            spot=spot,
            strike=position.strike,
            time_years=position.time_years,
            rate=book.rate,
            volatility=volatility,
            right=position.right,
            dividend_yield=book.dividend_yield,
            steps=_STEPS,
        ).price
    return unit * position.quantity * position.multiplier


def _independent_book_value(book: BookSnapshot, *, spot: float, vol_mult: float) -> float:
    return sum(
        _independent_leg_value(
            book,
            position,
            spot=spot,
            volatility=position.volatility * vol_mult,
        )
        for position in book.positions
    )


def test_default_scenario_moves_are_the_documented_small_grid() -> None:
    assert DEFAULT_SCENARIO_MOVES == (-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20)


def test_reprice_matches_independently_computed_two_contract_example() -> None:
    book = example_xyz_call_spread()
    assert len(book.positions) == 2
    spot_mult = 1.10
    vol_mult = 0.90
    result = reprice_book(book, spot_mult=spot_mult, vol_mult=vol_mult, steps=_STEPS)
    base = _independent_book_value(book, spot=book.spot, vol_mult=1.0)
    scenario = _independent_book_value(
        book,
        spot=book.spot * spot_mult,
        vol_mult=vol_mult,
    )
    assert result.base_value == pytest.approx(base, abs=1e-9)
    assert result.scenario_value == pytest.approx(scenario, abs=1e-9)
    assert result.pnl == pytest.approx(scenario - base, abs=1e-9)


def test_heatmap_cell_matches_independent_two_contract_example() -> None:
    book = example_xyz_call_spread()
    grid = scenario_pnl_grid(book, steps=_STEPS)
    spot_move = 0.10
    vol_move = -0.10
    expected = reprice_book(
        book,
        spot_mult=1.0 + spot_move,
        vol_mult=1.0 + vol_move,
        steps=_STEPS,
    ).pnl
    independent = _independent_book_value(
        book,
        spot=book.spot * (1.0 + spot_move),
        vol_mult=1.0 + vol_move,
    ) - _independent_book_value(book, spot=book.spot, vol_mult=1.0)
    assert grid.cell(spot_move, vol_move) == pytest.approx(expected, abs=1e-9)
    assert grid.cell(spot_move, vol_move) == pytest.approx(independent, abs=1e-9)


def test_unchanged_spot_and_vol_has_zero_pnl() -> None:
    book = example_xyz_call_spread()
    result = reprice_book(book, spot_mult=1.0, vol_mult=1.0, steps=_STEPS)
    assert result.pnl == pytest.approx(0.0, abs=1e-9)
    grid = scenario_pnl_grid(book, steps=_STEPS)
    assert grid.cell(0.0, 0.0) == pytest.approx(0.0, abs=1e-9)


def test_short_call_spread_loses_on_upside() -> None:
    book = example_xyz_call_spread()
    up = reprice_book(book, spot_mult=1.20, vol_mult=1.0, steps=_STEPS)
    down = reprice_book(book, spot_mult=0.80, vol_mult=1.0, steps=_STEPS)
    assert up.pnl < 0.0
    assert down.pnl > up.pnl


def test_european_legs_use_black_scholes() -> None:
    book = BookSnapshot(
        spot=100.0,
        rate=0.05,
        positions=(
            OptionPosition(
                quantity=-1.0,
                strike=100.0,
                time_years=0.5,
                volatility=0.20,
                right="put",
                style="european",
            ),
        ),
    )
    marked = mark_book(book)
    unit = black_scholes_price_greeks(
        spot=100.0,
        strike=100.0,
        time_years=0.5,
        rate=0.05,
        volatility=0.20,
        right="put",
    ).price
    assert marked == pytest.approx(-1.0 * 100.0 * unit, abs=1e-12)


def test_rejects_non_positive_multipliers() -> None:
    book = example_xyz_call_spread()
    with pytest.raises(ValueError, match="spot_mult"):
        reprice_book(book, spot_mult=0.0, steps=_STEPS)
    with pytest.raises(ValueError, match="vol_mult"):
        reprice_book(book, spot_mult=1.0, vol_mult=-0.5, steps=_STEPS)


def test_grid_rejects_move_that_zeros_the_multiplier() -> None:
    book = example_xyz_call_spread()
    with pytest.raises(ValueError, match="move"):
        scenario_pnl_grid(book, spot_moves=(-1.0, 0.0), steps=_STEPS)
