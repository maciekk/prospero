from prospero.cli import acb, planner, portfolio, tax as tax_cli
from prospero.cli._options import print_run_header

import typer

app = typer.Typer(
    name="prospero",
    help="Portfolio tracker and wealth planner",
)


@app.callback(invoke_without_command=True)
def _root_callback(ctx: typer.Context) -> None:
    print_run_header()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


app.add_typer(acb.app, name="acb", help="ACB tracker for Canadian capital gains tax")
app.add_typer(planner.app, name="plan", help="Long-term wealth planner")
app.add_typer(portfolio.app, name="portfolio", help="Stock portfolio tracker")

# Re-register the standalone tax breakdown as a top-level command
app.command("tax-breakdown")(tax_cli.breakdown)


if __name__ == "__main__":
    app()
