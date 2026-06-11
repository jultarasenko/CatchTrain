from uz_watcher.validation import is_valid_date


def test_valid_date():
    assert is_valid_date("2026-07-01") is True


def test_invalid_format():
    assert is_valid_date("01-07-2026") is False
    assert is_valid_date("2026/07/01") is False
    assert is_valid_date("not a date") is False


def test_invalid_calendar_date():
    assert is_valid_date("2026-02-30") is False
    assert is_valid_date("2026-13-01") is False
