from decimal import Decimal, ROUND_HALF_UP

from prospero.models.portfolio import (
    HoldingValuation,
    Portfolio,
    PortfolioSummary,
)

TWO_PLACES = Decimal("0.01")


def valuate(portfolio: Portfolio, prices: dict[str, Decimal]) -> PortfolioSummary:
    """Compute portfolio valuation given current prices per ticker."""
    valuations: list[HoldingValuation] = []

    for holding in portfolio.holdings:
        current_price = prices[holding.ticker]
        book_value = (holding.quantity * holding.purchase_price).quantize(TWO_PLACES, ROUND_HALF_UP)
        market_value = (holding.quantity * current_price).quantize(TWO_PLACES, ROUND_HALF_UP)
        gain_loss = market_value - book_value
        gain_loss_pct = (
            (gain_loss / book_value * Decimal("100")).quantize(TWO_PLACES, ROUND_HALF_UP)
            if book_value != 0
            else Decimal("0")
        )

        valuations.append(
            HoldingValuation(
                holding=holding,
                current_price=current_price,
                market_value=market_value,
                book_value=book_value,
                gain_loss=gain_loss,
                gain_loss_pct=gain_loss_pct,
            )
        )

    total_book = sum((v.book_value for v in valuations), Decimal("0"))
    total_market = sum((v.market_value for v in valuations), Decimal("0"))
    total_gl = total_market - total_book
    total_gl_pct = (
        (total_gl / total_book * Decimal("100")).quantize(TWO_PLACES, ROUND_HALF_UP)
        if total_book != 0
        else Decimal("0")
    )

    return PortfolioSummary(
        valuations=valuations,
        total_market_value=total_market,
        total_book_value=total_book,
        total_gain_loss=total_gl,
        total_gain_loss_pct=total_gl_pct,
    )
