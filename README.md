# prospero

Financial simulation CLI — portfolio tracker and long-term wealth planner with Canadian (Ontario) tax support.

<details>
<summary><b>Disclaimer:</b></summary>

<small><i>This tool is for educational and illustrative purposes only. All projections and calculations are simplified simulations based on assumptions you provide; they are not predictions of future results. Nothing produced by this tool constitutes financial, tax, or investment advice. Consult a qualified financial advisor before making financial decisions.</i></small>
</details>

<img src="screenshot-configure.png" width="69%">
<img src="screenshot-plan-table.png" width="100%">
<img src="screenshot-tax-breakdown.png" width="43%">

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### Portfolio Tracker

```bash
# Add holdings
prospero portfolio add --ticker AAPL --date 2024-01-15 --quantity 10 --price 185.50
prospero portfolio add --ticker GOOG --date 2024-06-01 --quantity 5 --price 175.00

# View holdings (book values)
prospero portfolio show

# Fetch live prices and show valuation with gains/losses
prospero portfolio value

# Remove a holding
prospero portfolio remove --ticker AAPL --date 2024-01-15
```

### Wealth Planner

```bash
# Configure your plan (interactive prompts, with optional income changes)
prospero plan configure

# Configure with income changes: semi-retire at 55, fully retire at 65
prospero plan configure --income-change 55:80000 --income-change 65:0

# Auto-retire the year after reaching FIRE (4% rule)
prospero plan configure --income-change 0:0

# Run projection
prospero plan run

# Show every year (default: every 5th)
prospero plan run --every 1

# View saved config
prospero plan show-config
```

### Tax Breakdown

```bash
# Show a detailed tax breakdown for a given income
prospero tax-breakdown --income 150000

# Uses your configured salary if --income is omitted
prospero tax-breakdown
```

Breaks down federal income tax, Ontario income tax (including surtax), CPP1, CPP2, and EI — showing the amount and percentage of gross for each component.

### Tax Support

The wealth planner calculates taxes using 2025 Canadian federal + Ontario provincial rates:

- Federal progressive income tax brackets
- Ontario progressive brackets + Ontario surtax
- CPP/CPP2 employee contributions
- EI premiums
- Bracket indexation to inflation over time

### Income Changes

Use `--income-change AGE:SALARY` (repeatable) to model salary transitions at any age:

- `--income-change 65:0` — fully retire at 65
- `--income-change 55:80000 --income-change 65:0` — semi-retire at 55 to $80K, fully retire at 65
- `--income-change 0:0` — auto-retire the year after reaching FIRE (age `0` is the FIRE sentinel)
- Omit entirely — work indefinitely at the configured salary

Each new salary is a hard reset at that age; the global `salary_growth_pct` then applies from there forward.

## Data Storage

Portfolio and planner config are stored in `~/.prospero/`:
- `portfolio.json` — stock holdings
- `planner.toml` — planner configuration

## Tests

```bash
pytest -v
```

## Future Projects

- **RRSP / TFSA modeling** — tax-sheltered accounts are a major factor in Canadian wealth planning
- **Capital gains tax** on investment growth — currently the planner ignores tax on withdrawals
- **Multiple income sources** — CPP/OAS pension income after 65, rental income, etc.
- **Historical portfolio simulation** — backtest portfolio value over time using actual price history
- **Export** — JSON/CSV output for projection tables and portfolio reports
