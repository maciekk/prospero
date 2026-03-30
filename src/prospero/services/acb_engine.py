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


def compute_acb_pools(
    transactions: list[StockTransaction],
    as_of_year: int | None = None,
) -> dict[str, AcbPoolEntry]:
    """
    Replay all transactions in chronological order and return the ACB pool
    for each ticker that still has shares remaining.

    When as_of_year is provided, only transactions up to and including Dec 31
    of that year are replayed — useful for year-end snapshots in tax reports.
    Without it, the full history is replayed (current state).

    Tickers where all shares have been sold are excluded from the result.

    Raises ValueError if a SELL transaction exceeds the shares currently held.
    """
    # pools[ticker] = (total_shares, total_acb)
    pools: dict[str, tuple[Decimal, Decimal]] = {}

    filtered = [tx for tx in transactions if tx.date.year <= as_of_year] if as_of_year is not None else transactions
    for tx in _sorted_txs(filtered):
        shares, acb = pools.get(tx.ticker, (Decimal("0"), Decimal("0")))

        if tx.transaction_type in (TransactionType.OPENING, TransactionType.VEST, TransactionType.BUY):
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

        if tx.transaction_type in (TransactionType.OPENING, TransactionType.VEST, TransactionType.BUY):
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


def compute_capital_gains_cad(
    transactions: list[StockTransaction],
    year: int,
    fx_rates: dict,  # dict[date, Decimal] — date -> USD/CAD rate
) -> tuple[list[CapitalGainEntry], dict[str, tuple[Decimal, Decimal]]]:
    """
    Replay the full transaction history and return CapitalGainEntry objects for
    every SELL in `year`, with CAD fields populated using Bank of Canada rates.

    Why CAD ACB ≠ USD ACB × sell-date rate
    ----------------------------------------
    The CRA requires each acquisition to be converted to CAD at the rate on the
    *acquisition date*. Over time, many vests at different rates build up a CAD
    ACB pool that reflects historical exchange rates — not today's rate. When you
    sell, the CAD proceeds use the sell-date rate, but the CAD ACB used comes from
    that historically-built pool. The capital gain in CAD is therefore:

        proceeds_cad  = shares_sold × usd_price × sell_date_rate
        acb_used_cad  = shares_sold × (cad_acb_pool / shares)
        gain_cad      = proceeds_cad − acb_used_cad

    This function maintains a parallel CAD pool alongside the USD pool to compute
    this correctly.

    Transaction dates missing from fx_rates are skipped for CAD computation
    (the returned entry will have None CAD fields for those sells).

    Returns a tuple of (gains, final_cad_pools) where final_cad_pools maps ticker
    to (shares, total_acb_cad) — the CAD pool state after replaying all transactions.
    """
    gains: list[CapitalGainEntry] = []
    # USD pool: (total_shares, total_acb_usd)
    usd_pools: dict[str, tuple[Decimal, Decimal]] = {}
    # CAD pool: (total_shares, total_acb_cad) — parallel, same share counts
    cad_pools: dict[str, tuple[Decimal, Decimal]] = {}

    for tx in _sorted_txs(transactions):
        usd_shares, usd_acb = usd_pools.get(tx.ticker, (Decimal("0"), Decimal("0")))
        _, cad_acb = cad_pools.get(tx.ticker, (Decimal("0"), Decimal("0")))
        rate = fx_rates.get(tx.date)  # None if date not available

        if tx.transaction_type in (TransactionType.OPENING, TransactionType.VEST, TransactionType.BUY):
            cost_usd = tx.quantity * tx.price_per_share
            usd_pools[tx.ticker] = (usd_shares + tx.quantity, usd_acb + cost_usd)
            if rate is not None:
                cad_pools[tx.ticker] = (usd_shares + tx.quantity, cad_acb + cost_usd * rate)
            else:
                # No rate for this date — CAD pool gets a None sentinel so we know
                # the CAD values are incomplete. Store USD cost as fallback.
                cad_pools[tx.ticker] = (usd_shares + tx.quantity, cad_acb + cost_usd)

        elif tx.transaction_type == TransactionType.SELL:
            usd_acb_per_share = usd_acb / usd_shares
            usd_acb_used = (tx.quantity * usd_acb_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
            usd_proceeds = (tx.quantity * tx.price_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
            usd_gain = usd_proceeds - usd_acb_used
            usd_taxable = (usd_gain * _INCLUSION_RATE).quantize(_TWO_PLACES, ROUND_HALF_UP)

            usd_pools[tx.ticker] = (usd_shares - tx.quantity, usd_acb - usd_acb_used)
            cad_acb_per_share = cad_acb / usd_shares
            cad_acb_used = (tx.quantity * cad_acb_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
            cad_pools[tx.ticker] = (usd_shares - tx.quantity, cad_acb - cad_acb_used)

            if tx.date.year == year:
                # Populate CAD fields only if sell-date rate is available
                if rate is not None:
                    cad_proceeds = (usd_proceeds * rate).quantize(_TWO_PLACES, ROUND_HALF_UP)
                    cad_gain = cad_proceeds - cad_acb_used
                    cad_taxable = (cad_gain * _INCLUSION_RATE).quantize(_TWO_PLACES, ROUND_HALF_UP)
                else:
                    cad_proceeds = cad_gain = cad_taxable = None

                gains.append(CapitalGainEntry(
                    date=tx.date,
                    ticker=tx.ticker,
                    shares_sold=tx.quantity,
                    proceeds=usd_proceeds,
                    acb_used=usd_acb_used,
                    capital_gain=usd_gain,
                    taxable_gain=usd_taxable,
                    exchange_rate=rate,
                    proceeds_cad=cad_proceeds,
                    acb_used_cad=cad_acb_used,
                    capital_gain_cad=cad_gain,
                    taxable_gain_cad=cad_taxable,
                ))

    return gains, cad_pools


def acb_report(
    transactions: list[StockTransaction],
    year: int,
    fx_rates: dict | None = None,
) -> tuple[dict[str, AcbPoolEntry], list[CapitalGainEntry], Decimal, Decimal | None]:
    """
    Compute the full ACB report for a tax year.

    Pass fx_rates (dict[date, Decimal] from fx.get_rates_for_transactions) to get
    CAD-denominated values alongside USD values. When fx_rates is None, CAD fields
    on each CapitalGainEntry will be None and total_taxable_cad will be None.

    Returns:
        pools               — current ACB pool (USD) for all tickers with remaining shares
        gains               — one CapitalGainEntry per disposition in the requested year
        total_taxable_usd   — sum of taxable_gain (USD) entries
        total_taxable_cad   — sum of taxable_gain_cad entries, or None if no FX rates

    Note: totals can be negative if losses exceed gains. Capital losses can be
    applied against capital gains in the same year, carried back 3 years, or carried
    forward indefinitely (CRA T1A form).
    """
    pools = compute_acb_pools(transactions, as_of_year=year)
    if fx_rates is not None:
        gains, final_cad_pools = compute_capital_gains_cad(transactions, year, fx_rates)
        for ticker, entry in pools.items():
            if ticker in final_cad_pools:
                cad_shares, cad_acb = final_cad_pools[ticker]
                if cad_shares > 0:
                    pools[ticker] = entry.model_copy(update={
                        "total_acb_cad": cad_acb.quantize(_TWO_PLACES, ROUND_HALF_UP),
                        "acb_per_share_cad": (cad_acb / cad_shares).quantize(_EIGHT_PLACES, ROUND_HALF_UP),
                    })
    else:
        gains = compute_capital_gains(transactions, year)

    total_taxable_usd = sum(
        (g.taxable_gain for g in gains), Decimal("0")
    ).quantize(_TWO_PLACES, ROUND_HALF_UP)

    if fx_rates is not None and all(g.taxable_gain_cad is not None for g in gains):
        total_taxable_cad = sum(
            (g.taxable_gain_cad for g in gains), Decimal("0")  # type: ignore[arg-type]
        ).quantize(_TWO_PLACES, ROUND_HALF_UP)
    else:
        total_taxable_cad = None

    return pools, gains, total_taxable_usd, total_taxable_cad
