"""Ukrainian-language text strings used by the bot."""

DONATE_LINK = "https://next.privat24.ua/send/jxztj"

WELCOME = (
    "Вітаю! Я допоможу стежити за наявністю квитків на потяги Укрзалізниці.\n\n"
    "Команди:\n"
    "/watch — додати нове відстеження\n"
    "/my — мої відстеження\n"
    "/cancel — скасувати поточну дію\n\n"
    "Якщо бот виявиться корисним, буду вдячний за невелику підтримку: "
    f"{DONATE_LINK}"
)

ASK_FROM_STATION = "Введіть назву станції відправлення (наприклад, Київ):"
ASK_TO_STATION = "Введіть назву станції призначення (наприклад, Львів):"

NO_STATIONS_FOUND = "Станцій не знайдено. Спробуйте ввести назву ще раз:"
CHOOSE_STATION = "Оберіть станцію зі списку:"

ASK_DATE = "Введіть дату поїздки у форматі РРРР-ММ-ДД (наприклад, 2026-07-01):"
INVALID_DATE = "Невірний формат дати. Введіть дату у форматі РРРР-ММ-ДД:"
INVALID_DATE_PAST = "Ця дата вже минула. Введіть дату не раніше сьогоднішньої:"

ASK_TRAIN_NUMBERS = (
    "Введіть номери потягів через кому (наприклад, 070О,089К), "
    "або натисніть «Будь-який потяг», щоб стежити за всіма потягами на цьому маршруті:"
)
ANY_TRAIN_BUTTON = "Будь-який потяг"
INVALID_TRAIN_NUMBER = (
    "Невірний формат номера потяга: «{value}». "
    "Номер має складатися з 3 цифр та літери кирилицею (наприклад, 070О). "
    "Спробуйте ще раз:"
)

SUBSCRIPTION_SAVED = (
    "Готово! Стежу за маршрутом:\n"
    "{from_name} → {to_name}\n"
    "Дата: {date}\n"
    "Потяги: {trains}\n"
    "Повідомлю, щойно з'являться вільні місця."
)

ANY_TRAIN_LABEL = "будь-який"

NO_SUBSCRIPTIONS = "У вас немає активних відстежень. Додайте нове командою /watch."

SUBSCRIPTIONS_LIST_HEADER = "Ваші відстеження:"
SUBSCRIPTION_ITEM = (
    "#{id}: {from_name} → {to_name}, {date}, потяги: {trains}"
)
CANCEL_BUTTON = "Скасувати #{id}"

SUBSCRIPTION_CANCELLED = "Відстеження #{id} скасовано."
SUBSCRIPTION_NOT_FOUND = "Відстеження не знайдено."

CANCELLED_ACTION = "Дію скасовано."

TICKETS_AVAILABLE = (
    "🎫 З'явилися квитки!\n"
    "Маршрут: {from_name} → {to_name}\n"
    "Дата: {date}\n"
    "Потяг: {train_number}\n"
    "Відправлення: {departure} / Прибуття: {arrival}\n"
    "Вільні місця: {free_seats} ({classes})\n\n"
    "[Купити квиток]({booking_link})\n\n"
    "Якщо бот допоміг, підтримайте його роботу: "
    f"{DONATE_LINK}"
)

BOOKING_LINK_TEMPLATE = (
    "https://booking.uz.gov.ua/search-trips/{station_from_id}/{station_to_id}/list?startDate={date}"
)

SUBSCRIPTION_LIMIT_REACHED = (
    "Ви досягли ліміту в {limit} активних відстежень. "
    "Скасуйте одне з них командою /my, щоб додати нове."
)

ERROR_GENERIC = "Сталася помилка. Спробуйте ще раз пізніше."

TRAIN_DEPARTED = (
    "Дата поїздки за вашим відстеженням #{id} ({from_name} → {to_name}, {date}) "
    "вже минула. На жаль, нам не вдалося знайти квитки за вашим запитом. "
    "Відстеження видалено."
)
