"""Notification senders: Telegram message + local sound-trigger file."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, text: str) -> None:
        try:
            resp = httpx.post(
                self._url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to send Telegram notification: %s", exc)


class SoundTrigger:
    """Writes a trigger file that a local (non-Docker) script watches.

    The local script polls for this file's mtime and plays a sound when it
    changes, since the Docker container has no audio device access.
    """

    def __init__(self, trigger_path: str):
        self._path = Path(trigger_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def fire(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
