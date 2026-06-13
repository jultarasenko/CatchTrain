"""Per-subscription background polling tasks."""
from __future__ import annotations

import asyncio
import logging
import random

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from uz_watcher import texts
from uz_watcher.analytics import record_event
from uz_watcher.db import Database
from uz_watcher.uz_client import UZClient, UZClientError, extract_seat_summary

logger = logging.getLogger(__name__)


class PollerManager:
    """Starts and stops one asyncio task per subscription."""

    def __init__(self, bot: Bot, db: Database):
        self._bot = bot
        self._db = db
        self._tasks: dict[int, asyncio.Task] = {}

    def start(self, subscription: dict) -> None:
        sub_id = subscription["id"]
        if sub_id in self._tasks:
            return
        self._tasks[sub_id] = asyncio.create_task(self._run(subscription))

    def stop(self, sub_id: int) -> None:
        task = self._tasks.pop(sub_id, None)
        if task:
            task.cancel()

    async def _run(self, subscription: dict) -> None:
        sub_id = subscription["id"]
        chat_id = subscription["chat_id"]
        notified = set(subscription["notified_trains"])

        try:
            await asyncio.sleep(random.uniform(0, subscription["check_interval"]))
            async with UZClient() as client:
                while True:
                    try:
                        await self._check_once(client, subscription, notified)
                        await record_event(
                            self._db,
                            "poll_success",
                            subscription_id=sub_id,
                        )
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
                        return
                    except UZClientError as exc:
                        logger.error("UZ API error for subscription #%s: %s", sub_id, exc)
                        await record_event(
                            self._db,
                            "uz_api_error",
                            subscription_id=sub_id,
                            status_code=exc.status_code,
                        )
                    except Exception:
                        logger.exception("Unexpected error polling subscription #%s", sub_id)

                    jitter = random.uniform(-2, 2)
                    await asyncio.sleep(max(1, subscription["check_interval"] + jitter))
        except asyncio.CancelledError:
            logger.info("Stopped polling subscription #%s (chat %s)", sub_id, chat_id)
            raise

    async def _check_once(self, client: UZClient, subscription: dict, notified: set[str]) -> None:
        sub_id = subscription["id"]
        chat_id = subscription["chat_id"]
        train_numbers = subscription["train_numbers"]
        min_seats = subscription["min_seats"]

        trips = await client.search_trains(
            subscription["station_from_id"],
            subscription["station_to_id"],
            subscription["travel_date"],
        )
        trains = extract_seat_summary(trips)

        if train_numbers:
            trains = [t for t in trains if str(t["train_number"]) in train_numbers]
        trains = [t for t in trains if t["free_seats"] >= min_seats]

        still_available = set()
        changed = False
        for train in trains:
            still_available.add(train["train_number"])
            if train["train_number"] in notified:
                continue
            notified.add(train["train_number"])
            changed = True

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
            logger.info("Subscription #%s: found availability %s", sub_id, train)
            await self._bot.send_message(chat_id, message, parse_mode="Markdown")
            await record_event(
                self._db,
                "notification_sent",
                subscription_id=sub_id,
                chat_id=chat_id,
                station_from_id=subscription["station_from_id"],
                station_to_id=subscription["station_to_id"],
                train_number=train["train_number"],
            )

        if notified - still_available:
            notified.intersection_update(still_available)
            changed = True

        if changed:
            await self._db.update_notified_trains(sub_id, notified)
