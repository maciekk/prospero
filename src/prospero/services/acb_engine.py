"""
ACB (Adjusted Cost Basis) calculation engine for Canadian capital gains tax.

Canada uses the **identical-shares average cost method** (ITA s.47): all shares of
the same ticker form a single ACB pool. The pool tracks (total_shares, total_acb_cad),
and the per-share ACB is always total_acb_cad / total_shares.

ACB is always tracked in CAD. Each acquisition's USD price is converted to CAD at the
Bank of Canada rate for *that acquisition date* — not today's rate. This means the CAD
pool cannot be derived by multiplying a single USD value by a current rate.

Key rules encoded here:
  - VEST/BUY acquisition: add shares at CAD cost (price × fx_rate) to the pool.
  - SELL disposition: ACB used (CAD) = shares_sold × (total_acb_cad / total_shares).
    The proceeds price has no effect on the pool — only acb_used is removed.
  - Capital gain (CAD) = proceeds_cad − acb_used_cad.
  - 50% inclusion rate: only half of net capital gains are added to taxable income.
  - Cross-year accuracy: to get the correct ACB at the moment of any sale, we must
    replay ALL prior transactions regardless of which tax year we're reporting on.

All functions are pure (no I/O, no side effects).

When fx_rates is None or a date is missing from the dict, the affected pool's CAD
fields remain None — callers should handle this gracefully.
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
    fx_rates: dict | None = None,
    as_of_year: int | None = None,
) -> dict[str, AcbPoolEntry]:
    """
    Replay all transactions in chronological order and return the ACB pool
    for each ticker that still has shares remaining.

    When as_of_year is provided, only transactions up to and including Dec 31
    of that year are replayed — useful for year-end snapshots in tax reports.

    When fx_rates (dict[date, Decimal]) is provided, total_acb and acb_per_share
    on each entry are in CAD; otherwise they are None.

    Raises ValueError if a SELL transaction exceeds the shares currently held.
    """
    # cad_pools[ticker] = (total_shares, total_acb_cad)
    # share_pools[ticker] = total_shares (needed for sell validation even without FX)
    share_pools: dict[str, Decimal] = {}
    cad_pools: dict[str, tuple[Decimal, Decimal]] = {}   # (shares, acb_cad)
    cad_complete: dict[str, bool] = {}  # True if all acquisitions had FX rates

    filtered = [tx for tx in transactions if tx.date.year <= as_of_year] if as_of_year is not None else transactions
    for tx in _sorted_txs(filtered):
        shares = share_pools.get(tx.ticker, Decimal("0"))
        cad_shares, cad_acb = cad_pools.get(tx.ticker, (Decimal("0"), Decimal("0")))
        complete = cad_complete.get(tx.ticker, True)
        rate = fx_rates.get(tx.date) if fx_rates is not None else None

        if tx.transaction_type in (TransactionType.OPENING, TransactionType.VEST, TransactionType.BUY):
            new_shares = shares + tx.quantity
            share_pools[tx.ticker] = new_shares
            cost_usd = tx.quantity * tx.price_per_share
            if rate is not None:
                cad_pools[tx.ticker] = (new_shares, cad_acb + cost_usd * rate)
            else:
                cad_pools[tx.ticker] = (new_shares, cad_acb)
                complete = False
            cad_complete[tx.ticker] = complete

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
            new_shares = shares - tx.quantity
            share_pools[tx.ticker] = new_shares
            if cad_shares > 0:
                cad_acb_per_share = cad_acb / cad_shares
                cad_acb_used = (tx.quantity * cad_acb_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
                cad_pools[tx.ticker] = (cad_shares - tx.quantity, cad_acb - cad_acb_used)
            else:
                cad_pools[tx.ticker] = (new_shares, Decimal("0"))

    result: dict[str, AcbPoolEntry] = {}
    for ticker, shares in share_pools.items():
        if shares > 0:
            cad_sh, cad_acb = cad_pools.get(ticker, (Decimal("0"), Decimal("0")))
            complete = cad_complete.get(ticker, True)
            if fx_rates is not None and complete and cad_sh > 0:
                total_acb = cad_acb.quantize(_TWO_PLACES, ROUND_HALF_UP)
                acb_per_share = (cad_acb / cad_sh).quantize(_EIGHT_PLACES, ROUND_HALF_UP)
            else:
                total_acb = None
                acb_per_share = None
            result[ticker] = AcbPoolEntry(
                ticker=ticker,
                shares=shares,
                total_acb=total_acb,
                acb_per_share=acb_per_share,
            )

    return result


def compute_capital_gains(
    transactions: list[StockTransaction],
    year: int,
    fx_rates: dict | None = None,
) -> list[CapitalGainEntry]:
    """
    Replay the full transaction history and return one CapitalGainEntry for every
    SELL event that falls within the requested tax year.

    Why replay all years? The ACB at the moment of any sale depends on all prior
    acquisitions and dispositions, even those from earlier years.

    When fx_rates (dict[date, Decimal]) is provided, CAD fields are populated using
    Bank of Canada rates. Each acquisition's cost is converted at its own date.
    Without fx_rates, all CAD fields on each entry are None.
    """
    gains: list[CapitalGainEntry] = []
    share_pools: dict[str, Decimal] = {}
    cad_pools: dict[str, tuple[Decimal, Decimal]] = {}   # (shares, total_acb_cad)

    for tx in _sorted_txs(transactions):
        shares = share_pools.get(tx.ticker, Decimal("0"))
        cad_shares, cad_acb = cad_pools.get(tx.ticker, (Decimal("0"), Decimal("0")))
        rate = fx_rates.get(tx.date) if fx_rates is not None else None

        if tx.transaction_type in (TransactionType.OPENING, TransactionType.VEST, TransactionType.BUY):
            new_shares = shares + tx.quantity
            share_pools[tx.ticker] = new_shares
            cost_usd = tx.quantity * tx.price_per_share
            cad_cost = cost_usd * rate if rate is not None else Decimal("0")
            cad_pools[tx.ticker] = (new_shares, cad_acb + cad_cost)

        elif tx.transaction_type == TransactionType.SELL:
            proceeds_usd = (tx.quantity * tx.price_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)

            # Update pools (must stay accurate for future sells)
            new_shares = shares - tx.quantity
            share_pools[tx.ticker] = new_shares
            if cad_shares > 0:
                cad_acb_per_share = cad_acb / cad_shares
                cad_acb_used = (tx.quantity * cad_acb_per_share).quantize(_TWO_PLACES, ROUND_HALF_UP)
                cad_pools[tx.ticker] = (cad_shares - tx.quantity, cad_acb - cad_acb_used)
            else:
                cad_acb_used = Decimal("0")
                cad_pools[tx.ticker] = (new_shares, Decimal("0"))

            if tx.date.year == year:
                sell_rate = fx_rates.get(tx.date) if fx_rates is not None else None
                if sell_rate is not None and fx_rates is not None:
                    proceeds_cad = (proceeds_usd * sell_rate).quantize(_TWO_PLACES, ROUND_HALF_UP)
                    capital_gain = proceeds_cad - cad_acb_used
                    taxable_gain = (capital_gain * _INCLUSION_RATE).quantize(_TWO_PLACES, ROUND_HALF_UP)
                else:
                    proceeds_cad = capital_gain = taxable_gain = None

                gains.append(CapitalGainEntry(
                    date=tx.date,
                    ticker=tx.ticker,
                    shares_sold=tx.quantity,
                    proceeds=proceeds_usd,
                    exchange_rate=sell_rate,
                    proceeds_cad=proceeds_cad,
                    acb_used=cad_acb_used if fx_rates is not None else None,
                    capital_gain=capital_gain,
                    taxable_gain=taxable_gain,
                ))

    return gains


def sanity_check_capital_gains(gains: list[CapitalGainEntry]) -> list[str]:
    """
    Verify mathematical invariants on a list of CapitalGainEntry values.

    Checks (where all fields are non-None):
      1. proceeds_cad == proceeds × exchange_rate
      2. capital_gain == proceeds_cad - acb_used
      3. taxable_gain == capital_gain × _INCLUSION_RATE

    Returns a list of human-readable violation strings (empty = all good).
    """
    _TOL = Decimal("0.02")  # 2 cents — allows for one rounding step on each side
    errors: list[str] = []
    for g in gains:
        tag = f"{g.date} {g.ticker}"
        if g.proceeds_cad is not None and g.exchange_rate is not None:
            expected = (g.proceeds * g.exchange_rate).quantize(_TWO_PLACES, ROUND_HALF_UP)
            if abs(expected - g.proceeds_cad) > _TOL:
                errors.append(
                    f"{tag}: proceeds_cad {g.proceeds_cad} != "
                    f"proceeds {g.proceeds} x rate {g.exchange_rate} = {expected}"
                )
        if g.capital_gain is not None and g.proceeds_cad is not None and g.acb_used is not None:
            expected = g.proceeds_cad - g.acb_used
            if abs(expected - g.capital_gain) > _TOL:
                errors.append(
                    f"{tag}: capital_gain {g.capital_gain} != "
                    f"proceeds_cad {g.proceeds_cad} - acb_used {g.acb_used} = {expected}"
                )
        if g.taxable_gain is not None and g.capital_gain is not None:
            expected = (g.capital_gain * _INCLUSION_RATE).quantize(_TWO_PLACES, ROUND_HALF_UP)
            if abs(expected - g.taxable_gain) > _TOL:
                errors.append(
                    f"{tag}: taxable_gain {g.taxable_gain} != "
                    f"capital_gain {g.capital_gain} x {_INCLUSION_RATE} = {expected}"
                )
    return errors


def sanity_check_acb_pools(pools: dict[str, AcbPoolEntry]) -> list[str]:
    """
    Verify that acb_per_share == total_acb / shares for every pool entry.

    Returns a list of human-readable violation strings (empty = all good).
    """
    _TOL = Decimal("0.0001")  # allow for 8-place quantize rounding
    errors: list[str] = []
    for ticker, pool in pools.items():
        if pool.total_acb is not None and pool.acb_per_share is not None and pool.shares > 0:
            expected = (pool.total_acb / pool.shares).quantize(_EIGHT_PLACES, ROUND_HALF_UP)
            if abs(expected - pool.acb_per_share) > _TOL:
                errors.append(
                    f"{ticker}: acb_per_share {pool.acb_per_share} != "
                    f"total_acb {pool.total_acb} / shares {pool.shares} = {expected}"
                )
    return errors


def acb_report(
    transactions: list[StockTransaction],
    year: int,
    fx_rates: dict | None = None,
) -> tuple[dict[str, AcbPoolEntry], list[CapitalGainEntry], Decimal | None]:
    """
    Compute the full ACB report for a tax year.

    Pass fx_rates (dict[date, Decimal] from fx.get_rates_for_transactions) to get
    CAD-denominated values. When fx_rates is None, CAD fields on each entry will be
    None and total_taxable_cad will be None.

    Returns:
        pools               — year-end ACB pool (CAD) for all tickers with remaining shares
        gains               — one CapitalGainEntry per disposition in the requested year
        total_taxable_cad   — sum of taxable_gain entries in CAD, or None if no FX rates

    Note: totals can be negative if losses exceed gains.
    """
    pools = compute_acb_pools(transactions, fx_rates=fx_rates, as_of_year=year)
    gains = compute_capital_gains(transactions, year, fx_rates=fx_rates)

    if fx_rates is not None and all(g.taxable_gain is not None for g in gains):
        total_taxable_cad = sum(
            (g.taxable_gain for g in gains), Decimal("0")  # type: ignore[arg-type]
        ).quantize(_TWO_PLACES, ROUND_HALF_UP)
    else:
        total_taxable_cad = None

    return pools, gains, total_taxable_cad
