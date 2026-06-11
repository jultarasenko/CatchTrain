"""Daily maintenance jobs: activate pending subscriptions and clean up expired ones.

- At 07:00 Kyiv time, subscriptions whose travel date has come within the
  pending window are flipped from 'pending' to 'active' and start polling.
- At 00:00 Kyiv time, subscriptions whose travel date has already passed are
  removed, and the user is notified that the train has departed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from aiogram import Bot

from uz_watcher import texts
from uz_watcher.db import Database
from uz_watcher.poller import PollerManager
from uz_watcher.uz_client import KYIV_TZ
from uz_watcher.validation import compute_status, is_past_date

logger = logging.getLogger(__name__)

ACTIVATION_TIME = time(7, 0)
CLEANUP_TIME = time(0, 0)


async def run_daily_jobs(bot: Bot, db: Database, pollers: PollerManager) -> None:
    while True:
        now = datetime.now(KYIV_TZ)
        next_run, job = _next_job(now)
        await asyncio.sleep((next_run - now).total_seconds())

        try:
            if job == "activate":
                await activate_pending_subscriptions(db, pollers)
            else:
                await remove_expired_subscriptions(bot, db, pollers)
        except Exception:
            logger.exception("Daily job %s failed", job)


def _next_job(now: datetime) -> tuple[datetime, str]:
    """Return the next scheduled run time and which job it is."""
    candidates = []
    for run_time, job in ((ACTIVATION_TIME, "activate"), (CLEANUP_TIME, "cleanup")):
        run_at = datetime.combine(now.date(), run_time, tzinfo=KYIV_TZ)
        if run_at <= now:
            run_at += timedelta(days=1)
        candidates.append((run_at, job))
    return min(candidates, key=lambda c: c[0])


async def activate_pending_subscriptions(db: Database, pollers: PollerManager) -> None:
    today = datetime.now(KYIV_TZ).date()
    for subscription in await db.get_all_subscriptions():
        if subscription["status"] != "pending":
            continue
        if compute_status(subscription["travel_date"], today) == "active":
            await db.update_status(subscription["id"], "active")
            subscription["status"] = "active"
            pollers.start(subscription)
            logger.info("Activated subscription #%s", subscription["id"])


async def remove_expired_subscriptions(bot: Bot, db: Database, pollers: PollerManager) -> None:
    today = datetime.now(KYIV_TZ).date()
    for subscription in await db.get_all_subscriptions():
        if not is_past_date(subscription["travel_date"], today):
            continue

        sub_id = subscription["id"]
        pollers.stop(sub_id)
        await db.delete_subscription_by_id(sub_id)
        await bot.send_message(
            subscription["chat_id"],
            texts.TRAIN_DEPARTED.format(
                id=sub_id,
                from_name=subscription["station_from_name"],
                to_name=subscription["station_to_name"],
                date=subscription["travel_date"],
            ),
        )
        logger.info("Removed expired subscription #%s", sub_id)
