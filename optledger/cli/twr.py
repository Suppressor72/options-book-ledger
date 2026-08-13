"""Load EOD NLV + deposits and format a thin TWR report."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from optledger.data.dq import parse_finite_float
from optledger.data.schema import PIN_KINDS
from optledger.data.store import read_snapshots
from optledger.ledger.recon import parse_as_of_key
from optledger.ledger.schema import EVENT_KINDS
from optledger.ledger.store import read_ledger
from optledger.metrics import CashFlow, NlvPoint, TwrError, TwrResult, report_windows

_DEPOSIT_KIND = "cash_deposit"


def twr_from_snapshot_dir(root: Path) -> tuple[TwrResult, ...]:
    frames = read_snapshots(root)
    events = read_ledger(root)
    points = eod_nlv_points(frames["account_snapshot"])
    deposits = deposit_flows(events)
    return report_windows(points, deposits)


def eod_nlv_points(account: pd.DataFrame) -> tuple[NlvPoint, ...]:
    points: list[NlvPoint] = []
    for row in account.itertuples(index=False):
        pin_kind = _cell_str(row.pin_kind)
        if pin_kind not in PIN_KINDS:
            raise TwrError(f"unusable pin_kind {row.pin_kind!r}")
        if pin_kind != "eod":
            continue
        as_of = _as_of_datetime(row.as_of)
        nlv = parse_finite_float(row.nlv)
        if nlv is None:
            raise TwrError(f"account nlv is not a finite number at {row.as_of!r}")
        points.append(NlvPoint(as_of=as_of, nlv=nlv))
    if not points:
        raise TwrError("no EOD account pins")
    return tuple(points)


def deposit_flows(events: pd.DataFrame) -> tuple[CashFlow, ...]:
    if "event_kind" not in events.columns:
        raise TwrError("ledger missing event_kind")
    flows: list[CashFlow] = []
    for row in events.itertuples(index=False):
        kind = _cell_str(row.event_kind)
        if kind not in EVENT_KINDS:
            raise TwrError(f"unusable event_kind {row.event_kind!r}")
        if kind != _DEPOSIT_KIND:
            continue
        as_of = _as_of_datetime(row.as_of)
        amount = parse_finite_float(row.cash)
        if amount is None:
            raise TwrError(f"deposit cash is not a finite number at {row.as_of!r}")
        flows.append(CashFlow(as_of=as_of, amount=amount))
    return tuple(flows)


def format_twr_report(results: tuple[TwrResult, ...]) -> str:
    lines = [
        "simulated / seeded",
        f"{'window':<13} {'twr':>10} {'max_dd':>10} {'ttr_days':>10}",
    ]
    for result in results:
        ttr = "—" if result.time_to_recovery_days is None else str(result.time_to_recovery_days)
        lines.append(
            f"{result.window:<13} {_pct(result.twr):>10} {_pct(result.max_drawdown):>10} {ttr:>10}"
        )
    return "\n".join(lines)


def _pct(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def write_quantstats_html(
    returns: pd.Series,
    out: Path,
    *,
    html_fn: Callable[..., Any],
    title: str,
) -> None:
    """Write QuantStats HTML without a default benchmark download (no SPY fetch)."""
    kwargs: dict[str, Any] = {"output": str(out), "title": title}
    try:
        params = inspect.signature(html_fn).parameters
    except (TypeError, ValueError):
        html_fn(returns, **kwargs)
        return
    if "benchmark" in params:
        kwargs["benchmark"] = None
    html_fn(returns, **kwargs)


def _as_of_datetime(value: object) -> datetime:
    key = parse_as_of_key(value)
    if key is None:
        raise TwrError(f"unparseable as_of {value!r}")
    return datetime.fromisoformat(key)


def _cell_str(value: object) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None
