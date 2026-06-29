import datetime
from telegram import Update
from telegram.ext import ContextTypes
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_keyboard import (
    generate_time_options_keyboard,
    generate_options_keyboard,
    generate_calendar_keyboard
)
from app.handlers.states import CHOOSING_TIME, CHOOSING_ACTION
from app.core.calendar.utils import build_events_list_text
from app.core.calendar.services import CalendarService


async def handle_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    parts = query.data.split(":")
    if parts[0] != "calendar_day":
        return

    year = int(parts[1])
    month = int(parts[2])
    day = int(parts[3])

    selected_date = datetime.date(year, month, day)
    user_id = update.effective_user.id

    # Сохраняем выбранную дату в контекст пользователя
    context.user_data['selected_date'] = selected_date

    # Гасим часики анимации на инлайн-кнопке
    await query.answer()

    # 1. Запрашиваем из базы события на этот день
    async with context.application.database.connection() as conn:
        events = await CalendarRepository.get_events_by_date(conn, user_id, selected_date)
        context.user_data['event_text_record'] = events

        if not events:
            events_text = "На этот день ничего не запланировано.\n"
            return await handle_time_selection_option((query, day, month, year), events_text)
        else:
            # Магия: генерируем красивый ненумерованный список дел одной строчкой
            events_list = build_events_list_text(events, numbered=False)
            events_text = f"{events_list}"

            return await handle_options_with_exist_notes_in_day(events_text, (query, day, month, year))


async def handle_options_with_exist_notes_in_day(events_text: str, args: tuple) -> int:
    query, day, month, year = args
    # ---- СЦЕНАРИЙ А: НА ЭТОТ ДЕНЬ ЕСТЬ СОБЫТИЯ ----

    await query.edit_message_text(
        text=f"📅 *Выбранная дата*: {day:02d}.{month:02d}.{year}\n\n"
        f"{events_text}"
        f"Выберите действие с расписанием:",
        reply_markup=generate_options_keyboard(),
        parse_mode="Markdown"
    )

    return CHOOSING_ACTION


async def handle_time_selection_option(args: tuple, events_text: str = None) -> int:
    query, day, month, year = args
    # ---- СЦЕНАРИЙ Б: НА ЭТОТ ДЕНЬ НЕТ СОБЫТИЙ / ИЛИ НАЖАТА КНОПКА "ДОБАВИТЬ" ----

    # Подстраховка на случай, если events_text не прилетел из внешнего вызова
    if not events_text:
        events_text = "На этот день ничего не запланировано.\n"

    await query.edit_message_text(
        text=f"📅 *Выбранная дата*: {day:02d}.{month:02d}.{year}\n\n"
        f"{events_text}"
        f"Укажите формат времени проведения события:",
        reply_markup=generate_time_options_keyboard(),
        parse_mode="Markdown"
    )

    return CHOOSING_TIME


async def handle_calendar_nav_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Глобальный обработчик переключения месяцев инлайн-календаря (кнопки « Пред и След »).
    Пересчитывает сетку занятости для целевого месяца и обновляет интерфейс.
    """
    query = update.callback_query

    # Защитная проверка от пустых апдейтов
    if not query or not update.effective_user:
        return

    # 1. Гасим анимацию загрузки ("часики") на инлайн-кнопке
    await query.answer()

    # 2. Парсим целевую дату из callback_data (формат генерации: "calendar_nav:YYYY:MM")
    parts = query.data.split(":")
    target_year = int(parts[1])
    target_month = int(parts[2])
    user_id = update.effective_user.id

    # 3. Запрашиваем из бизнес-логики свежий статус занятости дней для НОВОГО месяца
    async with context.application.database.connection() as conn:
        busy_days = await CalendarService.get_user_busy_days(
            conn=conn,
            user_id=user_id,
            year=target_year,
            month=target_month
        )

    # 4. Обновляем ОЗУ пользователя, чтобы валидация создания ивентов all_day работала корректно
    context.user_data['month_busy_days'] = busy_days

    # 5. Генерируем новую конфигурацию кнопок (матрицу дней) под целевой месяц
    calendar_markup = generate_calendar_keyboard(
        year=target_year,
        month=target_month,
        busy_days=busy_days
    )

    # 6. Обновляем исключительно инлайн-сетку кнопок под сообщением, избегая мерцания текста
    await query.edit_message_reply_markup(reply_markup=calendar_markup)
