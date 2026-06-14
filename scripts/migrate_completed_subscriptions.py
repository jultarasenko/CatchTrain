"""One-off script: for subscriptions where we already found availability under
the old (pre-"completed" status) behavior, mark them as completed, stop their
pollers, clear notified_trains, and notify the affected users with the
continue-tracking / edit-and-continue buttons.
"""
from __future__ import annotations

import asyncio
import os
import sys

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
    affected = [
        sub for sub in subscriptions
        if sub["status"] == "active" and sub["notified_trains"]
    ]

    for sub in affected:
        sub_id = sub["id"]
        train_number = sorted(sub["notified_trains"])[0]

        if dry_run:
            print(
                f"[dry-run] Would mark subscription #{sub_id} (chat {sub['chat_id']}, "
                f"{sub['station_from_name']} -> {sub['station_to_name']}, {sub['travel_date']}, "
                f"notified={sorted(sub['notified_trains'])}) as completed and notify"
            )
            continue

        await db.update_status(sub_id, "completed")
        await db.update_notified_trains(sub_id, set())

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=texts.CONTINUE_TRACKING_BUTTON,
                    callback_data=f"resume_tracking:{sub_id}:{train_number}",
                )],
                [InlineKeyboardButton(
                    text=texts.EDIT_AND_CONTINUE_BUTTON,
                    callback_data=f"resume_edit:{sub_id}",
                )],
            ]
        )
        text = texts.SUBSCRIPTION_SUSPENDED_RETRO.format(
            id=sub_id,
            from_name=sub["station_from_name"],
            to_name=sub["station_to_name"],
            date=sub["travel_date"],
            train_number=train_number,
        )
        try:
            await bot.send_message(sub["chat_id"], text, reply_markup=keyboard)
            print(f"Marked #{sub_id} as completed, notified chat {sub['chat_id']}")
        except Exception as exc:
            print(f"Marked #{sub_id} as completed, but failed to notify chat {sub['chat_id']}: {exc}")

    if bot is not None:
        await bot.session.close()

    print(f"Total affected: {len(affected)}")


if __name__ == "__main__":
    asyncio.run(main())
