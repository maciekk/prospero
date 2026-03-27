from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from prospero.models.planner import PlannerConfig, PlanSummary, YearProjection
from prospero.services.tax import calculate_total_tax

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0")


def project(config: PlannerConfig) -> PlanSummary:
    projections: list[YearProjection] = []
    net_worth = config.current_savings
    salary = config.yearly_salary
    expenses = config.yearly_expenses
    current_year = date.today().year

    return_rate = config.annual_return_pct / Decimal("100")
    inflation_rate = config.inflation_pct / Decimal("100")
    salary_growth_rate = config.salary_growth_pct / Decimal("100")

    fire_age: int | None = None
    peak_net_worth = net_worth
    retired = False

    years = config.life_expectancy - config.current_age
    for i in range(years + 1):
        age = config.current_age + i
        year = current_year + i

        if i > 0 and not retired:
            salary = (salary * (1 + salary_growth_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)
        expenses = (
            (expenses * (1 + inflation_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)
            if i > 0
            else expenses
        )

        # Check if retirement kicks in this year
        if not retired:
            if config.retirement_age is not None:
                if config.retirement_age == 0:
                    # Auto-retire at FIRE — check if we reached FIRE last year
                    if fire_age is not None and age > fire_age:
                        retired = True
                elif age >= config.retirement_age:
                    retired = True

        if retired:
            income = ZERO
            taxes = ZERO
            net_income = ZERO
        else:
            income = salary
            taxes = calculate_total_tax(salary, years_from_base=i, inflation_rate=inflation_rate)
            net_income = salary - taxes

        savings_contribution = net_income - expenses
        investment_growth = (net_worth * return_rate).quantize(TWO_PLACES, ROUND_HALF_UP)
        net_worth = net_worth + savings_contribution + investment_growth

        if net_worth > peak_net_worth:
            peak_net_worth = net_worth

        # FIRE check: can net worth sustain expenses at 4% withdrawal rate?
        if fire_age is None and net_worth > 0:
            annual_withdrawal = net_worth * Decimal("0.04")
            if annual_withdrawal >= expenses:
                fire_age = age

        projections.append(
            YearProjection(
                age=age,
                year=year,
                income=income,
                taxes=taxes,
                net_income=net_income,
                expenses=expenses,
                savings_contribution=savings_contribution,
                investment_growth=investment_growth,
                net_worth=net_worth.quantize(TWO_PLACES, ROUND_HALF_UP),
            )
        )

    return PlanSummary(
        projections=projections,
        fire_age=fire_age,
        peak_net_worth=peak_net_worth.quantize(TWO_PLACES, ROUND_HALF_UP),
        final_net_worth=net_worth.quantize(TWO_PLACES, ROUND_HALF_UP),
    )
