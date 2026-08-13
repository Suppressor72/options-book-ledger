from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from optledger.cli.app import app
from optledger.data.dq import check_frames, parse_date, parse_finite_float
from optledger.data.schema import SnapshotFamily
from optledger.data.store import write_snapshots

runner = CliRunner()

_OPEN = "2024-06-05-open"
_EOD = "2024-06-05-eod"


def _clean_frames() -> dict[SnapshotFamily, pd.DataFrame]:
    account = pd.DataFrame(
        [
            {
                "snapshot_id": _OPEN,
                "as_of": "2024-06-05T09:30:00",
                "pin_kind": "open",
                "nlv": 100000.0,
                "cash": 100000.0,
            },
            {
                "snapshot_id": _EOD,
                "as_of": "2024-06-05T16:00:00",
                "pin_kind": "eod",
                "nlv": 100000.0,
                "cash": 100000.0,
            },
        ]
    )
    position_row = {
        "snapshot_id": _OPEN,
        "as_of": "2024-06-05T09:30:00",
        "pin_kind": "open",
        "symbol": "XYZ",
        "instrument_id": "XYZ-20240920-C-100",
        "right": "call",
        "strike": 100.0,
        "expiry": "2024-09-20",
        "qty": -1.0,
        "spot": 100.0,
        "iv": 0.2,
        "model_price": 4.0,
        "delta": 0.5,
        "vega": 0.1,
        "multiplier": 100.0,
        "style": "american",
    }
    eod_pos = dict(position_row)
    eod_pos["snapshot_id"] = _EOD
    eod_pos["as_of"] = "2024-06-05T16:00:00"
    eod_pos["pin_kind"] = "eod"
    metrics_row = {
        "snapshot_id": _OPEN,
        "as_of": "2024-06-05T09:30:00",
        "pin_kind": "open",
        "net_delta": -0.5,
        "net_vega": -0.1,
        "pnl_spot_m20": 0.0,
        "pnl_spot_m10": 0.0,
        "pnl_spot_m05": 0.0,
        "pnl_spot_0": 0.0,
        "pnl_spot_p05": 0.0,
        "pnl_spot_p10": 0.0,
        "pnl_spot_p20": 0.0,
    }
    eod_met = dict(metrics_row)
    eod_met["snapshot_id"] = _EOD
    eod_met["as_of"] = "2024-06-05T16:00:00"
    eod_met["pin_kind"] = "eod"
    return {
        "account_snapshot": account,
        "position_snapshot": pd.DataFrame([position_row, eod_pos]),
        "book_metrics": pd.DataFrame([metrics_row, eod_met]),
    }


def test_parse_finite_float_rejects_null_nan_inf() -> None:
    assert parse_finite_float(1.5) == 1.5
    assert parse_finite_float(None) is None
    assert parse_finite_float(math.nan) is None
    assert parse_finite_float(math.inf) is None
    assert parse_finite_float("not-a-number") is None


def test_parse_date_rejects_null_and_garbage() -> None:
    assert parse_date("2024-06-05T16:00:00") == "2024-06-05"
    assert parse_date(None) is None
    assert parse_date("None") is None
    assert parse_date("2025") is None
    assert parse_date("") is None
    assert parse_date("not-a-date") is None


def test_check_frames_reports_nan_spot_without_raising() -> None:
    frames = _clean_frames()
    frames["position_snapshot"].loc[0, "spot"] = math.nan
    report = check_frames(frames)
    assert not report.ok
    assert any(issue.code == "invalid_numeric" for issue in report.issues)


def test_check_frames_reports_null_as_of_without_raising() -> None:
    frames = _clean_frames()
    frames["account_snapshot"].loc[0, "as_of"] = None
    report = check_frames(frames)
    assert not report.ok
    assert any(issue.code == "schema" and "as_of" in issue.message for issue in report.issues)


def test_check_frames_reports_null_expiry_without_raising() -> None:
    frames = _clean_frames()
    frames["position_snapshot"].loc[0, "expiry"] = None
    report = check_frames(frames)
    assert not report.ok
    assert any(issue.code == "schema" and "expiry" in issue.message for issue in report.issues)


def test_check_frames_rejects_garbage_option_style() -> None:
    frames = _clean_frames()
    frames["position_snapshot"].loc[0, "style"] = "bermuda"
    report = check_frames(frames)
    assert not report.ok
    assert any(issue.code == "schema" and "style" in issue.message for issue in report.issues)


def test_check_frames_accepts_underlier_without_iv_or_expiry() -> None:
    frames = _clean_frames()
    underlier = {
        "snapshot_id": _EOD,
        "as_of": "2024-06-05T16:00:00",
        "pin_kind": "eod",
        "symbol": "XYZ",
        "instrument_id": "XYZ",
        "right": "",
        "strike": None,
        "expiry": None,
        "qty": 100.0,
        "spot": 100.0,
        "iv": None,
        "model_price": 100.0,
        "delta": 1.0,
        "vega": 0.0,
        "multiplier": 1.0,
        "style": "",
    }
    frames["position_snapshot"] = pd.concat(
        [frames["position_snapshot"], pd.DataFrame([underlier])],
        ignore_index=True,
    )
    report = check_frames(frames)
    assert report.ok


def test_dq_cli_exits_one_on_nan_spot_without_exception(tmp_path: Path) -> None:
    frames = _clean_frames()
    frames["position_snapshot"].loc[0, "spot"] = math.nan
    dest = tmp_path / "dirty"
    write_snapshots(dest, frames)
    result = runner.invoke(app, ["dq", "--data", str(dest)])
    assert result.exit_code == 1
    assert not isinstance(result.exception, (TypeError, ValueError))
    assert "invalid_numeric" in result.output


def test_null_snapshot_id_is_schema_not_nan_join() -> None:
    frames = _clean_frames()
    frames["position_snapshot"].loc[0, "snapshot_id"] = None
    report = check_frames(frames)
    assert not report.ok
    assert any(issue.code == "schema" and "snapshot_id" in issue.message for issue in report.issues)
    assert not any(issue.snapshot_id == "nan" for issue in report.issues)
    assert not any(issue.snapshot_id == "None" for issue in report.issues)


def test_nan_account_nlv_is_invalid_numeric() -> None:
    frames = _clean_frames()
    frames["account_snapshot"].loc[0, "nlv"] = math.nan
    report = check_frames(frames)
    assert not report.ok
    assert any(
        issue.family == "account_snapshot" and issue.code == "invalid_numeric"
        for issue in report.issues
    )


def test_nan_book_metrics_is_invalid_numeric() -> None:
    frames = _clean_frames()
    frames["book_metrics"].loc[0, "net_delta"] = math.nan
    report = check_frames(frames)
    assert not report.ok
    assert any(
        issue.family == "book_metrics" and issue.code == "invalid_numeric"
        for issue in report.issues
    )


def test_missing_metrics_column_still_reports_position_nan() -> None:
    frames = _clean_frames()
    frames["book_metrics"] = frames["book_metrics"].drop(columns=["net_vega"])
    frames["position_snapshot"].loc[0, "spot"] = math.nan
    report = check_frames(frames)
    assert any(issue.code == "schema" and "net_vega" in issue.message for issue in report.issues)
    assert any(
        issue.code == "invalid_numeric" and "spot" in issue.message for issue in report.issues
    )
