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

    # Pre-process income changes into age-triggered and FIRE-triggered buckets
    age_triggered = sorted(
        [c for c in config.income_changes if c.age != 0],
        key=lambda c: c.age,
    )
    fire_triggered = [c for c in config.income_changes if c.age == 0]
    age_idx = 0
    fire_applied = False
    resolved_change_ages: list[int] = []

    years = config.life_expectancy - config.current_age
    for i in range(years + 1):
        age = config.current_age + i
        year = current_year + i

        # Apply annual salary growth, then override if an income change fires
        if i > 0:
            salary = (salary * (1 + salary_growth_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)

        expenses = (
            (expenses * (1 + inflation_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)
            if i > 0
            else expenses
        )

        # Apply age-triggered income changes.
        # Salaries are specified in today's dollars; inflate to nominal value at transition year.
        while age_idx < len(age_triggered) and age >= age_triggered[age_idx].age:
            years_from_now = age_triggered[age_idx].age - config.current_age
            inflation_factor = (1 + inflation_rate) ** years_from_now
            salary = (age_triggered[age_idx].yearly_salary * inflation_factor).quantize(TWO_PLACES, ROUND_HALF_UP)
            resolved_change_ages.append(age_triggered[age_idx].age)
            age_idx += 1

        # Apply FIRE-triggered income changes (year after FIRE is reached).
        # Inflate by years elapsed to the actual trigger year.
        if fire_triggered and not fire_applied and fire_age is not None and age > fire_age:
            years_from_now = age - config.current_age
            inflation_factor = (1 + inflation_rate) ** years_from_now
            salary = (fire_triggered[-1].yearly_salary * inflation_factor).quantize(TWO_PLACES, ROUND_HALF_UP)
            resolved_change_ages.append(age)
            fire_applied = True

        if salary == ZERO:
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
        income_change_ages=resolved_change_ages,
    )
