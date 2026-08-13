"""Lifecycle event kinds and required ledger columns.

Instrument id is an opaque key. Option rights live on snapshots, not here.
"""

from __future__ import annotations

from typing import Literal

type EventKind = Literal["fill", "expire_worthless", "assignment", "cash_deposit", "fee"]

EVENT_KINDS: tuple[EventKind, ...] = (
    "fill",
    "expire_worthless",
    "assignment",
    "cash_deposit",
    "fee",
)

DEMO_ACCOUNT = "demo"

LEDGER_COLUMNS: tuple[str, ...] = (
    "event_id",
    "as_of",
    "account",
    "event_kind",
    "symbol",
    "instrument_id",
    "qty",
    "cash",
)
