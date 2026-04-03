from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


class TransactionType(str, Enum):
    OPENING = "opening"  # Carry-forward seed: shares held with known ACB before ledger history begins
    VEST = "vest"        # RSU vesting — FMV at vest becomes the ACB (already taxed as employment income on T4)
    BUY = "buy"          # Regular market purchase — purchase price becomes ACB
    SELL = "sell"        # Disposition — triggers capital gain/loss calculation


class StockTransaction(BaseModel):
    """A single acquisition or disposition event for one ticker."""

    ticker: str
    transaction_type: TransactionType
    date: date
    quantity: Decimal        # Always positive; direction is encoded in transaction_type
    price_per_share: Decimal  # FMV for vest, purchase price for buy, proceeds per share for sell

    @field_validator("ticker", mode="before")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("quantity", "price_per_share", mode="before")
    @classmethod
    def _positive(cls, v: object) -> Decimal:
        d = Decimal(str(v))
        if d <= 0:
            raise ValueError("must be positive")
        return d


class TransactionLedger(BaseModel):
    """Persistent store of all stock transactions. Saved to ~/.prospero/acb_ledger.json."""

    transactions: list[StockTransaction] = []


class AcbPoolEntry(BaseModel):
    """
    Computed snapshot of the ACB pool for one ticker. Never stored — always derived
    from the transaction ledger by replaying all events in chronological order.

    Canada uses the identical-shares (average cost) method: all shares of the same
    ticker form one pool. The ACB per share is the weighted average cost of all shares
    currently held, tracked in CAD.

    ACB is always tracked in CAD: each acquisition's USD cost is converted to CAD at
    the Bank of Canada rate for that acquisition date, then accumulated into the pool.
    Fields are None when FX rates are unavailable for any acquisition in the pool.
    """

    ticker: str
    shares: Decimal                          # Total shares currently held
    total_acb: Optional[Decimal] = None      # Total ACB in CAD
    acb_per_share: Optional[Decimal] = None  # total_acb / shares in CAD


class CapitalGainEntry(BaseModel):
    """
    Computed record of one sell event and its capital gain/loss. Never stored —
    always derived from the transaction ledger.

    All monetary amounts are in CAD:
      capital_gain  = proceeds_cad - acb_used  (positive = gain, negative = loss)
      taxable_gain  = capital_gain * 0.50       (50% inclusion rate, CRA 2024)

    proceeds (USD) and exchange_rate are kept for reference / display.
    CAD fields are None when FX rates are unavailable for this transaction or any
    prior acquisition that contributes to the ACB pool.
    """

    date: date
    ticker: str
    shares_sold: Decimal
    proceeds: Decimal                          # Total proceeds in USD (shares_sold * price_per_share)
    exchange_rate: Optional[Decimal] = None    # USD/CAD rate on the sell date
    proceeds_cad: Optional[Decimal] = None     # proceeds * exchange_rate
    acb_used: Optional[Decimal] = None         # CAD ACB of the sold shares
    capital_gain: Optional[Decimal] = None     # proceeds_cad - acb_used in CAD
    taxable_gain: Optional[Decimal] = None     # capital_gain * 0.50 in CAD
