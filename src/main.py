import asyncio

import click

from .flows import VEHICLES, scrape_all_flow, scrape_flow


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.argument("make")
@click.argument("model")
def scrape(make: str, model: str) -> None:
    """Scrape AutoScout24 Luxembourg for MAKE MODEL and persist to DuckDB."""
    asyncio.run(scrape_flow(make=make, model=model))


@cli.command("scrape-all")
@click.option(
    "--vehicle",
    "vehicles",
    type=(str, str),
    multiple=True,
    help="make model pair, e.g. --vehicle audi a4 --vehicle volkswagen golf",
)
def scrape_all(vehicles: tuple[tuple[str, str], ...]) -> None:
    """Scrape multiple vehicles. Uses default VEHICLES list if none specified."""
    vehicle_list = list(vehicles) if vehicles else VEHICLES
    asyncio.run(scrape_all_flow(vehicles=vehicle_list))


if __name__ == "__main__":
    cli()
