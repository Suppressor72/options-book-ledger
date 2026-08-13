from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from optledger.cli.app import app
from optledger.data.schema import FAMILIES, SnapshotFamily
from optledger.data.store import parquet_path, write_snapshots

REPO = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO / "fixtures" / "demo.json"
BROKEN_FIXTURE = REPO / "fixtures" / "broken_join.json"

runner = CliRunner()


def _frames_from_json(path: Path) -> dict[SnapshotFamily, pd.DataFrame]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {family: pd.DataFrame(raw[family]) for family in FAMILIES}


def test_demo_build_is_idempotent_on_the_same_seed(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    for dest in (first, second):
        result = runner.invoke(
            app,
            ["demo-build", "--out", str(dest), "--fixture", str(DEMO_FIXTURE)],
        )
        assert result.exit_code == 0, result.output
    for family in FAMILIES:
        left = parquet_path(first, family).read_bytes()
        right = parquet_path(second, family).read_bytes()
        assert left == right
    first_ledger = sorted((first / "ledger").glob("*.parquet"))
    second_ledger = sorted((second / "ledger").glob("*.parquet"))
    assert [path.name for path in first_ledger] == [path.name for path in second_ledger]
    assert first_ledger
    for left_path, right_path in zip(first_ledger, second_ledger, strict=True):
        assert left_path.read_bytes() == right_path.read_bytes()


def test_dq_exits_zero_on_demo(tmp_path: Path) -> None:
    built = tmp_path / "demo"
    build = runner.invoke(
        app,
        ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)],
    )
    assert build.exit_code == 0, build.output
    result = runner.invoke(app, ["dq", "--data", str(built)])
    assert result.exit_code == 0, result.output
    assert "ok:" in result.output


def test_dq_exits_one_on_broken_join_fixture(tmp_path: Path) -> None:
    dest = tmp_path / "broken"
    write_snapshots(dest, _frames_from_json(BROKEN_FIXTURE))
    result = runner.invoke(app, ["dq", "--data", str(dest)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert "join_break" in result.output
