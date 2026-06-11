"""Small input-validation helpers shared by the bot handlers."""
from __future__ import annotations

import re
from datetime import date, timedelta

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRAIN_NUMBER_RE = re.compile(r"^\d{3}[А-ЯҐЄІЇ]$")

PENDING_WINDOW_DAYS = 20


def is_valid_date(value: str) -> bool:
    """Check whether `value` is a real calendar date in YYYY-MM-DD format."""
    if not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_past_date(value: str, today: date) -> bool:
    """Check whether `value` (YYYY-MM-DD) is strictly before `today`."""
    return date.fromisoformat(value) < today


def is_valid_train_number(value: str) -> bool:
    """Check whether `value` is a UZ train number: 3 digits + a Cyrillic letter."""
    return bool(TRAIN_NUMBER_RE.match(value))


def compute_status(travel_date: str, today: date) -> str:
    """'pending' if travel_date is more than PENDING_WINDOW_DAYS away, else 'active'."""
    days_away = (date.fromisoformat(travel_date) - today).days
    return "pending" if days_away > PENDING_WINDOW_DAYS else "active"
