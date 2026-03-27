"""Canadian federal + Ontario provincial income tax, CPP, and EI calculations.

Uses 2025 rates/brackets as a baseline. Brackets are indexed to inflation each year
via the `bracket_inflation_pct` parameter in PlannerConfig.
"""

from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")

# 2025 Federal tax brackets: (threshold, marginal rate)
FEDERAL_BRACKETS: list[tuple[Decimal, Decimal]] = [
    (Decimal("57375"), Decimal("0.15")),
    (Decimal("114750"), Decimal("0.205")),
    (Decimal("158468"), Decimal("0.26")),
    (Decimal("221708"), Decimal("0.29")),
    (Decimal("999999999"), Decimal("0.33")),
]

# 2025 Federal basic personal amount
FEDERAL_BPA = Decimal("16129")

# 2025 Ontario tax brackets
ONTARIO_BRACKETS: list[tuple[Decimal, Decimal]] = [
    (Decimal("52886"), Decimal("0.0505")),
    (Decimal("105775"), Decimal("0.0915")),
    (Decimal("150000"), Decimal("0.1116")),
    (Decimal("220000"), Decimal("0.1216")),
    (Decimal("999999999"), Decimal("0.1316")),
]

# 2025 Ontario basic personal amount
ONTARIO_BPA = Decimal("11865")

# Ontario surtax thresholds (2025)
ONTARIO_SURTAX_THRESHOLD_1 = Decimal("5315")
ONTARIO_SURTAX_RATE_1 = Decimal("0.20")
ONTARIO_SURTAX_THRESHOLD_2 = Decimal("6802")
ONTARIO_SURTAX_RATE_2 = Decimal("0.36")

# 2025 CPP/CPP2
CPP_RATE = Decimal("0.0595")
CPP_MAX_PENSIONABLE = Decimal("71300")
CPP_BASIC_EXEMPTION = Decimal("3500")
CPP2_MAX_PENSIONABLE = Decimal("81200")
CPP2_RATE = Decimal("0.04")

# 2025 EI
EI_RATE = Decimal("0.0164")
EI_MAX_INSURABLE = Decimal("65700")


def _progressive_tax(
    income: Decimal,
    brackets: list[tuple[Decimal, Decimal]],
    personal_amount: Decimal,
) -> Decimal:
    """Calculate progressive tax given brackets and a basic personal amount credit."""
    tax = Decimal("0")
    prev_threshold = Decimal("0")
    for threshold, rate in brackets:
        taxable_in_bracket = min(income, threshold) - prev_threshold
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_threshold = threshold
        if income <= threshold:
            break

    # Basic personal amount is a non-refundable credit at the lowest marginal rate
    lowest_rate = brackets[0][1]
    credit = personal_amount * lowest_rate
    tax = max(Decimal("0"), tax - credit)
    return tax.quantize(TWO_PLACES, ROUND_HALF_UP)


def _inflate_brackets(
    brackets: list[tuple[Decimal, Decimal]],
    years: int,
    inflation_rate: Decimal,
) -> list[tuple[Decimal, Decimal]]:
    """Inflate bracket thresholds by a given rate over N years."""
    factor = (1 + inflation_rate) ** years
    return [
        ((threshold * factor).quantize(TWO_PLACES, ROUND_HALF_UP), rate)
        for threshold, rate in brackets
    ]


def _inflate(value: Decimal, years: int, rate: Decimal) -> Decimal:
    return (value * (1 + rate) ** years).quantize(TWO_PLACES, ROUND_HALF_UP)


def calculate_cpp(employment_income: Decimal, years_from_base: int = 0, inflation_rate: Decimal = Decimal("0")) -> Decimal:
    """Calculate CPP + CPP2 employee contributions."""
    max_pensionable = _inflate(CPP_MAX_PENSIONABLE, years_from_base, inflation_rate)
    basic_exemption = CPP_BASIC_EXEMPTION  # not indexed
    cpp2_max = _inflate(CPP2_MAX_PENSIONABLE, years_from_base, inflation_rate)

    # CPP1: on income between basic exemption and max pensionable
    cpp1_earnings = max(Decimal("0"), min(employment_income, max_pensionable) - basic_exemption)
    cpp1 = (cpp1_earnings * CPP_RATE).quantize(TWO_PLACES, ROUND_HALF_UP)

    # CPP2: on income between CPP max pensionable and CPP2 max
    cpp2_earnings = max(Decimal("0"), min(employment_income, cpp2_max) - max_pensionable)
    cpp2 = (cpp2_earnings * CPP2_RATE).quantize(TWO_PLACES, ROUND_HALF_UP)

    return cpp1 + cpp2


def calculate_ei(employment_income: Decimal, years_from_base: int = 0, inflation_rate: Decimal = Decimal("0")) -> Decimal:
    """Calculate EI employee premiums."""
    max_insurable = _inflate(EI_MAX_INSURABLE, years_from_base, inflation_rate)
    insurable = min(employment_income, max_insurable)
    return (insurable * EI_RATE).quantize(TWO_PLACES, ROUND_HALF_UP)


def calculate_total_tax(
    employment_income: Decimal,
    years_from_base: int = 0,
    inflation_rate: Decimal = Decimal("0"),
) -> Decimal:
    """Calculate total tax burden: federal + Ontario + CPP + EI."""
    federal_brackets = _inflate_brackets(FEDERAL_BRACKETS, years_from_base, inflation_rate)
    ontario_brackets = _inflate_brackets(ONTARIO_BRACKETS, years_from_base, inflation_rate)
    federal_bpa = _inflate(FEDERAL_BPA, years_from_base, inflation_rate)
    ontario_bpa = _inflate(ONTARIO_BPA, years_from_base, inflation_rate)

    federal = _progressive_tax(employment_income, federal_brackets, federal_bpa)
    ontario_base = _progressive_tax(employment_income, ontario_brackets, ontario_bpa)

    # Ontario surtax
    surtax_t1 = _inflate(ONTARIO_SURTAX_THRESHOLD_1, years_from_base, inflation_rate)
    surtax_t2 = _inflate(ONTARIO_SURTAX_THRESHOLD_2, years_from_base, inflation_rate)
    ontario_surtax = Decimal("0")
    if ontario_base > surtax_t1:
        ontario_surtax += (ontario_base - surtax_t1) * ONTARIO_SURTAX_RATE_1
    if ontario_base > surtax_t2:
        ontario_surtax += (ontario_base - surtax_t2) * ONTARIO_SURTAX_RATE_2
    ontario_surtax = ontario_surtax.quantize(TWO_PLACES, ROUND_HALF_UP)

    ontario = ontario_base + ontario_surtax
    cpp = calculate_cpp(employment_income, years_from_base, inflation_rate)
    ei = calculate_ei(employment_income, years_from_base, inflation_rate)

    return federal + ontario + cpp + ei
