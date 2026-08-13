from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from optledger.cli.app import app
from optledger.web.launch import APP_SCRIPT, streamlit_command

runner = CliRunner()


def test_web_cli_exits_one_without_streamlit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "streamlit", None)
    result = runner.invoke(app, ["web", "--data", "data"])
    assert result.exit_code == 1, result.output
    assert "web" in result.output


def test_streamlit_command_binds_localhost() -> None:
    command = streamlit_command(data=Path("data"), port=8502)
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4] == str(APP_SCRIPT)
    assert "--server.address" in command
    assert command[command.index("--server.address") + 1] == "localhost"
    assert command[command.index("--server.port") + 1] == "8502"
