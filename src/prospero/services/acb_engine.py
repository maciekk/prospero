"""
ACB (Adjusted Cost Basis) calculation engine for Canadian capital gains tax.

Canada uses the **identical-shares average cost method** (ITA s.47): all shares of
the same ticker form a single ACB pool. The pool tracks (total_shares, total_acb),
and the per-share ACB is always total_acb / total_shares.

Key rules encoded here:
  - VEST/BUY acquisition: add shares at cost to the pool (FMV for RSU vests, which
    equals ACB since the employment benefit is already reported on your T4).
  - SELL disposition: ACB used = shares_sold * (total_acb / total_shares).
    The *proceeds* price has no effect on the pool — only ACB_used is removed.
  - Capital gain = proceeds - ACB_used.
  - 50% inclusion rate: only half of net capital gains are added to taxable income.
  - Cross-year accuracy: to get the correct ACB at the moment of any sale, we must
    replay ALL prior transactions regardless of which tax year we're reporting on.
    The functions here always replay the full ledger and filter output by year.

All functions are pure (no I/O, no side effects).
"""

from decimal import ROUND_HALF_UP, Decimal

from prospero.models.acb import (
    AcbPoolEntry,
    CapitalGainEntry,
    StockTransaction,
    TransactionType,
)

# 50% capital gains inclusion rate (CRA 2024 for most taxpayers)
_INCLUSION_RATE = Decimal("0.50")

# Intermediate precision for per-share calculations to avoid accumulating rounding error
_EIGHT_PLACES = Decimal("0.00000001")

# Final precision for monetary amounts
_TWO_PLACES = Decimal("0.01")


def _sorted_txs(transactions: list[StockTransaction]) -> list[StockTransaction]:
    """Return transactions sorted by date (oldest first). Stable sort preserves insertion order for same-day events."""
    return sorted(transactions, key=lambda t: t.date)


def compute_acb_pools(transactions: list[StockTransaction]) -> dict[str, AcbPoolEntry]:
    """
    Replay all transactions in chronological order and return the **current** ACB pool
    for each ticker that still has shares remaining.

    Tickers where all shares have been sold are excluded from the result.

    Raises ValueError if a SELL transaction exceeds the shares currently held.
    """
    # pools[ticker] = (total_shares, total_acb)
    pools: dict[str, tuple[Decimal, Decimal]] = {}

    for tx in _sorted_txs(transactions):
        shares, acb = pools.get(tx.ticker, (Decimal("0"), Decimal("0")))

        if tx.transaction_type in (TransactionType.VEST, TransactionType.BUY):
            # Add shares to pool at their acquisition cost.
            # For RSU vests: FMV at vest == ACB because the employment benefit was
            # already included in your T4 income — no additional income on eventual sale.
            new_shares = shares + tx.quantity
            new_acb = acb + tx.quantity * tx.price_per_share
            pools[tx.ticker] = (new_shares, new_acb)

        elif tx.transaction_type == TransactionType.SELL:
            if shares == 0:
                raise ValueError(
                    f"Cannot sell {tx.ticker} on {tx.date}: no shares currently held."
                )
            if tx.quantity > shares:
                raise ValueError(
                    f"Cannot sell {tx.quantity} shares of {tx.ticker} on {tx.date}: "
                    f"only {shares} shares held."
                )

            # Remove the proportional ACB from the pool.
            # IMPORTANT: the proceeds price is irrelevant to pool accounting.
            # Only the ACB removed (acb_used) affects the remaining pool.
            acb_per_share = acb / shares
            acb_used = (tx.quantity * acb_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
            pools[tx.ticker] = (shares - tx.quantity, acb - acb_used)

    result: dict[str, AcbPoolEntry] = {}
    for ticker, (shares, total_acb) in pools.items():
        if shares > 0:
            acb_per_share = (total_acb / shares).quantize(_EIGHT_PLACES, ROUND_HALF_UP)
            result[ticker] = AcbPoolEntry(
                ticker=ticker,
                shares=shares,
                total_acb=total_acb.quantize(_TWO_PLACES, ROUND_HALF_UP),
                acb_per_share=acb_per_share,
            )

    return result


def compute_capital_gains(
    transactions: list[StockTransaction],
    year: int,
) -> list[CapitalGainEntry]:
    """
    Replay the **full** transaction history and return one CapitalGainEntry for every
    SELL event that falls within the requested tax year.

    Why replay all years? The ACB at the moment of any sale depends on all prior
    acquisitions and dispositions, even those from earlier years. For example, if you
    sold half your position in 2023, the 2024 sale must use the ACB of the remaining
    half — not the original full-position ACB. Replaying everything ensures correctness.

    Returns an empty list if there are no dispositions in the requested year.
    """
    gains: list[CapitalGainEntry] = []
    pools: dict[str, tuple[Decimal, Decimal]] = {}

    for tx in _sorted_txs(transactions):
        shares, acb = pools.get(tx.ticker, (Decimal("0"), Decimal("0")))

        if tx.transaction_type in (TransactionType.VEST, TransactionType.BUY):
            pools[tx.ticker] = (shares + tx.quantity, acb + tx.quantity * tx.price_per_share)

        elif tx.transaction_type == TransactionType.SELL:
            acb_per_share = acb / shares
            acb_used = (tx.quantity * acb_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
            proceeds = (tx.quantity * tx.price_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
            capital_gain = proceeds - acb_used
            taxable_gain = (capital_gain * _INCLUSION_RATE).quantize(_TWO_PLACES, ROUND_HALF_UP)

            # Update pool regardless of year — must stay accurate for future sells
            pools[tx.ticker] = (shares - tx.quantity, acb - acb_used)

            # Only emit an entry for the requested tax year
            if tx.date.year == year:
                gains.append(
                    CapitalGainEntry(
                        date=tx.date,
                        ticker=tx.ticker,
                        shares_sold=tx.quantity,
                        proceeds=proceeds,
                        acb_used=acb_used,
                        capital_gain=capital_gain,
                        taxable_gain=taxable_gain,
                    )
                )

    return gains


def acb_report(
    transactions: list[StockTransaction],
    year: int,
) -> tuple[dict[str, AcbPoolEntry], list[CapitalGainEntry], Decimal]:
    """
    Compute the full ACB report for a tax year.

    Returns:
        pools          — current ACB pool for all tickers with remaining shares
        gains          — one CapitalGainEntry per disposition in the requested year
        total_taxable  — sum of all taxable_gain entries (losses reduce the total)

    Note: total_taxable can be negative if losses exceed gains. Capital losses can be
    applied against capital gains in the same year, carried back 3 years, or carried
    forward indefinitely (CRA T1A form).
    """
    pools = compute_acb_pools(transactions)
    gains = compute_capital_gains(transactions, year)
    total_taxable = sum(
        (g.taxable_gain for g in gains), Decimal("0")
    ).quantize(_TWO_PLACES, ROUND_HALF_UP)
    return pools, gains, total_taxable
