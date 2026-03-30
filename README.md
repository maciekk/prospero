# prospero

Financial simulation CLI — portfolio tracker and long-term wealth planner with Canadian (Ontario) tax support.

<details>
<summary><b>Disclaimer:</b></summary>

<small><i>This tool is for educational and illustrative purposes only. All projections and calculations are simplified simulations based on assumptions you provide; they are not predictions of future results. Nothing produced by this tool constitutes financial, tax, or investment advice. Consult a qualified financial advisor before making financial decisions.</i></small>
</details>

## Tools

| Command | Description | Docs |
|---|---|---|
| `prospero-portfolio` | Add holdings, fetch live prices, see gains/losses | [docs/portfolio.md](docs/portfolio.md) |
| `prospero-plan` | Project net worth year-by-year, FIRE detection, retirement modelling | [docs/planner.md](docs/planner.md) |
| `prospero-acb` | ACB tracker for Canadian RSUs and capital gains reporting | [docs/acb.md](docs/acb.md) |
| `prospero-tax` | Canadian income tax breakdown (ON, 2025 base rates) | [docs/tax.md](docs/tax.md) |

Each tool is also available as a subcommand of the combined `prospero` CLI:

```bash
prospero portfolio value
prospero plan run
prospero acb report
prospero tax-breakdown --income 150000
```

All read commands accept `--json` for machine-readable output, enabling UNIX-style piping:

```bash
prospero-acb report --year 2024 --json | jq '.total_taxable_cad'
prospero-plan run --json | jq '.fire_age'
```

## Install

```bash
uv sync --extra dev
uv run prospero --help
```

Or install globally with uv:

```bash
uv tool install .
```

## Data storage

All data lives in `~/.prospero/`:

| File | Contents |
|---|---|
| `portfolio.json` | Stock holdings |
| `planner.toml` | Planner configuration (human-editable) |
| `acb_ledger.json` | ACB transaction history |
| `fx_rates_cache.json` | Cached Bank of Canada USD/CAD rates |

## Tests

```bash
uv run pytest -v
```

Dev dependencies (pytest etc.) are in the `dev` extra. Run `uv sync --extra dev` first if pytest is not found.

## Future projects

- **RRSP / TFSA modeling** — tax-sheltered accounts are a major factor in Canadian wealth planning
- **Capital gains tax** on investment growth — currently the planner ignores tax on withdrawals
- **Multiple income sources** — CPP/OAS pension income after 65, rental income, etc.
- **Historical portfolio simulation** — backtest portfolio value over time using actual price history
