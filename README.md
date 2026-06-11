# UZ Ticket Watcher

A small self-hosted bot that polls [booking.uz.gov.ua](https://booking.uz.gov.ua/)
(Ukrainian Railways) for ticket availability on a given route and date, and
notifies you via Telegram — with an optional sound alert on your machine —
the moment seats appear.

## How it works

- A Docker container polls the UZ ticket API on an interval (default 60s).
- When seats become available for the configured route, date, and (optional)
  train numbers, it sends a Telegram message and writes a small trigger file
  to a shared `./data` volume.
- An optional script run **on your host** (`local_notifier/play_alert.py`)
  watches that trigger file and plays a sound — this runs outside Docker
  since the container has no audio device.

Configuration (Telegram credentials, route, train numbers) lives in a local
`.env` file, which is excluded from git.

## Project layout

```
uz_watcher/          # watcher package
  main.py            # polling loop and notification logic
  uz_client.py       # client for the UZ ticket API
  notifier.py        # Telegram + sound-trigger notifications
local_notifier/
  play_alert.py      # host-side script that plays a sound on alert
Dockerfile
docker-compose.yml
.env.example
```

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

- `STATION_ID_FROM` / `STATION_ID_TO` — UZ station IDs (see below)
- `TRAVEL_DATE` — date to watch, `YYYY-MM-DD`
- `TRAIN_NUMBER` — optional, comma-separated list of train numbers to watch
  for (e.g. `070О,089К`); leave empty to watch all trains on the route
- `MIN_SEATS` — minimum free seats to trigger a notification
- `CHECK_INTERVAL_SECONDS` — polling interval, in seconds
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — see below

### 2. Set up a Telegram bot

1. Open Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`
   and follow the prompts to get a **bot token**.
2. Start a chat with your new bot (send it any message, e.g. `/start`).
3. Get your **chat ID**: visit
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in a browser
   after messaging the bot, and find `"chat":{"id": ...}` in the response.
4. Put both values into `.env`.

### 3. Find station IDs

The UZ API identifies stations by numeric ID. Look them up with:

```bash
docker compose run --rm uz-ticket-watcher python -c \
  "from uz_watcher.uz_client import UZClient; import json; \
   print(json.dumps(UZClient().find_station('Київ'), ensure_ascii=False, indent=2))"
```

Find the entry matching your station and copy its `id` into `STATION_ID_FROM`
/ `STATION_ID_TO`.

### 4. Run

```bash
docker compose up -d --build
docker compose logs -f
```

### 5. Enable sound alerts (optional, runs on your host)

```bash
python3 local_notifier/play_alert.py
```

Leave this running in a terminal — it plays a sound whenever the watcher
finds available tickets.

## Stopping

```bash
docker compose down
```
