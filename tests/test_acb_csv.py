"""
Tests for src/prospero/services/acb_csv.py

Covers: successful parsing, case-insensitive type column, column normalisation,
error reporting (individual field errors, multiple errors collected together),
edge cases (empty file, BOM), and the Morgan Stanley Activity Report parser.
"""

import pytest
from decimal import Decimal
from pathlib import Path

from prospero.models.acb import TransactionType
from prospero.services.acb_csv import parse_csv, parse_ms_activity_dir


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


# ---------------------------------------------------------------------------
# Morgan Stanley Activity Report parser
# ---------------------------------------------------------------------------

_MS_RELEASES = "Releases Net Shares Report.csv"
_MS_WITHDRAWALS = "Withdrawals Report.csv"

_RELEASES_CONTENT = """\
Date,Order Number,Plan,Type,Order Status,Price,Quantity,Net Share Proceeds,Net Share Proceeds,Tax Payment Method
25-Jan-2025,N/A,GSU Class C,Released Shares,Completed,$280.494582,11.269,$0.00,0.000,N/A
25-Jan-2025,N/A,GSU Class C,Released Shares,Completed,$280.494582,21.363,$0.00,0.000,N/A
"""

_WITHDRAWALS_CONTENT = """\
Execution Date,Order Number,Plan,Type,Order Status,Price,Quantity,Net Amount,Net Share Proceeds,Tax Payment Method
25-Jul-2025,WRC94ED3683-1EE,GSU Class C,Sale,Complete,$269.46,-380.565,"$102,545.82",0,N/A
Please note that any Alphabet share sales, transfers, or deposits that occurred on or prior to the July 15, 2022 stock split are reflected in pre-split. Any sales, transfers, or deposits that occurred after July 15, 2022 are in post-split values. For GSU vests, your activity is displayed in post-split values.
"""


def _write_ms_dir(tmp_path, releases=_RELEASES_CONTENT, withdrawals=_WITHDRAWALS_CONTENT):
    (tmp_path / _MS_RELEASES).write_text(releases, encoding="utf-8")
    (tmp_path / _MS_WITHDRAWALS).write_text(withdrawals, encoding="utf-8")
    return tmp_path


def test_ms_parses_vests(tmp_path):
    txs = parse_ms_activity_dir(_write_ms_dir(tmp_path), ticker="GOOG")
    vests = [t for t in txs if t.transaction_type == TransactionType.VEST]
    assert len(vests) == 2
    assert vests[0].ticker == "GOOG"
    assert vests[0].quantity == Decimal("11.269")
    assert vests[0].price_per_share == Decimal("280.494582")
    from datetime import date
    assert vests[0].date == date(2025, 1, 25)


def test_ms_parses_sells(tmp_path):
    txs = parse_ms_activity_dir(_write_ms_dir(tmp_path), ticker="GOOG")
    sells = [t for t in txs if t.transaction_type == TransactionType.SELL]
    assert len(sells) == 1
    assert sells[0].quantity == Decimal("380.565")  # sign stripped
    assert sells[0].price_per_share == Decimal("269.46")


def test_ms_footer_row_skipped(tmp_path):
    # Withdrawals file has a prose footer line — must not cause an error
    txs = parse_ms_activity_dir(_write_ms_dir(tmp_path), ticker="GOOG")
    sells = [t for t in txs if t.transaction_type == TransactionType.SELL]
    assert len(sells) == 1  # only one real sell row


def test_ms_ticker_uppercased(tmp_path):
    txs = parse_ms_activity_dir(_write_ms_dir(tmp_path), ticker="goog")
    assert all(t.ticker == "GOOG" for t in txs)


def test_ms_results_sorted_by_date(tmp_path):
    # Vests are in Jan, sell is in Jul — sorted output should put vests first
    txs = parse_ms_activity_dir(_write_ms_dir(tmp_path), ticker="GOOG")
    dates = [t.date for t in txs]
    assert dates == sorted(dates)


def test_ms_missing_releases_file_raises(tmp_path):
    (tmp_path / _MS_WITHDRAWALS).write_text(_WITHDRAWALS_CONTENT)
    with pytest.raises(FileNotFoundError, match=_MS_RELEASES):
        parse_ms_activity_dir(tmp_path, ticker="GOOG")


def test_ms_missing_withdrawals_file_raises(tmp_path):
    (tmp_path / _MS_RELEASES).write_text(_RELEASES_CONTENT)
    with pytest.raises(FileNotFoundError, match=_MS_WITHDRAWALS):
        parse_ms_activity_dir(tmp_path, ticker="GOOG")
