"""Local Parquet helpers for the slim Streamlit UI (no Streamlit import)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from optledger.book import BookSnapshot, OptionPosition, ScenarioGrid, scenario_pnl_grid
from optledger.book.models import ExerciseStyle
from optledger.data.dq import DqIssue, DqReport, optional_str, parse_date, parse_finite_float
from optledger.data.store import read_snapshots
from optledger.ledger.recon import ReconIssue, ReconReport
from optledger.pricing import OptionRight

DATA_ENV = "OPTLEDGER_DATA"
PAGE_TITLES: tuple[str, ...] = ("Data quality", "Ledger", "Scenarios")
DEFAULT_RATE = 0.05
DEFAULT_DIVIDEND_YIELD = 0.0
DEFAULT_STYLE: ExerciseStyle = "american"
DEFAULT_CRR_STEPS = 40

DQ_COLUMNS: tuple[str, ...] = ("family", "code", "snapshot_id", "message")
RECON_COLUMNS: tuple[str, ...] = ("code", "snapshot_id", "instrument_id", "message")
POSITION_TABLE_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "qty",
    "right",
    "strike",
    "expiry",
    "spot",
    "iv",
    "model_price",
    "delta",
    "vega",
    "style",
)


class WebLoadError(ValueError):
    """Fail-closed local-path or pin load error."""


def resolve_data_dir(raw: str) -> Path:
    """Return a local directory path. URLs and empty strings are rejected."""
    text = raw.strip()
    if not text:
        raise WebLoadError("data directory is required")
    if "://" in text:
        raise WebLoadError("data directory must be a local path")
    return Path(text).expanduser()


def dq_issue_frame(report: DqReport) -> pd.DataFrame:
    return pd.DataFrame(
        [_dq_row(issue) for issue in report.issues],
        columns=list(DQ_COLUMNS),
    )


def recon_issue_frame(report: ReconReport) -> pd.DataFrame:
    return pd.DataFrame(
        [_recon_row(issue) for issue in report.issues],
        columns=list(RECON_COLUMNS),
    )


def eod_snapshot_ids(positions: pd.DataFrame) -> tuple[str, ...]:
    if "pin_kind" not in positions.columns or "snapshot_id" not in positions.columns:
        return ()
    ids: list[str] = []
    seen: set[str] = set()
    for row in positions.itertuples(index=False):
        if optional_str(row.pin_kind) != "eod":
            continue
        snapshot_id = optional_str(row.snapshot_id)
        if snapshot_id is None or snapshot_id in seen:
            continue
        seen.add(snapshot_id)
        ids.append(snapshot_id)
    return tuple(ids)


def position_table(positions: pd.DataFrame, snapshot_id: str) -> pd.DataFrame:
    if "snapshot_id" not in positions.columns:
        return pd.DataFrame(columns=list(POSITION_TABLE_COLUMNS))
    frame = _rows_for_snapshot(positions, snapshot_id)
    present = [name for name in POSITION_TABLE_COLUMNS if name in frame.columns]
    if not present:
        return pd.DataFrame(columns=list(POSITION_TABLE_COLUMNS))
    return frame.loc[:, present].reset_index(drop=True)


def book_from_positions(
    positions: pd.DataFrame,
    snapshot_id: str,
    *,
    rate: float = DEFAULT_RATE,
    dividend_yield: float = DEFAULT_DIVIDEND_YIELD,
    style: ExerciseStyle = DEFAULT_STYLE,
) -> BookSnapshot:
    """Rebuild option lots at one pin. Underlier rows (empty right) are skipped."""
    if "snapshot_id" not in positions.columns:
        raise WebLoadError("position snapshot missing snapshot_id")
    frame = _rows_for_snapshot(positions, snapshot_id)
    lots: list[OptionPosition] = []
    spot: float | None = None
    for row in frame.itertuples(index=False):
        right = str(getattr(row, "right", "") or "").strip()
        option_right = _option_right(right)
        if option_right is None:
            continue
        qty = parse_finite_float(getattr(row, "qty", None))
        strike = parse_finite_float(getattr(row, "strike", None))
        iv = parse_finite_float(getattr(row, "iv", None))
        multiplier = parse_finite_float(getattr(row, "multiplier", None))
        row_spot = parse_finite_float(getattr(row, "spot", None))
        as_of = parse_date(getattr(row, "as_of", None))
        expiry = parse_date(getattr(row, "expiry", None))
        if (
            qty is None
            or strike is None
            or iv is None
            or multiplier is None
            or row_spot is None
            or as_of is None
            or expiry is None
        ):
            raise WebLoadError(f"unusable option row at {snapshot_id}")
        if spot is None:
            spot = row_spot
        time_years = max((_iso_date(expiry) - _iso_date(as_of)).days, 0) / 365.0
        lots.append(
            OptionPosition(
                quantity=qty,
                strike=strike,
                time_years=time_years,
                volatility=iv,
                right=option_right,
                multiplier=multiplier,
                style=_row_style(row, default=style),
            )
        )
    if spot is None or not lots:
        raise WebLoadError(f"no option legs at {snapshot_id}")
    return BookSnapshot(
        spot=spot,
        rate=rate,
        dividend_yield=dividend_yield,
        positions=tuple(lots),
    )


def scenario_grid_frame(
    book: BookSnapshot,
    *,
    steps: int = DEFAULT_CRR_STEPS,
) -> tuple[ScenarioGrid, pd.DataFrame]:
    grid = scenario_pnl_grid(book, steps=steps)
    columns = [f"{move:+.0%}" for move in grid.spot_moves]
    index = [f"{move:+.0%}" for move in grid.vol_moves]
    frame = pd.DataFrame(grid.pnl, index=index, columns=columns)
    return grid, frame


def load_position_snapshot(root: Path) -> pd.DataFrame:
    return read_snapshots(root)["position_snapshot"]


def _rows_for_snapshot(positions: pd.DataFrame, snapshot_id: str) -> pd.DataFrame:
    mask = [optional_str(value) == snapshot_id for value in positions["snapshot_id"]]
    return positions.loc[mask]


def _dq_row(issue: DqIssue) -> dict[str, str]:
    return {
        "family": issue.family,
        "code": issue.code,
        "snapshot_id": issue.snapshot_id or "",
        "message": issue.message,
    }


def _recon_row(issue: ReconIssue) -> dict[str, str]:
    return {
        "code": issue.code,
        "snapshot_id": issue.snapshot_id or "",
        "instrument_id": issue.instrument_id or "",
        "message": issue.message,
    }


def _row_style(row: object, *, default: ExerciseStyle) -> ExerciseStyle:
    if not hasattr(row, "style"):
        return default
    raw = optional_str(row.style)
    if raw is None:
        return default
    if raw == "american":
        return "american"
    if raw == "european":
        return "european"
    raise WebLoadError(f"unusable style {raw!r}")


def _option_right(value: str) -> OptionRight | None:
    if value == "call":
        return "call"
    if value == "put":
        return "put"
    return None


def _iso_date(value: str) -> date:
    return datetime.fromisoformat(value).date()
