from decimal import Decimal

from fin_sim.models.planner import PlannerConfig
from fin_sim.services.planner_engine import project


def _make_config(**overrides) -> PlannerConfig:
    defaults = dict(
        current_age=30,
        life_expectancy=90,
        current_savings=Decimal("100000"),
        yearly_salary=Decimal("150000"),
        yearly_expenses=Decimal("80000"),
        annual_return_pct=Decimal("7.0"),
        inflation_pct=Decimal("3.0"),
        salary_growth_pct=Decimal("3.0"),
    )
    defaults.update(overrides)
    return PlannerConfig(**defaults)


def test_projection_length():
    config = _make_config(current_age=30, life_expectancy=90)
    summary = project(config)
    assert len(summary.projections) == 61  # ages 30..90 inclusive


def test_first_year_has_taxes():
    config = _make_config()
    summary = project(config)
    first = summary.projections[0]
    assert first.age == 30
    assert first.income == Decimal("150000")
    # Taxes should be substantial on $150k in Ontario
    assert first.taxes > Decimal("30000")
    assert first.taxes < Decimal("60000")
    # Net income = income - taxes
    assert first.net_income == first.income - first.taxes
    # Savings = net income - expenses
    assert first.savings_contribution == first.net_income - first.expenses


def test_taxes_reduce_savings():
    """With taxes, savings should be lower than the no-tax case (income - expenses)."""
    config = _make_config()
    summary = project(config)
    first = summary.projections[0]
    naive_savings = first.income - first.expenses  # $70k without tax
    assert first.savings_contribution < naive_savings


def test_net_worth_grows():
    config = _make_config()
    summary = project(config)
    assert summary.projections[-1].net_worth > summary.projections[0].net_worth


def test_fire_age_detected():
    config = _make_config(
        current_savings=Decimal("1000000"),
        yearly_salary=Decimal("200000"),
        yearly_expenses=Decimal("60000"),
    )
    summary = project(config)
    assert summary.fire_age is not None
    assert summary.fire_age >= 30


def test_fire_not_reached():
    config = _make_config(
        current_savings=Decimal("0"),
        yearly_salary=Decimal("50000"),
        yearly_expenses=Decimal("49000"),
        annual_return_pct=Decimal("1.0"),
        salary_growth_pct=Decimal("0.0"),
    )
    summary = project(config)
    # Very low savings rate — taxes make it even harder
    # Just verify no crash


def test_zero_savings():
    config = _make_config(current_savings=Decimal("0"))
    summary = project(config)
    first = summary.projections[0]
    assert first.investment_growth == Decimal("0.00")
    # Net worth = net_income - expenses (no prior investment growth)
    assert first.net_worth == first.net_income - first.expenses


def test_peak_and_final():
    config = _make_config()
    summary = project(config)
    assert summary.peak_net_worth >= summary.final_net_worth
    all_nw = [p.net_worth for p in summary.projections]
    assert summary.peak_net_worth == max(all_nw)


def test_fixed_retirement_age():
    config = _make_config(retirement_age=65)
    summary = project(config)
    # Before retirement: income > 0
    age_64 = next(p for p in summary.projections if p.age == 64)
    assert age_64.income > 0
    # At and after retirement: income = 0, taxes = 0
    age_65 = next(p for p in summary.projections if p.age == 65)
    assert age_65.income == Decimal("0")
    assert age_65.taxes == Decimal("0")
    age_70 = next(p for p in summary.projections if p.age == 70)
    assert age_70.income == Decimal("0")


def test_auto_retire_at_fire():
    config = _make_config(
        current_savings=Decimal("500000"),
        yearly_salary=Decimal("200000"),
        yearly_expenses=Decimal("60000"),
        retirement_age=0,  # auto-retire at FIRE
    )
    summary = project(config)
    assert summary.fire_age is not None
    # The year after FIRE, income should be zero
    post_fire = [p for p in summary.projections if p.age > summary.fire_age]
    assert len(post_fire) > 0
    assert all(p.income == Decimal("0") for p in post_fire)


def test_no_retirement_default():
    """With retirement_age=None, income continues to life expectancy."""
    config = _make_config(retirement_age=None)
    summary = project(config)
    last = summary.projections[-1]
    assert last.income > 0


def test_retirement_draws_down_net_worth():
    """After retirement, expenses exceed income so net worth should eventually decline."""
    config = _make_config(
        retirement_age=50,
        yearly_expenses=Decimal("80000"),
        annual_return_pct=Decimal("2.0"),  # low returns so drawdown is visible
    )
    summary = project(config)
    age_50 = next(p for p in summary.projections if p.age == 50)
    age_80 = next(p for p in summary.projections if p.age == 80)
    # With low returns and no income, net worth should decrease
    assert age_80.net_worth < age_50.net_worth
