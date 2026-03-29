"""
Tests for src/prospero/services/acb_csv.py

Covers: successful parsing, case-insensitive type column, column normalisation,
error reporting (individual field errors, multiple errors collected together),
edge cases (empty file, BOM).
"""

import pytest
from decimal import Decimal
from pathlib import Path

from prospero.models.acb import TransactionType
from prospero.services.acb_csv import parse_csv


def write_csv(tmp_path: Path, content: str) -> Path:
    """Write CSV content to a temp file and return its path."""
    p = tmp_path / "transactions.csv"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_parses_all_three_types(tmp_path):
    csv = (
        "date,type,ticker,quantity,price\n"
        "2024-01-15,vest,AAPL,25,185.50\n"
        "2024-03-01,buy,AAPL,10,190.00\n"
        "2024-06-15,sell,AAPL,20,210.00\n"
    )
    txs = parse_csv(write_csv(tmp_path, csv))
    assert len(txs) == 3
    assert txs[0].transaction_type == TransactionType.VEST
    assert txs[1].transaction_type == TransactionType.BUY
    assert txs[2].transaction_type == TransactionType.SELL


def test_ticker_uppercased_on_import(tmp_path):
    csv = "date,type,ticker,quantity,price\n2024-01-15,vest,aapl,10,150.00\n"
    txs = parse_csv(write_csv(tmp_path, csv))
    assert txs[0].ticker == "AAPL"


def test_type_is_case_insensitive(tmp_path):
    csv = (
        "date,type,ticker,quantity,price\n"
        "2024-01-15,VEST,AAPL,10,150.00\n"
        "2024-03-01,Sell,AAPL,10,200.00\n"
    )
    txs = parse_csv(write_csv(tmp_path, csv))
    assert txs[0].transaction_type == TransactionType.VEST
    assert txs[1].transaction_type == TransactionType.SELL


def test_decimal_precision_preserved(tmp_path):
    csv = "date,type,ticker,quantity,price\n2024-01-15,vest,AAPL,25,185.1234\n"
    txs = parse_csv(write_csv(tmp_path, csv))
    assert txs[0].price_per_share == Decimal("185.1234")


def test_header_columns_are_whitespace_tolerant(tmp_path):
    # Some broker exports have spaces around column names
    csv = " date , type , ticker , quantity , price \n2024-01-15,vest,AAPL,10,150.00\n"
    txs = parse_csv(write_csv(tmp_path, csv))
    assert len(txs) == 1


def test_bom_prefix_stripped(tmp_path):
    # Excel sometimes adds a UTF-8 BOM
    p = tmp_path / "transactions.csv"
    p.write_bytes(b"\xef\xbb\xbf" + b"date,type,ticker,quantity,price\n2024-01-15,vest,AAPL,10,150.00\n")
    txs = parse_csv(p)
    assert len(txs) == 1


def test_empty_file_returns_empty_list(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    txs = parse_csv(p)
    assert txs == []


# ---------------------------------------------------------------------------
# Error cases — individual field errors
# ---------------------------------------------------------------------------


def test_invalid_date_format_raises(tmp_path):
    csv = "date,type,ticker,quantity,price\n15/01/2024,vest,AAPL,10,150.00\n"
    with pytest.raises(ValueError, match="Row 2"):
        parse_csv(write_csv(tmp_path, csv))


def test_invalid_type_raises(tmp_path):
    csv = "date,type,ticker,quantity,price\n2024-01-15,grant,AAPL,10,150.00\n"
    with pytest.raises(ValueError, match="invalid type"):
        parse_csv(write_csv(tmp_path, csv))


def test_negative_quantity_raises(tmp_path):
    csv = "date,type,ticker,quantity,price\n2024-01-15,vest,AAPL,-10,150.00\n"
    with pytest.raises(ValueError, match="quantity must be positive"):
        parse_csv(write_csv(tmp_path, csv))


def test_zero_price_raises(tmp_path):
    csv = "date,type,ticker,quantity,price\n2024-01-15,vest,AAPL,10,0\n"
    with pytest.raises(ValueError, match="price must be positive"):
        parse_csv(write_csv(tmp_path, csv))


def test_non_numeric_price_raises(tmp_path):
    csv = "date,type,ticker,quantity,price\n2024-01-15,vest,AAPL,10,abc\n"
    with pytest.raises(ValueError, match="invalid price"):
        parse_csv(write_csv(tmp_path, csv))


# ---------------------------------------------------------------------------
# Multiple errors collected together
# ---------------------------------------------------------------------------


def test_multiple_errors_reported_together(tmp_path):
    """All row errors should be collected and reported in one ValueError, not just the first."""
    csv = (
        "date,type,ticker,quantity,price\n"
        "bad-date,vest,AAPL,10,150.00\n"     # row 2: bad date
        "2024-01-15,unknown,AAPL,10,150.00\n" # row 3: bad type
        "2024-02-01,buy,AAPL,-5,150.00\n"    # row 4: negative quantity
    )
    with pytest.raises(ValueError) as exc_info:
        parse_csv(write_csv(tmp_path, csv))
    msg = str(exc_info.value)
    assert "Row 2" in msg
    assert "Row 3" in msg
    assert "Row 4" in msg


# ---------------------------------------------------------------------------
# Missing required columns
# ---------------------------------------------------------------------------


def test_missing_column_raises_before_any_rows(tmp_path):
    csv = "date,type,ticker,quantity\n2024-01-15,vest,AAPL,10\n"  # 'price' missing
    with pytest.raises(ValueError, match="missing required column"):
        parse_csv(write_csv(tmp_path, csv))


def test_file_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_csv(tmp_path / "nonexistent.csv")
