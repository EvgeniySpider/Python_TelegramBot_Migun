import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_keyboard import generate_time_options_keyboard
from app.handlers.states import CHOOSING_TIME, CHOOSING_ACTION


async def handle_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        events_text = "Запланированные дела:\n" + \
            "\n".join([f"• {e['title']}" for e in events]) + '\n\n'
        context.user_data['events_text'] = events_text
        return await handle_event_search_and_set_selection(context.user_data['events_text'], query, day, month, year)


async def handle_event_search_and_set_selection(events_text, *args):
    if events_text:
        return await handle_options_with_exist_notes_in_day(events_text, args)
    else:
        return await handle_time_selection_option(args)


async def handle_options_with_exist_notes_in_day(events_text, args):
    query, day, month, year = args
    # ---- СЦЕНАРИЙ А: НА ЭТОТ ДЕНЬ ЕСТЬ СОБЫТИЯ (Абсолютная унификация) ----

    # Одинаковый, понятный набор кнопок для любой даты в календаре
    options_keyboard = [
        [
            InlineKeyboardButton("➕ Добавить", callback_data="action_create"),
            InlineKeyboardButton("✏️ Изменить", callback_data="action_edit"),
            InlineKeyboardButton("❌ Удалить", callback_data="action_delete")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(options_keyboard)

    await query.edit_message_text(
        text=f"📅 *Выбранная дата*: {day:02d}.{month:02d}.{year}\n\n"
        f"{events_text}"
        f"Выберите действие с расписанием:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    # В будущем здесь будет возврат стейта меню действий, пока заглушка
    return CHOOSING_ACTION


async def handle_time_selection_option(args, events_text=None):
    query, day, month, year = args
    # ---- СЦЕНАРИЙ Б: НА ЭТОТ ДЕНЬ НЕТ СОБЫТИЙ ----
    # Сразу запускаем сценарий создания (выбор формата времени)
    time_markup = generate_time_options_keyboard()
    events_message = "На этот день ничего не запланировано.\n" if events_text is None else events_text

    await query.edit_message_text(
        text=f"📅 *Выбранная дата*: {day:02d}.{month:02d}.{year}\n\n"
        f"{events_message}"
        f"Укажите формат времени проведения события:",
        reply_markup=time_markup,
        parse_mode = "Markdown"
    )

    return CHOOSING_TIME
