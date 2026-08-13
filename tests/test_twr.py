from __future__ import annotations

from datetime import datetime

import pytest

from optledger.metrics import CashFlow, NlvPoint, TwrError, twr_for_window, twr_index


def _p(day: str, nlv: float, hour: int = 16) -> NlvPoint:
    return NlvPoint(as_of=datetime.fromisoformat(f"{day}T{hour:02d}:00:00"), nlv=nlv)


def _d(day: str, amount: float, hour: int = 0) -> CashFlow:
    return CashFlow(as_of=datetime.fromisoformat(f"{day}T{hour:02d}:00:00"), amount=amount)


def test_twr_without_flows_matches_linked_simple_returns() -> None:
    points = (_p("2024-01-01", 100.0), _p("2024-01-02", 110.0), _p("2024-01-03", 99.0))
    series = twr_index(points, ())
    assert series.values[0] == pytest.approx(1.0)
    assert series.values[1] == pytest.approx(1.10)
    assert series.values[2] == pytest.approx(0.99)
    result = twr_for_window(points, (), "all")
    assert result.twr == pytest.approx(-0.01)
    assert result.max_drawdown == pytest.approx(0.99 / 1.10 - 1.0)
    assert result.time_to_recovery_days is None


def test_opening_deposit_is_not_a_flow() -> None:
    points = (_p("2024-01-01", 100.0), _p("2024-01-02", 110.0))
    opening = (_d("2024-01-01", 100.0, hour=0),)
    with_flow = twr_index(points, opening)
    without = twr_index(points, ())
    assert with_flow.values == without.values
    assert with_flow.values[-1] == pytest.approx(1.10)


def test_mid_window_deposit_adjusts_the_interval_start() -> None:
    points = (_p("2024-01-01", 100.0), _p("2024-01-02", 165.0))
    deposit = (_d("2024-01-02", 50.0, hour=0),)
    result = twr_for_window(points, deposit, "all")
    assert result.twr == pytest.approx(0.10)


def test_max_dd_recovers_in_one_calendar_day() -> None:
    points = (
        _p("2024-01-01", 100.0),
        _p("2024-01-02", 120.0),
        _p("2024-01-03", 90.0),
        _p("2024-01-04", 120.0),
    )
    result = twr_for_window(points, (), "all")
    assert result.max_drawdown == pytest.approx(0.90 / 1.20 - 1.0)
    assert result.time_to_recovery_days == 1


def test_ytd_and_trailing_12_slice_independently() -> None:
    points = (
        _p("2023-06-01", 100.0),
        _p("2023-12-31", 110.0),
        _p("2024-01-15", 121.0),
        _p("2024-06-01", 100.0),
    )
    ytd = twr_for_window(points, (), "ytd")
    trailing = twr_for_window(points, (), "trailing-12")
    all_windows = twr_for_window(points, (), "all")
    assert ytd.start.date().isoformat() == "2024-01-15"
    assert ytd.twr == pytest.approx(100.0 / 121.0 - 1.0)
    assert trailing.start.date().isoformat() == "2023-12-31"
    assert trailing.twr == pytest.approx(100.0 / 110.0 - 1.0)
    assert all_windows.twr == pytest.approx(0.0)


def test_nonpositive_nlv_is_fail_closed() -> None:
    with pytest.raises(TwrError, match="non-positive"):
        twr_index((_p("2024-01-01", 100.0), _p("2024-01-02", 0.0)), ())


def test_empty_points_is_fail_closed() -> None:
    with pytest.raises(TwrError, match="at least one"):
        twr_index((), ())
