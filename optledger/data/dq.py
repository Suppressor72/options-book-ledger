"""Fail-closed pin, join, and schema checks on snapshot Parquet."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from optledger.data.schema import COLUMNS, FAMILIES, METRICS_COLUMNS, PIN_KINDS, SnapshotFamily
from optledger.data.store import read_snapshots


@dataclass(frozen=True, slots=True)
class DqIssue:
    family: str
    code: str
    message: str
    snapshot_id: str | None = None


@dataclass(frozen=True, slots=True)
class DqReport:
    issues: tuple[DqIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def check_snapshot_dir(root: Path) -> DqReport:
    try:
        frames = read_snapshots(root)
    except FileNotFoundError as exc:
        return DqReport(issues=(DqIssue(family="all", code="missing_file", message=str(exc)),))
    return check_frames(frames)


def check_frames(frames: dict[SnapshotFamily, pd.DataFrame]) -> DqReport:
    issues: list[DqIssue] = []
    issues.extend(_schema_issues(frames))
    issues.extend(_snapshot_id_issues(frames))
    if _can_join(frames):
        issues.extend(_join_issues(frames))
    for family in FAMILIES:
        if _has_columns(frames, family, ("as_of", "pin_kind")):
            issues.extend(_pin_issues_for(family, frames[family]))
    if _has_columns(frames, "position_snapshot", COLUMNS["position_snapshot"]):
        issues.extend(_value_issues(frames["position_snapshot"]))
    if _has_columns(frames, "account_snapshot", ("snapshot_id", "nlv", "cash")):
        issues.extend(_account_numeric_issues(frames["account_snapshot"]))
    if _has_columns(frames, "book_metrics", METRICS_COLUMNS):
        issues.extend(_metrics_numeric_issues(frames["book_metrics"]))
    return DqReport(issues=tuple(issues))


def format_report(report: DqReport) -> str:
    if report.ok:
        return "ok: 0 issues"
    lines = [f"FAIL ({len(report.issues)} issues)"]
    for issue in report.issues:
        prefix = f"{issue.family} {issue.code}"
        if issue.snapshot_id:
            prefix += f" {issue.snapshot_id}"
        lines.append(f"- {prefix}: {issue.message}")
    return "\n".join(lines)


def _schema_issues(frames: dict[SnapshotFamily, pd.DataFrame]) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for family in FAMILIES:
        if family not in frames:
            issues.append(
                DqIssue(family=family, code="schema", message="family missing from snapshot set")
            )
            continue
        missing = [name for name in COLUMNS[family] if name not in frames[family].columns]
        if missing:
            issues.append(
                DqIssue(
                    family=family,
                    code="schema",
                    message=f"missing columns: {', '.join(missing)}",
                )
            )
    return issues


def _snapshot_id_issues(frames: dict[SnapshotFamily, pd.DataFrame]) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for family in FAMILIES:
        if not _has_columns(frames, family, ("snapshot_id",)):
            continue
        for row in frames[family].itertuples(index=False):
            if _optional_str(row.snapshot_id) is None:
                issues.append(
                    DqIssue(
                        family=family,
                        code="schema",
                        message=f"unusable snapshot_id {row.snapshot_id!r}",
                    )
                )
    return issues


def _join_issues(frames: dict[SnapshotFamily, pd.DataFrame]) -> list[DqIssue]:
    ids = {family: _snapshot_ids(frames[family]) for family in FAMILIES}
    issues: list[DqIssue] = []
    for family in FAMILIES:
        for other in FAMILIES:
            if family == other:
                continue
            for snapshot_id in sorted(ids[family] - ids[other]):
                issues.append(
                    DqIssue(
                        family=family,
                        code="join_break",
                        message=f"snapshot_id present here but not in {other}",
                        snapshot_id=snapshot_id,
                    )
                )
    return issues


def _pin_issues_for(family: SnapshotFamily, frame: pd.DataFrame) -> list[DqIssue]:
    issues: list[DqIssue] = []
    by_date: dict[str, set[str]] = {}
    for row in frame.itertuples(index=False):
        snapshot_id = _optional_str(row.snapshot_id)
        pin_kind = _optional_str(row.pin_kind)
        day = parse_date(row.as_of)
        if pin_kind not in PIN_KINDS:
            issues.append(
                DqIssue(
                    family=family,
                    code="schema",
                    message=f"unknown pin_kind {pin_kind!r}",
                    snapshot_id=snapshot_id,
                )
            )
        if day is None:
            issues.append(
                DqIssue(
                    family=family,
                    code="schema",
                    message=f"unparseable as_of {row.as_of!r}",
                    snapshot_id=snapshot_id,
                )
            )
            continue
        if pin_kind in PIN_KINDS:
            by_date.setdefault(day, set()).add(pin_kind)
    for day, kinds in sorted(by_date.items()):
        if "eod" not in kinds:
            issues.append(
                DqIssue(
                    family=family,
                    code="missing_eod",
                    message=f"date {day} has pins {sorted(kinds)} but no eod",
                )
            )
    return issues


def _value_issues(positions: pd.DataFrame) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for row in positions.itertuples(index=False):
        snapshot_id = _optional_str(row.snapshot_id)
        spot = parse_finite_float(row.spot)
        iv = parse_finite_float(row.iv)
        qty = parse_finite_float(row.qty)
        if spot is None:
            issues.append(
                DqIssue(
                    family="position_snapshot",
                    code="invalid_numeric",
                    message=f"spot is not a finite number: {row.spot!r}",
                    snapshot_id=snapshot_id,
                )
            )
        elif spot <= 0.0:
            issues.append(
                DqIssue(
                    family="position_snapshot",
                    code="nonpositive_spot",
                    message=f"spot {spot} is not positive",
                    snapshot_id=snapshot_id,
                )
            )
        option_leg = _optional_str(row.right) in {"call", "put"}
        if option_leg:
            if iv is None:
                issues.append(
                    DqIssue(
                        family="position_snapshot",
                        code="invalid_numeric",
                        message=f"iv is not a finite number: {row.iv!r}",
                        snapshot_id=snapshot_id,
                    )
                )
            elif iv <= 0.0:
                issues.append(
                    DqIssue(
                        family="position_snapshot",
                        code="iv_nonpositive",
                        message=f"iv {iv} must be > 0",
                        snapshot_id=snapshot_id,
                    )
                )
        if qty is None:
            issues.append(
                DqIssue(
                    family="position_snapshot",
                    code="invalid_numeric",
                    message=f"qty is not a finite number: {row.qty!r}",
                    snapshot_id=snapshot_id,
                )
            )
        elif qty == 0.0:
            issues.append(
                DqIssue(
                    family="position_snapshot",
                    code="qty_zero",
                    message="qty must be non-zero",
                    snapshot_id=snapshot_id,
                )
            )
        as_of = parse_date(row.as_of)
        if as_of is None:
            issues.append(
                DqIssue(
                    family="position_snapshot",
                    code="schema",
                    message=f"unparseable as_of {row.as_of!r}",
                    snapshot_id=snapshot_id,
                )
            )
        if option_leg:
            expiry = parse_date(row.expiry)
            if expiry is None:
                issues.append(
                    DqIssue(
                        family="position_snapshot",
                        code="schema",
                        message=f"unparseable expiry {row.expiry!r}",
                        snapshot_id=snapshot_id,
                    )
                )
            if expiry is not None and as_of is not None and expiry < as_of:
                issues.append(
                    DqIssue(
                        family="position_snapshot",
                        code="expiry_before_as_of",
                        message=f"expiry {expiry} is before as_of {as_of}",
                        snapshot_id=snapshot_id,
                    )
                )
            style = _optional_str(row.style)
            if style not in {"american", "european"}:
                issues.append(
                    DqIssue(
                        family="position_snapshot",
                        code="schema",
                        message=f"unusable style {row.style!r}",
                        snapshot_id=snapshot_id,
                    )
                )
    return issues


def _account_numeric_issues(account: pd.DataFrame) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for row in account.itertuples(index=False):
        snapshot_id = _optional_str(row.snapshot_id)
        for field in ("nlv", "cash"):
            if parse_finite_float(getattr(row, field)) is None:
                issues.append(
                    DqIssue(
                        family="account_snapshot",
                        code="invalid_numeric",
                        message=f"{field} is not a finite number: {getattr(row, field)!r}",
                        snapshot_id=snapshot_id,
                    )
                )
    return issues


def _metrics_numeric_issues(metrics: pd.DataFrame) -> list[DqIssue]:
    issues: list[DqIssue] = []
    numeric = tuple(
        name for name in METRICS_COLUMNS if name not in {"snapshot_id", "as_of", "pin_kind"}
    )
    for row in metrics.itertuples(index=False):
        snapshot_id = _optional_str(row.snapshot_id)
        for field in numeric:
            if parse_finite_float(getattr(row, field)) is None:
                issues.append(
                    DqIssue(
                        family="book_metrics",
                        code="invalid_numeric",
                        message=f"{field} is not a finite number: {getattr(row, field)!r}",
                        snapshot_id=snapshot_id,
                    )
                )
    return issues


def _can_join(frames: dict[SnapshotFamily, pd.DataFrame]) -> bool:
    return all(_has_columns(frames, family, ("snapshot_id",)) for family in FAMILIES)


def _has_columns(
    frames: dict[SnapshotFamily, pd.DataFrame],
    family: SnapshotFamily,
    names: tuple[str, ...],
) -> bool:
    if family not in frames:
        return False
    columns = frames[family].columns
    return all(name in columns for name in names)


def _snapshot_ids(frame: pd.DataFrame) -> set[str]:
    ids: set[str] = set()
    for row in frame.itertuples(index=False):
        snapshot_id = _optional_str(row.snapshot_id)
        if snapshot_id is not None:
            ids.add(snapshot_id)
    return ids


def parse_finite_float(value: object) -> float | None:
    """Return a finite float, or None if missing, NaN, inf, or non-numeric."""
    if _is_null(value):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def parse_date(value: object) -> str | None:
    """Return YYYY-MM-DD, or None if the cell is null or not an ISO date."""
    if _is_null(value):
        return None
    if isinstance(value, pd.Timestamp):
        if bool(pd.isna(value)):
            return None
        return date(int(value.year), int(value.month), int(value.day)).isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text:
        text = text.split(" ", 1)[0]
    chunk = text[:10]
    if len(chunk) < 10:
        return None
    try:
        return date.fromisoformat(chunk).isoformat()
    except ValueError:
        return None


def optional_str(value: object) -> str | None:
    """Return a stripped string, or None if missing, NaN, or blank."""
    if _is_null(value):
        return None
    text = str(value).strip()
    return text or None


_optional_str = optional_str


def _is_null(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
