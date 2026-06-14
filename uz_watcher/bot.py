"""Telegram bot: conversation flow for creating and managing subscriptions."""
from __future__ import annotations

import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
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
from uz_watcher.uz_client import KYIV_TZ, UZClient
from uz_watcher.validation import compute_status, is_past_date, is_valid_date, is_valid_train_number

MAX_STATION_OPTIONS = 8
MAX_SUBSCRIPTIONS_PER_CHAT = 5

logger = logging.getLogger(__name__)

router = Router()


class WatchForm(StatesGroup):
    from_station = State()
    choosing_from_station = State()
    to_station = State()
    choosing_to_station = State()
    date = State()
    train_numbers = State()
    min_seats = State()
    wagon_classes = State()
    editing_train_numbers = State()
    editing_min_seats = State()
    editing_wagon_classes = State()
    managing_train_numbers = State()
    managing_min_seats = State()
    managing_wagon_classes = State()
    feedback = State()


_FLOW_NAMES_BY_STATE = {
    WatchForm.feedback: "feedback",
    WatchForm.from_station: "watch",
    WatchForm.choosing_from_station: "watch",
    WatchForm.to_station: "watch",
    WatchForm.choosing_to_station: "watch",
    WatchForm.date: "watch",
    WatchForm.train_numbers: "watch",
    WatchForm.min_seats: "watch",
    WatchForm.wagon_classes: "watch",
    WatchForm.editing_train_numbers: "watch",
    WatchForm.editing_min_seats: "watch",
    WatchForm.editing_wagon_classes: "watch",
    WatchForm.managing_train_numbers: "manage",
    WatchForm.managing_min_seats: "manage",
    WatchForm.managing_wagon_classes: "manage",
}


async def _record_interruption(db: Database, state: FSMContext, chat_id: int, new_command: str) -> None:
    """If a flow is in progress, log that it was interrupted by `new_command`."""
    current = await state.get_state()
    flow = _FLOW_NAMES_BY_STATE.get(current)
    if flow is not None:
        await record_event(db, "flow_interrupted", chat_id=chat_id, flow=flow, command=new_command)


def _station_keyboard(stations: list[dict], prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=s["name"], callback_data=f"{prefix}:{i}")]
        for i, s in enumerate(stations[:MAX_STATION_OPTIONS])
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _any_train_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ANY_TRAIN_BUTTON, callback_data="any_train")]]
    )


def _min_seats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=str(n), callback_data=f"min_seats:{n}") for n in (1, 2, 3, 4)]
        ]
    )


async def _clear_train_numbers_keyboard(message: Message, state: FSMContext) -> None:
    """Delete the "Будь-який потяг" prompt message, if any."""
    data = await state.get_data()
    message_id = data.get("train_numbers_prompt_id")
    if message_id is not None:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=message_id)
        except Exception:
            pass


def _wagon_classes_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for i, name in enumerate(texts.WAGON_CLASS_NAMES):
        label = f"✅ {name}" if name in selected else name
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"wagon_class:{i}")])
    buttons.append([InlineKeyboardButton(text=texts.DONE_BUTTON, callback_data="wagon_class_done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _wagon_classes_label(wagon_classes: list[str] | None) -> str:
    if not wagon_classes:
        return texts.ANY_WAGON_CLASS_LABEL
    return ", ".join(wagon_classes)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="start", chat_id=message.chat.id)
    await _record_interruption(db, state, message.chat.id, "start")
    await state.clear()
    await message.answer(texts.WELCOME)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="cancel", chat_id=message.chat.id)
    await _record_interruption(db, state, message.chat.id, "cancel")
    await state.clear()
    await message.answer(texts.CANCELLED_ACTION)


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="feedback", chat_id=message.chat.id)
    await _record_interruption(db, state, message.chat.id, "feedback")
    await state.clear()
    await state.set_state(WatchForm.feedback)
    await message.answer(texts.ASK_FEEDBACK)


@router.message(Command("watch"))
async def cmd_watch(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="watch", chat_id=message.chat.id)
    count = await db.count_subscriptions_for_chat(message.chat.id)
    if count >= MAX_SUBSCRIPTIONS_PER_CHAT:
        await message.answer(texts.SUBSCRIPTION_LIMIT_REACHED.format(limit=MAX_SUBSCRIPTIONS_PER_CHAT))
        return

    await _record_interruption(db, state, message.chat.id, "watch")
    await state.clear()
    await state.set_state(WatchForm.from_station)
    await message.answer(texts.ASK_FROM_STATION)


@router.message(Command("my"))
async def cmd_my(message: Message, state: FSMContext, db: Database) -> None:
    await record_event(db, "command", name="my", chat_id=message.chat.id)
    await _record_interruption(db, state, message.chat.id, "my")
    await state.clear()
    subscriptions = await db.get_subscriptions_for_chat(message.chat.id)
    if not subscriptions:
        await message.answer(texts.NO_SUBSCRIPTIONS)
        return

    lines = [texts.SUBSCRIPTIONS_LIST_HEADER]
    buttons = []
    for sub in subscriptions:
        trains_label = ", ".join(sub["train_numbers"]) if sub["train_numbers"] else texts.ANY_TRAIN_LABEL
        status_icon = texts.STATUS_ICON_COMPLETED if sub["status"] == "completed" else texts.STATUS_ICON_OK
        lines.append(
            texts.SUBSCRIPTION_ITEM.format(
                status_icon=status_icon,
                id=sub["id"],
                from_name=sub["station_from_name"],
                to_name=sub["station_to_name"],
                date=sub["travel_date"],
                trains=trains_label,
                min_seats=sub["min_seats"],
                wagon_classes=_wagon_classes_label(sub["wagon_classes"]),
            )
        )
        buttons.append(
            [InlineKeyboardButton(text=texts.MANAGE_BUTTON.format(id=sub["id"]), callback_data=f"manage_sub:{sub['id']}")]
        )

    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(StateFilter(WatchForm.feedback))
async def process_feedback(message: Message, state: FSMContext, db: Database, feedback_bot) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(texts.ASK_FEEDBACK)
        return

    await state.clear()
    await record_event(db, "feedback_submitted", chat_id=message.chat.id)
    await db.save_feedback(message.chat.id, text)

    sent = False
    if feedback_bot is not None:
        alert_chat_id = os.getenv("ALERT_CHAT_ID")
        if alert_chat_id:
            try:
                await feedback_bot.send_message(
                    alert_chat_id,
                    f"📝 Відгук від {message.chat.id}:\n\n{text}",
                )
                sent = True
            except Exception:
                logger.exception("Failed to forward feedback from chat %s", message.chat.id)

    await message.answer(texts.FEEDBACK_THANKS if sent else texts.FEEDBACK_FAILED)


@router.message(StateFilter(WatchForm.from_station))
async def process_from_station(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    async with UZClient() as client:
        stations = await client.find_station(query)

    if not stations:
        await message.answer(texts.NO_STATIONS_FOUND)
        return

    await state.set_state(WatchForm.choosing_from_station)
    await state.update_data(from_stations=stations)
    await message.answer(texts.CHOOSE_STATION, reply_markup=_station_keyboard(stations, "from"))


@router.callback_query(StateFilter(WatchForm.choosing_from_station), F.data.startswith("from:"))
async def process_from_station_choice(callback: CallbackQuery, state: FSMContext) -> None:
    _, index = callback.data.split(":", 1)
    data = await state.get_data()
    station = data["from_stations"][int(index)]
    await state.update_data(from_id=station["id"], from_name=station["name"])
    await state.set_state(WatchForm.to_station)
    await callback.message.delete()
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
    await state.update_data(to_stations=stations)
    await message.answer(texts.CHOOSE_STATION, reply_markup=_station_keyboard(stations, "to"))


@router.callback_query(StateFilter(WatchForm.choosing_to_station), F.data.startswith("to:"))
async def process_to_station_choice(callback: CallbackQuery, state: FSMContext) -> None:
    _, index = callback.data.split(":", 1)
    data = await state.get_data()
    station = data["to_stations"][int(index)]
    await state.update_data(to_id=station["id"], to_name=station["name"])
    await state.set_state(WatchForm.date)
    await callback.message.delete()
    await callback.message.answer(texts.ASK_DATE)
    await callback.answer()


@router.message(StateFilter(WatchForm.date))
async def process_date(message: Message, state: FSMContext, db: Database) -> None:
    value = (message.text or "").strip()
    if not is_valid_date(value):
        await message.answer(texts.INVALID_DATE)
        return

    today = datetime.now(KYIV_TZ).date()
    if is_past_date(value, today):
        await message.answer(texts.INVALID_DATE_PAST)
        return

    data = await state.get_data()
    duplicate = await db.find_duplicate_subscription(
        chat_id=message.chat.id,
        station_from_id=data["from_id"],
        station_to_id=data["to_id"],
        travel_date=value,
    )
    if duplicate:
        await state.update_data(date=value, duplicate_id=duplicate["id"])
        await state.set_state(WatchForm.editing_train_numbers)
        trains_label = (
            ", ".join(duplicate["train_numbers"]) if duplicate["train_numbers"] else texts.ANY_TRAIN_LABEL
        )
        await message.answer(
            texts.DUPLICATE_SUBSCRIPTION.format(
                id=duplicate["id"],
                from_name=duplicate["station_from_name"],
                to_name=duplicate["station_to_name"],
                date=duplicate["travel_date"],
                trains=trains_label,
                min_seats=duplicate["min_seats"],
                wagon_classes=_wagon_classes_label(duplicate["wagon_classes"]),
            ),
            reply_markup=_duplicate_keyboard(),
        )
        return

    await state.update_data(date=value)
    await state.set_state(WatchForm.train_numbers)
    prompt = await message.answer(texts.ASK_TRAIN_NUMBERS, reply_markup=_any_train_keyboard())
    await state.update_data(train_numbers_prompt_id=prompt.message_id)


def _duplicate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.EDIT_TRAIN_NUMBERS_BUTTON, callback_data="dup_edit:trains")],
            [InlineKeyboardButton(text=texts.EDIT_MIN_SEATS_BUTTON, callback_data="dup_edit:seats")],
            [InlineKeyboardButton(text=texts.EDIT_WAGON_CLASSES_BUTTON, callback_data="dup_edit:wagon_classes")],
            [InlineKeyboardButton(text=texts.KEEP_EXISTING_BUTTON, callback_data="dup_edit:keep")],
        ]
    )


@router.callback_query(StateFilter(WatchForm.editing_train_numbers), F.data.startswith("dup_edit:"))
async def process_duplicate_choice(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    choice = callback.data.split(":", 1)[1]
    await callback.message.delete()
    if choice == "trains":
        prompt = await callback.message.answer(texts.ASK_TRAIN_NUMBERS, reply_markup=_any_train_keyboard())
        await state.update_data(train_numbers_prompt_id=prompt.message_id)
        await callback.answer()
        return
    if choice == "seats":
        await state.set_state(WatchForm.editing_min_seats)
        await callback.message.answer(texts.ASK_MIN_SEATS, reply_markup=_min_seats_keyboard())
        await callback.answer()
        return
    if choice == "wagon_classes":
        data = await state.get_data()
        duplicate = await db.find_duplicate_subscription(
            chat_id=callback.message.chat.id,
            station_from_id=data["from_id"],
            station_to_id=data["to_id"],
            travel_date=data["date"],
        )
        selected = list(duplicate["wagon_classes"] or [])
        await state.update_data(selected_wagon_classes=selected)
        await state.set_state(WatchForm.editing_wagon_classes)
        await callback.message.answer(texts.ASK_WAGON_CLASSES, reply_markup=_wagon_classes_keyboard(selected))
        await callback.answer()
        return

    await state.clear()
    await callback.message.answer(texts.CANCELLED_ACTION)
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.editing_train_numbers), F.data == "any_train")
async def process_duplicate_any_train(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    await callback.message.delete()
    data = await state.get_data()
    duplicate = await db.find_duplicate_subscription(
        chat_id=callback.message.chat.id,
        station_from_id=data["from_id"],
        station_to_id=data["to_id"],
        travel_date=data["date"],
    )
    await _apply_duplicate_update(
        callback.message, state, db, pollers, duplicate,
        train_numbers=None, min_seats=duplicate["min_seats"], wagon_classes=duplicate["wagon_classes"],
    )
    await callback.answer()


@router.message(StateFilter(WatchForm.editing_train_numbers))
async def process_duplicate_train_numbers(message: Message, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    raw = (message.text or "").strip()
    train_numbers = [n.strip().upper() for n in raw.split(",") if n.strip()] or None

    if train_numbers:
        for number in train_numbers:
            if not is_valid_train_number(number):
                await message.answer(texts.INVALID_TRAIN_NUMBER.format(value=number))
                return

    await _clear_train_numbers_keyboard(message, state)

    data = await state.get_data()
    duplicate = await db.find_duplicate_subscription(
        chat_id=message.chat.id,
        station_from_id=data["from_id"],
        station_to_id=data["to_id"],
        travel_date=data["date"],
    )
    await _apply_duplicate_update(
        message, state, db, pollers, duplicate,
        train_numbers=train_numbers, min_seats=duplicate["min_seats"], wagon_classes=duplicate["wagon_classes"],
    )


@router.callback_query(StateFilter(WatchForm.editing_min_seats), F.data.startswith("min_seats:"))
async def process_duplicate_min_seats(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    min_seats = int(callback.data.split(":", 1)[1])
    await callback.message.delete()
    data = await state.get_data()
    duplicate = await db.find_duplicate_subscription(
        chat_id=callback.message.chat.id,
        station_from_id=data["from_id"],
        station_to_id=data["to_id"],
        travel_date=data["date"],
    )
    await _apply_duplicate_update(
        callback.message, state, db, pollers, duplicate,
        train_numbers=duplicate["train_numbers"], min_seats=min_seats, wagon_classes=duplicate["wagon_classes"],
    )
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.editing_wagon_classes), F.data.startswith("wagon_class:"))
async def process_duplicate_wagon_class_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":", 1)[1])
    name = texts.WAGON_CLASS_NAMES[index]
    data = await state.get_data()
    selected = list(data.get("selected_wagon_classes", []))
    if name in selected:
        selected.remove(name)
    else:
        selected.append(name)
    await state.update_data(selected_wagon_classes=selected)
    await callback.message.edit_reply_markup(reply_markup=_wagon_classes_keyboard(selected))
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.editing_wagon_classes), F.data == "wagon_class_done")
async def process_duplicate_wagon_classes_done(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    await callback.message.delete()
    data = await state.get_data()
    wagon_classes = data.get("selected_wagon_classes") or None
    duplicate = await db.find_duplicate_subscription(
        chat_id=callback.message.chat.id,
        station_from_id=data["from_id"],
        station_to_id=data["to_id"],
        travel_date=data["date"],
    )
    await _apply_duplicate_update(
        callback.message, state, db, pollers, duplicate,
        train_numbers=duplicate["train_numbers"], min_seats=duplicate["min_seats"], wagon_classes=wagon_classes,
    )
    await callback.answer()


async def _apply_duplicate_update(
    message: Message,
    state: FSMContext,
    db: Database,
    pollers: PollerManager,
    duplicate: dict,
    train_numbers: list[str] | None,
    min_seats: int,
    wagon_classes: list[str] | None,
) -> None:
    await _apply_subscription_update(message, state, db, pollers, duplicate, train_numbers, min_seats, wagon_classes)


@router.callback_query(StateFilter(WatchForm.train_numbers), F.data == "any_train")
async def process_any_train(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.delete()
    await state.update_data(train_numbers=None)
    await state.set_state(WatchForm.min_seats)
    await callback.message.answer(texts.ASK_MIN_SEATS, reply_markup=_min_seats_keyboard())
    await callback.answer()


@router.message(StateFilter(WatchForm.train_numbers))
async def process_train_numbers(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    train_numbers = [n.strip().upper() for n in raw.split(",") if n.strip()] or None

    if train_numbers:
        for number in train_numbers:
            if not is_valid_train_number(number):
                await message.answer(texts.INVALID_TRAIN_NUMBER.format(value=number))
                return

    await _clear_train_numbers_keyboard(message, state)
    await state.update_data(train_numbers=train_numbers)
    await state.set_state(WatchForm.min_seats)
    await message.answer(texts.ASK_MIN_SEATS, reply_markup=_min_seats_keyboard())


@router.callback_query(StateFilter(WatchForm.min_seats), F.data.startswith("min_seats:"))
async def process_min_seats(callback: CallbackQuery, state: FSMContext) -> None:
    min_seats = int(callback.data.split(":", 1)[1])
    await callback.message.delete()
    await state.update_data(min_seats=min_seats, selected_wagon_classes=[])
    await state.set_state(WatchForm.wagon_classes)
    await callback.message.answer(texts.ASK_WAGON_CLASSES, reply_markup=_wagon_classes_keyboard([]))
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.wagon_classes), F.data.startswith("wagon_class:"))
async def process_wagon_class_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":", 1)[1])
    name = texts.WAGON_CLASS_NAMES[index]
    data = await state.get_data()
    selected = list(data.get("selected_wagon_classes", []))
    if name in selected:
        selected.remove(name)
    else:
        selected.append(name)
    await state.update_data(selected_wagon_classes=selected)
    await callback.message.edit_reply_markup(reply_markup=_wagon_classes_keyboard(selected))
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.wagon_classes), F.data == "wagon_class_done")
async def process_wagon_classes_done(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    await callback.message.delete()
    data = await state.get_data()
    wagon_classes = data.get("selected_wagon_classes") or None
    await _save_subscription(callback.message, state, db, pollers, min_seats=data["min_seats"], wagon_classes=wagon_classes)
    await callback.answer()


async def _save_subscription(
    message: Message,
    state: FSMContext,
    db: Database,
    pollers: PollerManager,
    min_seats: int,
    wagon_classes: list[str] | None,
) -> None:
    data = await state.get_data()
    train_numbers = data["train_numbers"]

    today = datetime.now(KYIV_TZ).date()
    status = compute_status(data["date"], today)

    sub_id = await db.add_subscription(
        chat_id=message.chat.id,
        station_from_id=data["from_id"],
        station_from_name=data["from_name"],
        station_to_id=data["to_id"],
        station_to_name=data["to_name"],
        travel_date=data["date"],
        train_numbers=train_numbers,
        min_seats=min_seats,
        check_interval=480,
        status=status,
        wagon_classes=wagon_classes,
    )
    await state.clear()

    if status == "active":
        subscription = {
            "id": sub_id,
            "chat_id": message.chat.id,
            "station_from_id": data["from_id"],
            "station_from_name": data["from_name"],
            "station_to_id": data["to_id"],
            "station_to_name": data["to_name"],
            "travel_date": data["date"],
            "train_numbers": train_numbers,
            "min_seats": min_seats,
            "wagon_classes": wagon_classes,
            "check_interval": 480,
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
            min_seats=min_seats,
            wagon_classes=_wagon_classes_label(wagon_classes),
        )
    )


def _manage_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.MANAGE_DONE_BUTTON, callback_data=f"manage_done:{sub_id}")],
            [InlineKeyboardButton(text=texts.EDIT_TRAIN_NUMBERS_BUTTON, callback_data=f"manage_edit:{sub_id}:trains")],
            [InlineKeyboardButton(text=texts.EDIT_MIN_SEATS_BUTTON, callback_data=f"manage_edit:{sub_id}:seats")],
            [InlineKeyboardButton(text=texts.EDIT_WAGON_CLASSES_BUTTON, callback_data=f"manage_edit:{sub_id}:wagon_classes")],
            [InlineKeyboardButton(text=texts.CANCEL_BUTTON.format(id=sub_id), callback_data=f"cancel_sub:{sub_id}")],
        ]
    )


def _completed_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.RESTORE_BUTTON.format(id=sub_id), callback_data=f"restore_sub:{sub_id}")],
            [InlineKeyboardButton(text=texts.CANCEL_BUTTON.format(id=sub_id), callback_data=f"cancel_sub:{sub_id}")],
        ]
    )


async def _show_manage_menu(message: Message, sub: dict) -> None:
    trains_label = ", ".join(sub["train_numbers"]) if sub["train_numbers"] else texts.ANY_TRAIN_LABEL
    await message.answer(
        texts.MANAGE_SUBSCRIPTION_HEADER.format(
            id=sub["id"],
            from_name=sub["station_from_name"],
            to_name=sub["station_to_name"],
            date=sub["travel_date"],
            trains=trains_label,
            min_seats=sub["min_seats"],
            wagon_classes=_wagon_classes_label(sub["wagon_classes"]),
        ),
        reply_markup=_manage_keyboard(sub["id"]),
    )


async def _show_completed_menu(message: Message, sub: dict) -> None:
    trains_label = ", ".join(sub["train_numbers"]) if sub["train_numbers"] else texts.ANY_TRAIN_LABEL
    await message.answer(
        texts.COMPLETED_SUBSCRIPTION_HEADER.format(
            id=sub["id"],
            from_name=sub["station_from_name"],
            to_name=sub["station_to_name"],
            date=sub["travel_date"],
            trains=trains_label,
            min_seats=sub["min_seats"],
            wagon_classes=_wagon_classes_label(sub["wagon_classes"]),
        ),
        reply_markup=_completed_keyboard(sub["id"]),
    )


@router.callback_query(F.data.startswith("manage_sub:"))
async def process_manage_subscription(callback: CallbackQuery, db: Database) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    sub = await db.get_subscription_by_id(sub_id, callback.message.chat.id)
    if sub is None:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
        await callback.answer()
        return

    if sub["status"] == "completed":
        await _show_completed_menu(callback.message, sub)
    else:
        await _show_manage_menu(callback.message, sub)
    await callback.answer()


@router.callback_query(F.data.startswith("restore_sub:"))
async def process_restore_subscription(callback: CallbackQuery, db: Database, pollers: PollerManager) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    sub = await db.get_subscription_by_id(sub_id, callback.message.chat.id)
    if sub is None:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
        await callback.answer()
        return

    await db.update_status(sub_id, "active")
    sub["status"] = "active"
    pollers.start(sub)

    await record_event(db, "subscription_resumed", subscription_id=sub_id, chat_id=callback.message.chat.id)
    await callback.message.answer(texts.TRACKING_RESUMED.format(id=sub_id))
    await _show_manage_menu(callback.message, sub)
    await callback.answer()


@router.callback_query(F.data.startswith("manage_edit:"))
async def process_manage_edit_choice(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, sub_id, field = callback.data.split(":", 2)
    await callback.message.delete()
    await state.update_data(managing_sub_id=int(sub_id))
    if field == "trains":
        await state.set_state(WatchForm.managing_train_numbers)
        prompt = await callback.message.answer(texts.ASK_TRAIN_NUMBERS, reply_markup=_any_train_keyboard())
        await state.update_data(train_numbers_prompt_id=prompt.message_id)
    elif field == "wagon_classes":
        sub = await db.get_subscription_by_id(int(sub_id), callback.message.chat.id)
        selected = list(sub["wagon_classes"] or [])
        await state.update_data(selected_wagon_classes=selected)
        await state.set_state(WatchForm.managing_wagon_classes)
        await callback.message.answer(texts.ASK_WAGON_CLASSES, reply_markup=_wagon_classes_keyboard(selected))
    else:
        await state.set_state(WatchForm.managing_min_seats)
        await callback.message.answer(texts.ASK_MIN_SEATS, reply_markup=_min_seats_keyboard())
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.managing_train_numbers), F.data == "any_train")
async def process_manage_any_train(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    await callback.message.delete()
    data = await state.get_data()
    sub = await db.get_subscription_by_id(data["managing_sub_id"], callback.message.chat.id)
    await _apply_subscription_update(
        callback.message, state, db, pollers, sub, train_numbers=None, min_seats=sub["min_seats"],
        wagon_classes=sub["wagon_classes"],
    )
    await callback.answer()


@router.message(StateFilter(WatchForm.managing_train_numbers))
async def process_manage_train_numbers(message: Message, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    raw = (message.text or "").strip()
    train_numbers = [n.strip().upper() for n in raw.split(",") if n.strip()] or None

    if train_numbers:
        for number in train_numbers:
            if not is_valid_train_number(number):
                await message.answer(texts.INVALID_TRAIN_NUMBER.format(value=number))
                return

    await _clear_train_numbers_keyboard(message, state)

    data = await state.get_data()
    sub = await db.get_subscription_by_id(data["managing_sub_id"], message.chat.id)
    await _apply_subscription_update(
        message, state, db, pollers, sub, train_numbers=train_numbers, min_seats=sub["min_seats"],
        wagon_classes=sub["wagon_classes"],
    )


@router.callback_query(StateFilter(WatchForm.managing_min_seats), F.data.startswith("min_seats:"))
async def process_manage_min_seats(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    min_seats = int(callback.data.split(":", 1)[1])
    await callback.message.delete()
    data = await state.get_data()
    sub = await db.get_subscription_by_id(data["managing_sub_id"], callback.message.chat.id)
    await _apply_subscription_update(
        callback.message, state, db, pollers, sub, train_numbers=sub["train_numbers"], min_seats=min_seats,
        wagon_classes=sub["wagon_classes"],
    )
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.managing_wagon_classes), F.data.startswith("wagon_class:"))
async def process_manage_wagon_class_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":", 1)[1])
    name = texts.WAGON_CLASS_NAMES[index]
    data = await state.get_data()
    selected = list(data.get("selected_wagon_classes", []))
    if name in selected:
        selected.remove(name)
    else:
        selected.append(name)
    await state.update_data(selected_wagon_classes=selected)
    await callback.message.edit_reply_markup(reply_markup=_wagon_classes_keyboard(selected))
    await callback.answer()


@router.callback_query(StateFilter(WatchForm.managing_wagon_classes), F.data == "wagon_class_done")
async def process_manage_wagon_classes_done(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    await callback.message.delete()
    data = await state.get_data()
    wagon_classes = data.get("selected_wagon_classes") or None
    sub = await db.get_subscription_by_id(data["managing_sub_id"], callback.message.chat.id)
    await _apply_subscription_update(
        callback.message, state, db, pollers, sub, train_numbers=sub["train_numbers"], min_seats=sub["min_seats"],
        wagon_classes=wagon_classes,
    )
    await callback.answer()


async def _apply_subscription_update(
    message: Message,
    state: FSMContext,
    db: Database,
    pollers: PollerManager,
    sub: dict,
    train_numbers: list[str] | None,
    min_seats: int,
    wagon_classes: list[str] | None,
) -> None:
    await db.update_subscription_filters(sub["id"], train_numbers, min_seats, wagon_classes)
    pollers.update_filters(sub["id"], train_numbers, min_seats, wagon_classes)

    await state.set_state(None)

    updated = dict(sub)
    updated["train_numbers"] = train_numbers
    updated["min_seats"] = min_seats
    updated["wagon_classes"] = wagon_classes
    await _show_manage_menu(message, updated)


@router.callback_query(F.data.startswith("manage_done:"))
async def process_manage_done(callback: CallbackQuery, state: FSMContext, db: Database, pollers: PollerManager) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    await callback.message.delete()
    data = await state.get_data()
    sub = await db.get_subscription_by_id(sub_id, callback.message.chat.id)
    if sub is None:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
        await callback.answer()
        return

    resumed = data.get("resume_after_edit", False)
    if resumed:
        await db.update_status(sub_id, "active")
        sub["status"] = "active"
        pollers.start(sub)
        await record_event(db, "subscription_resumed", subscription_id=sub_id, chat_id=callback.message.chat.id)

    await state.clear()

    trains_label = ", ".join(sub["train_numbers"]) if sub["train_numbers"] else texts.ANY_TRAIN_LABEL
    template = texts.SUBSCRIPTION_RESUMED_AND_UPDATED if resumed else texts.SUBSCRIPTION_UPDATED
    await callback.message.answer(
        template.format(
            id=sub["id"],
            from_name=sub["station_from_name"],
            to_name=sub["station_to_name"],
            date=sub["travel_date"],
            trains=trains_label,
            min_seats=sub["min_seats"],
            wagon_classes=_wagon_classes_label(sub["wagon_classes"]),
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_sub:"))
async def process_cancel_subscription(callback: CallbackQuery, db: Database, pollers: PollerManager) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    deleted = await db.delete_subscription(sub_id, callback.message.chat.id)
    if deleted:
        pollers.stop(sub_id)
        await record_event(db, "subscription_cancelled", subscription_id=sub_id, chat_id=callback.message.chat.id)
        await callback.message.answer(texts.SUBSCRIPTION_CANCELLED.format(id=sub_id))
    else:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
    await callback.answer()


@router.callback_query(F.data.startswith("resume_tracking:"))
async def process_resume_tracking(callback: CallbackQuery, db: Database, pollers: PollerManager) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    sub = await db.get_subscription_by_id(sub_id, callback.message.chat.id)
    if sub is None:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
        await callback.answer()
        return

    await db.update_status(sub_id, "active")
    sub["status"] = "active"
    pollers.start(sub)

    await record_event(db, "subscription_resumed", subscription_id=sub_id, chat_id=callback.message.chat.id)
    await callback.message.answer(texts.TRACKING_RESUMED.format(id=sub_id))
    await callback.answer()


@router.callback_query(F.data.startswith("resume_edit:"))
async def process_resume_edit(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    sub_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    sub = await db.get_subscription_by_id(sub_id, callback.message.chat.id)
    if sub is None:
        await callback.message.answer(texts.SUBSCRIPTION_NOT_FOUND)
        await callback.answer()
        return

    await state.update_data(managing_sub_id=sub_id, resume_after_edit=True)
    await _show_manage_menu(callback.message, sub)
    await callback.answer()


def create_dispatcher(db: Database, pollers: PollerManager, feedback_bot: Bot | None = None) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher["db"] = db
    dispatcher["pollers"] = pollers
    dispatcher["feedback_bot"] = feedback_bot
    return dispatcher
