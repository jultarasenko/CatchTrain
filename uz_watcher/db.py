"""SQLite storage for user subscriptions."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import aiosqlite

from uz_watcher.validation import compute_check_interval_minutes

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    station_from_id INTEGER NOT NULL,
    station_from_name TEXT NOT NULL,
    station_to_id INTEGER NOT NULL,
    station_to_name TEXT NOT NULL,
    travel_date TEXT NOT NULL,
    train_numbers TEXT,
    min_seats INTEGER NOT NULL DEFAULT 1,
    wagon_classes TEXT,
    check_interval INTEGER NOT NULL DEFAULT 480,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Bot-facing events: commands, messages, subscription lifecycle.
CREATE TABLE IF NOT EXISTS bot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    chat_id INTEGER,
    subscription_id INTEGER,
    station_from_id INTEGER,
    station_to_id INTEGER,
    travel_date TEXT,
    train_number TEXT,
    status_code INTEGER,
    extra TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bot_events_type ON bot_events (event_type);
CREATE INDEX IF NOT EXISTS idx_bot_events_created_at ON bot_events (created_at);

-- Poll-status events: per-subscription UZ API poll outcomes.
CREATE TABLE IF NOT EXISTS poll_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    subscription_id INTEGER,
    status_code INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_poll_events_type ON poll_events (event_type);
CREATE INDEX IF NOT EXISTS idx_poll_events_created_at ON poll_events (created_at);

-- User-submitted feedback and issue reports.
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at);
"""

POLL_EVENT_TYPES = {"poll_success", "uz_api_error"}


class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA)
            async with db.execute("PRAGMA table_info(subscriptions)") as cursor:
                columns = {row[1] async for row in cursor}
            if "status" not in columns:
                await db.execute(
                    "ALTER TABLE subscriptions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                )
            if "notified_trains" in columns:
                await db.execute("ALTER TABLE subscriptions DROP COLUMN notified_trains")
            if "wagon_classes" not in columns:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN wagon_classes TEXT")

            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
            ) as cursor:
                has_old_events = await cursor.fetchone() is not None
            if has_old_events:
                placeholders = ",".join("?" for _ in POLL_EVENT_TYPES)
                await db.execute(
                    f"""
                    INSERT INTO poll_events (event_type, subscription_id, status_code, created_at)
                    SELECT event_type, subscription_id, status_code, created_at
                    FROM events WHERE event_type IN ({placeholders})
                    """,
                    tuple(POLL_EVENT_TYPES),
                )
                await db.execute(
                    f"""
                    INSERT INTO bot_events (
                        event_type, chat_id, subscription_id, station_from_id,
                        station_to_id, travel_date, train_number, status_code, extra, created_at
                    )
                    SELECT event_type, chat_id, subscription_id, station_from_id,
                        station_to_id, travel_date, train_number, status_code, extra, created_at
                    FROM events WHERE event_type NOT IN ({placeholders})
                    """,
                    tuple(POLL_EVENT_TYPES),
                )
                await db.execute("DROP TABLE events")

            await db.commit()

    async def add_subscription(
        self,
        chat_id: int,
        station_from_id: int,
        station_from_name: str,
        station_to_id: int,
        station_to_name: str,
        travel_date: str,
        train_numbers: list[str] | None,
        min_seats: int,
        check_interval: int,
        status: str = "active",
        wagon_classes: list[str] | None = None,
    ) -> int:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                """
                INSERT INTO subscriptions (
                    chat_id, station_from_id, station_from_name,
                    station_to_id, station_to_name, travel_date,
                    train_numbers, min_seats, wagon_classes, check_interval, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    station_from_id,
                    station_from_name,
                    station_to_id,
                    station_to_name,
                    travel_date,
                    json.dumps(train_numbers, ensure_ascii=False) if train_numbers else None,
                    min_seats,
                    json.dumps(wagon_classes, ensure_ascii=False) if wagon_classes else None,
                    check_interval,
                    status,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_all_subscriptions(self) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM subscriptions") as cursor:
                rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def count_subscriptions_for_chat(self, chat_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE chat_id = ?", (chat_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0]

    async def get_all_chat_ids(self) -> list[int]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT DISTINCT chat_id FROM subscriptions") as cursor:
                rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_subscriptions_for_chat(self, chat_id: int) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE chat_id = ?", (chat_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def get_subscription_by_id(self, sub_id: int, chat_id: int) -> dict | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE id = ? AND chat_id = ?", (sub_id, chat_id)
            ) as cursor:
                row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    async def find_duplicate_subscription(
        self,
        chat_id: int,
        station_from_id: int,
        station_to_id: int,
        travel_date: str,
    ) -> dict | None:
        """Find an existing subscription with the same chat_id, route, and date."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM subscriptions
                WHERE chat_id = ? AND station_from_id = ? AND station_to_id = ? AND travel_date = ?
                """,
                (chat_id, station_from_id, station_to_id, travel_date),
            ) as cursor:
                row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    async def update_subscription_filters(
        self,
        sub_id: int,
        train_numbers: list[str] | None,
        min_seats: int,
        wagon_classes: list[str] | None,
    ) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE subscriptions SET train_numbers = ?, min_seats = ?, wagon_classes = ? WHERE id = ?",
                (
                    json.dumps(train_numbers, ensure_ascii=False) if train_numbers else None,
                    min_seats,
                    json.dumps(wagon_classes, ensure_ascii=False) if wagon_classes else None,
                    sub_id,
                ),
            )
            await db.commit()

    async def delete_subscription(self, sub_id: int, chat_id: int) -> bool:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "DELETE FROM subscriptions WHERE id = ? AND chat_id = ?", (sub_id, chat_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_subscription_by_id(self, sub_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
            await db.commit()

    async def update_status(self, sub_id: int, status: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE subscriptions SET status = ? WHERE id = ?", (status, sub_id)
            )
            await db.commit()

    async def get_stats(self) -> dict:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status = 'active'"
            ) as cursor:
                active_requests = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM subscriptions") as cursor:
                total_requests = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM subscriptions"
            ) as cursor:
                active_users = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions GROUP BY chat_id"
            ) as cursor:
                rows = await cursor.fetchall()
            requests_per_user = {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
            for (count,) in rows:
                key = str(count) if count < 5 else "5+"
                requests_per_user[key] += 1

            async with db.execute(
                """
                SELECT
                    SUM(CASE WHEN event_type = 'poll_success' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'uz_api_error' THEN 1 ELSE 0 END)
                FROM poll_events
                WHERE created_at >= datetime('now', '-1 hour')
                """
            ) as cursor:
                success_count, error_count = await cursor.fetchone()

            async with db.execute(
                """
                SELECT subscription_id, created_at
                FROM poll_events
                WHERE event_type = 'poll_success'
                  AND created_at >= datetime('now', '-1 hour')
                ORDER BY subscription_id, created_at
                """
            ) as cursor:
                poll_rows = await cursor.fetchall()

            async with db.execute(
                """
                SELECT subscription_id, MAX(created_at)
                FROM poll_events
                WHERE event_type = 'poll_success'
                GROUP BY subscription_id
                """
            ) as cursor:
                last_poll_rows = await cursor.fetchall()

            async with db.execute(
                "SELECT id FROM subscriptions WHERE status = 'active'"
            ) as cursor:
                active_sub_id_rows = await cursor.fetchall()

        success_count = success_count or 0
        error_count = error_count or 0
        total_polls = success_count + error_count
        unprocessed_pct = (error_count / total_polls * 100) if total_polls else 0.0

        active_sub_ids = {row[0] for row in active_sub_id_rows}
        now = datetime.utcnow()

        max_wait_seconds = 0.0
        max_wait_sub_id: int | None = None
        last_timestamp: dict[int, datetime] = {}
        for sub_id, created_at in poll_rows:
            ts = datetime.fromisoformat(created_at)
            if sub_id in last_timestamp:
                gap = (ts - last_timestamp[sub_id]).total_seconds()
                if gap > max_wait_seconds:
                    max_wait_seconds = gap
                    max_wait_sub_id = sub_id
            last_timestamp[sub_id] = ts
        # poll_rows/last_poll_rows only include poll_success events, so both
        # metrics below reflect time between error-free requests.

        check_interval_minutes = compute_check_interval_minutes(active_requests)
        long_wait_threshold_minutes = math.ceil(check_interval_minutes * 1.25)
        long_wait_threshold_seconds = long_wait_threshold_minutes * 60

        users_waiting_too_long = 0
        for sub_id, last_created_at in last_poll_rows:
            if sub_id not in active_sub_ids:
                continue
            elapsed = (now - datetime.fromisoformat(last_created_at)).total_seconds()
            # An active subscription currently waiting on its next success
            # also counts toward the max wait, even before that wait ends.
            if elapsed > max_wait_seconds:
                max_wait_seconds = elapsed
                max_wait_sub_id = sub_id
            if elapsed > long_wait_threshold_seconds:
                users_waiting_too_long += 1

        return {
            "active_requests": active_requests,
            "total_requests": total_requests,
            "active_users": active_users,
            "requests_per_user": requests_per_user,
            "unprocessed_pct_1h": unprocessed_pct,
            "polls_total_1h": total_polls,
            "polls_failed_1h": error_count,
            "max_wait_seconds_1h": max_wait_seconds,
            "max_wait_subscription_id": max_wait_sub_id,
            "check_interval_minutes": check_interval_minutes,
            "long_wait_threshold_minutes": long_wait_threshold_minutes,
            "users_waiting_too_long": users_waiting_too_long,
        }

    async def log_event(
        self,
        event_type: str,
        chat_id: int | None = None,
        subscription_id: int | None = None,
        station_from_id: int | None = None,
        station_to_id: int | None = None,
        travel_date: str | None = None,
        train_number: str | None = None,
        status_code: int | None = None,
        **extra,
    ) -> None:
        async with aiosqlite.connect(self._path) as db:
            if event_type in POLL_EVENT_TYPES:
                await db.execute(
                    """
                    INSERT INTO poll_events (event_type, subscription_id, status_code)
                    VALUES (?, ?, ?)
                    """,
                    (event_type, subscription_id, status_code),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO bot_events (
                        event_type, chat_id, subscription_id, station_from_id,
                        station_to_id, travel_date, train_number, status_code, extra
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_type,
                        chat_id,
                        subscription_id,
                        station_from_id,
                        station_to_id,
                        travel_date,
                        str(train_number) if train_number is not None else None,
                        status_code,
                        json.dumps(extra, ensure_ascii=False) if extra else None,
                    ),
                )
            await db.commit()

    async def get_error_rate(self, window_minutes: int = 60) -> float:
        """Fraction (0.0-1.0) of poll_events in the given window that were errors."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT
                    SUM(CASE WHEN event_type = 'poll_success' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'uz_api_error' THEN 1 ELSE 0 END)
                FROM poll_events
                WHERE created_at >= datetime('now', ? || ' minutes')
                """,
                (f"-{window_minutes}",),
            ) as cursor:
                success_count, error_count = await cursor.fetchone()

        success_count = success_count or 0
        error_count = error_count or 0
        total = success_count + error_count
        return (error_count / total) if total else 0.0

    async def save_feedback(self, chat_id: int, text: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO feedback (chat_id, text) VALUES (?, ?)", (chat_id, text)
            )
            await db.commit()

    async def prune_poll_success_events(self) -> None:
        """Delete poll_success rows older than 1 hour (uz_api_error rows are kept)."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                DELETE FROM poll_events
                WHERE event_type = 'poll_success'
                  AND created_at < datetime('now', '-1 hour')
                """
            )
            await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict:
    data = dict(row)
    data["train_numbers"] = json.loads(data["train_numbers"]) if data["train_numbers"] else None
    data["wagon_classes"] = json.loads(data["wagon_classes"]) if data["wagon_classes"] else None
    return data
