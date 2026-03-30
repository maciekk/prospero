from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from prospero.models.planner import PlannerConfig
from prospero.services.planner_engine import project
from prospero.storage.store import load_planner_config, save_planner_config
from prospero.display.tables import render_plan_summary

app = typer.Typer(help="Long-term wealth planner")
console = Console()


def _parse_dollars(value: str) -> Decimal:
    """Parse a dollar amount, allowing optional '$' prefix and commas (e.g. '$4,000,000')."""
    return Decimal(value.strip().lstrip("$").replace(",", ""))


def _fmt_dollars(value: Decimal) -> str:
    return f"${value:,.0f}"


def _prompt(msg: str, *, default=None, **kwargs) -> str:
    """Prompt with an optional default; omits default kwarg when None (makes field required)."""
    if default is None:
        return typer.prompt(msg, **kwargs)
    return typer.prompt(msg, default=default, **kwargs)


def _parse_income_change(raw: str) -> dict:
    """Parse 'AGE:SALARY' into a dict for IncomeChange. Age 0 = retire at FIRE."""
    try:
        age_str, salary_str = raw.split(":", 1)
        return {"age": int(age_str.strip()), "yearly_salary": _parse_dollars(salary_str.strip())}
    except (ValueError, TypeError) as exc:
        raise typer.BadParameter(f"Expected AGE:SALARY (e.g. 55:80000), got {raw!r}") from exc


@app.command()
def configure(
    income_change: Optional[list[str]] = typer.Option(
        None,
        "--income-change",
        help="Income change as AGE:SALARY in today's dollars (repeatable). Age 0 = retire at FIRE. e.g. --income-change 55:80000 --income-change 65:0",
    ),
) -> None:
    """Configure your wealth plan parameters."""
    existing = load_planner_config()
    e = existing  # shorthand

    current_age = _prompt("Current age", default=e.current_age if e else None)
    life_expectancy = _prompt("Life expectancy", default=e.life_expectancy if e else 90)
    # Dollar defaults are shown as "$123,456" — _parse_dollars strips "$" and commas on the way back in
    current_savings = _prompt("Current savings/investments", default=_fmt_dollars(e.current_savings) if e else "$0")
    yearly_salary = _prompt("Yearly salary/compensation", default=_fmt_dollars(e.yearly_salary) if e else None)
    yearly_expenses = _prompt("Yearly expenses", default=_fmt_dollars(e.yearly_expenses) if e else None)
    annual_return_pct = _prompt("Annual investment return %", default=float(e.annual_return_pct) if e else 7.0)
    inflation_pct = _prompt("Annual inflation %", default=float(e.inflation_pct) if e else 3.0)
    salary_growth_pct = _prompt("Annual salary growth %", default=float(e.salary_growth_pct) if e else 3.0)

    if income_change is not None:
        parsed_changes = [_parse_income_change(c) for c in income_change]
    elif e is not None:
        parsed_changes = [ic.model_dump(mode='json') for ic in e.income_changes]
    else:
        parsed_changes = []

    config = PlannerConfig(
        current_age=current_age,
        life_expectancy=life_expectancy,
        current_savings=_parse_dollars(str(current_savings)),
        yearly_salary=_parse_dollars(str(yearly_salary)),
        yearly_expenses=_parse_dollars(str(yearly_expenses)),
        annual_return_pct=Decimal(str(annual_return_pct)),
        inflation_pct=Decimal(str(inflation_pct)),
        salary_growth_pct=Decimal(str(salary_growth_pct)),
        income_changes=parsed_changes,
    )
    path = save_planner_config(config)
    console.print(f"[green]Config saved to {path}[/green]")


@app.command()
def run(
    every_n: int = typer.Option(5, "--every", help="Show every Nth year in the table"),
    output_json: bool = typer.Option(False, "--json", help="Output full projection as JSON instead of a table."),
) -> None:
    """Run the wealth projection and display results."""
    config = load_planner_config()
    if config is None:
        console.print("[red]No planner config found. Run 'prospero plan configure' first.[/red]")
        raise typer.Exit(1)
    summary = project(config)
    if output_json:
        typer.echo(summary.model_dump_json(indent=2))
    else:
        render_plan_summary(summary, config, every_n=every_n)



@app.command("show-config")
def show_config() -> None:
    """Show the current planner configuration."""
    config = load_planner_config()
    if config is None:
        console.print("[red]No planner config found. Run 'prospero plan configure' first.[/red]")
        raise typer.Exit(1)
    for key, value in config.model_dump().items():
        label = key.replace("_", " ").title()
        if key == "income_changes":
            if not value:
                console.print(f"  {label}: (none)")
            else:
                console.print(f"  {label}:")
                for ic in value:
                    age_label = "At FIRE" if ic["age"] == 0 else f"Age {ic['age']}"
                    sal = Decimal(str(ic["yearly_salary"]))
                    status = "fully retire" if sal == 0 else f"salary \u2192 ${sal:,.0f}/yr (today's $)"
                    console.print(f"    {age_label}: {status}")
        else:
            console.print(f"  {label}: {value}")
