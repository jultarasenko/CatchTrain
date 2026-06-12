"""Watchdog: periodically checks that the CatchTrain bot and the UZ API are
reachable, and sends an alert via a separate Telegram bot if either fails.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx
from dotenv import load_dotenv

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
    resp = await client.get(UZ_STATIONS_URL, params={"search": "Київ"})
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


async def main() -> None:
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    watchdog_token = os.getenv("WATCHDOG_BOT_TOKEN")
    chat_id = os.getenv("ALERT_CHAT_ID")

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

    was_down = False
    async with httpx.AsyncClient(timeout=15.0) as client:
        logger.info("Starting watchdog (interval: %ss)...", CHECK_INTERVAL)
        while True:
            was_down = await run_check(client, bot_token, watchdog_token, chat_id, was_down)
            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
