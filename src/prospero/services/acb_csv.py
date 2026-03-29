"""
CSV parsers for the Prospero ACB transaction ledger.

## Canonical format  (parse_csv)

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

## Morgan Stanley Activity Report format  (parse_ms_activity_dir)

Accepts the directory produced by unpacking a Morgan Stanley Activity Report zip.
Two files are used; the rest are ignored:

  Releases Net Shares Report.csv  — RSU vesting events
      Columns used: Date (DD-Mon-YYYY), Price ($N.NNN), Quantity (net shares received)

  Withdrawals Report.csv          — sale events
      Columns used: Execution Date (DD-Mon-YYYY), Price ($N.NN), Quantity (negative)
      The footer disclaimer line is skipped automatically.

The ticker symbol is not present in MS files and must be supplied by the caller.
"""

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from prospero.models.acb import StockTransaction, TransactionType

_MS_RELEASES_FILE = "Releases Net Shares Report.csv"
_MS_WITHDRAWALS_FILE = "Withdrawals Report.csv"

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


# ---------------------------------------------------------------------------
# Morgan Stanley Activity Report parser
# ---------------------------------------------------------------------------


def _parse_ms_date(s: str) -> date:
    """Parse DD-Mon-YYYY (e.g. '25-Jan-2025') as used in MS reports."""
    return datetime.strptime(s.strip(), "%d-%b-%Y").date()


def _parse_ms_price(s: str) -> Decimal:
    """Strip leading '$' and parse as Decimal (e.g. '$280.494582' → Decimal)."""
    return Decimal(s.strip().lstrip("$").replace(",", ""))


def parse_ms_activity_dir(directory: Path, ticker: str) -> list[StockTransaction]:
    """
    Parse a Morgan Stanley Activity Report directory into StockTransaction objects.

    Reads two files from `directory`:
      - "Releases Net Shares Report.csv" → vest transactions
            Date       — vest date (DD-Mon-YYYY)
            Price      — FMV per share at vest ($N.NNN)
            Quantity   — net shares received after tax withholding
      - "Withdrawals Report.csv" → sell transactions
            Execution Date — sale date (DD-Mon-YYYY)
            Price          — proceeds per share ($N.NN)
            Quantity       — shares sold (reported as negative; sign is ignored)
            Rows where Quantity is 0 or non-numeric are skipped (e.g. footer disclaimer).

    `ticker` must be provided by the caller — it is not present in MS files.

    Raises:
        FileNotFoundError — if either expected file is missing from the directory.
        ValueError        — if any data rows cannot be parsed (all errors collected).
    """
    ticker = ticker.strip().upper()
    transactions: list[StockTransaction] = []
    errors: list[str] = []

    # --- Vests: Releases Net Shares Report ---
    releases_path = directory / _MS_RELEASES_FILE
    if not releases_path.exists():
        raise FileNotFoundError(
            f"Expected '{_MS_RELEASES_FILE}' in {directory} — file not found."
        )

    text = releases_path.read_text(encoding="utf-8-sig")
    for row_num, row in enumerate(csv.DictReader(text.splitlines()), start=2):
        row = {k.strip(): v.strip() for k, v in row.items()}
        try:
            tx_date = _parse_ms_date(row["Date"])
            price = _parse_ms_price(row["Price"])
            quantity = Decimal(row["Quantity"].replace(",", ""))
            if quantity <= 0:
                errors.append(
                    f"{_MS_RELEASES_FILE} row {row_num}: quantity must be positive, got {row['Quantity']!r}"
                )
                continue
            transactions.append(StockTransaction(
                ticker=ticker,
                transaction_type=TransactionType.VEST,
                date=tx_date,
                quantity=quantity,
                price_per_share=price,
            ))
        except (KeyError, ValueError, InvalidOperation) as e:
            errors.append(f"{_MS_RELEASES_FILE} row {row_num}: {e}")

    # --- Sells: Withdrawals Report ---
    withdrawals_path = directory / _MS_WITHDRAWALS_FILE
    if not withdrawals_path.exists():
        raise FileNotFoundError(
            f"Expected '{_MS_WITHDRAWALS_FILE}' in {directory} — file not found."
        )

    text = withdrawals_path.read_text(encoding="utf-8-sig")
    for row_num, row in enumerate(csv.DictReader(text.splitlines()), start=2):
        # DictReader uses None as the key for overflow fields (e.g. footer rows
        # that have more commas than the header); skip those entries.
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k is not None}

        # Skip footer disclaimer rows (Quantity is blank or non-numeric)
        raw_qty = row.get("Quantity", "").replace(",", "")
        if not raw_qty:
            continue
        try:
            quantity = abs(Decimal(raw_qty))  # MS reports sells as negative quantity
        except InvalidOperation:
            continue  # non-numeric → footer/note row, skip silently

        if quantity == 0:
            continue

        try:
            tx_date = _parse_ms_date(row["Execution Date"])
            price = _parse_ms_price(row["Price"])
            transactions.append(StockTransaction(
                ticker=ticker,
                transaction_type=TransactionType.SELL,
                date=tx_date,
                quantity=quantity,
                price_per_share=price,
            ))
        except (KeyError, ValueError, InvalidOperation) as e:
            errors.append(f"{_MS_WITHDRAWALS_FILE} row {row_num}: {e}")

    if errors:
        raise ValueError("MS activity report contains errors:\n" + "\n".join(errors))

    # Return sorted chronologically so callers get a consistent order
    return sorted(transactions, key=lambda t: t.date)
