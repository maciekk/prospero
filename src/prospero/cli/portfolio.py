from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from prospero.models.portfolio import Holding
from prospero.services.market_data import get_current_prices, MarketDataError
from prospero.services.portfolio_engine import valuate
from prospero.storage.store import load_portfolio, save_portfolio
from prospero.display.tables import render_holdings, render_portfolio_summary
from prospero.cli._options import PDF_OPTION

app = typer.Typer(help="Stock portfolio tracker")
console = Console()


@app.command()
def add(
    ticker: str = typer.Option(..., help="Stock ticker symbol (e.g. AAPL)"),
    purchase_date: str = typer.Option(..., "--date", help="Purchase date (YYYY-MM-DD)"),
    quantity: float = typer.Option(..., help="Number of shares"),
    price: float = typer.Option(..., help="Purchase price per share"),
) -> None:
    """Add a stock holding to the portfolio."""
    holding = Holding(
        ticker=ticker.upper(),
        purchase_date=date.fromisoformat(purchase_date),
        quantity=Decimal(str(quantity)),
        purchase_price=Decimal(str(price)),
    )
    portfolio = load_portfolio()
    portfolio.holdings.append(holding)
    save_portfolio(portfolio)
    console.print(
        f"[green]Added {holding.quantity} shares of {holding.ticker} "
        f"@ ${holding.purchase_price} on {holding.purchase_date}[/green]"
    )


@app.command()
def remove(
    ticker: str = typer.Option(..., help="Stock ticker symbol"),
    purchase_date: Optional[str] = typer.Option(None, "--date", help="Purchase date to match (YYYY-MM-DD)"),
) -> None:
    """Remove holding(s) from the portfolio."""
    portfolio = load_portfolio()
    ticker = ticker.upper()
    before = len(portfolio.holdings)

    portfolio.holdings = [
        h for h in portfolio.holdings
        if not (
            h.ticker == ticker
            and (purchase_date is None or h.purchase_date == date.fromisoformat(purchase_date))
        )
    ]

    removed = before - len(portfolio.holdings)
    if removed == 0:
        console.print(f"[yellow]No matching holdings found for {ticker}[/yellow]")
    else:
        save_portfolio(portfolio)
        console.print(f"[green]Removed {removed} holding(s) for {ticker}[/green]")


@app.command()
def show(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON instead of a table."),
) -> None:
    """List all holdings with book values."""
    portfolio = load_portfolio()
    if output_json:
        typer.echo(portfolio.model_dump_json(indent=2))
    else:
        render_holdings(portfolio)


@app.command()
def value(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON instead of a table."),
    output_pdf: Optional[Path] = PDF_OPTION,
) -> None:
    """Fetch live prices and show full portfolio valuation."""
    portfolio = load_portfolio()
    if not portfolio.holdings:
        console.print("[dim]No holdings yet. Use 'portfolio add' to add one.[/dim]")
        raise typer.Exit()

    tickers = list({h.ticker for h in portfolio.holdings})
    try:
        console.print(f"[dim]Fetching prices for {', '.join(tickers)}...[/dim]")
        prices = get_current_prices(tickers)
    except MarketDataError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    summary = valuate(portfolio, prices)
    if output_json:
        typer.echo(summary.model_dump_json(indent=2))
    else:
        render_portfolio_summary(summary)
    if output_pdf is not None:
        from prospero.display.pdf import pdf_portfolio_summary
        pdf_portfolio_summary(summary, output_pdf)
        console.print(f"[dim]PDF saved to {output_pdf}[/dim]")
