import httpx
from prefect import flow, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.logging import get_run_logger
from prefect.runtime import flow_run

from .database import (
    create_tables,
    detect_price_changes,
    get_connection,
    save_listings,
    save_raw_listings,
)
from .extractors import fetch_page, parse_listings
from .models import Listing, PriceChange

# Fahrzeugliste für scrape_all_flow
VEHICLES: list[tuple[str, str]] = [
    ("audi", "a4"),
    ("volkswagen", "golf"),
    ("bmw", "3er"),
]


@task(retries=3, retry_delay_seconds=15)
async def fetch_page_task(make: str, model: str, page: int) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await fetch_page(client, make, model, page)


@task
def parse_listings_task(html: str, make: str, model: str) -> list[Listing]:
    return parse_listings(html, make, model)


@task
def persist_listings_task(listings: list[Listing], run_id: str) -> tuple[int, list[PriceChange]]:
    con = get_connection()
    try:
        create_tables(con)
        save_raw_listings(con, listings, run_id)      # Bronze — append-only
        changes = detect_price_changes(con, listings)  # Silver prep
        saved = save_listings(con, listings)           # Silver — current state
        return saved, changes
    finally:
        con.close()


@flow(
    log_prints=True,
    flow_run_name="{make}-{model}"
)
async def scrape_flow(make: str, model: str) -> None:
    import os
    print(f"DATABASE_URL = {os.environ.get('DATABASE_URL', 'NOT SET')}")
    logger = get_run_logger()
    run_id = str(flow_run.id)
    all_listings: list[Listing] = []

    page = 1
    while True:
        html = await fetch_page_task(make, model, page)
        listings = parse_listings_task(html, make, model)

        if not listings:
            print(f"Page {page}: empty — stopping pagination.")
            break

        print(f"Page {page}: {len(listings)} listings parsed.")
        all_listings.extend(listings)
        page += 1

    if not all_listings:
        print("No listings found.")
        return

    saved, changes = persist_listings_task(all_listings, run_id)
    print(f"Saved/updated {saved} listings. Price changes detected: {len(changes)}.")

    for ch in changes:
        print(f"  {ch.guid}: {ch.old_price} -> {ch.new_price}")

    await create_table_artifact(
        key="listings-sample",
        table=[
            {
                "guid": l.guid,
                "price": l.price,
                "mileage": l.mileage,
                "fuel_type": l.fuel_type,
                "first_registration": l.first_registration,
                "seller_type": l.seller_type,
            }
            for l in all_listings[:25]
        ],
        description=f"First 25 of {len(all_listings)} listings for {make} {model}",
    )

    if changes:
        rows = "\n".join(f"| {c.guid} | {c.old_price}€ | {c.new_price}€ |" for c in changes)
        await create_markdown_artifact(
            key="price-changes",
            markdown=f"## Price Changes ({make} {model})\n\n| GUID | Old Price | New Price |\n|------|-----------|----------|\n{rows}",
            description=f"{len(changes)} price changes detected",
        )


from datetime import datetime

def generate_all_flow_name() -> str:
    return f"scrape-all-{datetime.now():%Y-%m-%d-%H%M}"

@flow(
    log_prints=True,
    flow_run_name=generate_all_flow_name
)
async def scrape_all_flow(vehicles: list[tuple[str, str]] = VEHICLES) -> None:
    """Scrape multiple make/model combinations sequentially."""
    print(f"Starting scrape for {len(vehicles)} vehicle(s).")
    for make, model in vehicles:
        print(f"--- {make} {model} ---")
        await scrape_flow(make=make, model=model)
    print("All vehicles scraped.")