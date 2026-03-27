from datetime import date
from decimal import Decimal
from pathlib import Path

from fin_sim.models.planner import PlannerConfig
from fin_sim.models.portfolio import Holding, Portfolio
from fin_sim.storage import store


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
