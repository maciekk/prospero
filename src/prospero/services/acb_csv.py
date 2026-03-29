"""
CSV parser for the Prospero ACB transaction ledger.

Expected CSV format (header row required):
    date,type,ticker,quantity,price

Columns:
    date      — YYYY-MM-DD
    type      — vest / buy / sell  (case-insensitive)
    ticker    — e.g. AAPL  (uppercased automatically)
    quantity  — positive number of shares
    price     — price per share (FMV for vest, purchase price for buy, proceeds for sell)

All rows are validated before any are returned. If any row has an error, a ValueError
is raised listing every problem found — so you can fix your CSV in a single pass.
"""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from prospero.models.acb import StockTransaction, TransactionType

_REQUIRED_COLUMNS = {"date", "type", "ticker", "quantity", "price"}


def parse_csv(path: Path) -> list[StockTransaction]:
    """
    Parse a CSV file of stock transactions into a list of StockTransaction objects.

    Validates every row and collects all errors before raising, so the caller sees
    the complete list of problems in one shot.

    Raises:
        ValueError  — if the file has missing columns or any row has invalid data.
                      The message lists every error found.
        FileNotFoundError — if `path` does not exist.
    """
    text = path.read_text(encoding="utf-8-sig")  # strip BOM if present (common in broker exports)
    reader = csv.DictReader(text.splitlines())

    if reader.fieldnames is None:
        return []  # empty file

    # Normalise header names: strip whitespace, lowercase
    normalised_headers = {h.strip().lower() for h in reader.fieldnames}
    missing = _REQUIRED_COLUMNS - normalised_headers
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
            f"Required: {', '.join(sorted(_REQUIRED_COLUMNS))}"
        )

    transactions: list[StockTransaction] = []
    errors: list[str] = []

    for row_num, raw_row in enumerate(reader, start=2):  # row 1 is the header
        # Normalise keys
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}

        row_errors: list[str] = []

        # --- date ---
        try:
            tx_date = date.fromisoformat(row["date"])
        except (ValueError, KeyError):
            row_errors.append(f"invalid date {row.get('date')!r} (expected YYYY-MM-DD)")
            tx_date = None  # placeholder; won't be used if we collect an error

        # --- type ---
        raw_type = row.get("type", "").lower()
        try:
            tx_type = TransactionType(raw_type)
        except ValueError:
            valid = ", ".join(t.value for t in TransactionType)
            row_errors.append(f"invalid type {row.get('type')!r} (must be one of: {valid})")
            tx_type = None

        # --- ticker ---
        ticker = row.get("ticker", "").strip().upper()
        if not ticker:
            row_errors.append("ticker is empty")

        # --- quantity ---
        try:
            quantity = Decimal(row["quantity"])
            if quantity <= 0:
                row_errors.append(f"quantity must be positive, got {row['quantity']!r}")
                quantity = None
        except (InvalidOperation, KeyError):
            row_errors.append(f"invalid quantity {row.get('quantity')!r} (must be a number)")
            quantity = None

        # --- price ---
        try:
            price = Decimal(row["price"])
            if price <= 0:
                row_errors.append(f"price must be positive, got {row['price']!r}")
                price = None
        except (InvalidOperation, KeyError):
            row_errors.append(f"invalid price {row.get('price')!r} (must be a number)")
            price = None

        if row_errors:
            errors.append(f"Row {row_num}: " + "; ".join(row_errors))
            continue

        transactions.append(
            StockTransaction(
                ticker=ticker,
                transaction_type=tx_type,  # type: ignore[arg-type]
                date=tx_date,  # type: ignore[arg-type]
                quantity=quantity,  # type: ignore[arg-type]
                price_per_share=price,  # type: ignore[arg-type]
            )
        )

    if errors:
        raise ValueError("CSV contains errors:\n" + "\n".join(errors))

    return transactions
