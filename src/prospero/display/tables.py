from decimal import Decimal

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from prospero.models.planner import PlannerConfig, PlanSummary
from prospero.models.portfolio import PortfolioSummary, HoldingValuation, Portfolio

console = Console()


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _money_whole(value: Decimal) -> str:
    return f"${value:,.0f}"


def _money_k(value: Decimal) -> str:
    """Format as $XXK (thousands), rounded to nearest thousand."""
    thousands = int(value / 1000)
    return f"${thousands:,}K"


def _pct(value: Decimal) -> str:
    return f"{value:,.2f}%"


def _colored_money(value: Decimal) -> Text:
    text = _money(value)
    if value > 0:
        return Text(f"+{text}", style="green")
    elif value < 0:
        return Text(text, style="red")
    return Text(text)


def _colored_pct(value: Decimal) -> Text:
    text = _pct(value)
    if value > 0:
        return Text(f"+{text}", style="green")
    elif value < 0:
        return Text(text, style="red")
    return Text(text)


# --- Planner ---

def render_plan_summary(summary: PlanSummary, config: PlannerConfig, every_n: int = 5) -> None:
    # expand=True fills terminal width; ratio values are proportional to typical content
    # width so the surplus space lands where columns naturally need it most.
    table = Table(title="Wealth Projection (ON, Canada)", show_lines=False, expand=True)
    table.add_column("Age",       justify="right", ratio=3)
    table.add_column("Year",      justify="right", ratio=4)
    table.add_column("Gross",     justify="right", ratio=8)
    table.add_column("Tax",       justify="right", ratio=8)
    table.add_column("Net Inc",   justify="right", ratio=9)
    table.add_column("Expenses",  justify="right", ratio=9)
    table.add_column("Saved",     justify="right", ratio=6)
    table.add_column("Growth",    justify="right", ratio=7)
    table.add_column("Net Worth", justify="right", ratio=11)

    transition_ages = set(summary.income_change_ages)

    for i, p in enumerate(summary.projections):
        is_fire_year = summary.fire_age is not None and p.age == summary.fire_age
        is_transition_year = p.age in transition_ages
        show = (i == 0 or i == len(summary.projections) - 1
                or i % every_n == 0 or is_fire_year or is_transition_year)
        if show:
            if is_fire_year:
                style = "bold yellow"
            elif is_transition_year:
                style = "bold cyan" if p.income == 0 else "bold magenta"
            else:
                style = None
            table.add_row(
                str(p.age),
                str(p.year),
                _money_whole(p.income),
                _money_whole(p.taxes),
                _money_whole(p.net_income),
                _money_k(p.expenses),
                _money_k(p.savings_contribution),
                _money_k(p.investment_growth),
                _money_whole(p.net_worth),
                style=style,
            )

    console.print(table)

    # Summary panel — three columns: outcomes | income changes | key assumptions
    left: list[str] = []
    left.append(f"Peak net worth:     {_money_whole(summary.peak_net_worth)}")
    left.append(f"Final net worth:    {_money_whole(summary.final_net_worth)}")
    if summary.fire_age is not None:
        left.append(f"FIRE age (4% rule): {summary.fire_age}")
    else:
        left.append("FIRE age:           not reached")

    mid: list[str] = []
    mid.append("Income changes (in future $):")
    mid.append(f"  Age {config.current_age}: {_money_whole(config.yearly_salary)}/yr (start)")
    if transition_ages:
        for p in summary.projections:
            if p.age in transition_ages:
                if p.income == 0:
                    desc = "fully retired"
                else:
                    desc = f"salary \u2192 {_money_whole(p.income)}/yr"
                mid.append(f"  Age {p.age}: {desc}")
    if not transition_ages:
        mid.append("  (none)")

    def _pct1(v: Decimal) -> str:
        return f"{v:.1f}%"

    right: list[str] = []
    right.append("Key assumptions:")
    right.append(f"  Annual return:   {_pct1(config.annual_return_pct)}")
    right.append(f"  Inflation:       {_pct1(config.inflation_pct)}")
    right.append(f"  Salary growth:   {_pct1(config.salary_growth_pct)}")
    right.append(f"  Life expectancy: {config.life_expectancy}")

    # Pad all columns to equal height
    height = max(len(left), len(mid), len(right))
    left  += [""] * (height - len(left))
    mid   += [""] * (height - len(mid))
    right += [""] * (height - len(right))

    grid = Table.grid(padding=(0, 4), expand=True)
    grid.add_column()
    grid.add_column()
    grid.add_column()
    for l, m, r in zip(left, mid, right):
        grid.add_row(l, m, r)

    console.print(Panel(grid, title="Summary"))


# --- Portfolio ---

def render_holdings(portfolio: Portfolio) -> None:
    if not portfolio.holdings:
        console.print("[dim]No holdings yet. Use 'portfolio add' to add one.[/dim]")
        return

    table = Table(title="Holdings (Book Value)")
    table.add_column("Ticker")
    table.add_column("Date")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Book Value", justify="right")

    for h in portfolio.holdings:
        book = h.quantity * h.purchase_price
        table.add_row(
            h.ticker,
            str(h.purchase_date),
            str(h.quantity),
            _money(h.purchase_price),
            _money(book),
        )

    console.print(table)


def render_portfolio_summary(summary: PortfolioSummary) -> None:
    table = Table(title="Portfolio Valuation")
    table.add_column("Ticker")
    table.add_column("Date")
    table.add_column("Qty", justify="right")
    table.add_column("Book", justify="right")
    table.add_column("Market", justify="right")
    table.add_column("Gain/Loss", justify="right")
    table.add_column("G/L %", justify="right")

    for v in summary.valuations:
        table.add_row(
            v.holding.ticker,
            str(v.holding.purchase_date),
            str(v.holding.quantity),
            _money(v.book_value),
            _money(v.market_value),
            _colored_money(v.gain_loss),
            _colored_pct(v.gain_loss_pct),
        )

    console.print(table)
    console.print()
    console.print(Panel(
        f"Total book value:   {_money(summary.total_book_value)}\n"
        f"Total market value: {_money(summary.total_market_value)}\n"
        f"Total gain/loss:    {_money(summary.total_gain_loss)} ({_pct(summary.total_gain_loss_pct)})",
        title="Portfolio Summary",
    ))
