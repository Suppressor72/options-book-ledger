"""Mark-to-model book reprice on a small spot × vol grid."""

from __future__ import annotations

import math
from collections.abc import Sequence

from optledger.book.models import (
    DEFAULT_SCENARIO_MOVES,
    BookReprice,
    BookSnapshot,
    OptionPosition,
    ScenarioGrid,
    as_move_tuple,
)
from optledger.pricing import black_scholes_price_greeks, crr_american_price_greeks


def mark_book(book: BookSnapshot, *, steps: int = 100) -> float:
    """Model value of the book at the pinned spot and each lot's IV."""
    return _book_value(book, spot=book.spot, vol_mult=1.0, steps=steps)


def reprice_book(
    book: BookSnapshot,
    spot_mult: float,
    vol_mult: float = 1.0,
    *,
    steps: int = 100,
) -> BookReprice:
    """Reprice the book at ``spot * spot_mult`` and ``iv * vol_mult``.

    P/L is scenario mark minus base mark. Short lots (negative quantity) gain
    when the option's model price falls.
    """
    if not math.isfinite(spot_mult) or spot_mult <= 0.0:
        raise ValueError(f"spot_mult must be positive and finite, got {spot_mult!r}")
    if not math.isfinite(vol_mult) or vol_mult <= 0.0:
        raise ValueError(f"vol_mult must be positive and finite, got {vol_mult!r}")
    base_value = mark_book(book, steps=steps)
    scenario_value = _book_value(
        book,
        spot=book.spot * spot_mult,
        vol_mult=vol_mult,
        steps=steps,
    )
    return BookReprice(
        base_value=base_value,
        scenario_value=scenario_value,
        pnl=scenario_value - base_value,
        spot_mult=spot_mult,
        vol_mult=vol_mult,
    )


def scenario_pnl_grid(
    book: BookSnapshot,
    *,
    spot_moves: Sequence[float] = DEFAULT_SCENARIO_MOVES,
    vol_moves: Sequence[float] = DEFAULT_SCENARIO_MOVES,
    steps: int = 100,
) -> ScenarioGrid:
    """Small 2-D mark-to-model P/L grid. This is not a VaR engine."""
    spots = as_move_tuple(spot_moves)
    vols = as_move_tuple(vol_moves)
    base_value = mark_book(book, steps=steps)
    rows: list[tuple[float, ...]] = []
    for vol_move in vols:
        row = tuple(
            _book_value(
                book,
                spot=book.spot * (1.0 + spot_move),
                vol_mult=1.0 + vol_move,
                steps=steps,
            )
            - base_value
            for spot_move in spots
        )
        rows.append(row)
    return ScenarioGrid(spot_moves=spots, vol_moves=vols, pnl=tuple(rows))


def _book_value(
    book: BookSnapshot,
    *,
    spot: float,
    vol_mult: float,
    steps: int,
) -> float:
    return sum(
        _leg_value(
            book, position, spot=spot, volatility=position.volatility * vol_mult, steps=steps
        )
        for position in book.positions
    )


def _leg_value(
    book: BookSnapshot,
    position: OptionPosition,
    *,
    spot: float,
    volatility: float,
    steps: int,
) -> float:
    unit = _unit_price(book, position, spot=spot, volatility=volatility, steps=steps)
    return unit * position.quantity * position.multiplier


def _unit_price(
    book: BookSnapshot,
    position: OptionPosition,
    *,
    spot: float,
    volatility: float,
    steps: int,
) -> float:
    if position.style == "european":
        return black_scholes_price_greeks(
            spot=spot,
            strike=position.strike,
            time_years=position.time_years,
            rate=book.rate,
            volatility=volatility,
            right=position.right,
            dividend_yield=book.dividend_yield,
        ).price
    return crr_american_price_greeks(
        spot=spot,
        strike=position.strike,
        time_years=position.time_years,
        rate=book.rate,
        volatility=volatility,
        right=position.right,
        dividend_yield=book.dividend_yield,
        steps=steps,
    ).price
