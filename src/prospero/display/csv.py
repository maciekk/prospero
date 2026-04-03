"""CSV export functions for ACB commands."""

import csv
from decimal import Decimal
from pathlib import Path
from typing import Optional

from prospero.models.acb import AcbPoolEntry, CapitalGainEntry, StockTransaction, TransactionType


def csv_import_preview(
    transactions: list[StockTransaction],
    path: Path,
    fx_rates: dict,
    acb_used_cad_map: dict,
    pool_units_after_map: dict,
    pool_acb_cad_after_map: dict,
) -> None:
    """Write import preview data to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date", "type", "ticker", "net_units", "total_units_after",
            "price_usd", "exchange_rate_usd_cad", "acb_used_cad", "total_acb_cad_after",
        ])
        for tx in sorted(transactions, key=lambda t: t.date):
            rate = fx_rates.get(tx.date)
            is_sell = tx.transaction_type == TransactionType.SELL
            net_units = f"-{tx.quantity}" if is_sell else str(tx.quantity)
            acb_used = acb_used_cad_map.get(id(tx))
            pool_units = pool_units_after_map.get(id(tx))
            pool_acb = pool_acb_cad_after_map.get(id(tx))
            writer.writerow([
                str(tx.date),
                tx.transaction_type.value,
                tx.ticker,
                net_units,
                str(pool_units) if pool_units is not None else "",
                str(tx.price_per_share),
                str(rate) if rate is not None else "",
                str(acb_used) if acb_used is not None else "",
                str(pool_acb) if pool_acb is not None else "",
            ])


def csv_capital_gains_report(
    gains: list[CapitalGainEntry],
    year: int,
    path: Path,
    total_taxable_cad: Optional[Decimal] = None,
    pools: Optional[dict[str, AcbPoolEntry]] = None,
    pools_title: str = "Year End Holdings & Cost Basis",
) -> None:
    """Write capital gains report (and optionally ACB pools) to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Capital gains section
        writer.writerow([f"Capital Gains / Losses - {year}"])
        writer.writerow([
            "date", "ticker", "shares_sold", "proceeds_usd",
            "exchange_rate_usd_cad", "proceeds_cad", "acb_used_cad",
            "capital_gain_cad", "taxable_gain_cad",
        ])
        for g in gains:
            writer.writerow([
                str(g.date),
                g.ticker,
                str(g.shares_sold),
                str(g.proceeds),
                str(g.exchange_rate) if g.exchange_rate is not None else "",
                str(g.proceeds_cad) if g.proceeds_cad is not None else "",
                str(g.acb_used) if g.acb_used is not None else "",
                str(g.capital_gain) if g.capital_gain is not None else "",
                str(g.taxable_gain) if g.taxable_gain is not None else "",
            ])
        writer.writerow(["", "", "", "", "", "", "", "Total Taxable (CAD)",
                         str(total_taxable_cad) if total_taxable_cad is not None else ""])

        if pools:
            writer.writerow([])
            writer.writerow([pools_title])
            writer.writerow(["ticker", "shares", "total_acb_cad", "acb_per_share_cad"])
            for p in pools.values():
                writer.writerow([
                    p.ticker,
                    str(p.shares),
                    str(p.total_acb) if p.total_acb is not None else "",
                    str(p.acb_per_share) if p.acb_per_share is not None else "",
                ])
