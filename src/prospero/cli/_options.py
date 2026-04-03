"""Shared Typer option definitions reused across CLI modules."""

import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

_header_printed = False
_console = Console()


def print_run_header() -> None:
    """Print a Rich rule stamped with the current date/time. Idempotent — prints once per process."""
    global _header_printed
    if _header_printed:
        return
    _header_printed = True
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _console.rule(f"[dim]Prospero run — {now}[/dim]", style="dim")

PDF_OPTION: Optional[Path] = typer.Option(
    None,
    "--pdf",
    help="Write output to a PDF file at this path (terminal output still shown).",
)

CSV_OPTION: Optional[Path] = typer.Option(
    None,
    "--csv",
    help="Write output to a CSV file at this path (terminal output still shown).",
)
