from decimal import Decimal

from prospero.display.tables import _signed, _money, _money_whole, _money_k, _colored_money


# --- _signed ---

def test_signed_positive():
    assert _signed("$100.00", Decimal("100")) == "$100.00"

def test_signed_negative():
    assert _signed("$100.00", Decimal("-100")) == "($100.00)"

def test_signed_zero():
    assert _signed("$0.00", Decimal("0")) == "$0.00"


# --- _money ---

def test_money_positive():
    assert _money(Decimal("1234.56")) == "$1,234.56"

def test_money_negative():
    assert _money(Decimal("-1234.56")) == "($1,234.56)"

def test_money_zero():
    assert _money(Decimal("0")) == "$0.00"

def test_money_large():
    assert _money(Decimal("1000000.00")) == "$1,000,000.00"


# --- _money_whole ---

def test_money_whole_positive():
    assert _money_whole(Decimal("1234.99")) == "$1,235"

def test_money_whole_negative():
    assert _money_whole(Decimal("-1234.99")) == "($1,235)"

def test_money_whole_zero():
    assert _money_whole(Decimal("0")) == "$0"


# --- _money_k ---

def test_money_k_positive():
    assert _money_k(Decimal("75000")) == "$75K"

def test_money_k_negative():
    assert _money_k(Decimal("-75000")) == "($75K)"

def test_money_k_zero():
    assert _money_k(Decimal("0")) == "$0K"


# --- _colored_money ---

def test_colored_money_positive_text():
    t = _colored_money(Decimal("500"))
    assert t.plain == "$500.00"

def test_colored_money_positive_style():
    t = _colored_money(Decimal("500"))
    assert "green" in str(t._spans[0].style) if t._spans else t.style == "green"

def test_colored_money_negative_text():
    t = _colored_money(Decimal("-500"))
    assert t.plain == "($500.00)"

def test_colored_money_negative_style():
    t = _colored_money(Decimal("-500"))
    assert "red" in str(t._spans[0].style) if t._spans else t.style == "red"

def test_colored_money_zero_no_style():
    t = _colored_money(Decimal("0"))
    assert t.plain == "$0.00"
    assert not t._spans
