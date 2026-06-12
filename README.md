# UZ Ticket Watcher Bot

A self-hosted Telegram bot that polls [booking.uz.gov.ua](https://booking.uz.gov.ua/)
(Ukrainian Railways) for ticket availability and notifies users the moment
seats appear on a route, date, and (optionally) train numbers they choose.

## Why

Ukrzaliznytsia is changing its train schedule starting June 28, and many
trains haven't been listed for booking yet. Once a train is added, tickets
can go on sale at any moment — but until it appears on the site, there's no
way to track it or get notified. This bot automates the waiting: each user
sets up a watch once, and gets pinged on Telegram the instant a matching
route, date, and train becomes available for booking, with a direct link to
book.

## How it works

- Each user configures their own watch through a guided conversation with
  the bot (`/watch`): pick departure station, destination station, date, and
  optionally specific train numbers.
- The bot starts an independent background poller for each subscription,
  checking the UZ ticket API every 60 seconds.
- When matching seats become available, the bot sends a Telegram message to
  that user.
- Subscriptions are stored in a local SQLite database so they survive
  restarts.
- All bot messages are in Ukrainian.

## Project layout

```
uz_watcher/          # bot package
  main.py            # entrypoint: starts the bot and resumes pollers
  bot.py             # Telegram conversation handlers (FSM)
  poller.py          # per-subscription background polling
  uz_client.py       # async client for the UZ ticket API
  db.py              # SQLite subscription storage
  texts.py           # Ukrainian-language bot messages
watchdog/            # standalone health-check process (separate container)
  main.py            # polls the bot + UZ API every 10 minutes, alerts on failure
Dockerfile
docker-compose.yml
.env.example
```

## Setup

### 1. Set up a Telegram bot

Open Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`
and follow the prompts to get a **bot token**.

Optionally, create a **second bot** the same way for health-check alerts
(`WATCHDOG_BOT_TOKEN` below). To get your chat ID for `ALERT_CHAT_ID`, send
any message to that second bot, then visit
`https://api.telegram.org/bot<WATCHDOG_BOT_TOKEN>/getUpdates` and read the
`chat.id` field from the response.

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set `TELEGRAM_BOT_TOKEN` to the token from BotFather. If
using the watchdog, also set `WATCHDOG_BOT_TOKEN` and `ALERT_CHAT_ID`.

### 3. Run

```bash
docker compose up -d --build
docker compose logs -f
```

### 4. Use the bot

In Telegram, open a chat with your bot and send:

- `/start` — show available commands
- `/watch` — set up a new ticket watch (guided conversation)
- `/my` — list your active watches and cancel them
- `/cancel` — cancel the current setup conversation

## Health checks

The `watchdog` service runs alongside the bot in its own container. Every 10
minutes it checks that:

- the CatchTrain bot responds to Telegram's `getMe`, and
- the UZ ticket API (`app.uz.gov.ua`) is reachable.

If either check fails, it sends an alert to `ALERT_CHAT_ID` via the
`WATCHDOG_BOT_TOKEN` bot (a separate bot, so it can still alert you even if
the main bot is down). It also sends a recovery message once checks pass
again.

## Stopping

```bash
docker compose down
```

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```
