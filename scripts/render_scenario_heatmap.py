"""Render the seeded XYZ call-spread scenario heatmap for the README.

Not imported by ``optledger``. Requires matplotlib (``uv run --with matplotlib``).
"""

from __future__ import annotations

from pathlib import Path

from optledger.book import example_xyz_call_spread, scenario_pnl_grid

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "xyz-scenario-heatmap.png"


def main() -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    book = example_xyz_call_spread()
    grid = scenario_pnl_grid(book, steps=80)
    data = np.array(grid.pnl, dtype=float)
    limit = float(max(abs(data.min()), abs(data.max()), 1.0))

    fig, ax = plt.subplots(figsize=(8.2, 6.2), layout="constrained")
    image = ax.imshow(
        data,
        cmap="RdBu",
        origin="lower",
        vmin=-limit,
        vmax=limit,
        aspect="auto",
    )
    ax.set_xticks(range(len(grid.spot_moves)), [f"{m:+.0%}" for m in grid.spot_moves])
    ax.set_yticks(range(len(grid.vol_moves)), [f"{m:+.0%}" for m in grid.vol_moves])
    ax.set_xlabel("Spot move")
    ax.set_ylabel("Vol move")
    ax.set_title(
        "Simulated / seeded XYZ short 100/110 call spread — scenario P/L\n"
        "Not a VaR engine. 7×7 mark-to-model grid from the same CRR pins."
    )
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("P/L (USD)")
    for row, vol_move in enumerate(grid.vol_moves):
        for col, spot_move in enumerate(grid.spot_moves):
            value = grid.cell(spot_move, vol_move)
            ax.text(
                col,
                row,
                f"{value:.0f}",
                ha="center",
                va="center",
                color="black" if abs(value) < 0.45 * limit else "white",
                fontsize=8,
            )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=140)
    plt.close(fig)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
