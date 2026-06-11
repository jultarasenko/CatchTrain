"""Small input-validation helpers shared by the bot handlers."""
from __future__ import annotations

import re
from datetime import date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_valid_date(value: str) -> bool:
    """Check whether `value` is a real calendar date in YYYY-MM-DD format."""
    if not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
