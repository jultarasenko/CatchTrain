"""Per-subscription background polling tasks."""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uz_watcher import texts
from uz_watcher.analytics import record_event
from uz_watcher.db import Database
from uz_watcher.uz_client import UZClient, UZClientError, extract_seat_summary
from uz_watcher.validation import compute_check_interval_minutes

logger = logging.getLogger(__name__)

PROCESS_START_TIME = time.monotonic()


async def compute_retry_delay(db: Database, check_interval: float) -> float:
    """Progressive retry delay for 429/441 errors, based on the recent error rate.

    The error rate is rounded up to the nearest 10% and applied as a fraction
    of the normal check interval (e.g. <=10% error -> 10% of check_interval,
    >90% error -> 100% of check_interval).

    During the first hour after a restart, the error rate is computed over the
    last 5 minutes instead of the last hour, since the hourly window may still
    contain stale data from before the restart.
    """
    since_start = time.monotonic() - PROCESS_START_TIME
    window_minutes = 5 if since_start < 3600 else 60
    error_rate = await db.get_error_rate(window_minutes)
    fraction = math.ceil(error_rate * 10) / 10
    fraction = max(0.1, min(1.0, fraction))
    return check_interval * fraction


class PollerManager:
    """Starts and stops one asyncio task per subscription."""

    def __init__(self, bot: Bot, db: Database):
        self._bot = bot
        self._db = db
        self._tasks: dict[int, asyncio.Task] = {}
        self._subscriptions: dict[int, dict] = {}

    def start(self, subscription: dict) -> None:
        sub_id = subscription["id"]
        if sub_id in self._tasks:
            return
        self._subscriptions[sub_id] = subscription
        self._tasks[sub_id] = asyncio.create_task(self._run(subscription))

    def stop(self, sub_id: int) -> None:
        task = self._tasks.pop(sub_id, None)
        self._subscriptions.pop(sub_id, None)
        if task:
            task.cancel()

    def update_filters(
        self,
        sub_id: int,
        train_numbers: list[str] | None,
        min_seats: int,
        wagon_classes: list[str] | None = None,
    ) -> None:
        """Apply new train_numbers/min_seats/wagon_classes to a running poller in place."""
        subscription = self._subscriptions.get(sub_id)
        if subscription is None:
            return
        subscription["train_numbers"] = train_numbers
        subscription["min_seats"] = min_seats
        subscription["wagon_classes"] = wagon_classes

    async def _run(self, subscription: dict) -> None:
        sub_id = subscription["id"]
        chat_id = subscription["chat_id"]

        try:
            check_interval = compute_check_interval_minutes(len(self._subscriptions)) * 60
            await asyncio.sleep(random.uniform(0, check_interval))
            async with UZClient() as client:
                while True:
                    try:
                        completed = await self._check_once(client, subscription)
                        await record_event(
                            self._db,
                            "poll_success",
                            subscription_id=sub_id,
                        )
                        if completed:
                            self._tasks.pop(sub_id, None)
                            return
                    except TelegramForbiddenError:
                        logger.warning(
                            "Bot blocked by user, removing subscription #%s (chat %s)",
                            sub_id, chat_id,
                        )
                        await self._db.delete_subscription_by_id(sub_id)
                        await record_event(
                            self._db,
                            "subscription_removed_blocked",
                            subscription_id=sub_id,
                            chat_id=chat_id,
                        )
                        self._tasks.pop(sub_id, None)
                        self._subscriptions.pop(sub_id, None)
                        return
                    except UZClientError as exc:
                        logger.error("UZ API error for subscription #%s: %s", sub_id, exc)
                        await record_event(
                            self._db,
                            "uz_api_error",
                            subscription_id=sub_id,
                            status_code=exc.status_code,
                        )
                        if exc.status_code in (429, 441):
                            check_interval = compute_check_interval_minutes(len(self._subscriptions)) * 60
                            retry_delay = await compute_retry_delay(self._db, check_interval)
                            await asyncio.sleep(retry_delay)
                            continue
                    except Exception:
                        logger.exception("Unexpected error polling subscription #%s", sub_id)

                    check_interval = compute_check_interval_minutes(len(self._subscriptions)) * 60
                    jitter = random.uniform(-2, 2)
                    await asyncio.sleep(max(1, check_interval + jitter))
        except asyncio.CancelledError:
            logger.info("Stopped polling subscription #%s (chat %s)", sub_id, chat_id)
            raise

    async def _check_once(self, client: UZClient, subscription: dict) -> bool:
        """Check for available trains. Returns True if the subscription was
        marked as completed and polling should stop."""
        sub_id = subscription["id"]
        chat_id = subscription["chat_id"]
        train_numbers = subscription["train_numbers"]
        min_seats = subscription["min_seats"]
        wagon_classes = subscription.get("wagon_classes")

        trips = await client.search_trains(
            subscription["station_from_id"],
            subscription["station_to_id"],
            subscription["travel_date"],
        )
        trains = extract_seat_summary(trips)

        if train_numbers:
            trains = [t for t in trains if str(t["train_number"]) in train_numbers]

        if wagon_classes:
            trains = [
                t for t in trains
                if sum(wc["free_seats"] for wc in t["wagon_classes"] if wc["name"] in wagon_classes) >= min_seats
            ]
        else:
            trains = [t for t in trains if t["free_seats"] >= min_seats]

        for train in trains:
            classes = ", ".join(
                f"{wc['name']}: {wc['free_seats']}" for wc in train["wagon_classes"]
            )
            booking_link = texts.BOOKING_LINK_TEMPLATE.format(
                station_from_id=subscription["station_from_id"],
                station_to_id=subscription["station_to_id"],
                date=subscription["travel_date"],
            )
            message = texts.TICKETS_AVAILABLE.format(
                subscription_id=sub_id,
                from_name=subscription["station_from_name"],
                to_name=subscription["station_to_name"],
                date=subscription["travel_date"],
                train_number=train["train_number"],
                departure=train["departure"],
                arrival=train["arrival"],
                free_seats=train["free_seats"],
                classes=classes,
                booking_link=booking_link,
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text=texts.CONTINUE_TRACKING_BUTTON,
                        callback_data=f"resume_tracking:{sub_id}",
                    )],
                    [InlineKeyboardButton(
                        text=texts.EDIT_AND_CONTINUE_BUTTON,
                        callback_data=f"resume_edit:{sub_id}",
                    )],
                    [InlineKeyboardButton(
                        text=texts.DELETE_TRACKING_BUTTON,
                        callback_data=f"cancel_sub:{sub_id}",
                    )],
                ]
            )
            logger.info("Subscription #%s: found availability %s", sub_id, train)
            await self._bot.send_message(chat_id, message, parse_mode="Markdown", reply_markup=keyboard)
            await record_event(
                self._db,
                "notification_sent",
                subscription_id=sub_id,
                chat_id=chat_id,
                station_from_id=subscription["station_from_id"],
                station_to_id=subscription["station_to_id"],
                train_number=train["train_number"],
            )

            await self._db.update_status(sub_id, "completed")
            await record_event(self._db, "subscription_completed", subscription_id=sub_id, chat_id=chat_id)
            self._subscriptions.pop(sub_id, None)
            return True

        return False
