import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_keyboard import generate_time_options_keyboard
from app.handlers.states import CHOOSING_TIME


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

    # 2. Разветвление логики: День ЗАНЯТ vs День СВОБОДЕН
    if events:
        # ---- СЦЕНАРИЙ А: НА ЭТОТ ДЕНЬ ЕСТЬ СОБЫТИЯ (Абсолютная унификация) ----
        events_text = "\n".join([f"• {e['title']}" for e in events])
        
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
                 f"Запланированные дела:\n{events_text}\n\n"
                 f"Выберите действие с расписанием:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # В будущем здесь будет возврат стейта меню действий, пока заглушка
        return ConversationHandler.END

    else:
        # ---- СЦЕНАРИЙ Б: НА ЭТОТ ДЕНЬ НЕТ СОБЫТИЙ ----
        # Сразу запускаем сценарий создания (выбор формата времени)
        time_markup = generate_time_options_keyboard()

        await query.edit_message_text(
            text=f"Выбрана дата: {day:02d}.{month:02d}.{year}\n"
                 f"На этот день ничего не запланировано.\n\n"
                 f"Укажите формат времени проведения события:",
            reply_markup=time_markup
        )

        return CHOOSING_TIME