from datetime import date
from decimal import Decimal

from prospero.models.portfolio import Holding, Portfolio
from prospero.services.portfolio_engine import valuate


def _portfolio(*holdings: Holding) -> Portfolio:
    return Portfolio(holdings=list(holdings))


def _holding(ticker: str = "AAPL", qty: str = "10", price: str = "150.00") -> Holding:
    return Holding(
        ticker=ticker,
        purchase_date=date(2024, 1, 15),
        quantity=Decimal(qty),
        purchase_price=Decimal(price),
    )


def test_single_holding_gain():
    portfolio = _portfolio(_holding("AAPL", "10", "150.00"))
    prices = {"AAPL": Decimal("200.00")}
    summary = valuate(portfolio, prices)

    assert len(summary.valuations) == 1
    v = summary.valuations[0]
    assert v.book_value == Decimal("1500.00")
    assert v.market_value == Decimal("2000.00")
    assert v.gain_loss == Decimal("500.00")
    assert v.gain_loss_pct == Decimal("33.33")


def test_single_holding_loss():
    portfolio = _portfolio(_holding("AAPL", "10", "200.00"))
    prices = {"AAPL": Decimal("150.00")}
    summary = valuate(portfolio, prices)

    v = summary.valuations[0]
    assert v.gain_loss == Decimal("-500.00")
    assert v.gain_loss_pct == Decimal("-25.00")


def test_multiple_holdings():
    portfolio = _portfolio(
        _holding("AAPL", "10", "150.00"),
        _holding("GOOG", "5", "100.00"),
    )
    prices = {"AAPL": Decimal("200.00"), "GOOG": Decimal("120.00")}
    summary = valuate(portfolio, prices)

    assert len(summary.valuations) == 2
    # AAPL: book=1500, market=2000
    # GOOG: book=500, market=600
    assert summary.total_book_value == Decimal("2000.00")
    assert summary.total_market_value == Decimal("2600.00")
    assert summary.total_gain_loss == Decimal("600.00")
    assert summary.total_gain_loss_pct == Decimal("30.00")


def test_empty_portfolio():
    portfolio = _portfolio()
    summary = valuate(portfolio, {})
    assert len(summary.valuations) == 0
    assert summary.total_market_value == Decimal("0")
    assert summary.total_gain_loss_pct == Decimal("0")
