"""Typer CLI: demo-build, dq, ledger-recon, twr, and web."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from optledger.cli.twr import format_twr_report, twr_from_snapshot_dir, write_quantstats_html
from optledger.data import check_snapshot_dir, format_report, write_snapshots
from optledger.ledger import format_recon_report, recon_snapshot_dir, write_ledger
from optledger.metrics import TwrError
from optledger.simulate import build_demo_bundle, load_demo_spec

app = typer.Typer(no_args_is_help=True, add_completion=False)

_DEFAULT_OUT = Path("data")
_DEFAULT_FIXTURE = Path("fixtures/demo.json")


@app.command("demo-build")
def demo_build(
    out: Annotated[
        Path,
        typer.Option("--out", help="Directory for snapshot Parquet."),
    ] = _DEFAULT_OUT,
    fixture: Annotated[
        Path,
        typer.Option("--fixture", help="Seeded XYZ demo spec."),
    ] = _DEFAULT_FIXTURE,
) -> None:
    """Write RNG-seeded XYZ snapshot and ledger Parquet. Same seed is identical."""
    spec = load_demo_spec(fixture)
    bundle = build_demo_bundle(spec)
    written = write_snapshots(out, bundle.frames)
    written.extend(write_ledger(out, bundle.events))
    for path in written:
        typer.echo(f"wrote {path}")


@app.command()
def dq(
    data: Annotated[
        Path,
        typer.Option("--data", help="Directory of snapshot Parquet."),
    ] = _DEFAULT_OUT,
) -> None:
    """Fail-closed pin/join/schema checks. Exit 0 on a clean book, 1 on breaks."""
    report = check_snapshot_dir(data)
    typer.echo(format_report(report))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("ledger-recon")
def ledger_recon(
    data: Annotated[
        Path,
        typer.Option("--data", help="Directory of snapshot and ledger Parquet."),
    ] = _DEFAULT_OUT,
) -> None:
    """Fail-closed qty/cash/NLV recon. Exit 0 on a clean book, 1 on breaks."""
    report = recon_snapshot_dir(data)
    typer.echo(format_recon_report(report))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def twr(
    data: Annotated[
        Path,
        typer.Option("--data", help="Directory of snapshot and ledger Parquet."),
    ] = _DEFAULT_OUT,
) -> None:
    """Flow-adjusted TWR, max DD, and time-to-recovery. Simulated / seeded."""
    try:
        results = twr_from_snapshot_dir(data)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except TwrError as exc:
        typer.echo(f"FAIL: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(format_twr_report(results))


@app.command()
def tearsheet(
    data: Annotated[
        Path,
        typer.Option("--data", help="Directory of snapshot and ledger Parquet."),
    ] = _DEFAULT_OUT,
    out: Annotated[
        Path,
        typer.Option("--out", help="HTML path for the QuantStats tearsheet."),
    ] = Path("data/twr-tearsheet.html"),
) -> None:
    """Optional QuantStats HTML from the TWR series. Requires optledger[tearsheet]."""
    try:
        import quantstats as qs
    except ImportError as exc:
        typer.echo("optledger tearsheet requires: uv sync --extra tearsheet")
        raise typer.Exit(code=1) from exc
    try:
        results = twr_from_snapshot_dir(data)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except TwrError as exc:
        typer.echo(f"FAIL: {exc}")
        raise typer.Exit(code=1) from exc
    series = next((item for item in results if item.window == "all"), None)
    if series is None:
        typer.echo("FAIL: TWR results missing 'all' window")
        raise typer.Exit(code=1)
    if len(series.index.values) < 2:
        typer.echo("FAIL: need at least two EOD pins for a tearsheet")
        raise typer.Exit(code=1)
    returns = [
        curr / prev - 1.0
        for prev, curr in zip(series.index.values, series.index.values[1:], strict=True)
    ]
    import pandas as pd

    frame = pd.Series(
        returns,
        index=pd.DatetimeIndex(series.index.times[1:]),
        name="twr",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    write_quantstats_html(
        frame,
        out,
        html_fn=qs.reports.html,
        title="Simulated / seeded XYZ TWR",
    )
    typer.echo(f"wrote {out}")


@app.command()
def web(
    data: Annotated[
        Path,
        typer.Option("--data", help="Directory of snapshot and ledger Parquet."),
    ] = _DEFAULT_OUT,
    port: Annotated[
        int,
        typer.Option("--port", help="Localhost port for Streamlit."),
    ] = 8501,
) -> None:
    """Slim Streamlit: Data quality, Ledger, Scenarios. Requires optledger[web]."""
    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        typer.echo("optledger web requires: uv sync --extra web")
        raise typer.Exit(code=1) from exc
    from optledger.web.launch import run_streamlit

    raise typer.Exit(code=run_streamlit(data=data, port=port))
