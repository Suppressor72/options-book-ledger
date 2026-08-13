"""Small-grid option-book reprice (supporting math only).

Product snapshot I/O lives in later phases. This package must not import
``optledger.cli``, ``optledger.web``, or optional extras.
"""

from __future__ import annotations

from optledger.book.example import example_xyz_call_spread
from optledger.book.models import (
    DEFAULT_SCENARIO_MOVES,
    BookReprice,
    BookSnapshot,
    ExerciseStyle,
    OptionPosition,
    ScenarioGrid,
)
from optledger.book.reprice import mark_book, reprice_book, scenario_pnl_grid

__all__ = [
    "DEFAULT_SCENARIO_MOVES",
    "BookReprice",
    "BookSnapshot",
    "ExerciseStyle",
    "OptionPosition",
    "ScenarioGrid",
    "example_xyz_call_spread",
    "mark_book",
    "reprice_book",
    "scenario_pnl_grid",
]
