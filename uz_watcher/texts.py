"""Ukrainian-language text strings used by the bot."""

DONATE_LINK = "https://next.privat24.ua/send/jxztj"

WELCOME = (
    "Вітаю! Я допоможу стежити за наявністю квитків на потяги Укрзалізниці.\n\n"
    "Команди:\n"
    "/watch — додати нове відстеження\n"
    "/my — мої відстеження\n"
    "/feedback — залишити відгук або повідомити про проблему\n"
    "/cancel — скасувати поточну дію\n\n"
    "Якщо бот виявиться корисним, буду вдячний за невелику підтримку: "
    f"{DONATE_LINK}"
)

ASK_FEEDBACK = "Напишіть ваш відгук або опишіть проблему. Щоб скасувати, надішліть /cancel:"
FEEDBACK_THANKS = "Дякую за повідомлення! Ми його розглянемо."
FEEDBACK_FAILED = "Не вдалося надіслати повідомлення. Спробуйте пізніше."

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

ASK_MIN_SEATS = "Скільки вільних місць має бути доступно, щоб ви отримали сповіщення?"

ASK_WAGON_CLASSES = (
    "Оберіть типи місць, які вас цікавлять (можна декілька), і натисніть «Готово». "
    "Якщо не оберете жодного, шукатимемо серед усіх типів місць:"
)
# UZ API wagon class names, in display order.
WAGON_CLASS_NAMES = (
    "Люкс",
    "Купе",
    "Дитяче купе",
    "Жіноче купе",
    "Плацкарт",
    "1 клас",
    "2 клас",
)
ANY_WAGON_CLASS_BUTTON = "Будь-який тип місць"
DONE_BUTTON = "Готово"
ANY_WAGON_CLASS_LABEL = "будь-який"

DUPLICATE_SUBSCRIPTION = (
    "У вас вже є відстеження за цим маршрутом і датою (#{id}):\n"
    "{from_name} → {to_name}, {date}\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n"
    "Типи місць: {wagon_classes}\n\n"
    "Замість нового відстеження ви можете змінити параметри існуючого."
)
EDIT_TRAIN_NUMBERS_BUTTON = "Змінити номери потягів"
EDIT_MIN_SEATS_BUTTON = "Змінити мінімум місць"
EDIT_WAGON_CLASSES_BUTTON = "Змінити типи місць"
KEEP_EXISTING_BUTTON = "Залишити без змін"

DUPLICATE_MERGED_NOTICE = (
    "На жаль, у вас було кілька однакових відстежень за маршрутом "
    "{from_name} → {to_name} на дату {date}.\n\n"
    "Ми об'єднали їх в одне відстеження (#{id}):\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n\n"
    "Зайві дублікати видалено. Перевірити свої відстеження можна командою /my."
)

SUBSCRIPTION_UPDATED = (
    "Готово! Оновлено відстеження #{id}:\n"
    "{from_name} → {to_name}\n"
    "Дата: {date}\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n"
    "Типи місць: {wagon_classes}"
)

SUBSCRIPTION_RESUMED_AND_UPDATED = (
    "Гаразд, продовжуємо стежити за відстеженням #{id}:\n"
    "{from_name} → {to_name}\n"
    "Дата: {date}\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n"
    "Типи місць: {wagon_classes}"
)

SUBSCRIPTION_SAVED = (
    "Готово! Стежу за маршрутом:\n"
    "{from_name} → {to_name}\n"
    "Дата: {date}\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n"
    "Типи місць: {wagon_classes}\n"
    "Повідомлю, щойно з'являться вільні місця. "
    "Як тільки знайдемо перший підходящий варіант, ми зупинимо подальшу перевірку."
)

ANY_TRAIN_LABEL = "будь-який"

NO_SUBSCRIPTIONS = "У вас немає активних відстежень. Додайте нове командою /watch."

SUBSCRIPTIONS_LIST_HEADER = "Ваші відстеження. Оберіть, чим керувати:"
SUBSCRIPTION_ITEM = (
    "{status_icon} #{id}: {from_name} → {to_name}, {date}, потяги: {trains}, "
    "місць від {min_seats}, типи місць: {wagon_classes}"
)
STATUS_ICON_OK = "✅"
STATUS_ICON_COMPLETED = "❌"
MANAGE_BUTTON = "Керувати #{id}"
CANCEL_BUTTON = "Скасувати відстеження #{id}"
MANAGE_DONE_BUTTON = "Залишити без змін"
RESTORE_BUTTON = "Відновити відстеження #{id}"

MANAGE_SUBSCRIPTION_HEADER = (
    "Відстеження #{id}:\n"
    "{from_name} → {to_name}, {date}\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n"
    "Типи місць: {wagon_classes}\n\n"
    "Що ви хочете змінити?"
)
COMPLETED_SUBSCRIPTION_HEADER = (
    "Відстеження #{id}:\n"
    "{from_name} → {to_name}, {date}\n"
    "Потяги: {trains}\n"
    "Мінімум вільних місць: {min_seats}\n"
    "Типи місць: {wagon_classes}\n\n"
    "Це відстеження завершено. Відновіть його, щоб продовжити стеження, або скасуйте."
)
BACK_BUTTON = "« Назад"

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
    "Це відстеження (#{subscription_id}) виконано, тож ми зупинили перевірку.\n\n"
    "Якщо бот допоміг, підтримайте його роботу: "
    f"{DONATE_LINK}"
)

CONTINUE_TRACKING_BUTTON = "Не вдалося купити, продовжити стеження"
EDIT_AND_CONTINUE_BUTTON = "Цей варіант не підходить, змінити запит"
DELETE_TRACKING_BUTTON = "Видалити це відстеження"

TRACKING_RESUMED = "Гаразд, продовжуємо стежити за відстеженням #{id}."

SUBSCRIPTION_SUSPENDED_RETRO = (
    "🎫 Раніше для вашого відстеження (#{id}) {from_name} → {to_name} ({date}) "
    "ми вже знаходили вільні місця (потяг {train_number}), але через оновлення бота "
    "продовжували перевірку.\n\n"
    "Тепер ми зупинили це відстеження. Якщо ви ще не купили квиток — натисніть кнопку "
    "нижче, щоб продовжити стеження, або змініть параметри запиту."
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
