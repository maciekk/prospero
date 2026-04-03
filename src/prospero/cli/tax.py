"""
Tax breakdown command — standalone Typer app.

Exposed as both:
  prospero tax-breakdown   (sub-command on the main prospero app)
  prospero-tax             (standalone entry point)
"""

import dataclasses
import json
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from prospero.display.tables import render_tax_breakdown
from prospero.services.tax import TaxBreakdown, calculate_tax_breakdown
from prospero.storage.store import load_planner_config
from prospero.cli._options import PDF_OPTION

app = typer.Typer(help="Canadian income tax breakdown (ON, 2025 base rates)")
err = Console(stderr=True)


def _parse_dollars(value: str) -> Decimal:
    return Decimal(value.strip().lstrip("$").replace(",", ""))


def _breakdown_to_dict(bd: TaxBreakdown) -> dict:
    d = dataclasses.asdict(bd)
    d["ontario"] = bd.ontario
    d["total"] = bd.total
    d["take_home"] = bd.take_home
    return d


def _json_default(obj: object) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@app.command()
def breakdown(
    income: Optional[str] = typer.Option(
        None,
        "--income",
        help="Gross income to calculate tax on (e.g. 150000 or $150,000). Defaults to configured salary.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON instead of a table."),
    output_pdf: Optional[Path] = PDF_OPTION,
) -> None:
    """Show a detailed tax breakdown for a given income (ON, Canada, 2025 base rates)."""
    if income is not None:
        gross = _parse_dollars(income)
    else:
        config = load_planner_config()
        if config is None:
            err.print("[red]No planner config found. Provide --income or run 'prospero plan configure' first.[/red]")
            raise typer.Exit(1)
        gross = config.yearly_salary

    result = calculate_tax_breakdown(gross)
    if output_json:
        typer.echo(json.dumps(_breakdown_to_dict(result), default=_json_default, indent=2))
    else:
        render_tax_breakdown(result)
    if output_pdf is not None:
        from prospero.display.pdf import pdf_tax_breakdown
        pdf_tax_breakdown(result, output_pdf)
        Console().print(f"[dim]PDF saved to {output_pdf}[/dim]")
