"""Small input-validation helpers shared by the bot handlers."""
from __future__ import annotations

import re
from datetime import date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRAIN_NUMBER_RE = re.compile(r"^\d{3}[А-ЯҐЄІЇ]$")


def is_valid_date(value: str) -> bool:
    """Check whether `value` is a real calendar date in YYYY-MM-DD format."""
    if not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_valid_train_number(value: str) -> bool:
    """Check whether `value` is a UZ train number: 3 digits + a Cyrillic letter."""
    return bool(TRAIN_NUMBER_RE.match(value))
