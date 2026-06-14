"""One-off script: send an announcement message to every chat with a subscription."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot

from uz_watcher.db import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("broadcast")

MESSAGE = (
    "Вітаємо! Сьогодні кількість користувачів бота перевищила 100 — це означає, "
    "що попереду великі зміни, і деякі з них уже відбулися 🎉\n\n"
    "Що нового:\n"
    "• Тепер можна редагувати своє відстеження потяга\n"
    "• З'явилися фільтри: мінімальна кількість вільних місць та тип місця\n\n"
    "Як тільки знайдемо перший підходящий варіант — зупиняємо пошук, поки ви "
    "не попросите продовжити.\n\n"
    "Якщо у вас є відгук або ви зіткнулися з проблемою — напишіть нам командою "
    "/feedback, ми швидко все вирішимо.\n\n"
    "Сподіваюся, бот вам корисний. Підтримати його можна відгуком, поширенням "
    "серед друзів або донатом 🙏"
)


async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Missing required environment variable: TELEGRAM_BOT_TOKEN")

    db_path = os.getenv("DATABASE_PATH", "/data/subscriptions.db")
    db = Database(db_path)
    await db.init()

    chat_ids = await db.get_all_chat_ids()
    logger.info("Sending to %d chats", len(chat_ids))

    bot = Bot(token=token)
    sent, failed = 0, 0
    try:
        for chat_id in chat_ids:
            try:
                await bot.send_message(chat_id, MESSAGE)
                sent += 1
            except Exception:
                logger.exception("Failed to send to chat %s", chat_id)
                failed += 1
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()

    logger.info("Done. sent=%d failed=%d", sent, failed)


if __name__ == "__main__":
    asyncio.run(main())
