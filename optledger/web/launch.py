"""Launch Streamlit on localhost against a local snapshot directory."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from optledger.web.load import DATA_ENV, resolve_data_dir

APP_SCRIPT = Path(__file__).with_name("app.py")


def streamlit_command(*, data: Path, port: int) -> list[str]:
    resolve_data_dir(str(data))
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_SCRIPT),
        "--server.address",
        "localhost",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
    ]


def run_streamlit(*, data: Path, port: int) -> int:
    command = streamlit_command(data=data, port=port)
    env = os.environ.copy()
    env[DATA_ENV] = str(resolve_data_dir(str(data)))
    return int(subprocess.call(command, env=env))
