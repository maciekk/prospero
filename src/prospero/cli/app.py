from decimal import Decimal
from typing import Optional

import typer

from prospero.cli import acb, planner, portfolio
from prospero.services.tax import calculate_tax_breakdown
from prospero.storage.store import load_planner_config
from prospero.display.tables import render_tax_breakdown

app = typer.Typer(
    name="prospero",
    help="Portfolio tracker and wealth planner",
)
app.add_typer(acb.app, name="acb", help="ACB tracker for Canadian capital gains tax")
app.add_typer(planner.app, name="plan", help="Long-term wealth planner")
app.add_typer(portfolio.app, name="portfolio", help="Stock portfolio tracker")

console = typer.get_text_stream("stdout")


def _parse_dollars(value: str) -> Decimal:
    return Decimal(value.strip().lstrip("$").replace(",", ""))


@app.command("tax-breakdown")
def tax_breakdown(
    income: Optional[str] = typer.Option(
        None,
        "--income",
        help="Gross income to calculate tax on (e.g. 150000 or $150,000). Defaults to configured salary.",
    ),
) -> None:
    """Show a detailed tax breakdown for a given income (ON, Canada, 2025 base rates)."""
    from rich.console import Console
    err = Console(stderr=True)

    if income is not None:
        gross = _parse_dollars(income)
    else:
        config = load_planner_config()
        if config is None:
            err.print("[red]No planner config found. Provide --income or run 'prospero plan configure' first.[/red]")
            raise typer.Exit(1)
        gross = config.yearly_salary

    render_tax_breakdown(calculate_tax_breakdown(gross))


if __name__ == "__main__":
    app()
