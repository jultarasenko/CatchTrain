"""Watchdog: periodically checks that the CatchTrain bot and the UZ API are
reachable, and sends an alert via a separate Telegram bot if either fails.
Also exposes a /stats command with usage statistics.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from uz_watcher.db import Database
from uz_watcher.uz_client import DEFAULT_HEADERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL = 600  # 10 minutes
UZ_STATIONS_URL = "https://app.uz.gov.ua/api/stations"


class HealthCheckError(RuntimeError):
    pass


async def check_main_bot(client: httpx.AsyncClient, bot_token: str) -> None:
    resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
    if resp.status_code != 200 or not resp.json().get("ok"):
        raise HealthCheckError(f"CatchTrain bot getMe failed: {resp.status_code} {resp.text[:200]}")


async def check_uz_api(client: httpx.AsyncClient) -> None:
    headers = {**DEFAULT_HEADERS, "x-session-id": str(uuid.uuid4())}
    resp = await client.get(UZ_STATIONS_URL, params={"search": "Київ"}, headers=headers)
    if resp.status_code >= 400:
        raise HealthCheckError(f"UZ API unreachable: {resp.status_code} {resp.text[:200]}")


async def send_alert(client: httpx.AsyncClient, watchdog_token: str, chat_id: str, text: str) -> None:
    resp = await client.post(
        f"https://api.telegram.org/bot{watchdog_token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
    )
    if resp.status_code != 200:
        logger.error("Failed to send alert: %s %s", resp.status_code, resp.text[:200])


async def run_check(client: httpx.AsyncClient, bot_token: str, watchdog_token: str, chat_id: str, was_down: bool) -> bool:
    """Run all health checks. Returns whether the system is currently down."""
    checks = {
        "CatchTrain bot": check_main_bot(client, bot_token),
        "UZ API": check_uz_api(client),
    }

    failures = []
    for name, coro in checks.items():
        try:
            await coro
        except Exception as exc:
            failures.append(f"{name}: {exc}")

    if failures:
        logger.error("Health check failed: %s", "; ".join(failures))
        await send_alert(
            client, watchdog_token, chat_id,
            "⚠️ CatchTrain health check failed:\n" + "\n".join(failures),
        )
        return True

    logger.info("Health check OK")
    if was_down:
        await send_alert(client, watchdog_token, chat_id, "✅ CatchTrain is back to normal.")
    return False


def format_stats(stats: dict) -> str:
    per_user = stats["requests_per_user"]
    per_user_lines = "\n".join(
        f"  {bucket}: {count} users" for bucket, count in per_user.items()
    )
    return (
        "📊 CatchTrain stats\n\n"
        f"Active subscriptions: {stats['active_requests']}\n"
        f"Total subscriptions: {stats['total_requests']}\n"
        f"Active users: {stats['active_users']}\n\n"
        f"Subscriptions per user:\n{per_user_lines}\n\n"
        f"UZ API polls (last 1h): {stats['polls_total_1h']}\n"
        f"Failed polls (last 1h): {stats['polls_failed_1h']}\n"
        f"Unprocessed rate (last 1h): {stats['unprocessed_pct_1h']:.1f}%\n"
        f"Max wait between requests (last 1h): {stats['max_wait_seconds_1h']:.0f}s\n"
        f"Users waiting >5 min: {stats['users_waiting_over_5min']}"
    )


def create_dispatcher(db: Database) -> Dispatcher:
    dispatcher = Dispatcher()

    @dispatcher.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        stats = await db.get_stats()
        await message.answer(format_stats(stats))

    return dispatcher


async def run_health_checks(bot_token: str, watchdog_token: str, chat_id: str) -> None:
    was_down = False
    async with httpx.AsyncClient(timeout=15.0) as client:
        logger.info("Starting health checks (interval: %ss)...", CHECK_INTERVAL)
        while True:
            was_down = await run_check(client, bot_token, watchdog_token, chat_id, was_down)
            await asyncio.sleep(CHECK_INTERVAL)


async def main() -> None:
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    watchdog_token = os.getenv("WATCHDOG_BOT_TOKEN")
    chat_id = os.getenv("ALERT_CHAT_ID")
    db_path = os.getenv("DATABASE_PATH", "/data/subscriptions.db")

    missing = [
        name for name, value in (
            ("TELEGRAM_BOT_TOKEN", bot_token),
            ("WATCHDOG_BOT_TOKEN", watchdog_token),
            ("ALERT_CHAT_ID", chat_id),
        ) if not value
    ]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    db = Database(db_path)
    await db.init()

    bot = Bot(token=watchdog_token)
    dispatcher = create_dispatcher(db)

    health_task = asyncio.create_task(run_health_checks(bot_token, watchdog_token, chat_id))
    try:
        await dispatcher.start_polling(bot)
    finally:
        health_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
