from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.handlers.commands import calendar_command
from app.core.calendar.services import CalendarService
from app.handlers.states import CHOOSING_TIME


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Проверяем, какая именно кнопка была нажата
    if query.data == "action_create":

        # Достаем сохраненную дату из контекста
        selected_date = context.user_data.get('selected_date')

        events_text = context.user_data.get('events_text', None)

        async with context.application.database.connection() as conn:
            record_events_rows = await CalendarService.get_user_busy_days(
                conn,
                update.effective_user.id,
                selected_date.year,
                selected_date.month
            )

            if record_events_rows.get(selected_date.day) == 'full':
                await query.answer(
                    text=f'❌ Ошибка: этот день полностью занят.\n'
                    f'Выберите другую дату\n',
                    show_alert=False
                )
                return CHOOSING_TIME

        args = (query, selected_date.day,
                selected_date.month, selected_date.year)

        # Напрямую вызываем корутину и возвращаем её стейт (CHOOSING_TIME)
        state = await handle_time_selection_option(args, events_text)

    # Заглушки под остальные кнопки на будущее
    elif query.data == "action_edit":
        pass
    elif query.data == "action_delete":
        pass

    return state


# --- ТОЧЕЧНЫЙ ХЭНДЛЕР ВОЗВРАТА К КАЛЕНДАРЮ ---
async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Гасим часики
    await update.callback_query.answer()
    await calendar_command(update, context)

    return ConversationHandler.END
