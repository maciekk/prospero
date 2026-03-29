"""
Tests for src/prospero/services/acb_engine.py

These tests cover the core Canadian ACB calculation rules:
  - Average cost pool maintenance (vest, buy, sell)
  - Capital gain/loss computation per sale
  - 50% inclusion rate applied to taxable gains
  - Cross-year accuracy (prior-year sells must affect ACB for future sells)
  - Edge cases: full position close, multiple tickers, oversell validation
"""

import pytest
from decimal import Decimal
from datetime import date

from prospero.models.acb import StockTransaction, TransactionType
from prospero.services.acb_engine import compute_acb_pools, compute_capital_gains, acb_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def opening(ticker: str, dt: str, shares: str, acb_per_share: str) -> StockTransaction:
    return StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.OPENING,
        date=date.fromisoformat(dt),
        quantity=Decimal(shares),
        price_per_share=Decimal(acb_per_share),
    )


def vest(ticker: str, dt: str, qty: str, fmv: str) -> StockTransaction:
    return StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.VEST,
        date=date.fromisoformat(dt),
        quantity=Decimal(qty),
        price_per_share=Decimal(fmv),
    )


def buy(ticker: str, dt: str, qty: str, price: str) -> StockTransaction:
    return StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.BUY,
        date=date.fromisoformat(dt),
        quantity=Decimal(qty),
        price_per_share=Decimal(price),
    )


def sell(ticker: str, dt: str, qty: str, price: str) -> StockTransaction:
    return StockTransaction(
        ticker=ticker,
        transaction_type=TransactionType.SELL,
        date=date.fromisoformat(dt),
        quantity=Decimal(qty),
        price_per_share=Decimal(price),
    )


# ---------------------------------------------------------------------------
# compute_acb_pools — pool maintenance
# ---------------------------------------------------------------------------


def test_opening_balance_seeds_pool():
    # Opening balance of 100 shares @ $120 ACB/share, then sell in the same year
    txs = [
        opening("GOOG", "2024-12-31", "100", "120.00"),
        sell("GOOG", "2025-07-01", "40", "200.00"),
    ]
    pools = compute_acb_pools(txs)
    # 60 shares remain, ACB unchanged per share
    assert pools["GOOG"].shares == Decimal("60")
    assert pools["GOOG"].total_acb == Decimal("7200.00")  # 60 * 120


def test_opening_balance_averages_with_subsequent_vests():
    txs = [
        opening("GOOG", "2024-12-31", "100", "120.00"),   # pool: 100 @ 120 = 12000
        vest("GOOG", "2025-01-25", "50", "200.00"),        # pool: 150 @ 146.67 = 22000
    ]
    pools = compute_acb_pools(txs)
    assert pools["GOOG"].shares == Decimal("150")
    assert pools["GOOG"].total_acb == Decimal("22000.00")


def test_opening_balance_enables_sell_that_would_otherwise_fail():
    # Without opening balance this sell would raise ValueError (insufficient shares)
    txs = [
        opening("GOOG", "2024-12-31", "500", "100.00"),
        vest("GOOG", "2025-01-25", "50", "200.00"),
        sell("GOOG", "2025-07-01", "400", "250.00"),
    ]
    gains = compute_capital_gains(txs, 2025)
    assert len(gains) == 1
    # ACB per share after opening + vest: (500*100 + 50*200) / 550 = 60000/550 ≈ 109.09
    assert gains[0].shares_sold == Decimal("400")


def test_single_vest_creates_pool():
    txs = [vest("AAPL", "2024-01-15", "25", "185.50")]
    pools = compute_acb_pools(txs)
    assert "AAPL" in pools
    p = pools["AAPL"]
    assert p.shares == Decimal("25")
    assert p.total_acb == Decimal("4637.50")
    assert p.acb_per_share == Decimal("185.50000000")


def test_buy_averages_acb_pool():
    # VEST 25 @ 185.50 = 4637.50 ACB; BUY 10 @ 190.00 = 1900.00 ACB
    # total: 35 shares, 6537.50 ACB, acb/share = 186.78571429
    txs = [
        vest("AAPL", "2024-01-15", "25", "185.50"),
        buy("AAPL", "2024-03-01", "10", "190.00"),
    ]
    pools = compute_acb_pools(txs)
    p = pools["AAPL"]
    assert p.shares == Decimal("35")
    assert p.total_acb == Decimal("6537.50")
    expected_acb_per_share = (Decimal("6537.50") / Decimal("35")).quantize(Decimal("0.00000001"))
    assert p.acb_per_share == expected_acb_per_share


def test_sell_reduces_pool_by_acb_not_proceeds():
    """
    Critical test: when selling, the pool ACB decreases by (shares_sold * acb_per_share),
    NOT by (shares_sold * proceeds_per_share). The sell price has no effect on the pool.
    """
    txs = [
        vest("AAPL", "2024-01-15", "25", "185.50"),
        sell("AAPL", "2024-06-15", "20", "210.00"),  # sell at higher price
    ]
    pools = compute_acb_pools(txs)
    p = pools["AAPL"]
    assert p.shares == Decimal("5")
    # Remaining ACB = 4637.50 - (20 * 185.50) = 4637.50 - 3710.00 = 927.50
    assert p.total_acb == Decimal("927.50")
    # Verify the proceeds price (210.00) was NOT used to reduce the pool
    assert p.total_acb != Decimal("5") * Decimal("210.00")


def test_sell_entire_position_removes_ticker():
    txs = [
        vest("AAPL", "2024-01-15", "10", "150.00"),
        sell("AAPL", "2024-06-01", "10", "200.00"),
    ]
    pools = compute_acb_pools(txs)
    assert "AAPL" not in pools  # fully closed position excluded


def test_multiple_tickers_have_independent_pools():
    txs = [
        vest("AAPL", "2024-01-15", "10", "150.00"),
        vest("GOOG", "2024-02-01", "5", "100.00"),
    ]
    pools = compute_acb_pools(txs)
    assert pools["AAPL"].shares == Decimal("10")
    assert pools["AAPL"].total_acb == Decimal("1500.00")
    assert pools["GOOG"].shares == Decimal("5")
    assert pools["GOOG"].total_acb == Decimal("500.00")
    # AAPL sell should not affect GOOG
    txs.append(sell("AAPL", "2024-06-01", "10", "200.00"))
    pools2 = compute_acb_pools(txs)
    assert "AAPL" not in pools2
    assert pools2["GOOG"].total_acb == Decimal("500.00")  # unchanged


def test_oversell_raises_value_error():
    txs = [
        vest("AAPL", "2024-01-15", "5", "150.00"),
        sell("AAPL", "2024-06-01", "10", "200.00"),  # selling more than held
    ]
    with pytest.raises(ValueError, match="only 5 shares held"):
        compute_acb_pools(txs)


def test_sell_with_no_prior_acquisitions_raises():
    txs = [sell("AAPL", "2024-06-01", "10", "200.00")]
    with pytest.raises(ValueError, match="no shares currently held"):
        compute_acb_pools(txs)


# ---------------------------------------------------------------------------
# compute_capital_gains — gain/loss computation
# ---------------------------------------------------------------------------


def test_capital_gain_simple_vest_and_sell():
    # Vest 25 @ 185.50, sell 20 @ 210.00
    # ACB used = 20 * 185.50 = 3710.00
    # Proceeds = 20 * 210.00 = 4200.00
    # Gain = 490.00, taxable = 245.00
    txs = [
        vest("AAPL", "2024-01-15", "25", "185.50"),
        sell("AAPL", "2024-06-15", "20", "210.00"),
    ]
    gains = compute_capital_gains(txs, 2024)
    assert len(gains) == 1
    g = gains[0]
    assert g.ticker == "AAPL"
    assert g.shares_sold == Decimal("20")
    assert g.proceeds == Decimal("4200.00")
    assert g.acb_used == Decimal("3710.00")
    assert g.capital_gain == Decimal("490.00")
    assert g.taxable_gain == Decimal("245.00")  # 50% inclusion


def test_capital_loss():
    txs = [
        vest("AAPL", "2024-01-15", "10", "200.00"),
        sell("AAPL", "2024-06-01", "10", "150.00"),  # sell below ACB
    ]
    gains = compute_capital_gains(txs, 2024)
    g = gains[0]
    assert g.capital_gain == Decimal("-500.00")
    assert g.taxable_gain == Decimal("-250.00")  # negative = capital loss


def test_gains_filtered_to_requested_year():
    txs = [
        vest("AAPL", "2023-06-01", "20", "100.00"),
        sell("AAPL", "2023-12-01", "10", "120.00"),
        sell("AAPL", "2024-03-01", "10", "200.00"),
    ]
    gains_2023 = compute_capital_gains(txs, 2023)
    gains_2024 = compute_capital_gains(txs, 2024)

    assert len(gains_2023) == 1
    assert gains_2023[0].date.year == 2023

    assert len(gains_2024) == 1
    assert gains_2024[0].date.year == 2024


def test_cross_year_acb_correctness():
    """
    A sell in 2023 must reduce the ACB pool so the 2024 sell uses the updated per-share ACB.
    If the engine incorrectly recalculates from scratch for 2024, it would overstate
    the remaining ACB and understate the capital gain.
    """
    # Vest 20 @ 100, sell 10 in 2023, sell remaining 10 in 2024
    txs = [
        vest("AAPL", "2023-01-01", "20", "100.00"),
        sell("AAPL", "2023-06-01", "10", "120.00"),   # reduces pool to 10 @ 100 total = 1000
        sell("AAPL", "2024-03-01", "10", "150.00"),
    ]
    gains = compute_capital_gains(txs, 2024)
    assert len(gains) == 1
    g = gains[0]
    # After 2023 sell: 10 shares remain, total_acb = 2000 - (10 * 100) = 1000
    # 2024 sell: proceeds = 1500, acb_used = 10 * (1000/10) = 1000, gain = 500
    assert g.acb_used == Decimal("1000.00")
    assert g.capital_gain == Decimal("500.00")
    assert g.taxable_gain == Decimal("250.00")


def test_multiple_sells_same_ticker_same_year():
    txs = [
        vest("AAPL", "2024-01-01", "30", "100.00"),
        sell("AAPL", "2024-03-01", "10", "120.00"),   # gain = 200, taxable = 100
        sell("AAPL", "2024-09-01", "10", "80.00"),    # loss = -200, taxable = -100
    ]
    gains = compute_capital_gains(txs, 2024)
    assert len(gains) == 2
    total = sum(g.capital_gain for g in gains)
    assert total == Decimal("0.00")  # gain and loss cancel out


def test_no_sells_returns_empty_list():
    txs = [
        vest("AAPL", "2024-01-01", "10", "150.00"),
        buy("GOOG", "2024-06-01", "5", "100.00"),
    ]
    gains = compute_capital_gains(txs, 2024)
    assert gains == []


# ---------------------------------------------------------------------------
# acb_report — integration
# ---------------------------------------------------------------------------


def test_acb_report_returns_correct_tuple():
    txs = [
        vest("AAPL", "2024-01-15", "25", "185.50"),
        sell("AAPL", "2024-06-15", "20", "210.00"),
    ]
    pools, gains, total_taxable = acb_report(txs, 2024)

    assert "AAPL" in pools
    assert pools["AAPL"].shares == Decimal("5")

    assert len(gains) == 1
    assert gains[0].capital_gain == Decimal("490.00")

    assert total_taxable == Decimal("245.00")


def test_acb_report_total_taxable_sums_all_gains():
    txs = [
        vest("AAPL", "2024-01-01", "30", "100.00"),
        sell("AAPL", "2024-03-01", "10", "120.00"),  # taxable = 100
        sell("AAPL", "2024-09-01", "10", "110.00"),  # taxable = 50
    ]
    _, gains, total_taxable = acb_report(txs, 2024)
    expected = sum(g.taxable_gain for g in gains)
    assert total_taxable == expected
    assert total_taxable == Decimal("150.00")


def test_acb_report_no_sells_zero_taxable():
    txs = [
        vest("AAPL", "2024-01-01", "10", "150.00"),
        buy("GOOG", "2024-06-01", "5", "100.00"),
    ]
    pools, gains, total_taxable = acb_report(txs, 2024)
    assert gains == []
    assert total_taxable == Decimal("0.00")
    assert "AAPL" in pools
    assert "GOOG" in pools
