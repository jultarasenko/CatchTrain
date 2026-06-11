"""Structured analytics events.

Each event is logged as a single line in the form:

    event=<name> key1=value1 key2=value2 ...

so it stays greppable from `docker compose logs`, and is also persisted to
the `events` table in SQLite (via `Database.log_event`) so it survives
restarts and can be queried with SQL.
"""
from __future__ import annotations

import logging

from uz_watcher.db import Database

logger = logging.getLogger("uz_watcher.analytics")

_KNOWN_FIELDS = {
    "chat_id",
    "subscription_id",
    "station_from_id",
    "station_to_id",
    "travel_date",
    "train_number",
    "status_code",
}


def log_event(event: str, **fields) -> None:
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("event=%s %s", event, parts)


async def record_event(db: Database, event: str, **fields) -> None:
    """Log an event line and persist it to SQLite."""
    log_event(event, **fields)

    known = {key: value for key, value in fields.items() if key in _KNOWN_FIELDS}
    extra = {key: value for key, value in fields.items() if key not in _KNOWN_FIELDS}
    if "date" in extra:
        known.setdefault("travel_date", extra.pop("date"))

    await db.log_event(event, **known, **extra)
