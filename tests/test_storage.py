from datetime import date
from decimal import Decimal
from pathlib import Path

from prospero.models.planner import IncomeChange, PlannerConfig
from prospero.models.portfolio import Holding, Portfolio
from prospero.storage import store


def test_planner_config_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)

    config = PlannerConfig(
        current_age=30,
        life_expectancy=85,
        current_savings=Decimal("50000"),
        yearly_salary=Decimal("120000"),
        yearly_expenses=Decimal("70000"),
        annual_return_pct=Decimal("6.5"),
        inflation_pct=Decimal("2.5"),
        salary_growth_pct=Decimal("4.0"),
    )
    store.save_planner_config(config)
    loaded = store.load_planner_config()

    assert loaded is not None
    assert loaded.current_age == 30
    assert loaded.yearly_salary == Decimal("120000")
    assert loaded.annual_return_pct == Decimal("6.5")


def test_planner_config_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert store.load_planner_config() is None


def test_portfolio_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)

    portfolio = Portfolio(holdings=[
        Holding(
            ticker="AAPL",
            purchase_date=date(2024, 1, 15),
            quantity=Decimal("10"),
            purchase_price=Decimal("185.50"),
        ),
        Holding(
            ticker="GOOG",
            purchase_date=date(2024, 6, 1),
            quantity=Decimal("5"),
            purchase_price=Decimal("175.00"),
        ),
    ])
    store.save_portfolio(portfolio)
    loaded = store.load_portfolio()

    assert len(loaded.holdings) == 2
    assert loaded.holdings[0].ticker == "AAPL"
    assert loaded.holdings[1].purchase_price == Decimal("175.00")


def test_empty_portfolio(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    portfolio = store.load_portfolio()
    assert portfolio.holdings == []


def test_planner_config_income_changes_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    config = PlannerConfig(
        current_age=35,
        life_expectancy=90,
        current_savings=Decimal("200000"),
        yearly_salary=Decimal("130000"),
        yearly_expenses=Decimal("70000"),
        income_changes=[
            IncomeChange(age=55, yearly_salary=Decimal("80000")),
            IncomeChange(age=65, yearly_salary=Decimal("0")),
        ],
    )
    store.save_planner_config(config)
    loaded = store.load_planner_config()
    assert loaded is not None
    assert len(loaded.income_changes) == 2
    assert loaded.income_changes[0].age == 55
    assert loaded.income_changes[0].yearly_salary == Decimal("80000")
    assert loaded.income_changes[1].age == 65
    assert loaded.income_changes[1].yearly_salary == Decimal("0")


def test_planner_config_migration_from_toml(tmp_path: Path, monkeypatch):
    """A TOML file written with retirement_age loads and migrates correctly."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    old_toml = (
        'current_age = 30\nlife_expectancy = 90\ncurrent_savings = "100000"\n'
        'yearly_salary = "150000"\nyearly_expenses = "80000"\n'
        'annual_return_pct = "7.0"\ninflation_pct = "3.0"\n'
        'salary_growth_pct = "3.0"\nretirement_age = 65\n'
    )
    (tmp_path / "planner.toml").write_text(old_toml)
    loaded = store.load_planner_config()
    assert loaded is not None
    assert len(loaded.income_changes) == 1
    assert loaded.income_changes[0].age == 65
    assert loaded.income_changes[0].yearly_salary == Decimal("0")


def test_planner_config_empty_income_changes_roundtrip(tmp_path: Path, monkeypatch):
    """Empty income_changes is saved and loaded correctly."""
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    config = PlannerConfig(
        current_age=30,
        life_expectancy=90,
        current_savings=Decimal("100000"),
        yearly_salary=Decimal("150000"),
        yearly_expenses=Decimal("80000"),
        income_changes=[],
    )
    store.save_planner_config(config)
    loaded = store.load_planner_config()
    assert loaded is not None
    assert loaded.income_changes == []
