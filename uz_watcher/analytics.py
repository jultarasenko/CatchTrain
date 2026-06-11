"""Structured analytics events, written to a dedicated logger.

Each event is logged as a single line in the form:

    event=<name> key1=value1 key2=value2 ...

This keeps analytics greppable from `docker compose logs` without adding
an external analytics dependency.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("uz_watcher.analytics")


def log_event(event: str, **fields) -> None:
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("event=%s %s", event, parts)
