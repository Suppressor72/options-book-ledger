from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from optledger.data import check_frames, read_snapshots, write_snapshots
from optledger.ledger import recon_frames
from optledger.simulate import build_demo_bundle, load_demo_spec
from optledger.web import PAGE_TITLES
from optledger.web.load import (
    WebLoadError,
    book_from_positions,
    dq_issue_frame,
    eod_snapshot_ids,
    position_table,
    recon_issue_frame,
    resolve_data_dir,
    scenario_grid_frame,
)

REPO = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO / "fixtures" / "demo.json"


def _demo_positions() -> pd.DataFrame:
    return build_demo_bundle(load_demo_spec(DEMO_FIXTURE)).frames["position_snapshot"]


def test_page_titles_are_exactly_the_three_product_pages() -> None:
    assert PAGE_TITLES == ("Data quality", "Ledger", "Scenarios")
    source = (REPO / "optledger" / "web" / "app.py").read_text(encoding="utf-8")
    assert source.count("st.Page(") == 3
    assert "title=PAGE_TITLES[0]" in source
    assert "title=PAGE_TITLES[1]" in source
    assert "title=PAGE_TITLES[2]" in source


def test_resolve_data_dir_rejects_urls() -> None:
    with pytest.raises(WebLoadError, match="local path"):
        resolve_data_dir("https://example.invalid/data")
    with pytest.raises(WebLoadError, match="required"):
        resolve_data_dir("  ")
    assert resolve_data_dir("data").as_posix().endswith("data")


def test_demo_dq_and_recon_frames_are_empty() -> None:
    bundle = build_demo_bundle(load_demo_spec(DEMO_FIXTURE))
    dq = check_frames(bundle.frames)
    recon = recon_frames(bundle.frames, bundle.events)
    assert dq.ok
    assert recon.ok
    assert list(dq_issue_frame(dq).columns) == ["family", "code", "snapshot_id", "message"]
    assert dq_issue_frame(dq).empty
    assert recon_issue_frame(recon).empty


def test_eod_pins_and_book_from_demo_positions() -> None:
    positions = _demo_positions()
    pins = eod_snapshot_ids(positions)
    assert pins
    assert pins[-1].endswith("-eod")
    book = book_from_positions(positions, pins[-1])
    assert len(book.positions) == 2
    table = position_table(positions, pins[-1])
    assert len(table) == 2
    grid, frame = scenario_grid_frame(book)
    assert frame.shape == (7, 7)
    assert grid.cell(0.0, 0.0) == pytest.approx(0.0, abs=1.0)


def test_underlier_only_pin_is_fail_closed() -> None:
    positions = pd.DataFrame(
        [
            {
                "snapshot_id": "2024-06-21-eod",
                "as_of": "2024-06-21T16:00:00",
                "pin_kind": "eod",
                "symbol": "XYZ",
                "instrument_id": "XYZ",
                "right": "",
                "strike": 0.0,
                "expiry": "",
                "qty": 100.0,
                "spot": 100.0,
                "iv": 0.0,
                "model_price": 100.0,
                "delta": 1.0,
                "vega": 0.0,
                "multiplier": 1.0,
            }
        ]
    )
    with pytest.raises(WebLoadError, match="no option legs"):
        book_from_positions(positions, "2024-06-21-eod")


def test_null_eod_snapshot_id_is_not_a_pin() -> None:
    good = {
        "snapshot_id": "2024-06-21-eod",
        "as_of": "2024-06-21T16:00:00",
        "pin_kind": "eod",
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
    }
    null_id = dict(good)
    null_id["snapshot_id"] = None
    nan_id = dict(good)
    nan_id["snapshot_id"] = math.nan
    nan_id["instrument_id"] = "XYZ-20240920-C-110"
    positions = pd.DataFrame([good, null_id, nan_id])
    pins = eod_snapshot_ids(positions)
    assert pins == ("2024-06-21-eod",)
    assert "nan" not in pins
    assert "None" not in pins
    assert position_table(positions, "nan").empty
    assert position_table(positions, "None").empty
    assert list(position_table(positions, "2024-06-21-eod")["instrument_id"]) == [
        "XYZ-20240920-C-100"
    ]


def test_european_style_column_is_not_repriced_american() -> None:
    positions = pd.DataFrame(
        [
            {
                "snapshot_id": "2024-06-21-eod",
                "as_of": "2024-06-21T16:00:00",
                "pin_kind": "eod",
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
                "style": "european",
            }
        ]
    )
    book = book_from_positions(positions, "2024-06-21-eod")
    assert book.positions[0].style == "european"


def test_european_style_survives_parquet_roundtrip(tmp_path: Path) -> None:
    bundle = build_demo_bundle(load_demo_spec(DEMO_FIXTURE))
    frames = {
        "account_snapshot": bundle.frames["account_snapshot"],
        "position_snapshot": bundle.frames["position_snapshot"].copy(),
        "book_metrics": bundle.frames["book_metrics"],
    }
    frames["position_snapshot"]["style"] = "european"
    dest = tmp_path / "eu"
    write_snapshots(dest, frames)
    loaded = read_snapshots(dest)["position_snapshot"]
    assert set(loaded["style"].unique()) == {"european"}
    pins = eod_snapshot_ids(loaded)
    book = book_from_positions(loaded, pins[-1])
    assert book.positions
    assert all(position.style == "european" for position in book.positions)
