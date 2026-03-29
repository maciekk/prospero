"""
USD/CAD exchange rate service using the Bank of Canada Valet API.

CRA requires foreign-currency transactions to be converted to CAD at the
exchange rate on the date of each transaction. This module fetches daily
rates from the Bank of Canada and fills in non-business days (weekends,
holidays) with the most recent prior available rate, which is the standard
approach accepted by CRA.

Source: https://www.bankofcanada.ca/valet/docs
Series:  FXUSDCAD — Canadian dollars per US dollar, noon rate
"""

import json
import urllib.error
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

_BOC_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"


def fetch_usd_cad_rates(start_date: date, end_date: date) -> dict[date, Decimal]:
    """
    Fetch daily USD/CAD rates from the Bank of Canada for the given date range.

    Non-business days (weekends, public holidays) are not published by the BoC.
    This function fills them forward using the most recent prior available rate,
    which is the standard practice for CRA foreign-currency calculations.

    Returns a dict mapping every calendar date in [start_date, end_date] to a
    rate, provided at least one rate is available on or before start_date within
    the fetched range.

    Raises:
        RuntimeError — if the API call fails or returns an unexpected response.
        ValueError   — if no rates at all are found in the requested range.
    """
    url = f"{_BOC_URL}?start_date={start_date}&end_date={end_date}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Bank of Canada API: {e}. "
            "Check your internet connection and try again."
        ) from e

    # Parse the observations list into a sparse dict keyed by date
    raw: dict[date, Decimal] = {}
    for obs in data.get("observations", []):
        try:
            d = date.fromisoformat(obs["d"])
            v = obs.get("FXUSDCAD", {}).get("v")
            if v:
                raw[d] = Decimal(v)
        except (KeyError, ValueError):
            continue

    if not raw:
        raise ValueError(
            f"Bank of Canada returned no USD/CAD rates for {start_date} – {end_date}. "
            "The date range may be too far in the future or before available data."
        )

    # Forward-fill: walk every calendar day and carry the last known rate forward.
    # This means a transaction on a Saturday uses Friday's published rate.
    filled: dict[date, Decimal] = {}
    last_rate: Decimal | None = None
    current = start_date
    while current <= end_date:
        if current in raw:
            last_rate = raw[current]
        if last_rate is not None:
            filled[current] = last_rate
        current += timedelta(days=1)

    return filled


def get_rates_for_transactions(
    transactions: list,  # list[StockTransaction] — avoid circular import
) -> dict[date, Decimal]:
    """
    Convenience wrapper: collect all unique transaction dates, fetch rates in
    the minimum number of API calls (one per year-range), and return a combined
    dict covering every transaction date.

    Silently skips any date for which no rate could be resolved (caller should
    check for missing dates if strict coverage is required).
    """
    if not transactions:
        return {}

    dates = sorted({tx.date for tx in transactions})
    start = dates[0]
    end = dates[-1]

    # Fetch a little earlier than start so forward-fill works even if start_date
    # falls on a weekend or holiday with no prior rate in the requested window.
    padded_start = start - timedelta(days=7)

    try:
        rates = fetch_usd_cad_rates(padded_start, end)
    except (RuntimeError, ValueError):
        raise

    # Return only the dates we actually need
    return {d: rates[d] for d in dates if d in rates}
