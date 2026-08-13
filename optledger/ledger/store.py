"""Read and write yearly lifecycle-event Parquet under ``<root>/ledger/``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from optledger.data.dq import parse_date
from optledger.ledger.schema import LEDGER_COLUMNS

PARQUET_ENGINE = "pyarrow"
PARQUET_COMPRESSION: str | None = None
LEDGER_DIRNAME = "ledger"


def ledger_dir(root: Path) -> Path:
    return root / LEDGER_DIRNAME


def ledger_year_path(root: Path, year: int) -> Path:
    return ledger_dir(root) / f"{year}.parquet"


def write_ledger(root: Path, events: pd.DataFrame, *, replace: bool = False) -> list[Path]:
    """Write lifecycle events as yearly Parquet.

    The writer is authoritative for the years present in ``events`` (each such
    year file is fully overwritten). Year partitions that are **not** in the
    input are left untouched by default, so writing one year can never destroy
    another. Pass ``replace=True`` to prune years absent from the input.
    """
    frame = _normalize(events)
    if frame.empty:
        raise ValueError("ledger events must not be empty")
    years = frame["_year"].astype(int)
    dest = ledger_dir(root)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for year in sorted(set(years.tolist())):
        part = frame.loc[years == year, list(LEDGER_COLUMNS)].copy()
        path = ledger_year_path(root, int(year))
        part.to_parquet(path, engine=PARQUET_ENGINE, compression=PARQUET_COMPRESSION, index=False)
        written.append(path)
    keep = {path.name for path in written}
    if replace:
        # Opt-in: prune year partitions absent from this write. The default
        # leaves foreign years alone so an append-only ledger is never
        # destroyed by writing a single year.
        for stale in dest.glob("*.parquet"):
            if stale.name not in keep:
                stale.unlink()
    return written


def read_ledger(root: Path) -> pd.DataFrame:
    dest = ledger_dir(root)
    if not dest.is_dir():
        raise FileNotFoundError(f"missing ledger directory: {dest}")
    paths = sorted(dest.glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"missing ledger parquet under {dest}")
    parts = [pd.read_parquet(path, engine=PARQUET_ENGINE) for path in paths]
    return _normalize(pd.concat(parts, ignore_index=True)).loc[:, list(LEDGER_COLUMNS)]


def _normalize(events: pd.DataFrame) -> pd.DataFrame:
    missing = [name for name in LEDGER_COLUMNS if name not in events.columns]
    if missing:
        raise ValueError(f"ledger missing columns: {missing}")
    out = events.loc[:, list(LEDGER_COLUMNS)].copy()
    years: list[int] = []
    for value in out["as_of"]:
        day = parse_date(value)
        if day is None:
            raise ValueError(f"ledger as_of is not an ISO date: {value!r}")
        years.append(int(day[:4]))
    out["_year"] = years
    return out.sort_values(["as_of", "event_id"], kind="mergesort").reset_index(drop=True)
