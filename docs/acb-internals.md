# ACB Engine Internals

Design decisions and non-obvious behaviours for `prospero acb`. For user-facing docs see [acb.md](acb.md).

## Identical-shares average cost method

Canada uses ITA s.47: all shares of the same ticker pool together. Pool state is (`total_shares`, `total_acb_cad`); `acb_per_share_cad = total_acb_cad / total_shares` at any point.

## ACB is always tracked in CAD

`StockTransaction.price_per_share` is stored in USD (as received from brokers). The engine converts each acquisition to CAD at the Bank of Canada rate for *that acquisition date*, then accumulates the CAD cost into the pool. A single current-day exchange rate cannot be used to derive the CAD ACB from the USD total — the historical per-date rates are baked in. `AcbPoolEntry.total_acb` and `acb_per_share` are in CAD (Optional; None if FX rates were unavailable for any acquisition in the pool).

## Why `acb_engine.py` replays all history for every call

To compute the correct ACB at the moment of any sale, we must know all prior acquisitions *and* dispositions, even from earlier tax years. For example, a 2023 partial sell reduces the pool before the 2024 sell computes its ACB. `compute_capital_gains(transactions, year, fx_rates)` replays everything and only *emits* entries for the requested year — it does not skip prior-year events.

## RSU vest ACB = FMV at vest

When shares vest, CRA includes the FMV as employment income on your T4. This means the ACB equals FMV — there is no additional gain to recognise at vesting, only appreciation after vesting becomes a capital gain on eventual sale.

## CSV format

(`services/acb_csv.py`): `date,type,ticker,quantity,price`. Validation collects all row errors before raising so users see the complete list of problems in one pass. Accepts UTF-8 BOM (common in Excel exports). Column names are whitespace- and case-normalised.

## Inclusion rate

50% inclusion rate is hardcoded as `Decimal("0.50")` in `acb_engine.py`. If CRA changes this rate (Budget 2024 proposed 2/3 for gains over $250k — not yet law), update `_INCLUSION_RATE` there.

## `acb_report` return value

Returns a 3-tuple `(pools, gains, total_taxable_cad)` — the old 4-tuple with a separate `total_taxable_usd` was removed when ACB tracking was unified to CAD.
