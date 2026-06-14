from datetime import date

from uz_watcher.validation import (
    compute_check_interval_minutes,
    compute_status,
    is_past_date,
    is_valid_date,
    is_valid_train_number,
)


def test_valid_date():
    assert is_valid_date("2026-07-01") is True


def test_invalid_format():
    assert is_valid_date("01-07-2026") is False
    assert is_valid_date("2026/07/01") is False
    assert is_valid_date("not a date") is False


def test_invalid_calendar_date():
    assert is_valid_date("2026-02-30") is False
    assert is_valid_date("2026-13-01") is False


def test_valid_train_number():
    assert is_valid_train_number("070О") is True
    assert is_valid_train_number("096Л") is True


def test_invalid_train_number():
    assert is_valid_train_number("096л") is False
    assert is_valid_train_number("96Л") is False
    assert is_valid_train_number("0960") is False
    assert is_valid_train_number("070A") is False
    assert is_valid_train_number("Будь-який потяг") is False


def test_is_past_date():
    today = date(2026, 6, 11)
    assert is_past_date("2026-06-10", today) is True
    assert is_past_date("2026-06-11", today) is False
    assert is_past_date("2026-06-12", today) is False


def test_compute_status_active_within_window():
    today = date(2026, 6, 11)
    assert compute_status("2026-06-11", today) == "active"
    assert compute_status("2026-06-30", today) == "active"


def test_compute_status_pending_beyond_window():
    today = date(2026, 6, 11)
    assert compute_status("2026-07-01", today) == "pending"
    assert compute_status("2026-07-15", today) == "pending"


def test_compute_check_interval_minutes():
    assert compute_check_interval_minutes(0) == 1
    assert compute_check_interval_minutes(1) == 1
    assert compute_check_interval_minutes(15) == 1
    assert compute_check_interval_minutes(16) == 2
    assert compute_check_interval_minutes(57) == 4
