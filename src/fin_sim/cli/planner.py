from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from fin_sim.models.planner import PlannerConfig
from fin_sim.services.planner_engine import project
from fin_sim.storage.store import load_planner_config, save_planner_config
from fin_sim.display.tables import render_plan_summary

app = typer.Typer(help="Long-term wealth planner")
console = Console()


def _parse_dollars(value: str) -> Decimal:
    """Parse a dollar amount, allowing optional commas (e.g. '4,000,000')."""
    return Decimal(value.replace(",", ""))


@app.command()
def configure(
    retirement_age: Optional[int] = typer.Option(None, help="Retirement age (0 = auto-retire at FIRE, omit = never)"),
) -> None:
    """Configure your wealth plan parameters."""
    existing = load_planner_config()
    e = existing  # shorthand

    current_age = typer.prompt("Current age", default=e.current_age if e else ...)
    life_expectancy = typer.prompt("Life expectancy", default=e.life_expectancy if e else 90)
    current_savings = typer.prompt("Current savings/investments", default=str(e.current_savings) if e else "0")
    yearly_salary = typer.prompt("Yearly salary/compensation", default=str(e.yearly_salary) if e else ...)
    yearly_expenses = typer.prompt("Yearly expenses", default=str(e.yearly_expenses) if e else ...)
    annual_return_pct = typer.prompt("Annual investment return %", default=float(e.annual_return_pct) if e else 7.0)
    inflation_pct = typer.prompt("Annual inflation %", default=float(e.inflation_pct) if e else 3.0)
    salary_growth_pct = typer.prompt("Annual salary growth %", default=float(e.salary_growth_pct) if e else 3.0)
    if retirement_age is None and e is not None:
        retirement_age = e.retirement_age

    config = PlannerConfig(
        current_age=current_age,
        life_expectancy=life_expectancy,
        current_savings=_parse_dollars(str(current_savings)),
        yearly_salary=_parse_dollars(str(yearly_salary)),
        yearly_expenses=_parse_dollars(str(yearly_expenses)),
        annual_return_pct=Decimal(str(annual_return_pct)),
        inflation_pct=Decimal(str(inflation_pct)),
        salary_growth_pct=Decimal(str(salary_growth_pct)),
        retirement_age=retirement_age,
    )
    path = save_planner_config(config)
    console.print(f"[green]Config saved to {path}[/green]")


@app.command()
def run(
    every_n: int = typer.Option(5, "--every", help="Show every Nth year in the table"),
) -> None:
    """Run the wealth projection and display results."""
    config = load_planner_config()
    if config is None:
        console.print("[red]No planner config found. Run 'fin-sim plan configure' first.[/red]")
        raise typer.Exit(1)
    summary = project(config)
    render_plan_summary(summary, every_n=every_n)


@app.command("show-config")
def show_config() -> None:
    """Show the current planner configuration."""
    config = load_planner_config()
    if config is None:
        console.print("[red]No planner config found. Run 'fin-sim plan configure' first.[/red]")
        raise typer.Exit(1)
    for key, value in config.model_dump().items():
        label = key.replace("_", " ").title()
        console.print(f"  {label}: {value}")
