# CLAUDE.md

## Project Overview

**Prospero** is a financial simulation CLI for portfolio tracking and long-term wealth planning with Canadian (Ontario) tax support. Four tools, each installable as a standalone command:

| Entry point | Subcommand group | Description |
|---|---|---|
| `prospero-portfolio` | `prospero portfolio` | Add/remove holdings, fetch live prices, show gains/losses |
| `prospero-plan` | `prospero plan` | Project net worth year-by-year with salary changes, retirement, FIRE detection, and taxes |
| `prospero-acb` | `prospero acb` | Compute Adjusted Cost Basis and capital gains/losses for Canadian tax filing |
| `prospero-tax` | `prospero tax-breakdown` | Canadian income tax breakdown (ON, 2025 base rates) |

All read commands accept `--json` for machine-readable output.

Per-tool documentation: [docs/portfolio.md](docs/portfolio.md), [docs/planner.md](docs/planner.md), [docs/acb.md](docs/acb.md), [docs/tax.md](docs/tax.md).

Data is stored in `~/.prospero/`:
- `planner.toml` — human-editable planner config
- `portfolio.json` — stock holdings
- `acb_ledger.json` — ACB transaction history
- `fx_rates_cache.json` — cached Bank of Canada USD/CAD rates

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

## Adding a New Tool

1. Create `src/prospero/cli/new_feature.py` with its own `app = typer.Typer(...)` and commands.
2. Wire into `cli/app.py`: `app.add_typer(new_feature.app, name="feature", help="...")`.
3. Add entry point to `pyproject.toml`: `prospero-feature = "prospero.cli.new_feature:app"`.
4. Add `docs/new_feature.md` with usage documentation.

To re-expose a standalone app command as a top-level `prospero` shortcut (like `tax-breakdown`):
```python
# in cli/app.py
app.command("my-shortcut")(new_feature_cli.my_command)
```

## Non-Obvious Behaviours

**Income changes are in today's dollars.** When the user sets `--income-change 55:80000`, the $80k is inflated forward to the transition year using `inflation_pct` during projection. This keeps user input intuitive across long time horizons.

**FIRE detection uses the 4% rule.** Each year: if `net_worth × 0.04 >= expenses`, FIRE is reached. Income changes with `age=0` trigger the year *after* FIRE is detected.

**Tax brackets are inflation-adjusted.** `calculate_tax_breakdown()` takes `years_from_base` and `inflation_rate` to widen bracket thresholds over time, preventing bracket creep.

**`calculate_total_tax` delegates to `calculate_tax_breakdown`.** The breakdown function is the canonical implementation; `calculate_total_tax` is a thin wrapper returning `.total`. Both the planner engine and `tax-breakdown` command share the same logic.

**Backward compatibility.** Old config files used `retirement_age` (single value). A Pydantic `@model_validator(mode='before')` in `PlannerConfig` auto-migrates to the new `income_changes` list on load.

**Display filtering.** The projection table shows every Nth year (`--every N`, default 5), but always includes the first year, last year, FIRE year, and any income-change transition years.

## ACB Feature

For ACB business logic, design decisions, and non-obvious engine behaviours, see [docs/acb-internals.md](docs/acb-internals.md).

## Running the Project

```bash
uv sync --extra dev
uv run prospero --help
```

## Running Tests

```bash
uv run pytest -v               # all tests
uv run pytest tests/test_tax.py
uv run pytest -k fire          # filter by keyword
```

Dev dependencies (pytest etc.) are in the `dev` extra. If pytest is not found, run `uv sync --extra dev` first.

Tests use `tmp_path` + `monkeypatch` to redirect `DATA_DIR` — they never touch `~/.prospero/`.

## PDF Export

Selected read commands support `--pdf PATH` to write a formatted PDF alongside the normal terminal output. The flag is additive — terminal output always appears, and the PDF is written in addition.

**Commands with `--pdf`:**
- `prospero acb report` — combined PDF: capital gains table + year-end ACB pools (two pages/sections in one file)
- `prospero acb show` — ACB pools table
- `prospero plan run` — wealth projection table + summary
- `prospero portfolio value` — portfolio valuation table + summary
- `prospero tax-breakdown` — tax breakdown table

**Architecture:**
- `PDF_OPTION` is defined once in `src/prospero/cli/_options.py` and imported by each CLI module — not redefined per command.
- All PDF rendering lives in `src/prospero/display/pdf.py`, parallel to `display/tables.py`. One `pdf_*` function per `render_*` function.
- PDFs are black-and-white (grayscale only). Negative values use parentheses accounting notation `($1,234.56)` rather than colour.
- Built-in Helvetica font is used (latin-1 encoding). Avoid non-latin-1 characters (e.g. em dash `—`) in any strings written to PDF cells.

## README Screenshots

Screenshots are embedded using HTML `<img>` tags with percentage widths, scaled proportionally to each image's native pixel width so they render at a consistent apparent terminal font size.

To add a new screenshot:
1. Check native widths: `python3 -c "import struct; [print(f, struct.unpack('>I', open(f,'rb').read()[16:20])[0]) for f in ['s1.png', 's2.png']]"`
2. The widest image gets `width="100%"`; scale others as `round(w / max_w * 100)%`.
3. Use `<img src="screenshot-name.png" width="XX%">` in README.md.
