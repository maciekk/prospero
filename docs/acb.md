# prospero-acb

Adjusted Cost Basis (ACB) tracker for Canadian stock grants (RSUs) and capital gains/losses reporting.

Canada uses the **identical-shares average cost method** (ITA s.47): all shares of the same ticker form one ACB pool. The per-share ACB is always `total_acb / total_shares`. When RSUs vest, CRA treats the FMV at vest as employment income (reported on your T4), so the ACB equals FMV — only appreciation after vesting is a capital gain on eventual sale.

## Workflow

1. Import your broker's transaction history (or enter events manually)
   - Transactions are saved to `~/.prospero/acb_ledger.json`
   - If the ledger gets into a bad state, just delete that file and re-import
2. Run `prospero-acb report` for capital gains/losses, or `prospero-acb show` for current ACB pools

The `prospero acb` subcommand group works identically.

## Morgan Stanley Activity Report

Unpack the Activity Report zip and point `import-ms` at the folder — no manual CSV prep needed.

> [!NOTE]
> If you held shares before your earliest activity report (common when importing only the current tax year), the import will fail with an oversell error. Seed the ledger first:
>
> 1. Log in to MS Stockplan Connect → Reports → Vested Share Holdings
> 2. Set the date to **Dec 31 of the year before your earliest import** (e.g. Dec 31, 2024 if importing 2025 activity)
> 3. Note *Number of Shares* and *Acquisition Value* for your ticker
>    *(MS defines Acquisition Value as FMV at vest × shares held, which equals total ACB for RSUs)*
> 4. Run:
>    ```bash
>    prospero-acb add-opening-balance --ticker GOOG --date 2024-12-31 \
>      --shares <Number of Shares> --opening-acb-usd <Acquisition Value>
>    ```

```bash
prospero-acb import-ms --dir ~/Downloads/MS-activity-report-2025 --ticker GOOG --dry-run
prospero-acb import-ms --dir ~/Downloads/MS-activity-report-2025 --ticker GOOG
```

The ticker must be supplied as it is not included in the MS files. `--dry-run` previews without saving.

## CSV import

For other brokers, prepare a CSV from your transaction history:

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
prospero-acb import --file transactions.csv --dry-run

# Import (validates all rows before writing — reports every error at once)
prospero-acb import --file transactions.csv
```

## Manual entry

```bash
# Seed shares held before your transaction history begins
prospero-acb add-opening-balance --ticker GOOG --date 2024-12-31 \
  --shares 100 --opening-acb-usd 15000

# Record an RSU vesting event (FMV at vest = ACB)
prospero-acb add-vest --ticker AAPL --date 2024-01-15 --quantity 25 --fmv 185.50

# Record a regular market purchase
prospero-acb add-buy --ticker AAPL --date 2024-03-01 --quantity 10 --price 190.00

# Record a sale
prospero-acb add-sell --ticker AAPL --date 2024-06-15 --quantity 20 --price 210.00
```

## Reporting

```bash
# Show current ACB pools (remaining shares and average cost per ticker)
prospero-acb show

# Capital gains/losses for a tax year (defaults to the previous calendar year)
prospero-acb report
prospero-acb report --year 2024
```

The report shows proceeds, ACB used, and capital gain/loss per sale, with the 50% inclusion amount (the portion added to taxable income). It also notes the superficial loss rule and capital loss carryover rules. Bank of Canada USD/CAD rates are fetched automatically to show CAD amounts.

## JSON output

```bash
prospero-acb show --json
prospero-acb report --year 2024 --json
```

`report --json` outputs `{ "year", "gains": [...], "pools": [...], "total_taxable_cad" }`.

## Data storage

Transactions are stored in `~/.prospero/acb_ledger.json`. Exchange rates are cached in `~/.prospero/fx_rates_cache.json` to avoid repeated Bank of Canada API calls.
