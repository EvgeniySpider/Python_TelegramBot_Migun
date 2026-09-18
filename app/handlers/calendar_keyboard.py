import calendar
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def generate_calendar_keyboard(
    year: int, month: int,
    busy_days: set[int] = None,
    editing_day: int = None,
    is_back_button: bool = False
) -> InlineKeyboardMarkup:
    """Генерирует календарь с inline-кнопками"""
    # 1. Получаем текстовое название месяца (пока на английском, потом русифицируем)
    if busy_days is None:
        busy_days = {}

    RU_MONTHS = {
        1: "Январь",
        2: "Февраль",
        3: "Март",
        4: "Апрель",
        5: "Май",
        6: "Июнь",
        7: "Июль",
        8: "Август",
        9: "Сентябрь",
        10: "Октябрь",
        11: "Ноябрь",
        12: "Декабрь"
    }

    month_name = RU_MONTHS[month]

    keyboard = []

    # РЯД 1: Заголовок календаря (Месяц и Год)
    # Коллбэк ставим пустой ("ignore"), чтобы при нажатии на заголовок ничего не происходило
    keyboard.append([
        InlineKeyboardButton(
            text=f"{month_name} {year}", callback_data="calendar_ignore")
    ])

    # РЯД 2: Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([
        InlineKeyboardButton(text=day, callback_data="calendar_ignore") for day in week_days
    ])

    # РЯДЫ 3-8: Сами числа месяца
    # Функция monthcalendar возвращает матрицу недель, например: [0, 0, 1, 2, 3, 4, 5]
    month_matrix = calendar.monthcalendar(year, month)

    for week in month_matrix:
        row = []
        for day in week:
            if day == 0:
                # пустая кнопка
                row.append(InlineKeyboardButton(
                    text=" ", callback_data="calendar_ignore"
                ))
            else:
                if editing_day is not None and day == editing_day:
                    # Эффект вырезанного дня — серый круг
                    button_text = f"⚪ {day}"
                # 1. Определяем огонёк для full/partial дней
                elif busy_days.get(day) == 'full':
                    button_text = f"🔴 {day}"
                elif busy_days.get(day) == 'partial':
                    button_text = f"🟡 {day}"
                else:
                    button_text = f"{day}"

                # 2. ДОБАВЛЯЕМ КНОПКУ В РЯД (вынесли из внутреннего else)
                row.append(InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"calendar_day:{year}:{month}:{day}"
                ))

        # 3. ДОБАВЛЯЕМ РЯД В КЛАВИАТУРУ (сдвинули влево, теперь он срабатывает 1 раз на неделю!)
        keyboard.append(row)

    # РЯД 9: Кнопки навигации (Стрелочки)
    # Вычисляем прошлый и следующий месяц для коллбэков стрелочек
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1


    nav_row = [
            InlineKeyboardButton(text="« Пред", callback_data=f"calendar_nav:{prev_year}:{prev_month}")
        ]

    if is_back_button:
        nav_row.append(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_edit_menu"))

        # 3. Добавляем в конец ряда правую стрелочку
    nav_row.append(
        InlineKeyboardButton(text="След »", callback_data=f"calendar_nav:{next_year}:{next_month}")
    )
        # 4. И уже готовый, чистый ряд без всяких списков-матрешек пушим в клавиатуру
    keyboard.append(nav_row)

    return InlineKeyboardMarkup(keyboard)


def generate_time_options_keyboard(is_adding=False) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру выбора формата времени для мероприятия."""

    args_button = {'text': '🔙 Назад', 'callback_data': 'back_to_day_menu'} if is_adding \
        else {'text': '🔙 Изменить дату', 'callback_data': 'action_back_to_calendar'}

    keyboard = [
        [
            InlineKeyboardButton(text="☀️ Весь день",
                                 callback_data="event_time:all_day"),
            InlineKeyboardButton(text="⏱️ Точное время",
                                 callback_data="event_time:exact"),
            InlineKeyboardButton(
                text="⏳ Интервал", callback_data="event_time:interval")
        ],
        # РЯД 2: Кнопка возврата к сетке календаря
        [
            InlineKeyboardButton(**args_button)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def generate_options_keyboard() -> InlineKeyboardMarkup:
    options_keyboard = [
        [
            InlineKeyboardButton("➕ Добавить", callback_data="action_create"),
            InlineKeyboardButton("✏️ Изменить", callback_data="action_edit"),
            InlineKeyboardButton("❌ Удалить", callback_data="action_delete")
        ],
        [
            InlineKeyboardButton(text="🔙 Изменить дату",
                                 callback_data="action_back_to_calendar")
        ]
    ]
    return InlineKeyboardMarkup(options_keyboard)


def generate_yes_no_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="desc_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="desc_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def generate_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                "🗑️ Да, удалить", callback_data="confirm_delete_yes"),
            InlineKeyboardButton(
                "🔙 Нет, назад", callback_data="confirm_delete_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def generate_numbered_events_keyboard(count: int = None) -> InlineKeyboardMarkup:
    # 1. Базовая заготовка под цифровые ряды
    keyboard = [[], []]

    # 2. Если count передан (сценарий до 10 событий включительно), наполняем цифрами
    if count is not None:
        for c in range(count):
            button = InlineKeyboardButton(
                f"{c+1}", callback_data=f"del_num:{c}")
            if c < 5:
                keyboard[0].append(button)
            else:
                keyboard[1].append(button)

    # 3. Сервисные кнопки, которые нужны ВСЕГДА (и для кнопочного, и для текстового режима)
    extra_keyboard = [
        [
            InlineKeyboardButton("❌ Удалить все события",
                                 callback_data="del_num:everything"),
            InlineKeyboardButton("🔙  Назад", callback_data="del_num:cancel")
        ]
    ]

    # Расширяем клавиатуру (если цифр не было, списки keyboard[0] и [1] останутся пустыми и не отобразятся)
    keyboard.extend(extra_keyboard)

    return InlineKeyboardMarkup(keyboard)


def generate_numbered_edit_keyboard(count: int = None) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру с номерами задач для их РЕДАКТИРОВАНИЯ/ПРОСМОТРА."""
    keyboard = [[], []]

    # Наполняем цифрами 1, 2, 3...
    if count is not None:
        for c in range(count):
            button = InlineKeyboardButton(f"{c+1}", callback_data=f"edit_num:{c}")
            if c < 5:
                keyboard[0].append(button)
            else:
                keyboard[1].append(button)

    # Сервисная кнопка возврата в меню дня
    extra_keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="edit_num:cancel")]
    ]
    keyboard.extend(extra_keyboard)
    return InlineKeyboardMarkup(keyboard)


def generate_edit_fields_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✏️ Название", callback_data="edit_field:title"),
            InlineKeyboardButton("✏️ Время", callback_data="edit_field:time")
        ],
        [
            InlineKeyboardButton("✏️ Описание", callback_data="edit_field:desc"),
            InlineKeyboardButton("✏️ Дату", callback_data="edit_field:date")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="edit_field:cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)