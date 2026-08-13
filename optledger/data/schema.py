"""Snapshot family names, pin kinds, and required columns."""

from __future__ import annotations

from typing import Literal

type PinKind = Literal["open", "eod"]
type SnapshotFamily = Literal["account_snapshot", "position_snapshot", "book_metrics"]

PIN_KINDS: tuple[PinKind, ...] = ("open", "eod")
FAMILIES: tuple[SnapshotFamily, ...] = (
    "account_snapshot",
    "position_snapshot",
    "book_metrics",
)

ACCOUNT_COLUMNS: tuple[str, ...] = (
    "snapshot_id",
    "as_of",
    "pin_kind",
    "nlv",
    "cash",
)

POSITION_COLUMNS: tuple[str, ...] = (
    "snapshot_id",
    "as_of",
    "pin_kind",
    "symbol",
    "instrument_id",
    "right",
    "strike",
    "expiry",
    "qty",
    "spot",
    "iv",
    "model_price",
    "delta",
    "vega",
    "multiplier",
    "style",
)

# Selected scenario P/L columns: spot moves at unchanged vol (not a VaR engine).
SCENARIO_PNL_COLUMNS: tuple[str, ...] = (
    "pnl_spot_m20",
    "pnl_spot_m10",
    "pnl_spot_m05",
    "pnl_spot_0",
    "pnl_spot_p05",
    "pnl_spot_p10",
    "pnl_spot_p20",
)

METRICS_COLUMNS: tuple[str, ...] = (
    "snapshot_id",
    "as_of",
    "pin_kind",
    "net_delta",
    "net_vega",
    *SCENARIO_PNL_COLUMNS,
)

COLUMNS: dict[SnapshotFamily, tuple[str, ...]] = {
    "account_snapshot": ACCOUNT_COLUMNS,
    "position_snapshot": POSITION_COLUMNS,
    "book_metrics": METRICS_COLUMNS,
}

OPEN_CLOCK = "09:30:00"
EOD_CLOCK = "16:00:00"


def scenario_pnl_column(spot_move: float) -> str:
    pct = int(round(spot_move * 100))
    if pct == 0:
        return "pnl_spot_0"
    if pct < 0:
        return f"pnl_spot_m{abs(pct):02d}"
    return f"pnl_spot_p{pct:02d}"


def snapshot_id_for(as_of_date: str, pin_kind: PinKind) -> str:
    return f"{as_of_date}-{pin_kind}"
