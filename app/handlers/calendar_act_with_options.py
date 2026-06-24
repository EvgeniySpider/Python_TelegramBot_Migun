import datetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.core.calendar.services import CalendarService
from app.handlers.calendar_keyboard import generate_calendar_keyboard
from app.handlers.commands import calendar_command


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
    # Гасим часики
    await update.callback_query.answer()
    await calendar_command(update, context)

    return ConversationHandler.END
