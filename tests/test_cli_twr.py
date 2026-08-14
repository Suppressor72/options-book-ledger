from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from optledger.cli.app import app
from optledger.cli.twr import write_quantstats_html
from optledger.data.schema import FAMILIES, SnapshotFamily
from optledger.data.store import write_snapshots
from optledger.ledger.store import read_ledger, write_ledger

REPO = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO / "fixtures" / "demo.json"

runner = CliRunner()


def test_twr_cli_exits_zero_on_demo(tmp_path: Path) -> None:
    built = tmp_path / "demo"
    build = runner.invoke(
        app,
        ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)],
    )
    assert build.exit_code == 0, build.output
    result = runner.invoke(app, ["twr", "--data", str(built)])
    assert result.exit_code == 0, result.output
    assert "simulated / seeded" in result.output
    assert "all" in result.output
    assert "ytd" in result.output
    assert "trailing-12" in result.output
    # Pin the README-published seeded numbers so the demo output cannot drift silently.
    lines = result.output.splitlines()
    all_row = next(line for line in lines if line.startswith("all"))
    ytd_row = next(line for line in lines if line.startswith("ytd"))
    trailing_row = next(line for line in lines if line.startswith("trailing-12"))
    # The demo spans late 2023 into mid-2025, so the three windows produce distinct
    # TWR, and each recovers from its worst drawdown within the window (ttr_days set).
    assert "0.48%" in all_row and "-0.28%" in all_row and all_row.rstrip().endswith("63")
    assert "0.13%" in ytd_row and "-0.19%" in ytd_row and ytd_row.rstrip().endswith("21")
    assert (
        "0.25%" in trailing_row
        and "-0.28%" in trailing_row
        and trailing_row.rstrip().endswith("63")
    )
    assert len({all_row, ytd_row, trailing_row}) == 3


def test_twr_cli_exits_one_on_missing_account_column(tmp_path: Path) -> None:
    """A hand-edited account_snapshot missing a column FAILs cleanly, not a traceback."""
    built = tmp_path / "demo"
    runner.invoke(app, ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)])
    account = pd.read_parquet(built / "account_snapshot.parquet").drop(columns=["nlv"])
    account.to_parquet(built / "account_snapshot.parquet", index=False)
    result = runner.invoke(app, ["twr", "--data", str(built)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert not isinstance(result.exception, AttributeError)


def test_twr_cli_exits_one_on_nonpositive_nlv(tmp_path: Path) -> None:
    built = tmp_path / "demo"
    runner.invoke(app, ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)])
    frames: dict[SnapshotFamily, pd.DataFrame] = {
        family: pd.read_parquet(built / f"{family}.parquet") for family in FAMILIES
    }
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    frames["account_snapshot"].loc[eod, "nlv"] = 0.0
    write_snapshots(built, frames)
    result = runner.invoke(app, ["twr", "--data", str(built)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError))


def test_twr_cli_exits_one_on_dirty_eod_pin_kind(tmp_path: Path) -> None:
    built = tmp_path / "demo"
    runner.invoke(app, ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)])
    frames: dict[SnapshotFamily, pd.DataFrame] = {
        family: pd.read_parquet(built / f"{family}.parquet") for family in FAMILIES
    }
    eod = frames["account_snapshot"]["pin_kind"] == "eod"
    frames["account_snapshot"].loc[eod, "pin_kind"] = None
    write_snapshots(built, frames)
    result = runner.invoke(app, ["twr", "--data", str(built)])
    assert result.exit_code == 1, result.output
    assert "pin_kind" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError))


def test_twr_cli_exits_one_on_null_event_kind(tmp_path: Path) -> None:
    built = tmp_path / "demo"
    runner.invoke(app, ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)])
    events = read_ledger(built)
    events.loc[0, "event_kind"] = None
    write_ledger(built, events)
    result = runner.invoke(app, ["twr", "--data", str(built)])
    assert result.exit_code == 1, result.output
    assert "event_kind" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError))


def test_quantstats_html_helper_pins_benchmark_none() -> None:
    captured: dict[str, object] = {}

    def fake_html(
        returns: pd.Series,
        output: str | None = None,
        title: str | None = None,
        benchmark: str | None = "SPY",
    ) -> None:
        captured["output"] = output
        captured["title"] = title
        captured["benchmark"] = benchmark

    series = pd.Series([0.01, -0.02], index=pd.DatetimeIndex(["2024-06-04", "2024-06-05"]))
    write_quantstats_html(
        series,
        Path("unused.html"),
        html_fn=fake_html,
        title="Simulated / seeded XYZ TWR",
    )
    assert captured["benchmark"] is None
    assert captured["title"] == "Simulated / seeded XYZ TWR"


def test_tearsheet_without_quantstats_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    built = tmp_path / "demo"
    runner.invoke(app, ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)])
    monkeypatch.setitem(sys.modules, "quantstats", None)
    result = runner.invoke(
        app,
        ["tearsheet", "--data", str(built), "--out", str(tmp_path / "t.html")],
    )
    assert result.exit_code == 1, result.output
    assert "tearsheet" in result.output


def test_tearsheet_exits_one_when_all_window_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    built = tmp_path / "demo"
    runner.invoke(app, ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)])
    fake_qs = types.ModuleType("quantstats")
    fake_qs.reports = types.SimpleNamespace(html=lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "quantstats", fake_qs)
    monkeypatch.setattr(
        sys.modules["optledger.cli.app"],
        "twr_from_snapshot_dir",
        lambda _data: (),
    )
    result = runner.invoke(
        app,
        ["tearsheet", "--data", str(built), "--out", str(tmp_path / "t.html")],
    )
    assert result.exit_code == 1, result.output
    assert "all" in result.output
    assert not isinstance(result.exception, StopIteration)
