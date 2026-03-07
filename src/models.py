from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Listing(BaseModel):
    guid: str
    make: str
    model: str
    price: Optional[int] = None
    mileage: Optional[int] = None
    fuel_type: Optional[str] = None
    first_registration: Optional[str] = None
    seller_type: Optional[str] = None
    url: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PriceChange(BaseModel):
    guid: str
    old_price: Optional[int]
    new_price: Optional[int]
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
