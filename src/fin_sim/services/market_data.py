from decimal import Decimal

import yfinance as yf


class MarketDataError(Exception):
    pass


def get_current_prices(tickers: list[str]) -> dict[str, Decimal]:
    """Fetch current prices for a list of tickers. Returns {ticker: price}."""
    prices: dict[str, Decimal] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker)
            hist = info.history(period="1d")
            if hist.empty:
                raise MarketDataError(f"No data found for ticker '{ticker}'")
            close = hist["Close"].iloc[-1]
            prices[ticker] = Decimal(str(round(close, 2)))
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Failed to fetch price for '{ticker}': {e}") from e
    return prices
