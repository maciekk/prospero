from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class TransactionType(str, Enum):
    VEST = "vest"  # RSU vesting — FMV at vest becomes the ACB (already taxed as employment income on T4)
    BUY = "buy"    # Regular market purchase — purchase price becomes ACB
    SELL = "sell"  # Disposition — triggers capital gain/loss calculation


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
    currently held.
    """

    ticker: str
    shares: Decimal       # Total shares currently held
    total_acb: Decimal    # Total adjusted cost basis of all shares held
    acb_per_share: Decimal  # total_acb / shares — used when computing capital gains on sale


class CapitalGainEntry(BaseModel):
    """
    Computed record of one sell event and its capital gain/loss. Never stored —
    always derived from the transaction ledger.

    capital_gain  = proceeds - acb_used  (positive = gain, negative = loss)
    taxable_gain  = capital_gain * 0.50  (50% inclusion rate, CRA 2024)
    """

    date: date
    ticker: str
    shares_sold: Decimal
    proceeds: Decimal      # Total proceeds from this sale (shares_sold * price_per_share)
    acb_used: Decimal      # ACB of the sold shares (shares_sold * pool_acb_per_share at time of sale)
    capital_gain: Decimal  # proceeds - acb_used; positive = gain, negative = loss
    taxable_gain: Decimal  # capital_gain * 0.50
