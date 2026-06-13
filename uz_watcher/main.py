"""Entrypoint: starts the Telegram bot and resumes pollers for saved subscriptions."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

from aiogram import Bot
from dotenv import load_dotenv

from uz_watcher.bot import create_dispatcher
from uz_watcher.db import Database
from uz_watcher.poller import PollerManager
from uz_watcher.scheduler import run_daily_jobs, run_poll_event_pruning
from uz_watcher.uz_client import KYIV_TZ
from uz_watcher.validation import compute_status

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

    today = datetime.now(KYIV_TZ).date()
    pollers = PollerManager(bot, db)
    for subscription in await db.get_all_subscriptions():
        correct_status = compute_status(subscription["travel_date"], today)
        if correct_status != subscription["status"]:
            await db.update_status(subscription["id"], correct_status)
            subscription["status"] = correct_status
        if subscription["status"] == "active":
            pollers.start(subscription)

    dispatcher = create_dispatcher(db, pollers)
    scheduler_task = asyncio.create_task(run_daily_jobs(bot, db, pollers))
    pruning_task = asyncio.create_task(run_poll_event_pruning(db))

    logger.info("Starting bot...")
    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler_task.cancel()
        pruning_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
