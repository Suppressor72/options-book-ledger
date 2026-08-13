"""Streamlit AppTest smoke — skip if optledger[web] is not installed."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from optledger.cli.app import app
from optledger.web.load import DATA_ENV, PAGE_TITLES

REPO = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO / "fixtures" / "demo.json"
runner = CliRunner()


@pytest.mark.parametrize(
    ("page_name", "title", "expect"),
    [
        ("_page_data_quality", PAGE_TITLES[0], "ok:"),
        ("_page_ledger", PAGE_TITLES[1], "ok:"),
        ("_page_scenarios", PAGE_TITLES[2], "Spot"),
    ],
)
def test_streamlit_pages_open_on_demo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    page_name: str,
    title: str,
    expect: str,
) -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    built = tmp_path / "demo"
    build = runner.invoke(
        app,
        ["demo-build", "--out", str(built), "--fixture", str(DEMO_FIXTURE)],
    )
    assert build.exit_code == 0, build.output
    monkeypatch.setenv(DATA_ENV, str(built))
    script = f"from optledger.web.app import {page_name}\n{page_name}()\n"
    at = AppTest.from_string(script, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.title[0].value == title
    blob = "\n".join(_element_text(at))
    assert expect in blob


def _element_text(at: object) -> list[str]:
    texts: list[str] = []
    for attr in ("title", "code", "subheader", "caption"):
        for item in getattr(at, attr):
            value = getattr(item, "value", None)
            if isinstance(value, str):
                texts.append(value)
    return texts
