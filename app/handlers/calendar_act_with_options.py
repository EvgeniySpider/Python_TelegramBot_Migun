from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # Не забываем гасить часики на кнопках!

    # Проверяем, какая именно кнопка была нажата
    if query.data == "action_create":
        # Достаем сохраненную дату из контекста
        selected_date = context.user_data.get('selected_date')

        args = (query, selected_date.day,
                selected_date.month, selected_date.year)

        # Напрямую вызываем корутину и возвращаем её стейт (CHOOSING_TIME)
        return await handle_time_selection_option(args)

    # Заглушки под остальные кнопки на будущее
    elif query.data == "action_edit":
        pass
    elif query.data == "action_delete":
        pass

    return ConversationHandler.END
