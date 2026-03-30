from prospero.cli import acb, planner, portfolio, tax as tax_cli

import typer

app = typer.Typer(
    name="prospero",
    help="Portfolio tracker and wealth planner",
)
app.add_typer(acb.app, name="acb", help="ACB tracker for Canadian capital gains tax")
app.add_typer(planner.app, name="plan", help="Long-term wealth planner")
app.add_typer(portfolio.app, name="portfolio", help="Stock portfolio tracker")

# Re-register the standalone tax breakdown as a top-level command
app.command("tax-breakdown")(tax_cli.breakdown)


if __name__ == "__main__":
    app()
