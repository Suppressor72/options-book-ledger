from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from optledger.data.schema import FAMILIES, SnapshotFamily
from optledger.ledger.recon import parse_as_of_key, recon_frames
from optledger.ledger.schema import LEDGER_COLUMNS
from optledger.ledger.store import read_ledger, write_ledger

REPO = Path(__file__).resolve().parents[1]
EXPIRE = REPO / "fixtures" / "ledger_expire_worthless.json"
ASSIGN = REPO / "fixtures" / "ledger_assignment.json"
QTY_BREAK = REPO / "fixtures" / "ledger_qty_break.json"


def _load_ops(path: Path) -> tuple[dict[SnapshotFamily, pd.DataFrame], pd.DataFrame]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    frames = {family: pd.DataFrame(raw[family]) for family in FAMILIES}
    events = pd.DataFrame(raw["events"], columns=list(LEDGER_COLUMNS))
    return frames, events


def test_parse_as_of_key_rejects_null_and_garbage() -> None:
    assert parse_as_of_key("2024-06-21T16:00:00") == "2024-06-21T16:00:00"
    assert parse_as_of_key("2024-06-21") == "2024-06-21T00:00:00"
    assert parse_as_of_key(None) is None
    assert parse_as_of_key("None") is None
    assert parse_as_of_key("2025") is None
    assert parse_as_of_key("") is None


def test_expire_worthless_fixture_recons_clean() -> None:
    frames, events = _load_ops(EXPIRE)
    report = recon_frames(frames, events)
    assert report.ok
    assert "expire_worthless" in set(events["event_kind"])


def test_assignment_fixture_recons_clean_with_underlier() -> None:
    frames, events = _load_ops(ASSIGN)
    report = recon_frames(frames, events)
    assert report.ok
    assert "assignment" in set(events["event_kind"])
    eod = frames["position_snapshot"]
    eod = eod[eod["snapshot_id"] == "2024-06-21-eod"]
    assert list(eod["instrument_id"]) == ["XYZ"]
    assert float(eod["qty"].iloc[0]) == 100.0


def test_missing_expire_event_is_qty_break() -> None:
    frames, events = _load_ops(QTY_BREAK)
    report = recon_frames(frames, events)
    assert not report.ok
    assert any(issue.code == "qty_break" for issue in report.issues)
    assert any(issue.instrument_id == "XYZ-20240621-P-90" for issue in report.issues)


def test_cash_mismatch_is_cash_break() -> None:
    frames, events = _load_ops(EXPIRE)
    frames["account_snapshot"] = frames["account_snapshot"].copy()
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    frames["account_snapshot"].loc[eod, "cash"] = 1.0
    frames["account_snapshot"].loc[eod, "nlv"] = 1.0 + 500.0
    report = recon_frames(frames, events)
    assert not report.ok
    assert any(issue.code == "cash_break" for issue in report.issues)


def test_nlv_mismatch_is_nlv_break() -> None:
    frames, events = _load_ops(EXPIRE)
    frames["account_snapshot"] = frames["account_snapshot"].copy()
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    frames["account_snapshot"].loc[eod, "nlv"] = 0.0
    report = recon_frames(frames, events)
    assert not report.ok
    assert any(issue.code == "nlv_break" for issue in report.issues)


def test_garbage_event_as_of_is_schema_not_raise() -> None:
    frames, events = _load_ops(EXPIRE)
    events = events.copy()
    events.loc[0, "as_of"] = None
    report = recon_frames(frames, events)
    assert not report.ok
    assert any(issue.code == "schema" for issue in report.issues)


def test_null_eod_as_of_is_schema_and_missing_eod() -> None:
    frames, events = _load_ops(EXPIRE)
    frames["account_snapshot"] = frames["account_snapshot"].copy()
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    frames["account_snapshot"].loc[eod, "as_of"] = None
    report = recon_frames(frames, events)
    assert not report.ok
    assert any(issue.code == "schema" and "as_of" in issue.message for issue in report.issues)
    assert any(issue.code == "missing_eod" for issue in report.issues)


def test_open_only_account_is_missing_eod() -> None:
    frames, events = _load_ops(EXPIRE)
    account = frames["account_snapshot"]
    frames["account_snapshot"] = account[account["pin_kind"] == "open"].copy()
    report = recon_frames(frames, events)
    assert not report.ok
    assert any(issue.code == "missing_eod" for issue in report.issues)


def test_write_ledger_replaces_stale_year_files(tmp_path: Path) -> None:
    def _events(year: str, event_id: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "event_id": event_id,
                    "as_of": f"{year}-06-21T00:00:00",
                    "account": "demo",
                    "event_kind": "cash_deposit",
                    "symbol": "XYZ",
                    "instrument_id": "",
                    "qty": 0.0,
                    "cash": 1.0,
                }
            ],
            columns=list(LEDGER_COLUMNS),
        )

    write_ledger(tmp_path, _events("2023", "evt-old"))
    assert (tmp_path / "ledger" / "2023.parquet").is_file()
    write_ledger(tmp_path, _events("2024", "evt-new"))
    assert not (tmp_path / "ledger" / "2023.parquet").is_file()
    loaded = read_ledger(tmp_path)
    assert list(loaded["event_id"]) == ["evt-new"]
    assert str(loaded["as_of"].iloc[0]).startswith("2024")
