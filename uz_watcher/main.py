"""Entrypoint: starts the Telegram bot and resumes pollers for saved subscriptions."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot
from dotenv import load_dotenv

from uz_watcher.bot import create_dispatcher
from uz_watcher.db import Database
from uz_watcher.poller import PollerManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Missing required environment variable: TELEGRAM_BOT_TOKEN")
        sys.exit(1)

    db_path = os.getenv("DATABASE_PATH", "/data/subscriptions.db")

    bot = Bot(token=token)
    db = Database(db_path)
    await db.init()

    pollers = PollerManager(bot, db)
    for subscription in await db.get_all_subscriptions():
        pollers.start(subscription)

    dispatcher = create_dispatcher(db, pollers)

    logger.info("Starting bot...")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
