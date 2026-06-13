"""SQLite storage for user subscriptions."""
from __future__ import annotations

import json
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

CREATE TABLE IF NOT EXISTS events (
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

CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events (created_at);
"""


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
                FROM events
                WHERE event_type IN ('poll_success', 'uz_api_error')
                  AND created_at >= datetime('now', '-10 minutes')
                """
            ) as cursor:
                success_count, error_count = await cursor.fetchone()

        success_count = success_count or 0
        error_count = error_count or 0
        total_polls = success_count + error_count
        unprocessed_pct = (error_count / total_polls * 100) if total_polls else 0.0

        return {
            "active_requests": active_requests,
            "total_requests": total_requests,
            "active_users": active_users,
            "requests_per_user": requests_per_user,
            "unprocessed_pct_10min": unprocessed_pct,
            "polls_total_10min": total_polls,
            "polls_failed_10min": error_count,
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
            await db.execute(
                """
                INSERT INTO events (
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


def _row_to_dict(row: aiosqlite.Row) -> dict:
    data = dict(row)
    data["train_numbers"] = json.loads(data["train_numbers"]) if data["train_numbers"] else None
    data["notified_trains"] = set(json.loads(data["notified_trains"]))
    return data
