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


@app.command()
def configure(
    current_age: int = typer.Option(..., prompt=True, help="Your current age"),
    life_expectancy: int = typer.Option(90, prompt=True, help="Estimated life expectancy"),
    current_savings: float = typer.Option(0, prompt=True, help="Current total savings/investments"),
    yearly_salary: float = typer.Option(..., prompt=True, help="Current yearly salary/compensation"),
    yearly_expenses: float = typer.Option(..., prompt=True, help="Estimated yearly expenses"),
    annual_return_pct: float = typer.Option(7.0, prompt=True, help="Expected annual investment return %"),
    inflation_pct: float = typer.Option(3.0, prompt=True, help="Expected annual inflation %"),
    salary_growth_pct: float = typer.Option(3.0, prompt=True, help="Expected annual salary growth %"),
) -> None:
    """Configure your wealth plan parameters."""
    config = PlannerConfig(
        current_age=current_age,
        life_expectancy=life_expectancy,
        current_savings=Decimal(str(current_savings)),
        yearly_salary=Decimal(str(yearly_salary)),
        yearly_expenses=Decimal(str(yearly_expenses)),
        annual_return_pct=Decimal(str(annual_return_pct)),
        inflation_pct=Decimal(str(inflation_pct)),
        salary_growth_pct=Decimal(str(salary_growth_pct)),
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
