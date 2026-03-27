from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Holding(BaseModel):
    ticker: str
    purchase_date: date
    quantity: Decimal
    purchase_price: Decimal


class Portfolio(BaseModel):
    name: str = "default"
    holdings: list[Holding] = []


class HoldingValuation(BaseModel):
    holding: Holding
    current_price: Decimal
    market_value: Decimal
    book_value: Decimal
    gain_loss: Decimal
    gain_loss_pct: Decimal


class PortfolioSummary(BaseModel):
    valuations: list[HoldingValuation]
    total_market_value: Decimal
    total_book_value: Decimal
    total_gain_loss: Decimal
    total_gain_loss_pct: Decimal
