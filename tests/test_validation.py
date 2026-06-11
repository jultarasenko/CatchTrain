from uz_watcher.validation import is_valid_date, is_valid_train_number


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
