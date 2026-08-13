"""Streamlit entry: three book-operations pages, no pricer/VaR/smile gallery."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from optledger.data import check_snapshot_dir, format_report
from optledger.ledger import format_recon_report, read_ledger, recon_snapshot_dir
from optledger.web.load import (
    DATA_ENV,
    DEFAULT_CRR_STEPS,
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RATE,
    PAGE_TITLES,
    WebLoadError,
    book_from_positions,
    dq_issue_frame,
    eod_snapshot_ids,
    load_position_snapshot,
    position_table,
    recon_issue_frame,
    resolve_data_dir,
    scenario_grid_frame,
)

_SEED_CAPTION = "Simulated / seeded. Local Parquet only. Not a VaR engine."


def main() -> None:
    st.set_page_config(page_title="Options Book Ledger", layout="wide")
    st.navigation(
        [
            st.Page(_page_data_quality, title=PAGE_TITLES[0], url_path="dq", default=True),
            st.Page(_page_ledger, title=PAGE_TITLES[1], url_path="ledger"),
            st.Page(_page_scenarios, title=PAGE_TITLES[2], url_path="scenarios"),
        ]
    ).run()


def _page_data_quality() -> None:
    root = _data_root()
    st.title("Data quality")
    st.caption(_SEED_CAPTION)
    report = check_snapshot_dir(root)
    st.code(format_report(report), language="text")
    st.dataframe(dq_issue_frame(report), use_container_width=True)


def _page_ledger() -> None:
    root = _data_root()
    st.title("Ledger")
    st.caption(_SEED_CAPTION)
    report = recon_snapshot_dir(root)
    st.code(format_recon_report(report), language="text")
    st.dataframe(recon_issue_frame(report), use_container_width=True)
    try:
        events = read_ledger(root)
    except (FileNotFoundError, ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.subheader("Events")
    st.dataframe(events, use_container_width=True)


def _page_scenarios() -> None:
    root = _data_root()
    st.title("Scenarios")
    st.caption(_SEED_CAPTION)
    try:
        positions = load_position_snapshot(root)
    except (FileNotFoundError, ValueError, OSError) as exc:
        st.error(str(exc))
        return
    pins = eod_snapshot_ids(positions)
    if not pins:
        st.error("no EOD position pins")
        return
    snapshot_id = st.selectbox("EOD pin", pins, index=len(pins) - 1)
    st.subheader("Positions")
    st.dataframe(position_table(positions, snapshot_id), use_container_width=True)
    try:
        book = book_from_positions(
            positions,
            snapshot_id,
            rate=DEFAULT_RATE,
            dividend_yield=DEFAULT_DIVIDEND_YIELD,
        )
        _grid, frame = scenario_grid_frame(book, steps=DEFAULT_CRR_STEPS)
    except (WebLoadError, ValueError) as exc:
        st.error(str(exc))
        return
    st.subheader("Spot × vol P/L")
    st.caption(
        f"7×7 mark-to-model grid. Rate {DEFAULT_RATE:.2f} and dividend "
        f"{DEFAULT_DIVIDEND_YIELD:.2f} are UI defaults (not Parquet). "
        "Exercise style is the position style column (american/european). "
        "Not a VaR engine."
    )
    st.dataframe(frame.style.format("{:.0f}"), use_container_width=True)


def _data_root() -> Path:
    st.sidebar.caption("Local files only. Refresh re-reads Parquet.")
    default = os.environ.get(DATA_ENV, "data")
    raw = st.sidebar.text_input("Data directory", value=default)
    st.sidebar.button("Refresh")
    try:
        root = resolve_data_dir(raw)
    except WebLoadError as exc:
        st.sidebar.error(str(exc))
        st.stop()
        raise
    return root


if __name__ == "__main__":
    main()
