from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from optledger.cli.app import app
from optledger.data.schema import FAMILIES, SnapshotFamily
from optledger.data.store import write_snapshots
from optledger.ledger.schema import LEDGER_COLUMNS
from optledger.ledger.store import write_ledger

REPO = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO / "fixtures" / "demo.json"
EXPIRE = REPO / "fixtures" / "ledger_expire_worthless.json"
ASSIGN = REPO / "fixtures" / "ledger_assignment.json"
QTY_BREAK = REPO / "fixtures" / "ledger_qty_break.json"

runner = CliRunner()


def _write_ops(dest: Path, path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    frames: dict[SnapshotFamily, pd.DataFrame] = {
        family: pd.DataFrame(raw[family]) for family in FAMILIES
    }
    events = pd.DataFrame(raw["events"], columns=list(LEDGER_COLUMNS))
    write_snapshots(dest, frames)
    write_ledger(dest, events)


def test_ledger_recon_exits_zero_on_demo(tmp_path: Path) -> None:
    built = tmp_path / "demo"
    build = runner.invoke(
        app,
        ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)],
    )
    assert build.exit_code == 0, build.output
    assert any((built / "ledger").glob("*.parquet"))
    result = runner.invoke(app, ["ledger-recon", "--data", str(built)])
    assert result.exit_code == 0, result.output
    assert "ok:" in result.output


def test_ledger_recon_exits_zero_on_expire_and_assignment(tmp_path: Path) -> None:
    for fixture in (EXPIRE, ASSIGN):
        dest = tmp_path / fixture.stem
        _write_ops(dest, fixture)
        dq = runner.invoke(app, ["dq", "--data", str(dest)])
        assert dq.exit_code == 0, dq.output
        recon = runner.invoke(app, ["ledger-recon", "--data", str(dest)])
        assert recon.exit_code == 0, recon.output


def test_ledger_recon_exits_one_on_null_eod_as_of(tmp_path: Path) -> None:
    dest = tmp_path / "null-eod"
    _write_ops(dest, EXPIRE)
    frames = {family: pd.read_parquet(dest / f"{family}.parquet") for family in FAMILIES}
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    frames["account_snapshot"].loc[eod, "as_of"] = None
    write_snapshots(dest, frames)
    result = runner.invoke(app, ["ledger-recon", "--data", str(dest)])
    assert result.exit_code == 1, result.output
    assert not isinstance(result.exception, (TypeError, ValueError))
    assert "missing_eod" in result.output or "as_of" in result.output
    dest = tmp_path / "qty-break"
    _write_ops(dest, QTY_BREAK)
    result = runner.invoke(app, ["ledger-recon", "--data", str(dest)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert "qty_break" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError))


def test_ledger_recon_exits_one_on_cash_break(tmp_path: Path) -> None:
    dest = tmp_path / "cash-break"
    _write_ops(dest, EXPIRE)
    frames = {family: pd.read_parquet(dest / f"{family}.parquet") for family in FAMILIES}
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    # Ledger cash no longer matches the account cash pin.
    frames["account_snapshot"].loc[eod, "cash"] = 1.0
    frames["account_snapshot"].loc[eod, "nlv"] = 1.0 + 500.0
    write_snapshots(dest, frames)
    result = runner.invoke(app, ["ledger-recon", "--data", str(dest)])
    assert result.exit_code == 1, result.output
    assert "cash_break" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError))


def test_ledger_recon_exits_one_on_nlv_break(tmp_path: Path) -> None:
    dest = tmp_path / "nlv-break"
    _write_ops(dest, EXPIRE)
    frames = {family: pd.read_parquet(dest / f"{family}.parquet") for family in FAMILIES}
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    # Cash still reconciles, but nlv no longer equals cash plus the marked book.
    frames["account_snapshot"].loc[eod, "nlv"] = 0.0
    write_snapshots(dest, frames)
    result = runner.invoke(app, ["ledger-recon", "--data", str(dest)])
    assert result.exit_code == 1, result.output
    assert "nlv_break" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError))
