"""SQLite storage for user subscriptions."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

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
    check_interval INTEGER NOT NULL DEFAULT 180,
    notified_trains TEXT NOT NULL DEFAULT '[]',
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
    ) -> int:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                """
                INSERT INTO subscriptions (
                    chat_id, station_from_id, station_from_name,
                    station_to_id, station_to_name, travel_date,
                    train_numbers, min_seats, check_interval, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    async def get_subscriptions_for_chat(self, chat_id: int) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE chat_id = ?", (chat_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

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

    async def update_notified_trains(self, sub_id: int, train_numbers: set[str]) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE subscriptions SET notified_trains = ? WHERE id = ?",
                (json.dumps(sorted(train_numbers), ensure_ascii=False), sub_id),
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
                WHERE created_at >= datetime('now', '-1 hour')
                ORDER BY subscription_id, created_at
                """
            ) as cursor:
                poll_rows = await cursor.fetchall()

            async with db.execute(
                """
                SELECT subscription_id, MAX(created_at)
                FROM poll_events
                GROUP BY subscription_id
                """
            ) as cursor:
                last_poll_rows = await cursor.fetchall()

        success_count = success_count or 0
        error_count = error_count or 0
        total_polls = success_count + error_count
        unprocessed_pct = (error_count / total_polls * 100) if total_polls else 0.0

        max_wait_seconds = 0.0
        last_timestamp: dict[int, datetime] = {}
        for sub_id, created_at in poll_rows:
            ts = datetime.fromisoformat(created_at)
            if sub_id in last_timestamp:
                gap = (ts - last_timestamp[sub_id]).total_seconds()
                max_wait_seconds = max(max_wait_seconds, gap)
            last_timestamp[sub_id] = ts

        active_sub_ids = {
            sub["id"]
            for sub in await self.get_all_subscriptions()
            if sub["status"] == "active"
        }
        now = datetime.utcnow()
        waiting_over_5min = 0
        for sub_id, last_created_at in last_poll_rows:
            if sub_id not in active_sub_ids:
                continue
            elapsed = (now - datetime.fromisoformat(last_created_at)).total_seconds()
            if elapsed > 300:
                waiting_over_5min += 1

        return {
            "active_requests": active_requests,
            "total_requests": total_requests,
            "active_users": active_users,
            "requests_per_user": requests_per_user,
            "unprocessed_pct_1h": unprocessed_pct,
            "polls_total_1h": total_polls,
            "polls_failed_1h": error_count,
            "max_wait_seconds_1h": max_wait_seconds,
            "users_waiting_over_5min": waiting_over_5min,
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
    data["notified_trains"] = set(json.loads(data["notified_trains"]))
    return data
