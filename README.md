# fin-sim

Financial simulation CLI — portfolio tracker and long-term wealth planner with Canadian (Ontario) tax support.

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
fin-sim portfolio add --ticker AAPL --date 2024-01-15 --quantity 10 --price 185.50
fin-sim portfolio add --ticker GOOG --date 2024-06-01 --quantity 5 --price 175.00

# View holdings (book values)
fin-sim portfolio show

# Fetch live prices and show valuation with gains/losses
fin-sim portfolio value

# Remove a holding
fin-sim portfolio remove --ticker AAPL --date 2024-01-15
```

### Wealth Planner

```bash
# Configure your plan
fin-sim plan configure \
  --current-age 30 \
  --life-expectancy 90 \
  --current-savings 100000 \
  --yearly-salary 150000 \
  --yearly-expenses 80000 \
  --annual-return-pct 7 \
  --inflation-pct 3 \
  --salary-growth-pct 3 \
  --retirement-age 0  # 0 = auto-retire at FIRE, omit = work forever

# Run projection
fin-sim plan run

# Show every year (default: every 5th)
fin-sim plan run --every 1

# View saved config
fin-sim plan show-config
```

### Tax Support

The wealth planner calculates taxes using 2025 Canadian federal + Ontario provincial rates:

- Federal progressive income tax brackets
- Ontario progressive brackets + Ontario surtax
- CPP/CPP2 employee contributions
- EI premiums
- Bracket indexation to inflation over time

### Retirement Modes

- `--retirement-age 65` — stop working at age 65
- `--retirement-age 0` — auto-retire the year after reaching FIRE (4% rule)
- Omit — work indefinitely

## Data Storage

Portfolio and planner config are stored in `~/.fin-sim/`:
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
