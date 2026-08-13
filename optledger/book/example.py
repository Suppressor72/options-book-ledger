"""Seeded XYZ example used by tests and the README heatmap."""

from __future__ import annotations

from optledger.book.models import BookSnapshot, OptionPosition


def example_xyz_call_spread() -> BookSnapshot:
    """Two-contract short 100/110 XYZ call spread (simulated / seeded).

    Short 1× 100-strike call, long 1× 110-strike call, 0.25y, American, 100-multiplier.
    """
    time_years = 0.25
    return BookSnapshot(
        spot=100.0,
        rate=0.05,
        dividend_yield=0.0,
        positions=(
            OptionPosition(
                quantity=-1.0,
                strike=100.0,
                time_years=time_years,
                volatility=0.20,
                right="call",
                multiplier=100.0,
                style="american",
            ),
            OptionPosition(
                quantity=1.0,
                strike=110.0,
                time_years=time_years,
                volatility=0.18,
                right="call",
                multiplier=100.0,
                style="american",
            ),
        ),
    )
