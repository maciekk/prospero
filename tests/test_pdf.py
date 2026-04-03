"""
Tests for src/prospero/display/pdf.py

Each test calls a pdf_* function with minimal fixture data, then verifies:
  - The output file exists and is non-empty
  - The file starts with the PDF magic bytes b"%PDF"
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from prospero.display.pdf import (
    pdf_acb_pools,
    pdf_capital_gains_report,
    pdf_import_preview,
    pdf_plan_summary,
    pdf_portfolio_summary,
    pdf_tax_breakdown,
)
from prospero.models.acb import AcbPoolEntry, CapitalGainEntry, StockTransaction, TransactionType
from prospero.models.planner import PlannerConfig, PlanSummary, YearProjection
from prospero.models.portfolio import Holding, HoldingValuation, PortfolioSummary
from prospero.services.tax import TaxBreakdown


def _is_pdf(path: Path) -> bool:
    return path.read_bytes()[:4] == b"%PDF"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_pools() -> dict[str, AcbPoolEntry]:
    entry = AcbPoolEntry(
        ticker="GOOG",
        shares=Decimal("100"),
        total_acb=Decimal("15000.00"),
        acb_per_share=Decimal("150.00"),
    )
    return {"GOOG": entry}


def _make_gains() -> list[CapitalGainEntry]:
    return [
        CapitalGainEntry(
            date=date(2024, 6, 15),
            ticker="GOOG",
            shares_sold=Decimal("10"),
            proceeds=Decimal("2000.00"),
            acb_used=Decimal("1500.00"),
            capital_gain=Decimal("500.00"),
            taxable_gain=Decimal("250.00"),
        )
    ]


def _make_gains_with_cad() -> list[CapitalGainEntry]:
    return [
        CapitalGainEntry(
            date=date(2024, 6, 15),
            ticker="GOOG",
            shares_sold=Decimal("10"),
            proceeds=Decimal("2000.00"),
            exchange_rate=Decimal("1.3600"),
            proceeds_cad=Decimal("2720.00"),
            acb_used=Decimal("2040.00"),
            capital_gain=Decimal("680.00"),
            taxable_gain=Decimal("340.00"),
        )
    ]


def _make_plan_summary() -> tuple[PlanSummary, PlannerConfig]:
    config = PlannerConfig(
        current_age=35,
        life_expectancy=90,
        current_savings=Decimal("100000"),
        yearly_salary=Decimal("120000"),
        yearly_expenses=Decimal("60000"),
        annual_return_pct=Decimal("7.0"),
        inflation_pct=Decimal("3.0"),
        salary_growth_pct=Decimal("3.0"),
    )
    projections = [
        YearProjection(
            age=35 + i,
            year=2025 + i,
            income=Decimal("120000"),
            taxes=Decimal("40000"),
            net_income=Decimal("80000"),
            expenses=Decimal("60000"),
            savings_contribution=Decimal("20000"),
            investment_growth=Decimal("7000"),
            net_worth=Decimal("100000") + Decimal("27000") * i,
        )
        for i in range(10)
    ]
    summary = PlanSummary(
        projections=projections,
        fire_age=None,
        peak_net_worth=projections[-1].net_worth,
        final_net_worth=projections[-1].net_worth,
    )
    return summary, config


def _make_portfolio_summary() -> PortfolioSummary:
    holding = Holding(
        ticker="AAPL",
        purchase_date=date(2023, 1, 15),
        quantity=Decimal("50"),
        purchase_price=Decimal("150.00"),
    )
    val = HoldingValuation(
        holding=holding,
        current_price=Decimal("180.00"),
        book_value=Decimal("7500.00"),
        market_value=Decimal("9000.00"),
        gain_loss=Decimal("1500.00"),
        gain_loss_pct=Decimal("20.00"),
    )
    return PortfolioSummary(
        valuations=[val],
        total_book_value=Decimal("7500.00"),
        total_market_value=Decimal("9000.00"),
        total_gain_loss=Decimal("1500.00"),
        total_gain_loss_pct=Decimal("20.00"),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_pdf_acb_pools(tmp_path: Path) -> None:
    out = tmp_path / "pools.pdf"
    pdf_acb_pools(_make_pools(), out)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_capital_gains_report_usd_only(tmp_path: Path) -> None:
    out = tmp_path / "gains.pdf"
    pdf_capital_gains_report(_make_gains(), 2024, out)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_capital_gains_report_with_cad(tmp_path: Path) -> None:
    out = tmp_path / "gains_cad.pdf"
    pdf_capital_gains_report(
        _make_gains_with_cad(), 2024, out,
        total_taxable_cad=Decimal("340.00"),
    )
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_capital_gains_report_with_pools(tmp_path: Path) -> None:
    out = tmp_path / "gains_with_pools.pdf"
    pdf_capital_gains_report(
        _make_gains(), 2024, out,
        pools=_make_pools(),
    )
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_capital_gains_report_no_dispositions(tmp_path: Path) -> None:
    out = tmp_path / "no_gains.pdf"
    pdf_capital_gains_report([], 2024, out)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_plan_summary(tmp_path: Path) -> None:
    out = tmp_path / "plan.pdf"
    summary, config = _make_plan_summary()
    pdf_plan_summary(summary, config, out)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_portfolio_summary(tmp_path: Path) -> None:
    out = tmp_path / "portfolio.pdf"
    pdf_portfolio_summary(_make_portfolio_summary(), out)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_import_preview(tmp_path: Path) -> None:
    transactions = [
        StockTransaction(
            ticker="GOOG",
            transaction_type=TransactionType.VEST,
            date=date(2024, 3, 1),
            quantity=Decimal("50"),
            price_per_share=Decimal("170.00"),
        ),
        StockTransaction(
            ticker="GOOG",
            transaction_type=TransactionType.SELL,
            date=date(2024, 9, 15),
            quantity=Decimal("20"),
            price_per_share=Decimal("190.00"),
        ),
    ]
    tx_ids = [id(t) for t in transactions]
    acb_used_cad_map = {tx_ids[1]: Decimal("1700.00")}
    pool_units_after_map = {tx_ids[0]: Decimal("50"), tx_ids[1]: Decimal("30")}
    pool_acb_cad_after_map = {tx_ids[0]: Decimal("8500.00"), tx_ids[1]: Decimal("5100.00")}
    fx_rates = {}

    out = tmp_path / "import.pdf"
    pdf_import_preview(transactions, out, fx_rates, acb_used_cad_map, pool_units_after_map, pool_acb_cad_after_map)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)


def test_pdf_tax_breakdown(tmp_path: Path) -> None:
    out = tmp_path / "tax.pdf"
    bd = TaxBreakdown(
        income=Decimal("150000"),
        federal=Decimal("30000"),
        ontario_base=Decimal("15000"),
        ontario_surtax=Decimal("2000"),
        cpp1=Decimal("3500"),
        cpp2=Decimal("188"),
        ei=Decimal("1049"),
    )
    pdf_tax_breakdown(bd, out)
    assert out.exists() and out.stat().st_size > 0
    assert _is_pdf(out)
