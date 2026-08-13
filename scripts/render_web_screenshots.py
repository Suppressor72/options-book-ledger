"""Render seeded matplotlib mockups of the Streamlit pages for the README.

These are not Streamlit chrome captures. Not imported by ``optledger``.
Requires matplotlib (``uv run --with matplotlib``).
"""

from __future__ import annotations

from pathlib import Path

from optledger.data import check_frames, format_report
from optledger.ledger import format_recon_report, recon_frames
from optledger.simulate import build_demo_bundle, load_demo_spec
from optledger.web.load import book_from_positions, eod_snapshot_ids, scenario_grid_frame

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FIXTURE = ROOT / "fixtures" / "demo.json"


def main() -> None:
    import matplotlib.pyplot as plt

    bundle = build_demo_bundle(load_demo_spec(FIXTURE))
    dq = check_frames(bundle.frames)
    recon = recon_frames(bundle.frames, bundle.events)
    positions = bundle.frames["position_snapshot"]
    pin = eod_snapshot_ids(positions)[-1]
    book = book_from_positions(positions, pin)
    _grid, scenario = scenario_grid_frame(book)
    DOCS.mkdir(parents=True, exist_ok=True)
    _text_page(
        DOCS / "xyz-streamlit-dq.png",
        title="Data quality — simulated / seeded",
        body=format_report(dq),
    )
    _text_page(
        DOCS / "xyz-streamlit-ledger.png",
        title="Ledger — simulated / seeded",
        body=_ledger_body(recon, bundle.events),
    )
    _heatmap_page(DOCS / "xyz-streamlit-scenarios.png", scenario=scenario)
    plt.close("all")


def _text_page(path: Path, *, title: str, body: str) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9.2, 5.2), layout="constrained")
    ax.axis("off")
    ax.set_title(title)
    ax.text(0.0, 0.92, body, transform=ax.transAxes, fontsize=11, fontfamily="monospace", va="top")
    ax.text(
        0.0,
        0.08,
        "Local Parquet only. Not a VaR engine.",
        transform=ax.transAxes,
        fontsize=9,
        color="0.35",
    )
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"wrote {path}")


def _ledger_body(report: object, events: object) -> str:
    counts = events["event_kind"].value_counts().to_string()
    return f"{format_recon_report(report)}\n\n{counts}"


def _heatmap_page(path: Path, *, scenario: object) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    data = np.array(scenario.to_numpy(dtype=float), dtype=float)
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
    ax.set_xticks(range(len(scenario.columns)), list(scenario.columns))
    ax.set_yticks(range(len(scenario.index)), list(scenario.index))
    ax.set_xlabel("Spot move")
    ax.set_ylabel("Vol move")
    ax.set_title(
        "Scenarios — simulated / seeded XYZ EOD pin\n"
        "Not a VaR engine. 7×7 mark-to-model grid from the pinned book."
    )
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("P/L (USD)")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
