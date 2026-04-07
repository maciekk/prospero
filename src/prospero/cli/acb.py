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
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from prospero.models.acb import StockTransaction, TransactionType
from prospero.services.acb_csv import parse_csv, parse_ms_activity_dir
from prospero.services.fx import get_rates_for_transactions
from prospero.services.acb_engine import (
    acb_report,
    compute_acb_pools,
    sanity_check_acb_pools,
    sanity_check_capital_gains,
)
from prospero.storage.store import load_acb_ledger, save_acb_ledger
from prospero.display.tables import render_acb_pools, render_capital_gains_report
from prospero.cli._options import CSV_OPTION, PDF_OPTION, print_run_header

app = typer.Typer(help="ACB tracker for Canadian capital gains tax")
console = Console()
err = Console(stderr=True)


@app.callback(invoke_without_command=True)
def _acb_callback(ctx: typer.Context) -> None:
    print_run_header()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _warn_sanity(violations: list[str], label: str) -> None:
    """Print a confirmation or loud error block depending on sanity-check results."""
    if not violations:
        console.print(f"[dim]Validated: {label}[/dim]")
        return
    err.print(f"\n[bold red]!! ACB SANITY CHECK FAILED ({label}) — results may be incorrect !![/bold red]")
    for v in violations:
        err.print(f"[red]  • {v}[/red]")
    err.print("[bold red]!! Please report this as a bug at https://github.com/mkalisiak/prospero/issues !![/bold red]\n")


def _json_default(obj: object) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


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
    if tx.transaction_type == TransactionType.OPENING:
        return f"${tx.quantity * tx.price_per_share:,.2f} CAD"
    try:
        rates = get_rates_for_transactions([tx])
        rate = rates.get(tx.date)
        if rate is not None:
            cad = tx.quantity * tx.price_per_share * rate
            return f"${cad:,.2f} CAD"
    except Exception:
        pass
    return f"${tx.quantity * tx.price_per_share:,.2f} USD"


def _compute_preview_data(
    new_transactions: list[StockTransaction],
) -> tuple[dict[int, Decimal | None], dict[int, Decimal], dict[int, Decimal | None]]:
    """
    Replay the existing ledger plus new_transactions and return three mappings
    keyed by id(tx) for every transaction in new_transactions:

        acb_used_cad:       CAD ACB consumed (SELL rows only; absent for other types),
                            or None if the FX rate for any prior acquisition is unavailable
        pool_units_after:   total shares held for that ticker after the transaction
        pool_acb_cad_after: total pool ACB (CAD) for that ticker after the transaction,
                            or None if any FX rate in the pool history is unavailable

    total_acb_used_cad = shares_sold × (total_acb_cad / total_shares) at time of sale.
    """
    ledger = load_acb_ledger()
    new_ids = {id(tx) for tx in new_transactions}
    all_txs = sorted(ledger.transactions + new_transactions, key=lambda t: t.date)

    try:
        fx_rates = get_rates_for_transactions(all_txs)
    except Exception:
        fx_rates = {}

    share_pools: dict[str, Decimal] = {}               # ticker -> total_shares
    cad_pools: dict[str, tuple[Decimal, Decimal]] = {}  # ticker -> (shares, total_acb_cad)
    cad_complete: dict[str, bool] = {}                  # True if all acquisitions had FX rates

    acb_used_cad: dict[int, Decimal | None] = {}
    pool_units_after: dict[int, Decimal] = {}
    pool_acb_cad_after: dict[int, Decimal | None] = {}

    for tx in all_txs:
        shares = share_pools.get(tx.ticker, Decimal("0"))
        cad_shares, cad_acb = cad_pools.get(tx.ticker, (Decimal("0"), Decimal("0")))
        complete = cad_complete.get(tx.ticker, True)
        rate = fx_rates.get(tx.date)

        if tx.transaction_type == TransactionType.OPENING:
            new_shares = shares + tx.quantity
            share_pools[tx.ticker] = new_shares
            cost_cad = tx.quantity * tx.price_per_share  # price_per_share is CAD/share for OPENING
            new_cad_acb = cad_acb + cost_cad
            cad_pools[tx.ticker] = (new_shares, new_cad_acb)
            cad_complete[tx.ticker] = complete
            if id(tx) in new_ids:
                pool_units_after[id(tx)] = new_shares
                pool_acb_cad_after[id(tx)] = new_cad_acb.quantize(Decimal("0.01"))

        elif tx.transaction_type in (TransactionType.VEST, TransactionType.BUY):
            cost_usd = tx.quantity * tx.price_per_share
            new_shares = shares + tx.quantity
            share_pools[tx.ticker] = new_shares
            if rate is not None:
                new_cad_acb = cad_acb + cost_usd * rate
            else:
                new_cad_acb = cad_acb
                complete = False
            cad_pools[tx.ticker] = (new_shares, new_cad_acb)
            cad_complete[tx.ticker] = complete
            if id(tx) in new_ids:
                pool_units_after[id(tx)] = new_shares
                pool_acb_cad_after[id(tx)] = new_cad_acb.quantize(Decimal("0.01")) if complete else None

        elif tx.transaction_type == TransactionType.SELL:
            new_shares = shares - tx.quantity
            share_pools[tx.ticker] = new_shares
            if cad_shares > 0 and complete:
                cad_used = (tx.quantity * cad_acb / cad_shares).quantize(Decimal("0.01"))
                new_cad_acb = cad_acb - cad_used
                cad_pools[tx.ticker] = (cad_shares - tx.quantity, new_cad_acb)
                if id(tx) in new_ids:
                    acb_used_cad[id(tx)] = cad_used
                    pool_units_after[id(tx)] = new_shares
                    pool_acb_cad_after[id(tx)] = new_cad_acb.quantize(Decimal("0.01"))
            else:
                cad_pools[tx.ticker] = (cad_shares - tx.quantity, cad_acb)
                if id(tx) in new_ids:
                    acb_used_cad[id(tx)] = None
                    pool_units_after[id(tx)] = new_shares
                    pool_acb_cad_after[id(tx)] = None

    return acb_used_cad, pool_units_after, pool_acb_cad_after


def _sanity_check_preview_data(
    transactions: list[StockTransaction],
    acb_used_cad_map: dict[int, Decimal | None],
    pool_units_after_map: dict[int, Decimal],
    pool_acb_cad_after_map: dict[int, Decimal | None],
) -> list[str]:
    """
    Verify the average-cost identity for every SELL in the preview:

        pool_acb_cad_after == acb_used_cad * pool_units_after / shares_sold

    This follows from: ACB_removed + ACB_remaining = ACB_before, where each
    piece is proportional to shares.  A mismatch means the preview's pool
    replay disagrees with its own ACB-used figure.
    """
    _TOL = Decimal("0.02")
    errors: list[str] = []
    for tx in transactions:
        if tx.transaction_type != TransactionType.SELL:
            continue
        acb_used = acb_used_cad_map.get(id(tx))
        pool_after = pool_acb_cad_after_map.get(id(tx))
        units_after = pool_units_after_map.get(id(tx))
        if acb_used is None or pool_after is None or units_after is None:
            continue  # FX rates unavailable — can't verify
        if units_after == 0:
            continue  # position closed; nothing to cross-check
        expected = (acb_used * units_after / tx.quantity).quantize(Decimal("0.01"), ROUND_HALF_UP)
        if abs(expected - pool_after) > _TOL:
            errors.append(
                f"{tx.date} {tx.ticker} SELL: pool_acb_after {pool_after} != "
                f"acb_used {acb_used} x units_after {units_after} / sold {tx.quantity} = {expected}"
            )
    return errors


def _render_import_preview(
    transactions: list[StockTransaction],
) -> tuple[dict, dict, dict, dict]:
    """Print a summary table of transactions about to be imported.

    Returns (fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map)
    so callers can reuse the data (e.g. for PDF output).
    """
    console.print("[dim]Fetching Bank of Canada USD/CAD rates…[/dim]")
    try:
        fx_rates = get_rates_for_transactions(transactions)
    except Exception:
        fx_rates = {}

    acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map = _compute_preview_data(transactions)
    _warn_sanity(
        _sanity_check_preview_data(transactions, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map),
        label=f"Preview — {len(transactions)} transaction(s)",
    )

    def _ch(label: str) -> Text:
        return Text(label, justify="center")

    table = Table(title=f"Preview — {len(transactions)} transaction(s)", expand=False)
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("Ticker")
    table.add_column(_ch("Net Units"), justify="right")
    table.add_column(_ch("Total\nUnits"), justify="right")
    table.add_column(_ch("Price\n(USD)"), justify="right")
    table.add_column(_ch("Exchange\n(USD/CAD)"), justify="right")
    table.add_column(_ch("ACB Used\n(CAD)"), justify="right")
    table.add_column(_ch("Total ACB\n(CAD)"), justify="right")
    for tx in sorted(transactions, key=lambda t: t.date):
        rate = fx_rates.get(tx.date)
        rate_str = f"{rate:.4f}" if rate is not None else "—"
        acb_used_cad = acb_used_cad_map.get(id(tx))
        acb_str = f"${acb_used_cad:,.2f}" if acb_used_cad is not None else "—"
        pool_units = pool_units_after_map.get(id(tx))
        units_str = str(pool_units) if pool_units is not None else "—"
        pool_acb_cad = pool_acb_cad_after_map.get(id(tx))
        cad_str = f"${pool_acb_cad:,.2f}" if pool_acb_cad is not None else "—"
        is_sell = tx.transaction_type == TransactionType.SELL
        qty_str = f"-{tx.quantity}" if is_sell else str(tx.quantity)
        price_str = (
            f"${tx.price_per_share:,.2f} CAD"
            if tx.transaction_type == TransactionType.OPENING
            else f"${tx.price_per_share:,.2f}"
        )
        table.add_row(
            str(tx.date),
            tx.transaction_type.value,
            tx.ticker,
            qty_str,
            units_str,
            price_str,
            rate_str,
            acb_str,
            cad_str,
        )
    console.print()
    console.print(table)
    return fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map


@app.command("import")
def import_csv(
    file: Path = typer.Option(..., "--file", help="Path to CSV file (date,type,ticker,quantity,price)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be imported without saving"),
    output_pdf: Optional[Path] = PDF_OPTION,
    output_csv: Optional[Path] = CSV_OPTION,
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

    preview_data = _render_import_preview(transactions)

    if dry_run:
        console.print("[dim]Dry run — nothing saved.[/dim]")
    else:
        ledger = load_acb_ledger()
        ledger.transactions.extend(transactions)
        save_acb_ledger(ledger)
        console.print(f"[green]Imported {len(transactions)} transaction(s).[/green]")

    if output_pdf is not None:
        from prospero.display.pdf import pdf_import_preview
        fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map = preview_data
        pdf_import_preview(transactions, output_pdf, fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map)
        console.print(f"[dim]PDF saved to {output_pdf}[/dim]")
    if output_csv is not None:
        from prospero.display.csv import csv_import_preview
        fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map = preview_data
        csv_import_preview(transactions, output_csv, fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map)
        console.print(f"[dim]CSV saved to {output_csv}[/dim]")


@app.command("import-ms")
def import_ms(
    directory: Path = typer.Option(..., "--dir", help="Directory containing the unpacked MS Activity Report"),
    ticker: str = typer.Option(..., help="Ticker symbol for the stock (e.g. GOOG) — not present in MS files"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be imported without saving"),
    output_pdf: Optional[Path] = PDF_OPTION,
    output_csv: Optional[Path] = CSV_OPTION,
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
        transactions, ms_warnings = parse_ms_activity_dir(directory, ticker)
    except (FileNotFoundError, ValueError) as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    for w in ms_warnings:
        err.print(f"[yellow]Warning: {w}[/yellow]")

    if not transactions:
        console.print("[dim]No transactions found in MS activity report.[/dim]")
        return

    preview_data = _render_import_preview(transactions)

    if dry_run:
        console.print("[dim]Dry run — nothing saved.[/dim]")
    else:
        ledger = load_acb_ledger()
        ledger.transactions.extend(transactions)
        save_acb_ledger(ledger)
        console.print(f"[green]Imported {len(transactions)} transaction(s).[/green]")

    if output_pdf is not None:
        from prospero.display.pdf import pdf_import_preview
        fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map = preview_data
        pdf_import_preview(transactions, output_pdf, fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map)
        console.print(f"[dim]PDF saved to {output_pdf}[/dim]")
    if output_csv is not None:
        from prospero.display.csv import csv_import_preview
        fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map = preview_data
        csv_import_preview(transactions, output_csv, fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map)
        console.print(f"[dim]CSV saved to {output_csv}[/dim]")


@app.command("add-opening-balance")
def add_opening_balance(
    ticker: str = typer.Option(..., help="Ticker symbol (e.g. GOOG)"),
    date_str: str = typer.Option(..., "--date", help="Date of the opening balance (YYYY-MM-DD) — use the day before your first imported transaction"),
    shares: float = typer.Option(..., "--shares", help="Total shares held as of that date"),
    opening_acb_cad: float = typer.Option(..., "--opening-acb-cad", help="Total adjusted cost basis in CAD (historical cost already converted at the rates when acquired)"),
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
        price_per_share=Decimal(str(opening_acb_cad)) / Decimal(str(shares)),
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
def show(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON instead of a table."),
    output_pdf: Optional[Path] = PDF_OPTION,
) -> None:
    """Show the current ACB pool for all tickers (shares held and average cost basis)."""
    ledger = load_acb_ledger()
    if not ledger.transactions:
        console.print("[dim]No transactions recorded yet. Use 'prospero acb import' to get started.[/dim]")
        return
    fx_rates = None
    try:
        console.print("[dim]Fetching Bank of Canada USD/CAD rates…[/dim]")
        fx_rates = get_rates_for_transactions(ledger.transactions)
    except Exception as e:
        err.print(f"[yellow]Could not fetch FX rates ({e}). CAD ACB will be unavailable.[/yellow]")
    try:
        pools = compute_acb_pools(ledger.transactions, fx_rates=fx_rates)
    except ValueError as e:
        err.print(f"[red]Error: {e}[/red]")
        err.print("[yellow]Tip: this usually means transactions from a prior year are missing from the ledger. Import earlier activity reports first.[/yellow]")
        raise typer.Exit(1)
    if not pools:
        console.print("[dim]No current holdings — all positions have been closed.[/dim]")
        return
    _warn_sanity(sanity_check_acb_pools(pools), label="Holdings & Cost Basis")
    if output_json:
        typer.echo(json.dumps([p.model_dump(mode="json") for p in pools], default=_json_default, indent=2))
    else:
        render_acb_pools(pools)
    if output_pdf is not None:
        from prospero.display.pdf import pdf_acb_pools
        pdf_acb_pools(pools, output_pdf)
        console.print(f"[dim]PDF saved to {output_pdf}[/dim]")


@app.command("report")
def report(
    year: Optional[int] = typer.Option(
        None,
        "--year",
        help="Tax year to report on (defaults to the previous calendar year)",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON instead of a table."),
    output_pdf: Optional[Path] = PDF_OPTION,
    output_csv: Optional[Path] = CSV_OPTION,
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
        pools, gains, total_taxable_cad = acb_report(
            ledger.transactions, target_year, fx_rates
        )
    except ValueError as e:
        err.print(f"[red]Error: {e}[/red]")
        err.print("[yellow]Tip: this usually means transactions from a prior year are missing from the ledger. Import earlier activity reports first.[/yellow]")
        raise typer.Exit(1)
    _warn_sanity(
        sanity_check_capital_gains(gains) + sanity_check_acb_pools(pools),
        label=f"Capital Gains / Losses — {target_year} & Year End Holdings & Cost Basis ({target_year})",
    )
    if output_json:
        typer.echo(json.dumps(
            {
                "year": target_year,
                "gains": [g.model_dump(mode="json") for g in gains],
                "holdings": [p.model_dump(mode="json") for p in pools],
                "total_taxable_cad": str(total_taxable_cad) if total_taxable_cad is not None else None,
            },
            default=_json_default,
            indent=2,
        ))
    else:
        render_capital_gains_report(gains, target_year, total_taxable_cad)
        if pools:
            console.print()
            render_acb_pools(pools, title=f"Year End Holdings & Cost Basis ({target_year})")
    if output_pdf is not None:
        from prospero.display.pdf import pdf_capital_gains_report
        pdf_capital_gains_report(
            gains, target_year, output_pdf,
            total_taxable_cad=total_taxable_cad,
            pools=pools if pools else None,
            pools_title=f"Year End Holdings & Cost Basis ({target_year})",
        )
        console.print(f"[dim]PDF saved to {output_pdf}[/dim]")
    if output_csv is not None:
        from prospero.display.csv import csv_capital_gains_report
        csv_capital_gains_report(
            gains, target_year, output_csv,
            total_taxable_cad=total_taxable_cad,
            pools=pools if pools else None,
            pools_title=f"Year End Holdings & Cost Basis ({target_year})",
        )
        console.print(f"[dim]CSV saved to {output_csv}[/dim]")
