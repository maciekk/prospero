import typer

from prospero.cli import planner, portfolio

app = typer.Typer(
    name="prospero",
    help="Portfolio tracker and wealth planner",
)
app.add_typer(planner.app, name="plan", help="Long-term wealth planner")
app.add_typer(portfolio.app, name="portfolio", help="Stock portfolio tracker")

if __name__ == "__main__":
    app()
