from decimal import Decimal

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from fin_sim.models.planner import PlanSummary
from fin_sim.models.portfolio import PortfolioSummary, HoldingValuation, Portfolio

console = Console()


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


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

def render_plan_summary(summary: PlanSummary, every_n: int = 5) -> None:
    table = Table(title="Wealth Projection (ON, Canada)", show_lines=False)
    table.add_column("Age", justify="right")
    table.add_column("Year", justify="right")
    table.add_column("Gross", justify="right")
    table.add_column("Tax", justify="right")
    table.add_column("Net Inc", justify="right")
    table.add_column("Expenses", justify="right")
    table.add_column("Saved", justify="right")
    table.add_column("Growth", justify="right")
    table.add_column("Net Worth", justify="right")

    # Find retirement year (first year with zero income after having income)
    retirement_age: int | None = None
    for j, p in enumerate(summary.projections):
        if j > 0 and p.income == 0 and summary.projections[j - 1].income > 0:
            retirement_age = p.age
            break

    for i, p in enumerate(summary.projections):
        is_fire_year = summary.fire_age is not None and p.age == summary.fire_age
        is_retirement_year = retirement_age is not None and p.age == retirement_age
        show = (i == 0 or i == len(summary.projections) - 1
                or i % every_n == 0 or is_fire_year or is_retirement_year)
        if show:
            if is_retirement_year:
                style = "bold cyan"
            elif is_fire_year:
                style = "bold yellow"
            else:
                style = None
            table.add_row(
                str(p.age),
                str(p.year),
                _money(p.income),
                _money(p.taxes),
                _money(p.net_income),
                _money(p.expenses),
                _money(p.savings_contribution),
                _money(p.investment_growth),
                _money(p.net_worth),
                style=style,
            )

    console.print(table)

    # Summary panel
    lines = [f"Peak net worth: {_money(summary.peak_net_worth)}"]
    lines.append(f"Final net worth: {_money(summary.final_net_worth)}")
    if summary.fire_age is not None:
        lines.append(f"FIRE age (4% rule): {summary.fire_age}")
    else:
        lines.append("FIRE age: not reached")
    if retirement_age is not None:
        lines.append(f"Retirement age: {retirement_age}")
    console.print(Panel("\n".join(lines), title="Summary"))


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
