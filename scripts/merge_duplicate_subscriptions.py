"""One-off script: merge duplicate subscriptions (same chat_id, route, date) into
one, keeping the lowest min_seats and the union of train_numbers (or "any train"
if any duplicate watches all trains), then notify affected users via Telegram.
"""
from __future__ import annotations

import asyncio
import os
import sys

from aiogram import Bot
from dotenv import load_dotenv

from uz_watcher import texts
from uz_watcher.db import Database


async def main() -> None:
    load_dotenv()

    dry_run = "--dry-run" in sys.argv

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token and not dry_run:
        print("Missing required environment variable: TELEGRAM_BOT_TOKEN")
        sys.exit(1)

    db_path = os.getenv("DATABASE_PATH", "/data/subscriptions.db")
    db = Database(db_path)
    await db.init()

    bot = Bot(token=token) if not dry_run else None

    subscriptions = await db.get_all_subscriptions()
    groups: dict[tuple, list[dict]] = {}
    for sub in subscriptions:
        key = (sub["chat_id"], sub["station_from_id"], sub["station_to_id"], sub["travel_date"])
        groups.setdefault(key, []).append(sub)

    for subs in groups.values():
        if len(subs) < 2:
            continue

        any_train = any(sub["train_numbers"] is None for sub in subs)
        if any_train:
            merged_train_numbers = None
        else:
            merged = set()
            for sub in subs:
                merged.update(sub["train_numbers"])
            merged_train_numbers = sorted(merged)

        merged_min_seats = min(sub["min_seats"] for sub in subs)

        keeper = min(subs, key=lambda s: s["id"])
        duplicates = [sub for sub in subs if sub["id"] != keeper["id"]]

        trains_label = ", ".join(merged_train_numbers) if merged_train_numbers else texts.ANY_TRAIN_LABEL

        if dry_run:
            print(
                f"[dry-run] Would merge subscriptions {[s['id'] for s in subs]} -> "
                f"#{keeper['id']} (chat {keeper['chat_id']}, "
                f"{keeper['station_from_name']} -> {keeper['station_to_name']}, {keeper['travel_date']}); "
                f"train_numbers={merged_train_numbers}, min_seats={merged_min_seats}; "
                f"would delete {[s['id'] for s in duplicates]}"
            )
            continue

        await db.update_subscription_filters(keeper["id"], merged_train_numbers, merged_min_seats)
        for sub in duplicates:
            await db.delete_subscription_by_id(sub["id"])

        text = texts.DUPLICATE_MERGED_NOTICE.format(
            id=keeper["id"],
            from_name=keeper["station_from_name"],
            to_name=keeper["station_to_name"],
            date=keeper["travel_date"],
            trains=trains_label,
            min_seats=merged_min_seats,
        )
        try:
            await bot.send_message(keeper["chat_id"], text)
            print(f"Merged subscriptions {[s['id'] for s in subs]} -> #{keeper['id']}, notified chat {keeper['chat_id']}")
        except Exception as exc:
            print(f"Merged subscriptions {[s['id'] for s in subs]} -> #{keeper['id']}, but failed to notify chat {keeper['chat_id']}: {exc}")

    if bot is not None:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
