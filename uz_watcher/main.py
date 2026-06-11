"""Polls booking.uz.gov.ua for ticket availability on a configured route/date
and sends a Telegram notification (plus a local sound trigger file) when
seats become available.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from dotenv import load_dotenv

from uz_watcher.notifier import SoundTrigger, TelegramNotifier
from uz_watcher.uz_client import UZClient, UZClientError, extract_seat_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    load_dotenv()

    required = [
        "STATION_ID_FROM",
        "STATION_ID_TO",
        "TRAVEL_DATE",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    return {
        "station_id_from": os.environ["STATION_ID_FROM"],
        "station_id_to": os.environ["STATION_ID_TO"],
        "travel_date": os.environ["TRAVEL_DATE"],
        "train_numbers": [
            n.strip() for n in os.getenv("TRAIN_NUMBER", "").split(",") if n.strip()
        ] or None,
        "min_seats": int(os.getenv("MIN_SEATS", "1")),
        "check_interval": int(os.getenv("CHECK_INTERVAL_SECONDS", "60")),
        "telegram_bot_token": os.environ["TELEGRAM_BOT_TOKEN"],
        "telegram_chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "sound_trigger_path": os.getenv("SOUND_TRIGGER_PATH", "/data/sound_trigger.json"),
    }


def check_once(client: UZClient, config: dict) -> list[dict]:
    response = client.search_trains(
        config["station_id_from"], config["station_id_to"], config["travel_date"]
    )
    trains = extract_seat_summary(response)

    if config["train_numbers"]:
        trains = [t for t in trains if str(t["train_number"]) in config["train_numbers"]]

    return [t for t in trains if t["free_seats"] >= config["min_seats"]]


def main() -> None:
    config = load_config()
    telegram = TelegramNotifier(config["telegram_bot_token"], config["telegram_chat_id"])
    sound = SoundTrigger(config["sound_trigger_path"])

    logger.info(
        "Starting watcher: %s -> %s on %s (every %ss)",
        config["station_id_from"],
        config["station_id_to"],
        config["travel_date"],
        config["check_interval"],
    )

    already_notified: set[str] = set()

    with UZClient() as client:
        while True:
            try:
                available = check_once(client, config)
                still_available = set()

                for train in available:
                    still_available.add(train["train_number"])
                    if train["train_number"] in already_notified:
                        continue
                    already_notified.add(train["train_number"])

                    classes = ", ".join(
                        f"{wc['name']}: {wc['free_seats']}" for wc in train["wagon_classes"]
                    )
                    message = (
                        "🎫 Tickets available!\n"
                        f"Route: {config['station_id_from']} -> {config['station_id_to']}\n"
                        f"Date: {config['travel_date']}\n"
                        f"Train: {train['train_number']}\n"
                        f"Departure: {train['departure']} / Arrival: {train['arrival']}\n"
                        f"Free seats: {train['free_seats']} ({classes})\n"
                        f"Book here: https://booking.uz.gov.ua/"
                    )
                    logger.info("Found availability: %s", train)
                    telegram.send(message)
                    sound.fire({"event": "tickets_available", "train": train})

                if not available:
                    logger.info("No availability matching criteria.")

                already_notified &= still_available

            except UZClientError as exc:
                logger.error("UZ API error: %s", exc)
            except Exception:
                logger.exception("Unexpected error during check")

            time.sleep(config["check_interval"])


if __name__ == "__main__":
    main()
