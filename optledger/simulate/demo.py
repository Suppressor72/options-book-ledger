"""Seeded synthetic XYZ book → snapshot frames (offline, no market data)."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from optledger.book import (
    DEFAULT_SCENARIO_MOVES,
    BookSnapshot,
    OptionPosition,
    mark_book,
    reprice_book,
)
from optledger.book.models import ExerciseStyle
from optledger.data.schema import (
    EOD_CLOCK,
    OPEN_CLOCK,
    PinKind,
    SnapshotFamily,
    scenario_pnl_column,
    snapshot_id_for,
)
from optledger.ledger.schema import DEMO_ACCOUNT, LEDGER_COLUMNS
from optledger.pricing import OptionRight, crr_american_price_greeks

_DEMO_FEE_CASH = -1.0


@dataclass(frozen=True, slots=True)
class DemoLeg:
    quantity: float
    right: OptionRight
    strike: float
    expiry: date
    iv: float
    multiplier: float
    style: ExerciseStyle


@dataclass(frozen=True, slots=True)
class DemoBundle:
    frames: dict[SnapshotFamily, pd.DataFrame]
    events: pd.DataFrame


@dataclass(frozen=True, slots=True)
class DemoSpec:
    seed: int
    symbol: str
    start_date: date
    n_days: int
    start_spot: float
    rate: float
    dividend_yield: float
    starting_cash: float
    crr_steps: int
    legs: tuple[DemoLeg, ...]


def load_demo_spec(path: Path) -> DemoSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _spec_from_mapping(raw)


def build_demo_frames(spec: DemoSpec) -> dict[SnapshotFamily, pd.DataFrame]:
    return build_demo_bundle(spec).frames


def build_demo_bundle(spec: DemoSpec) -> DemoBundle:
    rng = random.Random(spec.seed)
    account_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    metrics_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    spot = spec.start_spot
    running_cash = spec.starting_cash
    event_seq = 0
    pins: tuple[tuple[PinKind, str, float], ...] = (
        ("open", OPEN_CLOCK, 0.008),
        ("eod", EOD_CLOCK, 0.004),
    )
    event_seq = _append_event(
        event_rows,
        event_seq,
        as_of=f"{spec.start_date.isoformat()}T00:00:00",
        event_kind="cash_deposit",
        symbol=spec.symbol,
        instrument_id="",
        qty=0.0,
        cash=spec.starting_cash,
    )
    for offset in range(spec.n_days):
        day = spec.start_date + timedelta(days=offset)
        for pin_kind, clock, vol in pins:
            spot *= math.exp(rng.gauss(0.0, vol))
            as_of = f"{day.isoformat()}T{clock}"
            snapshot_id = snapshot_id_for(day.isoformat(), pin_kind)
            book = _book_at(spec, spot=spot, as_of=datetime.fromisoformat(as_of))
            marked = mark_book(book, steps=spec.crr_steps)
            emit_opening = offset == 0 and pin_kind == "open"
            net_delta = 0.0
            net_vega = 0.0
            for spec_leg, position in zip(spec.legs, book.positions, strict=True):
                greeks = crr_american_price_greeks(
                    spot=spot,
                    strike=position.strike,
                    time_years=position.time_years,
                    rate=spec.rate,
                    volatility=position.volatility,
                    right=position.right,
                    dividend_yield=spec.dividend_yield,
                    steps=spec.crr_steps,
                )
                scale = position.quantity * position.multiplier
                net_delta += greeks.delta * scale
                net_vega += greeks.vega * scale
                if emit_opening:
                    fill_cash = -position.quantity * greeks.price * position.multiplier
                    event_seq = _append_event(
                        event_rows,
                        event_seq,
                        as_of=as_of,
                        event_kind="fill",
                        symbol=spec.symbol,
                        instrument_id=_instrument_id(spec.symbol, spec_leg),
                        qty=position.quantity,
                        cash=fill_cash,
                    )
                    running_cash += fill_cash
                position_rows.append(
                    {
                        "snapshot_id": snapshot_id,
                        "as_of": as_of,
                        "pin_kind": pin_kind,
                        "symbol": spec.symbol,
                        "instrument_id": _instrument_id(spec.symbol, spec_leg),
                        "right": position.right,
                        "strike": position.strike,
                        "expiry": spec_leg.expiry.isoformat(),
                        "qty": position.quantity,
                        "spot": spot,
                        "iv": position.volatility,
                        "model_price": greeks.price,
                        "delta": greeks.delta,
                        "vega": greeks.vega,
                        "multiplier": position.multiplier,
                        "style": position.style,
                    }
                )
            if emit_opening:
                event_seq = _append_event(
                    event_rows,
                    event_seq,
                    as_of=as_of,
                    event_kind="fee",
                    symbol=spec.symbol,
                    instrument_id="",
                    qty=0.0,
                    cash=_DEMO_FEE_CASH,
                )
                running_cash += _DEMO_FEE_CASH
            nlv = running_cash + marked
            account_rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "as_of": as_of,
                    "pin_kind": pin_kind,
                    "nlv": float(nlv),
                    "cash": float(running_cash),
                }
            )
            metrics_row: dict[str, Any] = {
                "snapshot_id": snapshot_id,
                "as_of": as_of,
                "pin_kind": pin_kind,
                "net_delta": net_delta,
                "net_vega": net_vega,
            }
            for move in DEFAULT_SCENARIO_MOVES:
                pnl = reprice_book(
                    book,
                    spot_mult=1.0 + move,
                    vol_mult=1.0,
                    steps=spec.crr_steps,
                ).pnl
                metrics_row[scenario_pnl_column(move)] = pnl
            metrics_rows.append(metrics_row)
    events = pd.DataFrame(event_rows, columns=list(LEDGER_COLUMNS))
    return DemoBundle(
        frames={
            "account_snapshot": pd.DataFrame(account_rows),
            "position_snapshot": pd.DataFrame(position_rows),
            "book_metrics": pd.DataFrame(metrics_rows),
        },
        events=events,
    )


def _append_event(
    rows: list[dict[str, Any]],
    seq: int,
    *,
    as_of: str,
    event_kind: str,
    symbol: str,
    instrument_id: str,
    qty: float,
    cash: float,
) -> int:
    seq += 1
    rows.append(
        {
            "event_id": f"evt-{seq:04d}",
            "as_of": as_of,
            "account": DEMO_ACCOUNT,
            "event_kind": event_kind,
            "symbol": symbol,
            "instrument_id": instrument_id,
            "qty": qty,
            "cash": cash,
        }
    )
    return seq


def _book_at(spec: DemoSpec, *, spot: float, as_of: datetime) -> BookSnapshot:
    positions = tuple(_position(leg, as_of=as_of) for leg in spec.legs)
    return BookSnapshot(
        spot=spot,
        rate=spec.rate,
        dividend_yield=spec.dividend_yield,
        positions=positions,
    )


def _position(leg: DemoLeg, *, as_of: datetime) -> OptionPosition:
    days = (leg.expiry - as_of.date()).days
    time_years = max(days, 0) / 365.0
    return OptionPosition(
        quantity=leg.quantity,
        strike=leg.strike,
        time_years=time_years,
        volatility=leg.iv,
        right=leg.right,
        multiplier=leg.multiplier,
        style=leg.style,
    )


def _instrument_id(symbol: str, leg: DemoLeg) -> str:
    right = "C" if leg.right == "call" else "P"
    strike = f"{leg.strike:g}"
    return f"{symbol}-{leg.expiry.strftime('%Y%m%d')}-{right}-{strike}"


def _spec_from_mapping(raw: dict[str, Any]) -> DemoSpec:
    legs = tuple(
        DemoLeg(
            quantity=float(item["quantity"]),
            right=_right(item["right"]),
            strike=float(item["strike"]),
            expiry=date.fromisoformat(str(item["expiry"])),
            iv=float(item["iv"]),
            multiplier=float(item["multiplier"]),
            style=_style(item["style"]),
        )
        for item in raw["legs"]
    )
    return DemoSpec(
        seed=int(raw["seed"]),
        symbol=str(raw["symbol"]),
        start_date=date.fromisoformat(str(raw["start_date"])),
        n_days=int(raw["n_days"]),
        start_spot=float(raw["start_spot"]),
        rate=float(raw["rate"]),
        dividend_yield=float(raw["dividend_yield"]),
        starting_cash=float(raw["starting_cash"]),
        crr_steps=int(raw["crr_steps"]),
        legs=legs,
    )


def _right(value: object) -> OptionRight:
    if value == "call":
        return "call"
    if value == "put":
        return "put"
    raise ValueError(f"right must be 'call' or 'put', got {value!r}")


def _style(value: object) -> ExerciseStyle:
    if value == "american":
        return "american"
    if value == "european":
        return "european"
    raise ValueError(f"style must be 'american' or 'european', got {value!r}")
