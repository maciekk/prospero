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

#### Income Changes

Use `--income-change AGE:SALARY` (repeatable) to model salary transitions at any age:

- `--income-change 65:0` — fully retire at 65
- `--income-change 55:80000 --income-change 65:0` — semi-retire at 55 to $80K, fully retire at 65
- `--income-change 0:0` — auto-retire the year after reaching FIRE (age `0` is the FIRE sentinel)
- Omit entirely — work indefinitely at the configured salary

Each new salary is a hard reset at that age; the global `salary_growth_pct` then applies from there forward.

#### Tax Support

The wealth planner calculates taxes using 2025 Canadian federal + Ontario provincial rates:

- Federal progressive income tax brackets
- Ontario progressive brackets + Ontario surtax
- CPP/CPP2 employee contributions
- EI premiums
- Bracket indexation to inflation over time

### Tax Breakdown

```bash
# Show a detailed tax breakdown for a given income
prospero tax-breakdown --income 150000

# Uses your configured salary if --income is omitted
prospero tax-breakdown
```

Breaks down federal income tax, Ontario income tax (including surtax), CPP1, CPP2, and EI — showing the amount and percentage of gross for each component.

### ACB Tracker

Track Adjusted Cost Basis for Canadian stock grants (RSUs) and compute capital gains/losses for tax filing.

**Workflow:**
1. Import your broker's transaction history (or enter events manually)
   - Transactions are saved to a local ledger (`~/.prospero/acb_ledger.json`)
   - If the ledger gets into a bad state, just delete that file and re-import
2. Run `prospero acb report` for capital gains/losses, or `prospero acb show` for current ACB pools

**Background:** When RSUs vest, CRA treats the fair market value (FMV) at vest as employment income — it appears on your T4. This means the ACB of your vested shares equals the FMV at vest. When you sell, only the appreciation *after* vesting is a capital gain. Canada uses the **identical-shares average cost method**: all shares of the same ticker form one ACB pool, and the per-share ACB is always `total_acb / total_shares`.

#### Morgan Stanley Activity Report

If your broker is Morgan Stanley, unpack the Activity Report zip and point `import-ms` at the folder — no manual CSV prep needed.

> [!NOTE]
> If you held shares before your earliest activity report (common when importing only the current tax year), the import will fail with an oversell error. Seed the ledger first:
>
> 1. Log in to MS Stockplan Connect → Reports → Vested Share Holdings
> 2. Set the date to **Dec 31 of the year before your earliest import** (e.g. Dec 31, 2024 if importing 2025 activity)
> 3. Note *Number of Shares* and *Acquisition Value* for your ticker
>    *(MS defines Acquisition Value as FMV at vest × shares held, which equals total ACB for RSUs)*
> 4. Run:
>    ```bash
>    prospero acb add-opening-balance --ticker GOOG --date 2024-12-31 \
>      --shares <Number of Shares> --opening-acb-usd <Acquisition Value>
>    ```

```bash
prospero acb import-ms --dir ~/Downloads/MS-activity-report-2025 --ticker GOOG --dry-run
prospero acb import-ms --dir ~/Downloads/MS-activity-report-2025 --ticker GOOG
```

The ticker must be supplied as it is not included in the MS files. `--dry-run` previews without saving.

#### CSV Import

For other brokers, prepare a CSV from your transaction history with these columns:

```
date,type,ticker,quantity,price
2024-01-15,vest,AAPL,25,185.50
2024-03-01,buy,AAPL,10,190.00
2024-06-15,sell,AAPL,20,210.00
```

| Column | Format | Notes |
|---|---|---|
| `date` | YYYY-MM-DD | Transaction date |
| `type` | `vest` / `buy` / `sell` | Case-insensitive |
| `ticker` | e.g. `AAPL` | Uppercased automatically |
| `quantity` | positive number | Shares involved |
| `price` | price per share | FMV for vest; purchase price for buy; proceeds for sell |

```bash
# Preview without saving
prospero acb import --file transactions.csv --dry-run

# Import (validates all rows before writing — reports every error at once)
prospero acb import --file transactions.csv
```

#### Manual entry

```bash
# Record an RSU vesting event (FMV at vest = ACB)
prospero acb add-vest --ticker AAPL --date 2024-01-15 --quantity 25 --fmv 185.50

# Record a regular market purchase
prospero acb add-buy --ticker AAPL --date 2024-03-01 --quantity 10 --price 190.00

# Record a sale
prospero acb add-sell --ticker AAPL --date 2024-06-15 --quantity 20 --price 210.00
```

#### Reporting

```bash
# Show current ACB pools (remaining shares and average cost per ticker)
prospero acb show

# Capital gains/losses for a tax year (defaults to the previous calendar year)
prospero acb report
prospero acb report --year 2024
```

The report shows proceeds, ACB used, and capital gain/loss per sale, with the 50% inclusion amount (the portion added to taxable income). It also notes the superficial loss rule and capital loss carryover rules.

Data is stored in `~/.prospero/acb_ledger.json`. Broker CSVs vary — massage your export to match the format above.

#### Manually verifying the report

After running `prospero acb report`, cross-check against your broker statement using these steps:

**1. Transaction count**

Count the vest/release rows and sale rows in your broker's activity report. The number of SELL rows in `acb report` and VEST rows visible in `acb show` should match. A mismatch means a transaction was missed or duplicated.

**2. Proceeds per sale**

For each row in the capital gains report, confirm **Shares Sold** and **Proceeds** against your trade confirmation:

- Shares Sold should equal the "Quantity" on the trade confirm
- Proceeds should equal `quantity × price per share` from the confirm (the tool uses the price in your CSV, which should be the gross sale price; if your broker deducted commissions from proceeds, the tool's number will be slightly higher)

**3. Manually reconstruct ACB Used for one sale**

Pick one SELL row and replay the acquisitions before it in chronological order:

1. List every VEST/BUY before that date with `(quantity, price_per_share)`
2. For any prior SELLs, remove the proportional ACB: `acb_removed = shares_sold × (running_total_acb / running_total_shares)`
3. After replaying: `acb_per_share = total_acb / total_shares`
4. `ACB Used = shares_sold × acb_per_share`

The "ACB Used" column in the report should match to the cent.

**4. Running share count**

After the report, `prospero acb show` displays current ACB pools. For each ticker, confirm:

```
shares in pool = sum(all VESTs + BUYs) − sum(all SELLs)
```

This should match your current account position at the broker.

**5. CAD gain sanity check (if using `--cad`)**

For each row, `Gain (CAD) ≈ Gain (USD) × exchange_rate_on_sell_date`. This is approximate because the ACB side uses historical rates (one per vest date), while proceeds use the sell-date rate. A divergence larger than ~5% usually means a vest date was missing an FX rate and the tool fell back to USD cost. Verify the "Rate" column against the [Bank of Canada daily rates](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/) for that date.

**6. Schedule 3 — T1 filing**

The "Taxable amount 50% (CAD)" in the summary panel is what goes on **Schedule 3, line 19900** of your T1. Confirm it equals `Total capital gain / loss (CAD) × 0.50`.

*For reference only — not professional tax advice.*

## Data Storage

Portfolio and planner config are stored in `~/.prospero/`:
- `portfolio.json` — stock holdings
- `planner.toml` — planner configuration
- `acb_ledger.json` — ACB transaction history

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
