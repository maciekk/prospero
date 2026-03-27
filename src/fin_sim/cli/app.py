import typer

from fin_sim.cli import planner, portfolio

app = typer.Typer(
    name="fin-sim",
    help="Financial simulation toolkit — portfolio tracker and wealth planner",
)
app.add_typer(planner.app, name="plan", help="Long-term wealth planner")
app.add_typer(portfolio.app, name="portfolio", help="Stock portfolio tracker")

if __name__ == "__main__":
    app()
