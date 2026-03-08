"""
OpenLineage integration for Prefect flows.

Sends lineage events to Marquez so you can track which flows
read/write which datasets (tables).

Usage in flows.py:
    from .lineage import LineageTracker

    tracker = LineageTracker()

    # At the start of your flow:
    tracker.start_run(
        job_name="scrape-flow-audi-a4",
        inputs=[],
        outputs=["default.raw_listings", "default.listings", "default.price_changes"]
    )

    # ... do your work ...

    # On success:
    tracker.complete_run()

    # On failure:
    tracker.fail_run(error_message="Something went wrong")
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from openlineage.client import OpenLineageClient
from openlineage.client.facet import SchemaDatasetFacet, SchemaField
from openlineage.client.event_v2 import (
    Dataset,
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)
from openlineage.client.transport.http import HttpConfig, HttpTransport

# Configure via env vars, with sensible defaults
MARQUEZ_URL = os.environ.get("OPENLINEAGE_URL", "http://marquez-api:5000")
NAMESPACE = os.environ.get("OPENLINEAGE_NAMESPACE", "prefect")


# Schema definitions for our tables
TABLE_SCHEMAS = {
    "raw_listings": SchemaDatasetFacet(
        fields=[
            SchemaField(name="run_id", type="VARCHAR"),
            SchemaField(name="guid", type="VARCHAR"),
            SchemaField(name="make", type="VARCHAR"),
            SchemaField(name="model", type="VARCHAR"),
            SchemaField(name="price", type="INTEGER"),
            SchemaField(name="mileage", type="INTEGER"),
            SchemaField(name="fuel_type", type="VARCHAR"),
            SchemaField(name="first_registration", type="VARCHAR"),
            SchemaField(name="seller_type", type="VARCHAR"),
            SchemaField(name="url", type="VARCHAR"),
            SchemaField(name="scraped_at", type="TIMESTAMPTZ"),
        ]
    ),
    "listings": SchemaDatasetFacet(
        fields=[
            SchemaField(name="guid", type="VARCHAR"),
            SchemaField(name="make", type="VARCHAR"),
            SchemaField(name="model", type="VARCHAR"),
            SchemaField(name="price", type="INTEGER"),
            SchemaField(name="mileage", type="INTEGER"),
            SchemaField(name="fuel_type", type="VARCHAR"),
            SchemaField(name="first_registration", type="VARCHAR"),
            SchemaField(name="seller_type", type="VARCHAR"),
            SchemaField(name="url", type="VARCHAR"),
            SchemaField(name="scraped_at", type="TIMESTAMPTZ"),
        ]
    ),
    "price_changes": SchemaDatasetFacet(
        fields=[
            SchemaField(name="guid", type="VARCHAR"),
            SchemaField(name="old_price", type="INTEGER"),
            SchemaField(name="new_price", type="INTEGER"),
            SchemaField(name="detected_at", type="TIMESTAMPTZ"),
        ]
    ),
}


def _get_table_name(full_name: str) -> str:
    """Extract table name from 'db.table' format."""
    return full_name.split(".")[-1]


class LineageTracker:
    """Tracks OpenLineage events for Prefect flows."""

    def __init__(self, marquez_url: str = MARQUEZ_URL, namespace: str = NAMESPACE):
        self.namespace = namespace
        self.run_id: Optional[str] = None
        self.job_name: Optional[str] = None
        self._inputs: list[InputDataset] = []
        self._outputs: list[OutputDataset] = []

        try:
            http_config = HttpConfig(url=marquez_url)
            transport = HttpTransport(http_config)
            self.client = OpenLineageClient(transport=transport)
        except Exception as e:
            print(f"[LineageTracker] Warning: Could not connect to Marquez at {marquez_url}: {e}")
            self.client = None

    def start_run(
        self,
        job_name: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        run_id: str | None = None,
    ) -> str:
        """Emit a START event. Returns the run_id."""
        self.run_id = run_id or str(uuid.uuid4())
        self.job_name = job_name

        self._inputs = []
        for ds_name in (inputs or []):
            table = _get_table_name(ds_name)
            schema = TABLE_SCHEMAS.get(table)
            facets = {"schema": schema} if schema else {}
            self._inputs.append(
                InputDataset(namespace=self.namespace, name=ds_name, facets=facets)
            )

        self._outputs = []
        for ds_name in (outputs or []):
            table = _get_table_name(ds_name)
            schema = TABLE_SCHEMAS.get(table)
            facets = {"schema": schema} if schema else {}
            self._outputs.append(
                OutputDataset(namespace=self.namespace, name=ds_name, facets=facets)
            )

        event = RunEvent(
            eventType=RunState.START,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=Run(runId=self.run_id),
            job=Job(namespace=self.namespace, name=job_name),
            inputs=self._inputs,
            outputs=self._outputs,
            producer="https://github.com/masterries/prefecttest",
        )

        self._emit(event)
        return self.run_id

    def complete_run(self) -> None:
        """Emit a COMPLETE event."""
        if not self.run_id or not self.job_name:
            return

        event = RunEvent(
            eventType=RunState.COMPLETE,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=Run(runId=self.run_id),
            job=Job(namespace=self.namespace, name=self.job_name),
            inputs=self._inputs,
            outputs=self._outputs,
            producer="https://github.com/masterries/prefecttest",
        )

        self._emit(event)

    def fail_run(self, error_message: str = "") -> None:
        """Emit a FAIL event."""
        if not self.run_id or not self.job_name:
            return

        event = RunEvent(
            eventType=RunState.FAIL,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=Run(runId=self.run_id),
            job=Job(namespace=self.namespace, name=self.job_name),
            inputs=self._inputs,
            outputs=self._outputs,
            producer="https://github.com/masterries/prefecttest",
        )

        self._emit(event)

    def _emit(self, event: RunEvent) -> None:
        """Send event to Marquez, silently fail if unavailable."""
        if not self.client:
            print(f"[LineageTracker] Skipping event (no client): {event.eventType}")
            return
        try:
            self.client.emit(event)
            print(f"[LineageTracker] Emitted {event.eventType} for {self.job_name}")
        except Exception as e:
            print(f"[LineageTracker] Warning: Failed to emit event: {e}")