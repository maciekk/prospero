# prospero-portfolio

Stock portfolio tracker — add holdings, fetch live prices, and see gains/losses.

## Commands

```bash
# Add a holding
prospero-portfolio add --ticker AAPL --date 2024-01-15 --quantity 10 --price 185.50

# List all holdings with book values
prospero-portfolio show

# Fetch live prices and show valuation with gains/losses
prospero-portfolio value

# Remove a holding (all lots for ticker, or a specific lot by date)
prospero-portfolio remove --ticker AAPL
prospero-portfolio remove --ticker AAPL --date 2024-01-15
```

The `prospero portfolio` subcommand group works identically:

```bash
prospero portfolio add --ticker GOOG --date 2024-06-01 --quantity 5 --price 175.00
prospero portfolio value
```

## JSON output

All read commands accept `--json` for machine-readable output:

```bash
prospero-portfolio show --json
prospero-portfolio value --json
```

`value --json` outputs a `PortfolioSummary` with per-holding valuations, total market value, total book value, and overall gain/loss.

## Data storage

Holdings are stored in `~/.prospero/portfolio.json`.
