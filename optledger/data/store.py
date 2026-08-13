"""Read and write the three snapshot Parquet families."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from optledger.data.schema import COLUMNS, FAMILIES, SnapshotFamily

PARQUET_ENGINE = "pyarrow"
PARQUET_COMPRESSION: str | None = None


def parquet_path(root: Path, family: SnapshotFamily) -> Path:
    return root / f"{family}.parquet"


def write_snapshots(root: Path, frames: dict[SnapshotFamily, pd.DataFrame]) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for family in FAMILIES:
        if family not in frames:
            raise KeyError(f"missing snapshot family {family!r}")
        frame = _normalize(family, frames[family])
        path = parquet_path(root, family)
        frame.to_parquet(path, engine=PARQUET_ENGINE, compression=PARQUET_COMPRESSION, index=False)
        written.append(path)
    return written


def read_snapshots(root: Path) -> dict[SnapshotFamily, pd.DataFrame]:
    frames: dict[SnapshotFamily, pd.DataFrame] = {}
    missing: list[str] = []
    for family in FAMILIES:
        path = parquet_path(root, family)
        if not path.is_file():
            missing.append(str(path))
            continue
        frames[family] = pd.read_parquet(path, engine=PARQUET_ENGINE)
    if missing:
        raise FileNotFoundError("missing snapshot files: " + ", ".join(missing))
    return frames


def _normalize(family: SnapshotFamily, frame: pd.DataFrame) -> pd.DataFrame:
    columns = list(COLUMNS[family])
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"{family} missing columns: {missing}")
    out = frame.loc[:, columns].copy()
    sort_cols = [name for name in ("snapshot_id", "instrument_id") if name in columns]
    return out.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
