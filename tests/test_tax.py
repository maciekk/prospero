from decimal import Decimal

from prospero.services.tax import (
    calculate_total_tax,
    calculate_cpp,
    calculate_ei,
    _progressive_tax,
    FEDERAL_BRACKETS,
    FEDERAL_BPA,
)


def test_federal_tax_low_income():
    """Income at or below basic personal amount should owe no federal tax."""
    tax = _progressive_tax(Decimal("16000"), FEDERAL_BRACKETS, FEDERAL_BPA)
    assert tax == Decimal("0")


def test_federal_tax_first_bracket():
    """$60k income: all taxable income in first bracket."""
    income = Decimal("60000")
    tax = _progressive_tax(income, FEDERAL_BRACKETS, FEDERAL_BPA)
    # (60000 - 0) taxed at various rates, minus BPA credit
    # First 57375 at 15%, next 2625 at 20.5%
    expected = Decimal("57375") * Decimal("0.15") + Decimal("2625") * Decimal("0.205")
    credit = FEDERAL_BPA * Decimal("0.15")
    expected = max(Decimal("0"), expected - credit)
    assert abs(tax - expected) < Decimal("0.02")


def test_cpp_below_exemption():
    """Income below basic exemption should have zero CPP."""
    cpp = calculate_cpp(Decimal("3000"))
    assert cpp == Decimal("0")


def test_cpp_normal_income():
    """CPP on a typical salary."""
    cpp = calculate_cpp(Decimal("70000"))
    # Should be roughly (70000 - 3500) * 5.95% = ~3956.75
    assert cpp > Decimal("3900")
    assert cpp < Decimal("4100")


def test_ei_capped():
    """EI premiums should be capped at max insurable earnings."""
    ei_high = calculate_ei(Decimal("200000"))
    ei_at_max = calculate_ei(Decimal("65700"))
    assert ei_high == ei_at_max


def test_total_tax_150k():
    """Sanity check: total tax on $150k should be roughly 30-40% effective."""
    income = Decimal("150000")
    total = calculate_total_tax(income)
    effective_rate = total / income * 100
    assert Decimal("28") < effective_rate < Decimal("42")


def test_total_tax_50k():
    """Lower income should have a lower effective rate."""
    total_50 = calculate_total_tax(Decimal("50000"))
    total_150 = calculate_total_tax(Decimal("150000"))
    rate_50 = total_50 / Decimal("50000")
    rate_150 = total_150 / Decimal("150000")
    assert rate_50 < rate_150


def test_bracket_inflation():
    """Inflated brackets should produce lower tax on the same nominal income."""
    income = Decimal("150000")
    tax_base = calculate_total_tax(income, years_from_base=0)
    tax_inflated = calculate_total_tax(income, years_from_base=10, inflation_rate=Decimal("0.03"))
    # After 10 years of 3% inflation, brackets are wider, so tax should be lower
    assert tax_inflated < tax_base
