from decimal import Decimal

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from prospero.models.acb import AcbPoolEntry, CapitalGainEntry
from prospero.models.planner import PlannerConfig, PlanSummary
from prospero.models.portfolio import PortfolioSummary, HoldingValuation, Portfolio
from prospero.services.tax import TaxBreakdown

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
    table.add_column("Expenses",  justify="right", ratio=7)
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
        left.append(f"[yellow]FIRE[/yellow] age (4% rule): {summary.fire_age}")
    else:
        left.append("[yellow]FIRE[/yellow] age:           not reached")

    mid: list[str] = []
    mid.append("Income [magenta]changes[/magenta] (in FUTURE $):")
    mid.append(f"  Age {config.current_age}: {_money_whole(config.yearly_salary)}/yr (start)")
    if transition_ages:
        for p in summary.projections:
            if p.age in transition_ages:
                if p.income == 0:
                    desc = "fully [cyan]retired[/cyan]"
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


def render_tax_breakdown(breakdown: TaxBreakdown) -> None:
    def _pct_of_income(value: Decimal) -> str:
        if breakdown.income == 0:
            return "  —  "
        return f"{value / breakdown.income * 100:.1f}%"

    table = Table(
        title=f"Tax breakdown for {_money_whole(breakdown.income)} income\n(2025 base rates, ON)",
        show_header=True,
        show_lines=False,
        expand=False,
    )
    table.add_column("Component", ratio=5)
    table.add_column("Amount", justify="right", ratio=3)
    table.add_column("% of gross", justify="right", ratio=2)

    def row(label: str, value: Decimal, style: str | None = None) -> None:
        table.add_row(label, _money_whole(value), _pct_of_income(value), style=style)

    row("Federal income tax", breakdown.federal)
    row("Ontario income tax", breakdown.ontario_base)
    if breakdown.ontario_surtax > 0:
        row("  └─ surtax", breakdown.ontario_surtax, style="dim")
    row("CPP1", breakdown.cpp1)
    if breakdown.cpp2 > 0:
        row("CPP2", breakdown.cpp2)
    row("EI", breakdown.ei)
    table.add_section()
    row("Total deductions", breakdown.total, style="bold")
    row("Take-home", breakdown.take_home, style="bold green")

    console.print(table)


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


def render_acb_pools(pools: dict[str, AcbPoolEntry]) -> None:
    """Render a table of current ACB pools — one row per ticker with remaining shares."""
    table = Table(title="Current ACB Pools", expand=False)
    table.add_column("Ticker")
    table.add_column("Shares", justify="right")
    table.add_column("ACB / Share", justify="right")
    table.add_column("Total ACB", justify="right")

    for entry in sorted(pools.values(), key=lambda e: e.ticker):
        table.add_row(
            entry.ticker,
            str(entry.shares),
            _money(entry.acb_per_share),
            _money(entry.total_acb),
        )

    console.print(table)


def render_capital_gains_report(
    gains: list[CapitalGainEntry],
    year: int,
    total_taxable_usd: Decimal,
    total_taxable_cad: Decimal | None = None,
) -> None:
    """
    Render a capital gains/losses report for a tax year.

    Shows one row per disposition, coloured green (gain) or red (loss), followed by
    a summary panel with totals and Canadian tax notes. When CAD fields are present
    on the gain entries, CAD columns are shown alongside USD.
    """
    if not gains:
        console.print(f"[dim]No dispositions recorded for {year}.[/dim]")
        return

    has_cad = any(g.capital_gain_cad is not None for g in gains)

    table = Table(title=f"Capital Gains / Losses — {year}", expand=False)
    table.add_column("Date")
    table.add_column("Ticker")
    table.add_column("Shares Sold", justify="right")
    table.add_column("Proceeds (USD)", justify="right")
    table.add_column("ACB Used (USD)", justify="right")
    table.add_column("Gain / Loss (USD)", justify="right")
    table.add_column("Taxable USD", justify="right")
    if has_cad:
        table.add_column("Rate", justify="right")
        table.add_column("Gain / Loss (CAD)", justify="right")
        table.add_column("Taxable CAD", justify="right")

    for g in sorted(gains, key=lambda e: e.date):
        row = [
            str(g.date),
            g.ticker,
            str(g.shares_sold),
            _money(g.proceeds),
            _money(g.acb_used),
            _colored_money(g.capital_gain),
            _colored_money(g.taxable_gain),
        ]
        if has_cad:
            rate_str = f"{g.exchange_rate:.4f}" if g.exchange_rate else "—"
            row.append(rate_str)
            row.append(_colored_money(g.capital_gain_cad) if g.capital_gain_cad is not None else "—")
            row.append(_colored_money(g.taxable_gain_cad) if g.taxable_gain_cad is not None else "—")
        table.add_row(*row)

    console.print(table)
    console.print()

    total_gain_usd = sum((g.capital_gain for g in gains), Decimal("0"))
    summary_color = "green" if total_gain_usd >= 0 else "red"

    lines = [
        f"Total capital gain / loss (USD):  {_money(total_gain_usd)}",
        f"Taxable amount 50% (USD):         {_money(total_taxable_usd)}",
    ]
    if has_cad and total_taxable_cad is not None:
        total_gain_cad = sum((g.capital_gain_cad for g in gains if g.capital_gain_cad is not None), Decimal("0"))
        lines += [
            f"Total capital gain / loss (CAD):  {_money(total_gain_cad)}",
            f"Taxable amount 50% (CAD):         {_money(total_taxable_cad)}",
            "[dim]Rates: Bank of Canada daily USD/CAD (weekends/holidays use prior business day)[/dim]",
        ]
    lines += [
        "",
        "[dim]The 50% inclusion rate applies to net capital gains for 2024.[/dim]",
        "[dim]Capital losses can offset gains in the same year, be carried back[/dim]",
        "[dim]3 years (T1A), or carried forward indefinitely.[/dim]",
        "[dim]Superficial loss rule: a loss may be denied if you repurchase the[/dim]",
        "[dim]same security within 30 days before or after the sale.[/dim]",
        "[dim italic]For reference only — not professional tax advice.[/dim italic]",
    ]

    console.print(Panel(
        "\n".join(lines),
        title=f"[{summary_color}]Tax Year {year} Summary (Canada — ON)[/{summary_color}]",
    ))
