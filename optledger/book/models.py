"""In-memory option book types for mark-to-model reprice.

Supporting math only — snapshot I/O lives in later product phases.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

from optledger.pricing import OptionRight

type ExerciseStyle = Literal["american", "european"]

# Documented default; not a VaR engine and not a dense trading-grid.
DEFAULT_SCENARIO_MOVES: tuple[float, ...] = (-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20)


@dataclass(frozen=True, slots=True)
class OptionPosition:
    """One option lot. ``quantity`` is signed (short is negative)."""

    quantity: float
    strike: float
    time_years: float
    volatility: float
    right: OptionRight
    multiplier: float = 100.0
    style: ExerciseStyle = "american"

    def __post_init__(self) -> None:
        _finite("quantity", self.quantity)
        _finite("strike", self.strike)
        _finite("time_years", self.time_years)
        _finite("volatility", self.volatility)
        _finite("multiplier", self.multiplier)
        if self.strike <= 0.0:
            raise ValueError(f"strike must be positive, got {self.strike!r}")
        if self.time_years < 0.0:
            raise ValueError(f"time_years must be >= 0, got {self.time_years!r}")
        if self.volatility < 0.0:
            raise ValueError(f"volatility must be >= 0, got {self.volatility!r}")
        if self.multiplier <= 0.0:
            raise ValueError(f"multiplier must be positive, got {self.multiplier!r}")
        if self.right not in ("call", "put"):
            raise ValueError(f"right must be 'call' or 'put', got {self.right!r}")
        if self.style not in ("american", "european"):
            raise ValueError(f"style must be 'american' or 'european', got {self.style!r}")


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """Pinned spot / rate / yield plus option lots sharing that underlying."""

    spot: float
    rate: float
    positions: tuple[OptionPosition, ...]
    dividend_yield: float = 0.0

    def __post_init__(self) -> None:
        _finite("spot", self.spot)
        _finite("rate", self.rate)
        _finite("dividend_yield", self.dividend_yield)
        if self.spot <= 0.0:
            raise ValueError(f"spot must be positive, got {self.spot!r}")


@dataclass(frozen=True, slots=True)
class BookReprice:
    """Mark-to-model values before and after a spot/vol scenario."""

    base_value: float
    scenario_value: float
    pnl: float
    spot_mult: float
    vol_mult: float


@dataclass(frozen=True, slots=True)
class ScenarioGrid:
    """P/L matrix for the documented small spot × vol grid.

    ``pnl[i][j]`` is the book P/L at ``vol_moves[i]`` and ``spot_moves[j]``.
    Moves are additive on 1.0 (``+0.10`` → multiplier ``1.10``).
    """

    spot_moves: tuple[float, ...]
    vol_moves: tuple[float, ...]
    pnl: tuple[tuple[float, ...], ...]

    def cell(self, spot_move: float, vol_move: float) -> float:
        try:
            col = self.spot_moves.index(spot_move)
            row = self.vol_moves.index(vol_move)
        except ValueError as exc:
            raise KeyError(f"no cell for spot_move={spot_move!r}, vol_move={vol_move!r}") from exc
        return self.pnl[row][col]


def _finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


def as_move_tuple(moves: Sequence[float]) -> tuple[float, ...]:
    out = tuple(float(m) for m in moves)
    if not out:
        raise ValueError("scenario moves must not be empty")
    for move in out:
        if not math.isfinite(move):
            raise ValueError(f"scenario move must be finite, got {move!r}")
        if move <= -1.0:
            raise ValueError(
                f"scenario move must be > -1 so the multiplier stays positive, got {move!r}"
            )
    return out
