import os

import psycopg2
import psycopg2.extras

from .models import Listing, PriceChange

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(DATABASE_URL)


def create_tables(con: psycopg2.extensions.connection) -> None:
    with con.cursor() as cur:
        cur.execute("""
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                guid               VARCHAR PRIMARY KEY,
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_changes (
                guid        VARCHAR NOT NULL,
                old_price   INTEGER,
                new_price   INTEGER,
                detected_at TIMESTAMPTZ NOT NULL
            )
        """)
    con.commit()


def save_raw_listings(
    con: psycopg2.extensions.connection, listings: list[Listing], run_id: str
) -> int:
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
    with con.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO raw_listings VALUES %s",
            rows,
        )
    con.commit()
    return len(rows)


def detect_price_changes(
    con: psycopg2.extensions.connection, listings: list[Listing]
) -> list[PriceChange]:
    if not listings:
        return []

    incoming = [(l.guid, l.price) for l in listings if l.price is not None]

    with con.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS _incoming")
        cur.execute("CREATE TEMP TABLE _incoming (guid VARCHAR, new_price INTEGER)")
        psycopg2.extras.execute_values(cur, "INSERT INTO _incoming VALUES %s", incoming)

        cur.execute("""
            SELECT
                existing.guid,
                existing.price  AS old_price,
                inc.new_price,
                NOW()           AS detected_at
            FROM listings existing
            JOIN _incoming inc ON existing.guid = inc.guid
            WHERE existing.price IS DISTINCT FROM inc.new_price
        """)
        rows = cur.fetchall()

    if not rows:
        return []

    changes = [
        PriceChange(guid=r[0], old_price=r[1], new_price=r[2], detected_at=r[3])
        for r in rows
    ]

    with con.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO price_changes VALUES %s",
            [(pc.guid, pc.old_price, pc.new_price, pc.detected_at) for pc in changes],
        )
    con.commit()
    return changes


def save_listings(con: psycopg2.extensions.connection, listings: list[Listing]) -> int:
    if not listings:
        return 0

    seen: dict[str, Listing] = {}
    for l in listings:
        seen[l.guid] = l
    listings = list(seen.values())

    rows = [
        (
            l.guid, l.make, l.model, l.price, l.mileage,
            l.fuel_type, l.first_registration, l.seller_type,
            l.url, l.scraped_at,
        )
        for l in listings
    ]
    with con.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO listings VALUES %s
            ON CONFLICT (guid) DO UPDATE SET
                price              = EXCLUDED.price,
                mileage            = EXCLUDED.mileage,
                fuel_type          = EXCLUDED.fuel_type,
                first_registration = EXCLUDED.first_registration,
                seller_type        = EXCLUDED.seller_type,
                scraped_at         = EXCLUDED.scraped_at
            """,
            rows,
        )
    con.commit()
    return len(rows)
