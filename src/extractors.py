from datetime import datetime, timezone
from typing import Optional

import httpx
from selectolax.parser import HTMLParser

from .models import Listing

_BASE_URL = "https://www.autoscout24.lu/lst/{make}/{model}"
_QUERY = "sort=standard&desc=0&ustate=N,U&atype=C&cy=L"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _listing_url(make: str, model: str) -> str:
    return _BASE_URL.format(make=make, model=model)


async def fetch_page(client: httpx.AsyncClient, make: str, model: str, page: int) -> str:
    url = f"{_listing_url(make, model)}?{_QUERY}&page={page}"
    response = await client.get(url, headers=_HEADERS, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_listings(html: str, make: str, model: str) -> list[Listing]:
    tree = HTMLParser(html)
    articles = tree.css("article.cldt-summary-full-item")
    now = datetime.now(timezone.utc)
    listings: list[Listing] = []

    for article in articles:
        attrs = article.attributes
        guid = attrs.get("data-guid")
        if not guid:
            continue

        listings.append(
            Listing(
                guid=guid,
                make=make,
                model=model,
                price=_parse_int(attrs.get("data-price")),
                mileage=_parse_int(attrs.get("data-mileage")),
                fuel_type=attrs.get("data-fuel-type"),
                first_registration=attrs.get("data-first-registration"),
                seller_type=attrs.get("data-seller-type"),
                url=_listing_url(make, model),
                scraped_at=now,
            )
        )

    return listings


async def scrape_all_pages(make: str, model: str) -> list[Listing]:
    all_listings: list[Listing] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 1
        while True:
            html = await fetch_page(client, make, model, page)
            listings = parse_listings(html, make, model)
            if not listings:
                break
            all_listings.extend(listings)
            page += 1
    return all_listings
