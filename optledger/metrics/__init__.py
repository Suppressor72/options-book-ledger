"""Flow-adjusted TWR, max drawdown, and time-to-recovery (supporting stats).

This package must not import ``optledger.cli``, ``optledger.web``,
``optledger.data``, ``optledger.ledger``, matplotlib, or optional extras.
"""

from __future__ import annotations

from optledger.metrics.twr import (
    WINDOWS,
    CashFlow,
    NlvPoint,
    TwrError,
    TwrResult,
    TwrWindowName,
    report_windows,
    twr_for_window,
    twr_index,
)

__all__ = [
    "WINDOWS",
    "CashFlow",
    "NlvPoint",
    "TwrError",
    "TwrResult",
    "TwrWindowName",
    "report_windows",
    "twr_for_window",
    "twr_index",
]
