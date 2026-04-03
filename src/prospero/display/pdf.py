"""
PDF rendering for prospero reports.

One pdf_* function per render_* function in tables.py. All output is black-and-white;
negative values use parentheses accounting notation rather than colour.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fpdf import FPDF, FontFace
from fpdf.enums import TableCellFillMode

from prospero.models.acb import AcbPoolEntry, CapitalGainEntry, StockTransaction, TransactionType
from prospero.models.planner import PlannerConfig, PlanSummary
from prospero.models.portfolio import PortfolioSummary
from prospero.services.tax import TaxBreakdown

# ── Gray palette ─────────────────────────────────────────────────────────────
HEADER_BG = (220, 220, 220)   # column header background
TOTALS_BG  = (200, 200, 200)  # totals / section row background
STRIPE_BG  = (248, 248, 248)  # alternating data row (subtle)

# ── Formatting helpers (parallel to tables.py -modules kept independent) ────

def _signed(magnitude: str, value: Decimal) -> str:
    if value < 0:
        return f"({magnitude})"
    return magnitude


def _money(value: Decimal) -> str:
    return _signed(f"${abs(value):,.2f}", value)


def _money_whole(value: Decimal) -> str:
    return _signed(f"${abs(value):,.0f}", value)


def _money_k(value: Decimal) -> str:
    thousands = abs(int(value / 1000))
    return _signed(f"${thousands:,}K", value)


def _pct(value: Decimal) -> str:
    return f"{value:,.2f}%"


def _pct1(value: Decimal) -> str:
    return f"{value:.1f}%"


def _strip_markup(text: str) -> str:
    """Remove Rich markup tags from a string before writing to PDF."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


# ── PDF infrastructure ────────────────────────────────────────────────────────

class _ProspecPDF(FPDF):
    """FPDF subclass with a consistent page header and footer."""

    _report_title: str = ""
    _report_subtitle: str = ""

    def header(self) -> None:
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(*HEADER_BG)
        # Left: "Prospero" brand
        self.cell(40, 7, "Prospero", fill=True)
        # Centre: report title
        self.set_font("Helvetica", "", 9)
        centre_w = self.epw - 80
        self.cell(centre_w, 7, self._report_title, align="C", fill=True)
        # Right: generation date
        self.cell(40, 7, f"Generated: {datetime.date.today()}", align="R", fill=True)
        self.ln(10)
        if self._report_subtitle:
            self.set_font("Helvetica", "B", 11)
            self.cell(0, 6, self._report_subtitle, align="C")
            self.ln(8)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


def _new_pdf(title: str, subtitle: str = "") -> _ProspecPDF:
    pdf = _ProspecPDF(orientation="L", format="A4")
    pdf.set_margins(left=15, top=15, right=15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf._report_title = title
    pdf._report_subtitle = subtitle
    pdf.add_page()
    return pdf


def _section_heading(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, text)
    pdf.ln(7)


def _summary_box(pdf: FPDF, rows: list[tuple[str, str]], title: str = "") -> None:
    """Two-column label/value grid, analogous to a Rich Panel."""
    pdf.ln(4)
    if title:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, title)
        pdf.ln(6)
    pdf.set_font("Helvetica", "", 8)
    label_w = 80
    value_w = 60
    for label, value in rows:
        pdf.cell(label_w, 5, label)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(value_w, 5, value)
        pdf.set_font("Helvetica", "", 8)
        pdf.ln(5)


def _notes_block(pdf: FPDF, lines: list[str]) -> None:
    """Small italic disclaimer text."""
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(80, 80, 80)
    for line in lines:
        pdf.cell(0, 4, _strip_markup(line))
        pdf.ln(4)
    pdf.set_text_color(0, 0, 0)


# ── ACB pools ─────────────────────────────────────────────────────────────────

def pdf_acb_pools(
    pools: dict[str, AcbPoolEntry],
    path: Path,
    title: str = "Holdings & Cost Basis",
) -> None:
    """Write a PDF of current ACB pools to *path*."""
    pdf = _new_pdf("ACB Pools", title)

    has_cad = any(e.acb_per_share_cad is not None for e in pools.values())
    acb_col = "ACB / Share (CAD)" if has_cad else "ACB / Share (USD)"

    headings = ["Ticker", "Shares", acb_col, "Total ACB (USD)"]
    col_widths = [0.15, 0.20, 0.35, 0.30]

    pdf.set_font("Helvetica", "", 8)
    header_face = FontFace(fill_color=HEADER_BG, emphasis="BOLD")

    with pdf.table(
        col_widths=col_widths,
        text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
        headings_style=header_face,
        repeat_headings=1,
        cell_fill_color=STRIPE_BG,
        cell_fill_mode=TableCellFillMode.ROWS,
        line_height=5,
    ) as table:
        hrow = table.row()
        for h in headings:
            hrow.cell(h)
        for entry in sorted(pools.values(), key=lambda e: e.ticker):
            acb_display = (
                _money(entry.acb_per_share_cad)
                if has_cad and entry.acb_per_share_cad is not None
                else _money(entry.acb_per_share)
            )
            row = table.row()
            row.cell(entry.ticker)
            row.cell(str(entry.shares))
            row.cell(acb_display)
            row.cell(_money(entry.total_acb))

    pdf.output(str(path))


# ── Capital gains report ──────────────────────────────────────────────────────

def pdf_capital_gains_report(
    gains: list[CapitalGainEntry],
    year: int,
    path: Path,
    total_taxable_cad: Optional[Decimal] = None,
    pools: Optional[dict[str, AcbPoolEntry]] = None,
    pools_title: str = "Year End Holdings & Cost Basis",
) -> None:
    """
    Write a capital gains/losses PDF report for *year* to *path*.

    If *pools* is provided, a second section with the ACB pools table is appended
    to the same file (one combined PDF, as produced by `acb report`).
    """
    pdf = _new_pdf("ACB Report", f"Capital Gains / Losses - {year}")

    if not gains:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 8, f"No dispositions recorded for {year}.")
        pdf.output(str(path))
        return

    has_cad = any(g.capital_gain_cad is not None for g in gains)

    if has_cad:
        headings = [
            "Date", "Ticker", "Shares Sold",
            "Proceeds (USD)", "ACB Used (USD)", "Gain/Loss (USD)",
            "Exch (USD/CAD)", "Gain/Loss (CAD)", "Taxable (CAD)",
        ]
        col_widths = [0.09, 0.07, 0.08, 0.10, 0.10, 0.11, 0.10, 0.11, 0.10]
        text_align = ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT")
    else:
        headings = [
            "Date", "Ticker", "Shares Sold",
            "Proceeds (USD)", "ACB Used (USD)", "Gain/Loss (USD)",
        ]
        col_widths = [0.13, 0.10, 0.12, 0.22, 0.22, 0.21]
        text_align = ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT")

    pdf.set_font("Helvetica", "", 8)
    header_face = FontFace(fill_color=HEADER_BG, emphasis="BOLD")
    totals_face = FontFace(fill_color=TOTALS_BG, emphasis="BOLD")

    total_proceeds = sum((g.proceeds for g in gains), Decimal("0"))
    total_acb_used = sum((g.acb_used for g in gains), Decimal("0"))
    total_gain_usd = sum((g.capital_gain for g in gains), Decimal("0"))

    with pdf.table(
        col_widths=col_widths,
        text_align=text_align,
        headings_style=header_face,
        repeat_headings=1,
        cell_fill_color=STRIPE_BG,
        cell_fill_mode=TableCellFillMode.ROWS,
        line_height=5,
    ) as table:
        hrow = table.row()
        for h in headings:
            hrow.cell(h)

        for g in sorted(gains, key=lambda e: e.date):
            row = table.row()
            row.cell(str(g.date))
            row.cell(g.ticker)
            row.cell(str(g.shares_sold))
            row.cell(_money(g.proceeds))
            row.cell(_money(g.acb_used))
            row.cell(_money(g.capital_gain))
            if has_cad:
                row.cell(f"{g.exchange_rate:.4f}" if g.exchange_rate else "n/a")
                row.cell(_money(g.capital_gain_cad) if g.capital_gain_cad is not None else "n/a")
                row.cell(_money(g.taxable_gain_cad) if g.taxable_gain_cad is not None else "n/a")

        # Totals row
        trow = table.row(style=totals_face)
        trow.cell("")
        trow.cell("TOTAL")
        trow.cell("")
        trow.cell(_money(total_proceeds))
        trow.cell(_money(total_acb_used))
        trow.cell(_money(total_gain_usd))
        if has_cad:
            total_gain_cad = sum(
                (g.capital_gain_cad for g in gains if g.capital_gain_cad is not None),
                Decimal("0"),
            )
            total_taxable_row = sum(
                (g.taxable_gain_cad for g in gains if g.taxable_gain_cad is not None),
                Decimal("0"),
            )
            trow.cell("")
            trow.cell(_money(total_gain_cad))
            trow.cell(_money(total_taxable_row))

    # Summary box
    summary_rows: list[tuple[str, str]] = [
        ("Total capital gain / loss (USD):", _money(total_gain_usd)),
    ]
    if has_cad and total_taxable_cad is not None:
        total_gain_cad = sum(
            (g.capital_gain_cad for g in gains if g.capital_gain_cad is not None),
            Decimal("0"),
        )
        summary_rows += [
            ("Total capital gain / loss (CAD):", _money(total_gain_cad)),
            ("Taxable amount 50% (CAD):", _money(total_taxable_cad)),
        ]
    _summary_box(pdf, summary_rows, title=f"Tax Year {year} Summary (Canada -ON)")

    notes = []
    if has_cad and total_taxable_cad is not None:
        notes.append("Rates: Bank of Canada daily USD/CAD (weekends/holidays use prior business day)")
    notes += [
        "The 50% inclusion rate applies to net capital gains for 2024.",
        "Capital losses can offset gains in the same year, be carried back 3 years (T1A), or carried forward indefinitely.",
        "Superficial loss rule: a loss may be denied if you repurchase the same security within 30 days before or after the sale.",
        "For reference only -not professional tax advice.",
    ]
    _notes_block(pdf, notes)

    # Second section: ACB pools
    if pools:
        pdf.add_page()
        _section_heading(pdf, pools_title)
        has_cad_pools = any(e.acb_per_share_cad is not None for e in pools.values())
        acb_col = "ACB / Share (CAD)" if has_cad_pools else "ACB / Share (USD)"
        pool_headings = ["Ticker", "Shares", acb_col, "Total ACB (USD)"]
        pool_widths = [0.15, 0.20, 0.35, 0.30]

        with pdf.table(
            col_widths=pool_widths,
            text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
            headings_style=header_face,
            repeat_headings=1,
            cell_fill_color=STRIPE_BG,
            cell_fill_mode=TableCellFillMode.ROWS,
            line_height=5,
        ) as table:
            hrow = table.row()
            for h in pool_headings:
                hrow.cell(h)
            for entry in sorted(pools.values(), key=lambda e: e.ticker):
                acb_display = (
                    _money(entry.acb_per_share_cad)
                    if has_cad_pools and entry.acb_per_share_cad is not None
                    else _money(entry.acb_per_share)
                )
                row = table.row()
                row.cell(entry.ticker)
                row.cell(str(entry.shares))
                row.cell(acb_display)
                row.cell(_money(entry.total_acb))

    pdf.output(str(path))


# ── Wealth planner ────────────────────────────────────────────────────────────

def pdf_plan_summary(
    summary: PlanSummary,
    config: PlannerConfig,
    path: Path,
    every_n: int = 5,
) -> None:
    """Write a wealth projection PDF to *path*."""
    pdf = _new_pdf("Wealth Planner", "Wealth Projection (ON, Canada)")

    headings = ["Age", "Year", "Gross", "Tax", "Net Inc", "Expenses", "Saved", "Growth", "Net Worth"]
    col_widths = [0.07, 0.07, 0.11, 0.11, 0.11, 0.11, 0.09, 0.09, 0.13]
    text_align = ("RIGHT",) * 9

    transition_ages = set(summary.income_change_ages)

    pdf.set_font("Helvetica", "", 8)
    header_face = FontFace(fill_color=HEADER_BG, emphasis="BOLD")
    fire_face   = FontFace(emphasis="BOLD")           # bold for FIRE year
    trans_face  = FontFace(emphasis="BOLD")           # bold for transition years

    with pdf.table(
        col_widths=col_widths,
        text_align=text_align,
        headings_style=header_face,
        repeat_headings=1,
        cell_fill_color=STRIPE_BG,
        cell_fill_mode=TableCellFillMode.ROWS,
        line_height=5,
    ) as table:
        hrow = table.row()
        for h in headings:
            hrow.cell(h)

        for i, p in enumerate(summary.projections):
            is_fire_year = summary.fire_age is not None and p.age == summary.fire_age
            is_transition = p.age in transition_ages
            show = (
                i == 0
                or i == len(summary.projections) - 1
                or i % every_n == 0
                or is_fire_year
                or is_transition
            )
            if not show:
                continue

            style = fire_face if is_fire_year else (trans_face if is_transition else None)
            row = table.row(style=style)
            row.cell(str(p.age))
            row.cell(str(p.year))
            row.cell(_money_whole(p.income))
            row.cell(_money_whole(p.taxes))
            row.cell(_money_whole(p.net_income))
            row.cell(_money_k(p.expenses))
            row.cell(_money_k(p.savings_contribution))
            row.cell(_money_k(p.investment_growth))
            row.cell(_money_whole(p.net_worth))

    # Summary section
    outcome_rows: list[tuple[str, str]] = [
        ("Peak net worth:", _money_whole(summary.peak_net_worth)),
        ("Final net worth:", _money_whole(summary.final_net_worth)),
        ("FIRE age (4% rule):", str(summary.fire_age) if summary.fire_age is not None else "not reached"),
    ]
    _summary_box(pdf, outcome_rows, title="Outcomes")

    assumption_rows: list[tuple[str, str]] = [
        ("Annual return:", _pct1(config.annual_return_pct)),
        ("Inflation:", _pct1(config.inflation_pct)),
        ("Salary growth:", _pct1(config.salary_growth_pct)),
        ("Life expectancy:", str(config.life_expectancy)),
    ]
    _summary_box(pdf, assumption_rows, title="Key Assumptions")

    if transition_ages:
        change_rows: list[tuple[str, str]] = [
            (f"Age {config.current_age}:", f"{_money_whole(config.yearly_salary)}/yr (start)"),
        ]
        for p in summary.projections:
            if p.age in transition_ages:
                label = f"Age {p.age}:"
                value = "fully retired" if p.income == 0 else f"salary -> {_money_whole(p.income)}/yr"
                change_rows.append((label, value))
        _summary_box(pdf, change_rows, title="Income Changes (in future $)")

    pdf.output(str(path))


# ── Portfolio ─────────────────────────────────────────────────────────────────

def pdf_portfolio_summary(summary: PortfolioSummary, path: Path) -> None:
    """Write a portfolio valuation PDF to *path*."""
    pdf = _new_pdf("Portfolio", "Portfolio Valuation")

    headings = ["Ticker", "Date", "Qty", "Book", "Market", "Gain/Loss", "G/L %"]
    col_widths = [0.10, 0.13, 0.10, 0.15, 0.15, 0.15, 0.12]
    text_align = ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT")

    pdf.set_font("Helvetica", "", 8)
    header_face = FontFace(fill_color=HEADER_BG, emphasis="BOLD")
    totals_face = FontFace(fill_color=TOTALS_BG, emphasis="BOLD")

    total_book   = summary.total_book_value
    total_market = summary.total_market_value
    total_gl     = summary.total_gain_loss
    total_gl_pct = summary.total_gain_loss_pct

    with pdf.table(
        col_widths=col_widths,
        text_align=text_align,
        headings_style=header_face,
        repeat_headings=1,
        cell_fill_color=STRIPE_BG,
        cell_fill_mode=TableCellFillMode.ROWS,
        line_height=5,
    ) as table:
        hrow = table.row()
        for h in headings:
            hrow.cell(h)
        for v in summary.valuations:
            row = table.row()
            row.cell(v.holding.ticker)
            row.cell(str(v.holding.purchase_date))
            row.cell(str(v.holding.quantity))
            row.cell(_money(v.book_value))
            row.cell(_money(v.market_value))
            row.cell(_money(v.gain_loss))
            row.cell(_pct(v.gain_loss_pct))

        trow = table.row(style=totals_face)
        trow.cell("TOTAL")
        trow.cell("")
        trow.cell("")
        trow.cell(_money(total_book))
        trow.cell(_money(total_market))
        trow.cell(_money(total_gl))
        trow.cell(_pct(total_gl_pct))

    _summary_box(pdf, [
        ("Total book value:", _money(total_book)),
        ("Total market value:", _money(total_market)),
        ("Total gain/loss:", f"{_money(total_gl)} ({_pct(total_gl_pct)})"),
    ], title="Portfolio Summary")

    pdf.output(str(path))


# ── Tax breakdown ─────────────────────────────────────────────────────────────

def pdf_tax_breakdown(breakdown: TaxBreakdown, path: Path) -> None:
    """Write a tax breakdown PDF to *path*."""
    pdf = _new_pdf("Tax Breakdown", f"Tax Breakdown - {_money_whole(breakdown.income)} income (ON, 2025 base rates)")

    def _pct_of_income(value: Decimal) -> str:
        if breakdown.income == 0:
            return "n/a"
        return f"{value / breakdown.income * 100:.1f}%"

    headings = ["Component", "Amount", "% of gross"]
    col_widths = [0.55, 0.25, 0.20]
    text_align = ("LEFT", "RIGHT", "RIGHT")

    pdf.set_font("Helvetica", "", 8)
    header_face = FontFace(fill_color=HEADER_BG, emphasis="BOLD")
    totals_face = FontFace(fill_color=TOTALS_BG, emphasis="BOLD")

    rows: list[tuple[str, Decimal, bool]] = [
        ("Federal income tax", breakdown.federal, False),
        ("Ontario income tax", breakdown.ontario_base, False),
    ]
    if breakdown.ontario_surtax > 0:
        rows.append(("  Ontario surtax", breakdown.ontario_surtax, False))
    rows.append(("CPP1", breakdown.cpp1, False))
    if breakdown.cpp2 > 0:
        rows.append(("CPP2", breakdown.cpp2, False))
    rows.append(("EI", breakdown.ei, False))

    with pdf.table(
        col_widths=col_widths,
        text_align=text_align,
        headings_style=header_face,
        cell_fill_color=STRIPE_BG,
        cell_fill_mode=TableCellFillMode.ROWS,
        line_height=5,
    ) as table:
        hrow = table.row()
        for h in headings:
            hrow.cell(h)
        for label, value, _ in rows:
            row = table.row()
            row.cell(label)
            row.cell(_money_whole(value))
            row.cell(_pct_of_income(value))

        # Total deductions
        trow = table.row(style=totals_face)
        trow.cell("Total deductions")
        trow.cell(_money_whole(breakdown.total))
        trow.cell(_pct_of_income(breakdown.total))

        # Take-home
        trow2 = table.row(style=totals_face)
        trow2.cell("Take-home")
        trow2.cell(_money_whole(breakdown.take_home))
        trow2.cell(_pct_of_income(breakdown.take_home))

    pdf.output(str(path))


# ── Import preview ────────────────────────────────────────────────────────────

def pdf_import_preview(
    transactions: list[StockTransaction],
    path: Path,
    fx_rates: dict,
    acb_used_map: dict,
    pool_acb_after_map: dict,
    pool_units_after_map: dict,
    pool_acb_cad_after_map: dict,
) -> None:
    """Write an import preview PDF to *path*."""
    pdf = _new_pdf("ACB Import", f"Import Preview - {len(transactions)} transaction(s)")

    headings = [
        "Date", "Type", "Ticker", "Units", "Total Units",
        "Price (USD)", "ACB Used (USD)", "Total ACB (USD)",
        "Exch (USD/CAD)", "Total ACB (CAD)",
    ]
    col_widths = [0.09, 0.07, 0.07, 0.07, 0.09, 0.10, 0.11, 0.11, 0.10, 0.11]
    text_align = ("LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT")

    pdf.set_font("Helvetica", "", 8)
    header_face = FontFace(fill_color=HEADER_BG, emphasis="BOLD")

    with pdf.table(
        col_widths=col_widths,
        text_align=text_align,
        headings_style=header_face,
        repeat_headings=1,
        cell_fill_color=STRIPE_BG,
        cell_fill_mode=TableCellFillMode.ROWS,
        line_height=5,
    ) as table:
        hrow = table.row()
        for h in headings:
            hrow.cell(h)

        for tx in sorted(transactions, key=lambda t: t.date):
            rate = fx_rates.get(tx.date)
            rate_str = f"{rate:.4f}" if rate is not None else "n/a"
            acb_used = acb_used_map.get(id(tx))
            acb_str = f"${acb_used:,.2f}" if acb_used is not None else "n/a"
            pool_acb = pool_acb_after_map.get(id(tx))
            pool_str = f"${pool_acb:,.2f}" if pool_acb is not None else "n/a"
            pool_units = pool_units_after_map.get(id(tx))
            units_str = str(pool_units) if pool_units is not None else "n/a"
            pool_acb_cad = pool_acb_cad_after_map.get(id(tx))
            cad_str = f"${pool_acb_cad:,.2f}" if pool_acb_cad is not None else "n/a"
            is_sell = tx.transaction_type == TransactionType.SELL
            qty_str = f"-{tx.quantity}" if is_sell else str(tx.quantity)

            row = table.row()
            row.cell(str(tx.date))
            row.cell(tx.transaction_type.value)
            row.cell(tx.ticker)
            row.cell(qty_str)
            row.cell(units_str)
            row.cell(f"${tx.price_per_share:,.2f}")
            row.cell(acb_str)
            row.cell(pool_str)
            row.cell(rate_str)
            row.cell(cad_str)

    pdf.output(str(path))
