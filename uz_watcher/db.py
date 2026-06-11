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
    check_interval INTEGER NOT NULL DEFAULT 60,
    notified_trains TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(SCHEMA)
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
    ) -> int:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                """
                INSERT INTO subscriptions (
                    chat_id, station_from_id, station_from_name,
                    station_to_id, station_to_name, travel_date,
                    train_numbers, min_seats, check_interval
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    async def update_notified_trains(self, sub_id: int, train_numbers: set[str]) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE subscriptions SET notified_trains = ? WHERE id = ?",
                (json.dumps(sorted(train_numbers), ensure_ascii=False), sub_id),
            )
            await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict:
    data = dict(row)
    data["train_numbers"] = json.loads(data["train_numbers"]) if data["train_numbers"] else None
    data["notified_trains"] = set(json.loads(data["notified_trains"]))
    return data
