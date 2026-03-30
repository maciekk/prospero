# Sample Data

Fictional Morgan Stanley GSU activity for ticker **ACME** (Acme Corp).
Mirrors the real MS Activity Report format used by `prospero acb import-ms`.

## What's here

```
complete/
  Releases Net Shares Report.csv   — 39 monthly vest events (Jan 2023 – Mar 2026)
  Withdrawals Report.csv           — 7 sell events (May 2023 – Dec 2025)
```

ACME's fictitious price starts around $100 in early 2023 and rises to ~$293 by March 2026.

## Loading the sample data

Run `process-csv.sh` to wipe the ledger and load from scratch:

```bash
bash data-sample/process-csv.sh
```

Or step through it manually:

```bash
# 1. Seed shares held before the activity report begins
uv run prospero acb add-opening-balance \
  --ticker ACME \
  --date 2022-12-31 \
  --shares 287.500 \
  --opening-acb-usd 23806.25

# 2. Import the MS activity report
uv run prospero acb import-ms --dir data-sample/complete --ticker ACME

# 3. View reports
uv run prospero acb report --year 2023
uv run prospero acb report --year 2024
uv run prospero acb report --year 2025
```

## Opening balance rationale

| Parameter          | Value        | Notes                                              |
|--------------------|--------------|----------------------------------------------------|
| `--date`           | `2022-12-31` | One day before the first vest on 25-Jan-2023       |
| `--shares`         | `287.500`    | Shares held prior to the activity report           |
| `--opening-acb-usd`| `23806.25`   | ≈ $82.80/share avg cost — below the Jan 2023 FMV  |

The opening ACB comes from a broker cost-basis statement (e.g. the "Acquisition Value" column in the Schwab/MS cost basis report). It represents the total adjusted cost of all shares held as of that date, in USD.
