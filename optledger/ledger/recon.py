"""Fail-closed qty / cash / NLV reconciliation of ledger events to EOD pins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from optledger.data.dq import parse_date, parse_finite_float
from optledger.data.schema import PIN_KINDS, SnapshotFamily
from optledger.data.store import read_snapshots
from optledger.ledger.schema import DEMO_ACCOUNT, EVENT_KINDS, LEDGER_COLUMNS
from optledger.ledger.store import read_ledger

_QTY_ABS_TOL = 1e-9
_MONEY_ABS_TOL = 1e-6


@dataclass(frozen=True, slots=True)
class ReconIssue:
    code: str
    message: str
    snapshot_id: str | None = None
    instrument_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReconReport:
    issues: tuple[ReconIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def recon_snapshot_dir(root: Path) -> ReconReport:
    try:
        frames = read_snapshots(root)
    except FileNotFoundError as exc:
        return ReconReport(issues=(ReconIssue(code="missing_file", message=str(exc)),))
    try:
        events = read_ledger(root)
    except FileNotFoundError as exc:
        return ReconReport(issues=(ReconIssue(code="missing_file", message=str(exc)),))
    except ValueError as exc:
        return ReconReport(issues=(ReconIssue(code="schema", message=str(exc)),))
    return recon_frames(frames, events)


def recon_frames(
    frames: dict[SnapshotFamily, pd.DataFrame],
    events: pd.DataFrame,
) -> ReconReport:
    issues = _ledger_schema_issues(events)
    if issues:
        return ReconReport(issues=tuple(issues))
    parsed = _parsed_events(events)
    pin_issues, pins = _collect_account_pins(frames["account_snapshot"])
    issues.extend(pin_issues)
    eod_pins = tuple(pin for pin in pins if pin.pin_kind == "eod")
    issues.extend(_qty_issues(eod_pins, frames["position_snapshot"], parsed))
    issues.extend(_cash_issues(eod_pins, parsed))
    issues.extend(_nlv_issues(eod_pins, frames["account_snapshot"], frames["position_snapshot"]))
    return ReconReport(issues=tuple(issues))


def format_recon_report(report: ReconReport) -> str:
    if report.ok:
        return "ok: 0 recon breaks"
    lines = [f"FAIL ({len(report.issues)} recon breaks)"]
    for issue in report.issues:
        prefix = issue.code
        if issue.snapshot_id:
            prefix += f" {issue.snapshot_id}"
        if issue.instrument_id:
            prefix += f" {issue.instrument_id}"
        lines.append(f"- {prefix}: {issue.message}")
    return "\n".join(lines)


def _ledger_schema_issues(events: pd.DataFrame) -> list[ReconIssue]:
    issues: list[ReconIssue] = []
    missing = [name for name in LEDGER_COLUMNS if name not in events.columns]
    if missing:
        return [
            ReconIssue(code="schema", message=f"missing columns: {', '.join(missing)}"),
        ]
    seen_ids: set[str] = set()
    for row in events.itertuples(index=False):
        event_id = _optional_str(row.event_id)
        if event_id is None:
            issues.append(ReconIssue(code="schema", message="event_id is missing"))
        elif event_id in seen_ids:
            issues.append(ReconIssue(code="schema", message=f"duplicate event_id {event_id}"))
        else:
            seen_ids.add(event_id)
        if parse_as_of_key(row.as_of) is None:
            issues.append(
                ReconIssue(
                    code="schema",
                    message=f"unparseable as_of {row.as_of!r}",
                    instrument_id=_optional_str(row.instrument_id),
                )
            )
        account = _optional_str(row.account)
        if account != DEMO_ACCOUNT:
            issues.append(
                ReconIssue(
                    code="schema",
                    message=f"account must be {DEMO_ACCOUNT!r}, got {row.account!r}",
                )
            )
        kind = _optional_str(row.event_kind)
        if kind not in EVENT_KINDS:
            issues.append(
                ReconIssue(
                    code="schema",
                    message=f"unknown event_kind {row.event_kind!r}",
                )
            )
        if parse_finite_float(row.qty) is None:
            issues.append(
                ReconIssue(
                    code="invalid_numeric",
                    message=f"qty is not a finite number: {row.qty!r}",
                    instrument_id=_optional_str(row.instrument_id),
                )
            )
        if parse_finite_float(row.cash) is None:
            issues.append(
                ReconIssue(
                    code="invalid_numeric",
                    message=f"cash is not a finite number: {row.cash!r}",
                    instrument_id=_optional_str(row.instrument_id),
                )
            )
    return issues


@dataclass(frozen=True, slots=True)
class _ParsedEvent:
    as_of_key: str
    instrument_id: str | None
    qty: float
    cash: float


def _parsed_events(events: pd.DataFrame) -> tuple[_ParsedEvent, ...]:
    parsed: list[_ParsedEvent] = []
    for row in events.itertuples(index=False):
        as_of_key = parse_as_of_key(row.as_of)
        qty = parse_finite_float(row.qty)
        cash = parse_finite_float(row.cash)
        if as_of_key is None or qty is None or cash is None:
            continue
        parsed.append(
            _ParsedEvent(
                as_of_key=as_of_key,
                instrument_id=_optional_str(row.instrument_id),
                qty=qty,
                cash=cash,
            )
        )
    return tuple(parsed)


@dataclass(frozen=True, slots=True)
class _AccountPin:
    snapshot_id: str
    as_of_key: str
    pin_kind: str
    cash: float | None


def _qty_issues(
    eod_pins: tuple[_AccountPin, ...],
    positions: pd.DataFrame,
    events: tuple[_ParsedEvent, ...],
) -> list[ReconIssue]:
    issues: list[ReconIssue] = []
    instruments = _qty_instruments(positions, events)
    for pin in eod_pins:
        snap_qty = _position_qty_by_instrument(positions, pin.snapshot_id)
        for instrument_id in instruments:
            ledger_qty = sum(
                event.qty
                for event in events
                if event.instrument_id == instrument_id and event.as_of_key <= pin.as_of_key
            )
            pinned = snap_qty.get(instrument_id, 0.0)
            if abs(ledger_qty - pinned) <= _QTY_ABS_TOL:
                continue
            issues.append(
                ReconIssue(
                    code="qty_break",
                    message=f"ledger qty {ledger_qty} != position qty {pinned} at EOD pin",
                    snapshot_id=pin.snapshot_id,
                    instrument_id=instrument_id,
                )
            )
    return issues


def _cash_issues(
    eod_pins: tuple[_AccountPin, ...],
    events: tuple[_ParsedEvent, ...],
) -> list[ReconIssue]:
    issues: list[ReconIssue] = []
    for pin in eod_pins:
        ledger_cash = sum(event.cash for event in events if event.as_of_key <= pin.as_of_key)
        if pin.cash is None:
            issues.append(
                ReconIssue(
                    code="invalid_numeric",
                    message="account cash is not a finite number",
                    snapshot_id=pin.snapshot_id,
                )
            )
            continue
        if abs(ledger_cash - pin.cash) <= _MONEY_ABS_TOL:
            continue
        issues.append(
            ReconIssue(
                code="cash_break",
                message=f"ledger cash {ledger_cash} != account cash {pin.cash}",
                snapshot_id=pin.snapshot_id,
            )
        )
    return issues


def _nlv_issues(
    eod_pins: tuple[_AccountPin, ...],
    account: pd.DataFrame,
    positions: pd.DataFrame,
) -> list[ReconIssue]:
    issues: list[ReconIssue] = []
    for pin in eod_pins:
        nlv = _account_nlv(account, pin.snapshot_id)
        if pin.cash is None or nlv is None:
            if nlv is None:
                issues.append(
                    ReconIssue(
                        code="invalid_numeric",
                        message="account nlv is not a finite number",
                        snapshot_id=pin.snapshot_id,
                    )
                )
            continue
        marked = _position_mark(positions, pin.snapshot_id)
        if marked is None:
            issues.append(
                ReconIssue(
                    code="invalid_numeric",
                    message="position mark is not a finite number",
                    snapshot_id=pin.snapshot_id,
                )
            )
            continue
        bridged = pin.cash + marked
        if abs(nlv - bridged) <= _MONEY_ABS_TOL:
            continue
        issues.append(
            ReconIssue(
                code="nlv_break",
                message=f"nlv {nlv} != cash {pin.cash} + position mark {marked}",
                snapshot_id=pin.snapshot_id,
            )
        )
    return issues


def _collect_account_pins(
    account: pd.DataFrame,
) -> tuple[list[ReconIssue], tuple[_AccountPin, ...]]:
    issues: list[ReconIssue] = []
    pins: list[_AccountPin] = []
    for row in account.itertuples(index=False):
        snapshot_id = _optional_str(row.snapshot_id)
        as_of_key = parse_as_of_key(row.as_of)
        pin_kind = _optional_str(row.pin_kind)
        if snapshot_id is None:
            issues.append(ReconIssue(code="schema", message="snapshot_id is missing"))
        if as_of_key is None:
            issues.append(
                ReconIssue(
                    code="schema",
                    message=f"unparseable as_of {row.as_of!r}",
                    snapshot_id=snapshot_id,
                )
            )
        if pin_kind not in PIN_KINDS:
            issues.append(
                ReconIssue(
                    code="schema",
                    message=f"unknown pin_kind {row.pin_kind!r}",
                    snapshot_id=snapshot_id,
                )
            )
        if snapshot_id is None or as_of_key is None or pin_kind not in PIN_KINDS:
            continue
        pins.append(
            _AccountPin(
                snapshot_id=snapshot_id,
                as_of_key=as_of_key,
                pin_kind=pin_kind,
                cash=parse_finite_float(row.cash),
            )
        )
    if not any(pin.pin_kind == "eod" for pin in pins):
        issues.append(
            ReconIssue(code="missing_eod", message="no usable EOD account pin"),
        )
    return issues, tuple(pins)


def _account_nlv(account: pd.DataFrame, snapshot_id: str) -> float | None:
    for row in account.itertuples(index=False):
        if _optional_str(row.snapshot_id) == snapshot_id:
            return parse_finite_float(row.nlv)
    return None


def _qty_instruments(
    positions: pd.DataFrame,
    events: tuple[_ParsedEvent, ...],
) -> tuple[str, ...]:
    names: set[str] = set()
    for event in events:
        if event.instrument_id:
            names.add(event.instrument_id)
    for row in positions.itertuples(index=False):
        instrument_id = _optional_str(row.instrument_id)
        if instrument_id:
            names.add(instrument_id)
    return tuple(sorted(names))


def _position_qty_by_instrument(positions: pd.DataFrame, snapshot_id: str) -> dict[str, float]:
    qty: dict[str, float] = {}
    for row in positions.itertuples(index=False):
        if _optional_str(row.snapshot_id) != snapshot_id:
            continue
        instrument_id = _optional_str(row.instrument_id)
        amount = parse_finite_float(row.qty)
        if instrument_id is None or amount is None:
            continue
        qty[instrument_id] = qty.get(instrument_id, 0.0) + amount
    return qty


def _position_mark(positions: pd.DataFrame, snapshot_id: str) -> float | None:
    total = 0.0
    for row in positions.itertuples(index=False):
        if _optional_str(row.snapshot_id) != snapshot_id:
            continue
        qty = parse_finite_float(row.qty)
        price = parse_finite_float(row.model_price)
        multiplier = parse_finite_float(row.multiplier)
        if qty is None or price is None or multiplier is None:
            return None
        total += qty * price * multiplier
    return total


def parse_as_of_key(value: object) -> str | None:
    """Return a sortable ``YYYY-MM-DDTHH:MM:SS`` key, or None if unparseable."""
    if _is_null(value):
        return None
    if isinstance(value, pd.Timestamp):
        if bool(pd.isna(value)):
            return None
        return datetime(
            int(value.year),
            int(value.month),
            int(value.day),
            int(value.hour),
            int(value.minute),
            int(value.second),
        ).isoformat()
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day).isoformat()
    text = str(value).strip()
    if not text:
        return None
    day = parse_date(text)
    if day is None:
        return None
    time_part = "00:00:00"
    if "T" in text:
        rest = text.split("T", 1)[1]
        rest = rest.replace("Z", "")
        if "+" in rest:
            rest = rest.split("+", 1)[0]
        time_part = rest.strip()
    elif " " in text:
        time_part = text.split(" ", 1)[1].strip()
    if len(time_part) == 5:
        time_part = f"{time_part}:00"
    if len(time_part) < 8:
        return None
    time_part = time_part[:8]
    try:
        parsed = datetime.fromisoformat(f"{day}T{time_part}")
    except ValueError:
        return None
    return parsed.isoformat()


def _optional_str(value: object) -> str | None:
    if _is_null(value):
        return None
    text = str(value).strip()
    return text or None


def _is_null(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
