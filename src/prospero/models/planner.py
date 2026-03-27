from decimal import Decimal

from pydantic import BaseModel, model_validator


class IncomeChange(BaseModel):
    age: int        # age at which the salary changes; 0 = the year after FIRE
    yearly_salary: Decimal  # new gross annual salary (0 = full retirement)


class PlannerConfig(BaseModel):
    current_age: int
    life_expectancy: int = 90
    current_savings: Decimal = Decimal("0")
    yearly_salary: Decimal
    yearly_expenses: Decimal
    annual_return_pct: Decimal = Decimal("7.0")
    inflation_pct: Decimal = Decimal("3.0")
    salary_growth_pct: Decimal = Decimal("3.0")
    income_changes: list[IncomeChange] = []

    @model_validator(mode='before')
    @classmethod
    def migrate_retirement_age(cls, data: dict) -> dict:
        if 'retirement_age' in data:
            ra = data.pop('retirement_age')
            if 'income_changes' not in data and ra is not None:
                data['income_changes'] = [{'age': int(ra), 'yearly_salary': '0'}]
        return data


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
    income_change_ages: list[int] = []
