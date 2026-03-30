"""
ACB (Adjusted Cost Basis) tracker for Canadian capital gains tax.

Commands:
    import      — load transactions from a CSV file (primary input)
    add-vest    — manually record an RSU vesting event
    add-buy     — manually record a regular market purchase
    add-sell    — manually record a disposition (sale)
    show        — display current ACB pool for all tickers
    report      — show capital gains/losses for a tax year

All data is persisted to ~/.prospero/acb_ledger.json.
"""

import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from prospero.models.acb import StockTransaction, TransactionType
from prospero.services.acb_csv import parse_csv, parse_ms_activity_dir
from prospero.services.fx import get_rates_for_transactions
from prospero.services.acb_engine import acb_report, compute_acb_pools
from prospero.storage.store import load_acb_ledger, save_acb_ledger
from prospero.display.tables import render_acb_pools, render_capital_gains_report

app = typer.Typer(help="ACB tracker for Canadian capital gains tax")
console = Console()
err = Console(stderr=True)


def _parse_date(s: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        raise typer.BadParameter(f"Expected YYYY-MM-DD, got {s!r}")


def _price_cad(tx: "StockTransaction") -> str:
    """Return a formatted price/share string in CAD, falling back to USD if rate unavailable."""
    try:
        rates = get_rates_for_transactions([tx])
        rate = rates.get(tx.date)
        if rate is not None:
            cad = tx.price_per_share * rate
            return f"${cad:,.4f} CAD"
    except Exception:
        pass
    return f"${tx.price_per_share:,.4f} USD"


def _total_acb_cad(tx: "StockTransaction") -> str:
    """Return a formatted total ACB string (quantity × price) in CAD, falling back to USD."""
    try:
        rates = get_rates_for_transactions([tx])
        rate = rates.get(tx.date)
        if rate is not None:
            cad = tx.quantity * tx.price_per_share * rate
            return f"${cad:,.2f} CAD"
    except Exception:
        pass
    return f"${tx.quantity * tx.price_per_share:,.2f} USD"


def _compute_sell_acb_used(
    new_transactions: list[StockTransaction],
) -> dict[int, Decimal]:
    """
    Replay the existing ledger plus new_transactions and return a mapping of
    id(tx) -> total_acb_used_usd for every SELL in new_transactions.

    total_acb_used = shares_sold × (total_acb / total_shares) at time of sale.

    This lets the preview table show the ACB consumed for each sale before
    the import is committed.
    """
    ledger = load_acb_ledger()
    new_ids = {id(tx) for tx in new_transactions}
    all_txs = sorted(ledger.transactions + new_transactions, key=lambda t: t.date)

    pools: dict[str, tuple[Decimal, Decimal]] = {}  # ticker -> (shares, total_acb)
    result: dict[int, Decimal] = {}

    for tx in all_txs:
        shares, acb = pools.get(tx.ticker, (Decimal("0"), Decimal("0")))
        if tx.transaction_type in (TransactionType.OPENING, TransactionType.VEST, TransactionType.BUY):
            pools[tx.ticker] = (shares + tx.quantity, acb + tx.quantity * tx.price_per_share)
        elif tx.transaction_type == TransactionType.SELL:
            acb_used = (tx.quantity * acb / shares).quantize(Decimal("0.01")) if shares > 0 else Decimal("0")
            if id(tx) in new_ids:
                result[id(tx)] = acb_used
            pools[tx.ticker] = (shares - tx.quantity, acb - acb_used)

    return result


def _render_import_preview(transactions: list[StockTransaction]) -> None:
    """Print a summary table of transactions about to be imported."""
    console.print("[dim]Fetching Bank of Canada USD/CAD rates…[/dim]")
    try:
        fx_rates = get_rates_for_transactions(transactions)
    except Exception:
        fx_rates = {}

    sell_acb = _compute_sell_acb_used(transactions)

    table = Table(title=f"Preview — {len(transactions)} transaction(s)", expand=False)
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("Ticker")
    table.add_column("Quantity", justify="right")
    table.add_column("Price / Share (USD)", justify="right")
    table.add_column("ACB Used (USD)", justify="right")
    table.add_column("USD/CAD", justify="right")
    table.add_column("Price / Share (CAD)", justify="right")
    for tx in sorted(transactions, key=lambda t: t.date):
        rate = fx_rates.get(tx.date)
        rate_str = f"{rate:.4f}" if rate is not None else "—"
        cad_str = f"${tx.price_per_share * rate:,.4f}" if rate is not None else "—"
        acb_used = sell_acb.get(id(tx))
        acb_str = f"${acb_used:,.2f}" if acb_used is not None else "—"
        table.add_row(
            str(tx.date),
            tx.transaction_type.value,
            tx.ticker,
            str(tx.quantity),
            f"${tx.price_per_share:,.4f}",
            acb_str,
            rate_str,
            cad_str,
        )
    console.print(table)


@app.command("import")
def import_csv(
    file: Path = typer.Option(..., "--file", help="Path to CSV file (date,type,ticker,quantity,price)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be imported without saving"),
) -> None:
    """
    Import transactions from a CSV file.

    Expected columns: date, type, ticker, quantity, price
      date      YYYY-MM-DD
      type      vest / buy / sell  (case-insensitive)
      ticker    e.g. AAPL
      quantity  number of shares (positive)
      price     price per share — FMV for vest, purchase price for buy, proceeds for sell

    The file is validated fully before anything is written. All errors are reported
    at once so you can fix your CSV in a single pass.
    """
    if not file.exists():
        err.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    try:
        transactions = parse_csv(file)
    except ValueError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if not transactions:
        console.print("[dim]No transactions found in file.[/dim]")
        return

    _render_import_preview(transactions)

    if dry_run:
        console.print("[dim]Dry run — nothing saved.[/dim]")
        return

    ledger = load_acb_ledger()
    ledger.transactions.extend(transactions)
    save_acb_ledger(ledger)
    console.print(f"[green]Imported {len(transactions)} transaction(s).[/green]")


@app.command("import-ms")
def import_ms(
    directory: Path = typer.Option(..., "--dir", help="Directory containing the unpacked MS Activity Report"),
    ticker: str = typer.Option(..., help="Ticker symbol for the stock (e.g. GOOG) — not present in MS files"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be imported without saving"),
) -> None:
    """
    Import from a Morgan Stanley Activity Report directory.

    Unpack the zip Morgan Stanley provides, then point --dir at the folder.
    Two files are read automatically:
      "Releases Net Shares Report.csv"  — RSU vesting events
      "Withdrawals Report.csv"          — sale events

    You must supply --ticker because MS files don't include the symbol.
    """
    if not directory.is_dir():
        err.print(f"[red]Not a directory: {directory}[/red]")
        raise typer.Exit(1)

    try:
        transactions = parse_ms_activity_dir(directory, ticker)
    except (FileNotFoundError, ValueError) as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if not transactions:
        console.print("[dim]No transactions found in MS activity report.[/dim]")
        return

    _render_import_preview(transactions)

    if dry_run:
        console.print("[dim]Dry run — nothing saved.[/dim]")
        return

    ledger = load_acb_ledger()
    ledger.transactions.extend(transactions)
    save_acb_ledger(ledger)
    console.print(f"[green]Imported {len(transactions)} transaction(s).[/green]")


@app.command("add-opening-balance")
def add_opening_balance(
    ticker: str = typer.Option(..., help="Ticker symbol (e.g. GOOG)"),
    date_str: str = typer.Option(..., "--date", help="Date of the opening balance (YYYY-MM-DD) — use the day before your first imported transaction"),
    shares: float = typer.Option(..., "--shares", help="Total shares held as of that date"),
    opening_acb_usd: float = typer.Option(..., "--opening-acb-usd", help="Total adjusted cost basis in USD (e.g. Acquisition Value from your broker's cost basis statement)"),
) -> None:
    """
    Seed the ACB pool with shares held before your transaction history begins.

    Use this when you held shares prior to your earliest imported activity report.
    Set --date to just before your first imported transaction (e.g. 2024-12-31).
    Get the values from your broker's cost basis statement or account page.
    """
    tx = StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.OPENING,
        date=_parse_date(date_str),
        quantity=Decimal(str(shares)),
        price_per_share=Decimal(str(opening_acb_usd)) / Decimal(str(shares)),
    )
    ledger = load_acb_ledger()
    ledger.transactions.append(tx)
    save_acb_ledger(ledger)
    console.print(
        f"[green]Opening balance: {tx.quantity} {tx.ticker} — total ACB {_total_acb_cad(tx)} on {tx.date}[/green]"
    )


@app.command("add-vest")
def add_vest(
    ticker: str = typer.Option(..., help="Ticker symbol (e.g. AAPL)"),
    date_str: str = typer.Option(..., "--date", help="Vest date (YYYY-MM-DD)"),
    quantity: float = typer.Option(..., help="Number of shares vested"),
    fmv: float = typer.Option(..., "--fmv", help="Fair market value per share at vest date"),
) -> None:
    """
    Record an RSU vesting event.

    The FMV at vest becomes the ACB because CRA treats the vesting benefit as
    employment income (reported on your T4) — so there is no additional income
    to recognise when you eventually sell. Only appreciation *after* vesting
    becomes a capital gain.
    """
    tx = StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.VEST,
        date=_parse_date(date_str),
        quantity=Decimal(str(quantity)),
        price_per_share=Decimal(str(fmv)),
    )
    ledger = load_acb_ledger()
    ledger.transactions.append(tx)
    save_acb_ledger(ledger)
    console.print(
        f"[green]Vested {tx.quantity} {tx.ticker} @ {_price_cad(tx)} on {tx.date} "
        f"(ACB = FMV)[/green]"
    )


@app.command("add-buy")
def add_buy(
    ticker: str = typer.Option(..., help="Ticker symbol"),
    date_str: str = typer.Option(..., "--date", help="Purchase date (YYYY-MM-DD)"),
    quantity: float = typer.Option(..., help="Number of shares purchased"),
    price: float = typer.Option(..., "--price", help="Purchase price per share"),
) -> None:
    """Record a regular market purchase. Adds shares to the ACB pool at the purchase price."""
    tx = StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.BUY,
        date=_parse_date(date_str),
        quantity=Decimal(str(quantity)),
        price_per_share=Decimal(str(price)),
    )
    ledger = load_acb_ledger()
    ledger.transactions.append(tx)
    save_acb_ledger(ledger)
    console.print(
        f"[green]Bought {tx.quantity} {tx.ticker} @ {_price_cad(tx)} on {tx.date}[/green]"
    )


@app.command("add-sell")
def add_sell(
    ticker: str = typer.Option(..., help="Ticker symbol"),
    date_str: str = typer.Option(..., "--date", help="Sale date (YYYY-MM-DD)"),
    quantity: float = typer.Option(..., help="Number of shares sold"),
    price: float = typer.Option(..., "--price", help="Proceeds per share"),
) -> None:
    """
    Record a disposition (sale).

    The capital gain or loss is determined when you run `prospero acb report`.
    This command validates that you hold enough shares before saving.
    """
    tx = StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.SELL,
        date=_parse_date(date_str),
        quantity=Decimal(str(quantity)),
        price_per_share=Decimal(str(price)),
    )
    ledger = load_acb_ledger()

    # Validate the sell against the current pool before committing to disk
    try:
        compute_acb_pools(ledger.transactions + [tx])
    except ValueError as e:
        err.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    ledger.transactions.append(tx)
    save_acb_ledger(ledger)
    console.print(
        f"[green]Sold {tx.quantity} {tx.ticker} @ {_price_cad(tx)} on {tx.date}[/green]"
    )


@app.command("show")
def show() -> None:
    """Show the current ACB pool for all tickers (shares held and average cost basis)."""
    ledger = load_acb_ledger()
    if not ledger.transactions:
        console.print("[dim]No transactions recorded yet. Use 'prospero acb import' to get started.[/dim]")
        return
    try:
        pools = compute_acb_pools(ledger.transactions)
    except ValueError as e:
        err.print(f"[red]Error: {e}[/red]")
        err.print("[yellow]Tip: this usually means transactions from a prior year are missing from the ledger. Import earlier activity reports first.[/yellow]")
        raise typer.Exit(1)
    if not pools:
        console.print("[dim]No current holdings — all positions have been closed.[/dim]")
        return
    render_acb_pools(pools)


@app.command("report")
def report(
    year: Optional[int] = typer.Option(
        None,
        "--year",
        help="Tax year to report on (defaults to the previous calendar year)",
    ),
) -> None:
    """
    Show capital gains and losses for a tax year.

    Defaults to the previous calendar year — the one you are most likely filing.
    Also shows your current ACB pools so you can see what carries forward.
    Automatically fetches Bank of Canada USD/CAD rates to show CAD amounts.
    """
    target_year = year or (datetime.date.today().year - 1)
    ledger = load_acb_ledger()
    if not ledger.transactions:
        console.print("[dim]No transactions recorded yet. Use 'prospero acb import' to get started.[/dim]")
        return

    # Fetch Bank of Canada FX rates for all transaction dates
    fx_rates = None
    try:
        console.print("[dim]Fetching Bank of Canada USD/CAD rates…[/dim]")
        fx_rates = get_rates_for_transactions(ledger.transactions)
    except Exception as e:
        err.print(f"[yellow]Could not fetch FX rates ({e}). Showing USD only.[/yellow]")

    try:
        pools, gains, total_taxable_usd, total_taxable_cad = acb_report(
            ledger.transactions, target_year, fx_rates
        )
    except ValueError as e:
        err.print(f"[red]Error: {e}[/red]")
        err.print("[yellow]Tip: this usually means transactions from a prior year are missing from the ledger. Import earlier activity reports first.[/yellow]")
        raise typer.Exit(1)
    render_capital_gains_report(gains, target_year, total_taxable_usd, total_taxable_cad)
    if pools:
        console.print()
        render_acb_pools(pools)
