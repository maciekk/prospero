# CLAUDE.md

## Project Overview

**Prospero** is a financial simulation CLI for portfolio tracking and long-term wealth planning with Canadian (Ontario) tax support. Two main features:
- **Portfolio tracker** — add/remove holdings, fetch live prices, show gains/losses
- **Wealth planner** — project net worth year-by-year with salary changes, retirement, FIRE detection, and taxes

## Project Structure

```
src/prospero/
├── cli/
│   ├── app.py          Root Typer app — wires subapps, hosts top-level commands (e.g. tax-breakdown)
│   ├── planner.py      Wealth planner commands (configure, run, show-config)
│   └── portfolio.py    Portfolio commands (add, remove, show, value)
├── models/
│   ├── planner.py      PlannerConfig, IncomeChange, YearProjection, PlanSummary
│   └── portfolio.py    Holding, Portfolio, HoldingValuation, PortfolioSummary
├── services/
│   ├── planner_engine.py   project() — runs the year-by-year simulation
│   ├── portfolio_engine.py valuate() — computes current market value / gains
│   └── tax.py              calculate_tax_breakdown(), calculate_total_tax(), TaxBreakdown
├── storage/
│   └── store.py        load/save for planner (TOML) and portfolio (JSON)
└── display/
    └── tables.py       Rich table rendering for all output

tests/
├── test_planner_engine.py  Most comprehensive — covers income changes, FIRE, draw-down
├── test_tax.py             Bracket tests, CPP/EI caps, bracket inflation
├── test_portfolio_engine.py Gains/losses, totals
└── test_storage.py         Roundtrip persistence, backward-compat migration
```

Data is stored in `~/.prospero/`:
- `planner.toml` — human-editable planner config
- `portfolio.json` — stock holdings

## Architecture

Five layers with clear separation:

1. **CLI** — parses user input, calls services, invokes display
2. **Models** — Pydantic v2 `BaseModel` for all data structures
3. **Services** — stateless calculation functions (no I/O)
4. **Storage** — persistence wrappers (load returns None / empty on missing files)
5. **Display** — Rich tables/panels; formatting helpers `_money()`, `_pct()` etc.

## Key Conventions

- **Decimal everywhere** — all currency/rate values use `Decimal`, never `float`. Use `Decimal(str(x))` when converting from int/float.
- All CLI inputs are `typer.Option()` (no positional args).
- Private helpers prefixed with `_`.
- Services are pure functions — no side effects, no I/O.

## Adding a New Top-Level Command

Add directly to `cli/app.py`:
```python
@app.command("my-command")
def my_command(...) -> None:
    """Help text."""
    ...
```

## Adding a New Subcommand Group

1. Create `src/prospero/cli/new_feature.py` with its own `app = typer.Typer(...)`.
2. Wire into `cli/app.py`: `app.add_typer(new_feature.app, name="feature", help="...")`.

## Non-Obvious Behaviours

**Income changes are in today's dollars.** When the user sets `--income-change 55:80000`, the $80k is inflated forward to the transition year using `inflation_pct` during projection. This keeps user input intuitive across long time horizons.

**FIRE detection uses the 4% rule.** Each year: if `net_worth × 0.04 >= expenses`, FIRE is reached. Income changes with `age=0` trigger the year *after* FIRE is detected.

**Tax brackets are inflation-adjusted.** `calculate_tax_breakdown()` takes `years_from_base` and `inflation_rate` to widen bracket thresholds over time, preventing bracket creep.

**`calculate_total_tax` delegates to `calculate_tax_breakdown`.** The breakdown function is the canonical implementation; `calculate_total_tax` is a thin wrapper returning `.total`. Both the planner engine and `tax-breakdown` command share the same logic.

**Backward compatibility.** Old config files used `retirement_age` (single value). A Pydantic `@model_validator(mode='before')` in `PlannerConfig` auto-migrates to the new `income_changes` list on load.

**Display filtering.** The projection table shows every Nth year (`--every N`, default 5), but always includes the first year, last year, FIRE year, and any income-change transition years.

## Running the Project

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
prospero --help
```

## Running Tests

```bash
pytest -v               # all tests
pytest tests/test_tax.py
pytest -k fire          # filter by keyword
```

Tests use `tmp_path` + `monkeypatch` to redirect `DATA_DIR` — they never touch `~/.prospero/`.

## README Screenshots

Screenshots are embedded using HTML `<img>` tags with percentage widths, scaled proportionally to each image's native pixel width so they render at a consistent apparent terminal font size.

To add a new screenshot:
1. Check native widths: `python3 -c "import struct; [print(f, struct.unpack('>I', open(f,'rb').read()[16:20])[0]) for f in ['s1.png', 's2.png']]"`
2. The widest image gets `width="100%"`; scale others as `round(w / max_w * 100)%`.
3. Use `<img src="screenshot-name.png" width="XX%">` in README.md.
