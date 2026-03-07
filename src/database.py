import os
from pathlib import Path

import duckdb

from .models import Listing, PriceChange

_DEFAULT_DB = Path(__file__).parent.parent / "data" / "autoscout.duckdb"
DB_PATH = Path(os.environ.get("AUTOSCOUT_DB_PATH", str(_DEFAULT_DB)))


def get_connection() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def create_tables(con: duckdb.DuckDBPyConnection) -> None:
    # Bronze layer — append-only source of truth, one row per listing per run
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_listings (
            run_id             VARCHAR NOT NULL,
            guid               VARCHAR NOT NULL,
            make               VARCHAR NOT NULL,
            model              VARCHAR NOT NULL,
            price              INTEGER,
            mileage            INTEGER,
            fuel_type          VARCHAR,
            first_registration VARCHAR,
            seller_type        VARCHAR,
            url                VARCHAR,
            scraped_at         TIMESTAMPTZ NOT NULL
        )
    """)
    # Silver layer — current state, upserted on every run
    con.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            guid             VARCHAR PRIMARY KEY,
            make             VARCHAR NOT NULL,
            model            VARCHAR NOT NULL,
            price            INTEGER,
            mileage          INTEGER,
            fuel_type        VARCHAR,
            first_registration VARCHAR,
            seller_type      VARCHAR,
            url              VARCHAR,
            scraped_at       TIMESTAMPTZ NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS price_changes (
            guid         VARCHAR NOT NULL,
            old_price    INTEGER,
            new_price    INTEGER,
            detected_at  TIMESTAMPTZ NOT NULL
        )
    """)


def save_raw_listings(
    con: duckdb.DuckDBPyConnection, listings: list[Listing], run_id: str
) -> int:
    """Append all scraped listings to the Bronze layer. Never updates existing rows."""
    if not listings:
        return 0

    rows = [
        (
            run_id, l.guid, l.make, l.model, l.price, l.mileage,
            l.fuel_type, l.first_registration, l.seller_type,
            l.url, l.scraped_at,
        )
        for l in listings
    ]
    con.executemany(
        "INSERT INTO raw_listings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def detect_price_changes(
    con: duckdb.DuckDBPyConnection, listings: list[Listing]
) -> list[PriceChange]:
    """Compare incoming listings against stored prices. Call BEFORE save_listings."""
    if not listings:
        return []

    con.execute("CREATE OR REPLACE TEMP TABLE _incoming (guid VARCHAR, new_price INTEGER)")
    con.executemany(
        "INSERT INTO _incoming VALUES (?, ?)",
        [(l.guid, l.price) for l in listings if l.price is not None],
    )

    rows = con.execute("""
        SELECT
            existing.guid,
            existing.price  AS old_price,
            inc.new_price,
            NOW()           AS detected_at
        FROM listings existing
        JOIN _incoming inc ON existing.guid = inc.guid
        WHERE existing.price IS DISTINCT FROM inc.new_price
    """).fetchall()

    if not rows:
        return []

    changes = [
        PriceChange(guid=r[0], old_price=r[1], new_price=r[2], detected_at=r[3])
        for r in rows
    ]

    con.executemany(
        "INSERT INTO price_changes VALUES (?, ?, ?, ?)",
        [(pc.guid, pc.old_price, pc.new_price, pc.detected_at) for pc in changes],
    )

    return changes


def save_listings(con: duckdb.DuckDBPyConnection, listings: list[Listing]) -> int:
    if not listings:
        return 0

    rows = [
        (
            l.guid, l.make, l.model, l.price, l.mileage,
            l.fuel_type, l.first_registration, l.seller_type,
            l.url, l.scraped_at,
        )
        for l in listings
    ]

    con.executemany("""
        INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (guid) DO UPDATE SET
            price              = EXCLUDED.price,
            mileage            = EXCLUDED.mileage,
            fuel_type          = EXCLUDED.fuel_type,
            first_registration = EXCLUDED.first_registration,
            seller_type        = EXCLUDED.seller_type,
            scraped_at         = EXCLUDED.scraped_at
    """, rows)

    return len(rows)
