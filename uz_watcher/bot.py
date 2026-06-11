"""Telegram bot: conversation flow for creating and managing subscriptions."""
from __future__ import annotations

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from uz_watcher import texts
from uz_watcher.analytics import record_event
from uz_watcher.db import Database
from uz_watcher.poller import PollerManager
from uz_watcher.uz_client import UZClient
from uz_watcher.validation import is_valid_date

MAX_STATION_OPTIONS = 8
MAX_SUBSCRIPTIONS_PER_CHAT = 5

router = Router()


class WatchForm(StatesGroup):
    from_station = State()
    choosing_from_station = State()
    to_station = State()
    choosing_to_station = State()
    date = State()
    train_numbers = State()


def _station_keyboard(stations: list[dict], prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=s["name"], callback_data=f"{prefix}:{s['id']}:{s['name']}")]
        for s in stations[:MAX_STATION_OPTIONS]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _any_train_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ANY_TRAIN_BUTTON, callback_data="any_train")]]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await record_event(db, "command", name="start", chat_id=message.chat.id)
    await message.answer(texts.WELCOME)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="cancel", chat_id=message.chat.id)
    await state.clear()
    await message.answer(texts.CANCELLED_ACTION)


@router.message(Command("watch"))
async def cmd_watch(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="watch", chat_id=message.chat.id)
    count = await db.count_subscriptions_for_chat(message.chat.id)
    if count >= MAX_SUBSCRIPTIONS_PER_CHAT:
        await message.answer(texts.SUBSCRIPTION_LIMIT_REACHED.format(limit=MAX_SUBSCRIPTIONS_PER_CHAT))
        return

    await state.set_state(WatchForm.from_station)
    await message.answer(texts.ASK_FROM_STATION)


@router.message(StateFilter(WatchForm.from_station))
async def process_from_station(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    async with UZClient() as client:
        stations = await client.find_station(query)

    if not stations:
        await message.answer(texts.NO_STATIONS_FOUND)
        return

    await state.set_state(WatchForm.choosing_from_station)
    await message.answer(texts.CHOOSE_STATION, reply_markup=_station_keyboard(stations, "from"))


@router.callback_query(StateFilter(WatchForm.choosing_from_station), F.data.startswith("from:"))
async def process_from_station_choice(callback: CallbackQuery, state: FSMContext) -> None:
    _, station_id, station_name = callback.data.split(":", 2)
    await state.update_data(from_id=int(station_id), from_name=station_name)
    await state.set_state(WatchForm.to_station)
    await callback.message.edit_text(f"{texts.CHOOSE_STATION}\n\n✅ {station_name}")
    await callback.message.answer(texts.ASK_TO_STATION)
    await callback.answer()


@router.message(StateFilter(WatchForm.to_station))
async def process_to_station(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    async with UZClient() as client:
        stations = await client.find_station(query)

    if not stations:
        await message.answer(texts.NO_STATIONS_FOUND)
        return

    await state.set_state(WatchForm.choosing_to_station)
    await message.answer(texts.CHOOSE_STATION, reply_markup=_station_keyboard(stations, "to"))


@router.callback_query(StateFilter(WatchForm.choosing_to_station), F.data.startswith("to:"))
async def process_to_station_choice(callback: CallbackQuery, state: FSMContext) -> None:
    _, station_id, station_name = callback.data.split(":", 2)
    await state.update_data(to_id=int(station_id), to_name=station_name)
    await state.set_state(WatchForm.date)
    await callback.message.edit_text(f"{texts.CHOOSE_STATION}\n\n✅ {station_name}")
    await callback.message.answer(texts.ASK_DATE)
    await callback.answer()


@router.message(StateFilter(WatchForm.date))
async def process_date(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not is_valid_date(value):
        await message.answer(texts.INVALID_DATE)
        return

    await state.update_data(date=value)
    await state.set_state(WatchForm.train_numbers)
    await message.answer(texts.ASK_TRAIN_NUMBERS, reply_markup=_any_train_keyboard())


@router.callback_query(StateFilter(WatchForm.train_numbers), F.data == "any_train")
async def process_any_train(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    await _save_subscription(callback.message, state, db, pollers, train_numbers=None)
    await callback.answer()


@router.message(StateFilter(WatchForm.train_numbers))
async def process_train_numbers(message: Message, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    raw = (message.text or "").strip()
    train_numbers = [n.strip().upper() for n in raw.split(",") if n.strip()] or None
    await _save_subscription(message, state, db, pollers, train_numbers=train_numbers)


async def _save_subscription(
    message: Message,
    state: FSMContext,
    db: Database,
    pollers: PollerManager,
    train_numbers: list[str] | None,
) -> None:
    data = await state.get_data()

    sub_id = await db.add_subscription(
        chat_id=message.chat.id,
        station_from_id=data["from_id"],
        station_from_name=data["from_name"],
        station_to_id=data["to_id"],
        station_to_name=data["to_name"],
        travel_date=data["date"],
        train_numbers=train_numbers,
        min_seats=1,
        check_interval=60,
    )
    await state.clear()

    subscription = {
        "id": sub_id,
        "chat_id": message.chat.id,
        "station_from_id": data["from_id"],
        "station_from_name": data["from_name"],
        "station_to_id": data["to_id"],
        "station_to_name": data["to_name"],
        "travel_date": data["date"],
        "train_numbers": train_numbers,
        "min_seats": 1,
        "check_interval": 60,
        "notified_trains": set(),
    }
    pollers.start(subscription)

    await record_event(
        db,
        "subscription_created",
        subscription_id=sub_id,
        chat_id=message.chat.id,
        station_from_id=data["from_id"],
        station_to_id=data["to_id"],
        travel_date=data["date"],
    )

    trains_label = ", ".join(train_numbers) if train_numbers else texts.ANY_TRAIN_LABEL
    await message.answer(
        texts.SUBSCRIPTION_SAVED.format(
            from_name=data["from_name"],
            to_name=data["to_name"],
            date=data["date"],
            trains=trains_label,
        )
    )


@router.message(Command("my"))
async def cmd_my(message: Message, db: Database) -> None:
    await record_event(db, "command", name="my", chat_id=message.chat.id)
    subscriptions = await db.get_subscriptions_for_chat(message.chat.id)
    if not subscriptions:
        await message.answer(texts.NO_SUBSCRIPTIONS)
        return

    lines = [texts.SUBSCRIPTIONS_LIST_HEADER]
    buttons = []
    for sub in subscriptions:
        trains_label = ", ".join(sub["train_numbers"]) if sub["train_numbers"] else texts.ANY_TRAIN_LABEL
        lines.append(
            texts.SUBSCRIPTION_ITEM.format(
                id=sub["id"],
                from_name=sub["station_from_name"],
                to_name=sub["station_to_name"],
                date=sub["travel_date"],
                trains=trains_label,
            )
        )
        buttons.append(
            [InlineKeyboardButton(text=texts.CANCEL_BUTTON.format(id=sub["id"]), callback_data=f"cancel_sub:{sub['id']}")]
        )

    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("cancel_sub:"))
async def process_cancel_subscription(callback: CallbackQuery, db: Database, pollers: PollerManager) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    deleted = await db.delete_subscription(sub_id, callback.message.chat.id)
    if deleted:
        pollers.stop(sub_id)
        await record_event(db, "subscription_cancelled", subscription_id=sub_id, chat_id=callback.message.chat.id)
        await callback.message.answer(texts.SUBSCRIPTION_CANCELLED.format(id=sub_id))
    else:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
    await callback.answer()


def create_dispatcher(db: Database, pollers: PollerManager) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher["db"] = db
    dispatcher["pollers"] = pollers
    return dispatcher
