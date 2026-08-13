"""Flow-adjusted time-weighted return from an NLV series and deposits.

Cash flows are treated as arriving at the start of the interval that contains
them: ``r = NLV_t / (NLV_{t-1} + deposits) - 1``. Deposits at or before the
first observation are ignored (already inside that NLV). Fees and fill
premiums are not flows; they already sit in marked NLV.

Windows are calendar ``all``, ``ytd``, and ``trailing-12`` (365 days).
``ytd`` is TWR across pins whose ``as_of`` falls in the calendar year of the
last pin — not a January-1 NAV interpolation. This is not a QuantStats clone:
no first-party Sharpe, Sortino, Calmar, or Ulcer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Sequence

type TwrWindowName = Literal["all", "ytd", "trailing-12"]

WINDOWS: tuple[TwrWindowName, ...] = ("all", "ytd", "trailing-12")
TRAILING_DAYS = 365
_INDEX_TOL = 1e-12


class TwrError(ValueError):
    """Fail-closed TWR input or arithmetic error."""


@dataclass(frozen=True, slots=True)
class NlvPoint:
    as_of: datetime
    nlv: float


@dataclass(frozen=True, slots=True)
class CashFlow:
    as_of: datetime
    amount: float


@dataclass(frozen=True, slots=True)
class TwrIndex:
    times: tuple[datetime, ...]
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TwrResult:
    window: TwrWindowName
    start: datetime
    end: datetime
    twr: float
    max_drawdown: float
    time_to_recovery_days: int | None
    index: TwrIndex


def twr_index(points: Sequence[NlvPoint], deposits: Sequence[CashFlow]) -> TwrIndex:
    """Link interval returns into an index that starts at 1.0."""
    ordered = _ordered_points(points)
    times = [ordered[0].as_of]
    values = [1.0]
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        flow = _interval_flow(deposits, start=prev.as_of, end=curr.as_of)
        start_value = prev.nlv + flow
        if not math.isfinite(start_value) or start_value <= 0.0:
            raise TwrError(
                f"non-positive TWR start value {start_value} at {curr.as_of.isoformat()}"
            )
        if not math.isfinite(curr.nlv) or curr.nlv <= 0.0:
            raise TwrError(f"non-positive NLV {curr.nlv} at {curr.as_of.isoformat()}")
        growth = curr.nlv / start_value
        values.append(values[-1] * growth)
        times.append(curr.as_of)
    return TwrIndex(times=tuple(times), values=tuple(values))


def twr_for_window(
    points: Sequence[NlvPoint],
    deposits: Sequence[CashFlow],
    window: TwrWindowName,
) -> TwrResult:
    if window not in WINDOWS:
        raise TwrError(f"unknown window {window!r}")
    sliced = _slice_window(points, window)
    series = twr_index(sliced, deposits)
    max_dd, ttr = _drawdown(series)
    return TwrResult(
        window=window,
        start=series.times[0],
        end=series.times[-1],
        twr=series.values[-1] - 1.0,
        max_drawdown=max_dd,
        time_to_recovery_days=ttr,
        index=series,
    )


def report_windows(
    points: Sequence[NlvPoint],
    deposits: Sequence[CashFlow],
) -> tuple[TwrResult, ...]:
    return tuple(twr_for_window(points, deposits, window) for window in WINDOWS)


def _ordered_points(points: Sequence[NlvPoint]) -> tuple[NlvPoint, ...]:
    if not points:
        raise TwrError("need at least one NLV point")
    ordered = tuple(sorted(points, key=lambda point: point.as_of))
    seen: set[datetime] = set()
    cleaned: list[NlvPoint] = []
    for point in ordered:
        if point.as_of in seen:
            raise TwrError(f"duplicate NLV as_of {point.as_of.isoformat()}")
        seen.add(point.as_of)
        if not math.isfinite(point.nlv) or point.nlv <= 0.0:
            raise TwrError(f"non-positive NLV {point.nlv} at {point.as_of.isoformat()}")
        cleaned.append(point)
    return tuple(cleaned)


def _interval_flow(
    deposits: Sequence[CashFlow],
    *,
    start: datetime,
    end: datetime,
) -> float:
    total = 0.0
    for flow in deposits:
        if not math.isfinite(flow.amount):
            raise TwrError(f"non-finite deposit {flow.amount} at {flow.as_of.isoformat()}")
        if start < flow.as_of <= end:
            total += flow.amount
    return total


def _slice_window(points: Sequence[NlvPoint], window: TwrWindowName) -> tuple[NlvPoint, ...]:
    ordered = _ordered_points(points)
    last = ordered[-1].as_of
    if window == "all":
        cutoff = ordered[0].as_of
    elif window == "ytd":
        cutoff = datetime(last.year, 1, 1)
    else:
        cutoff = last - timedelta(days=TRAILING_DAYS)
    sliced = tuple(point for point in ordered if point.as_of >= cutoff)
    if not sliced:
        raise TwrError(f"window {window!r} has no NLV points")
    return sliced


def _drawdown(series: TwrIndex) -> tuple[float, int | None]:
    peak = series.values[0]
    max_dd = 0.0
    trough_time = series.times[0]
    peak_at_trough = peak
    for time, value in zip(series.times, series.values, strict=True):
        if value > peak:
            peak = value
        drawdown = value / peak - 1.0
        if drawdown < max_dd:
            max_dd = drawdown
            trough_time = time
            peak_at_trough = peak
    if max_dd >= -_INDEX_TOL:
        return 0.0, None
    for time, value in zip(series.times, series.values, strict=True):
        if time > trough_time and value >= peak_at_trough - _INDEX_TOL:
            return max_dd, (time.date() - trough_time.date()).days
    return max_dd, None
