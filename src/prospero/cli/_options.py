"""Shared Typer option definitions reused across CLI modules."""

from pathlib import Path
from typing import Optional

import typer

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
