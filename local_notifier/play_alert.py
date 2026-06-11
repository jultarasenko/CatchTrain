"""Run this on your host machine (not in Docker) to play a sound whenever
the watcher container finds available tickets.

It polls the shared trigger file (./data/sound_trigger.json by default,
written by the container via the mounted ./data volume) and plays an
alert sound each time the file's modification time changes.

Usage:
    python3 local_notifier/play_alert.py [path_to_trigger_file]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

DEFAULT_TRIGGER_PATH = Path(__file__).resolve().parent.parent / "data" / "sound_trigger.json"
POLL_INTERVAL_SECONDS = 2


def play_sound() -> None:
    if sys.platform == "darwin":
        import subprocess

        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
    elif sys.platform.startswith("linux"):
        import subprocess

        subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], check=False)
    elif sys.platform == "win32":
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    else:
        print("\a", end="", flush=True)


def main() -> None:
    trigger_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRIGGER_PATH
    print(f"Watching {trigger_path} for ticket alerts (Ctrl+C to stop)...")

    last_mtime = trigger_path.stat().st_mtime if trigger_path.exists() else None

    while True:
        if trigger_path.exists():
            mtime = trigger_path.stat().st_mtime
            if mtime != last_mtime:
                last_mtime = mtime
                try:
                    payload = json.loads(trigger_path.read_text())
                except (OSError, json.JSONDecodeError):
                    payload = {}
                print(f"Ticket alert! {payload}")
                for _ in range(3):
                    play_sound()
                    time.sleep(0.5)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
