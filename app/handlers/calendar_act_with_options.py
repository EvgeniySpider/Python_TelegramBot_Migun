import datetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.core.calendar.services import CalendarService
from app.handlers.calendar_keyboard import generate_calendar_keyboard


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Проверяем, какая именно кнопка была нажата
    if query.data == "action_create":
        # Достаем сохраненную дату из контекста
        selected_date = context.user_data.get('selected_date')
        events_text = context.user_data.get('events_text', None)

        args = (query, selected_date.day,
                selected_date.month, selected_date.year)

        # Напрямую вызываем корутину и возвращаем её стейт (CHOOSING_TIME)
        return await handle_time_selection_option(args, events_text)

    # Заглушки под остальные кнопки на будущее
    elif query.data == "action_edit":
        pass
    elif query.data == "action_delete":
        pass

    return ConversationHandler.END


# --- ТОЧЕЧНЫЙ ХЭНДЛЕР ВОЗВРАТА К КАЛЕНДАРЮ ---
async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()  # Гасим часики

    # Достаем дату, на которую юзер кликал изначально
    selected_date = context.user_data.get('selected_date')
    if not selected_date:
        selected_date = datetime.date.today()

    user_id = update.effective_user.id

    # Нам нужно вытащить занятые дни из базы, чтобы вернуть календарь "живым" (с точками)
    async with context.application.database.connection() as conn:
        busy_days = await CalendarService.get_user_busy_days(
            conn, user_id, selected_date.year, selected_date.month
        )

    # Генерируем заново клавиатуру календаря для этого месяца
    calendar_markup = generate_calendar_keyboard(
        selected_date.year, selected_date.month, busy_days)

    # Перерисовываем интерфейс обратно на календарь
    await query.edit_message_text(
        text="📅 Выберите дату для создания или просмотра мероприятий:",
        reply_markup=calendar_markup
    )

    # Сбрасываем стейт в END!
    # Почему? Потому что клик по дате в календаре — это entry_point нашего автомата.
    # Автомат должен быть закрыт, чтобы диспетчер снова поймал клик по дате с чистого листа.
    return ConversationHandler.END
