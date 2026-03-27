from decimal import Decimal

from pydantic import BaseModel


class PlannerConfig(BaseModel):
    current_age: int
    life_expectancy: int = 90
    current_savings: Decimal = Decimal("0")
    yearly_salary: Decimal
    yearly_expenses: Decimal
    annual_return_pct: Decimal = Decimal("7.0")
    inflation_pct: Decimal = Decimal("3.0")
    salary_growth_pct: Decimal = Decimal("3.0")
    retirement_age: int | None = None  # None = no retirement; 0 = retire at FIRE


class YearProjection(BaseModel):
    age: int
    year: int
    income: Decimal
    taxes: Decimal
    net_income: Decimal
    expenses: Decimal
    savings_contribution: Decimal
    investment_growth: Decimal
    net_worth: Decimal


class PlanSummary(BaseModel):
    projections: list[YearProjection]
    fire_age: int | None
    peak_net_worth: Decimal
    final_net_worth: Decimal
