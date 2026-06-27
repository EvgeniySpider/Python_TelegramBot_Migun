from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.handlers.commands import calendar_command
from app.handlers.states import CHOOSING_TIME, CONFIRMING_DELETE
from app.handlers.calendar_keyboard import generate_confirm_keyboard


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    selected_date = context.user_data.get('selected_date')
    current_day_events = context.user_data.get('current_day_events', [])
    events_text = context.user_data.get('events_text', None)

    # Проверяем, какая именно кнопка была нажата
    if query.data == "action_create":
        month_busy_days = context.user_data.get('month_busy_days', {})

        if month_busy_days.get(selected_date.day) == 'full':
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

        # СЦЕНАРИЙ 1: Событие ровно одно и это "Весь день"
        # Проверяем либо через структуру данных, либо через твою идею с текстом: "(весь день)" in events_text
        if len(current_day_events) == 1 and current_day_events[0]['event_type'] == 'all_day':
            event = current_day_events[0]

            # Сохраняем ID этого единственного события в контекст для будущего SQL-запроса DELETE
            context.user_data['delete_event_id'] = event['id']

            await query.edit_message_text(
                text=f"❓ *Вы уверены, что хотите удалить мероприятие на весь день?*\n\n"
                f"📌 *Событие*: {event['title']}\n"
                f"📅 *Дата*: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n\n"
                f"⚠️ Это действие полностью сотрет заметку.",
                reply_markup=generate_confirm_keyboard(),
                parse_mode="Markdown"
            )
            return CONFIRMING_DELETE

        # СЦЕНАРИИ 2 и 3: Событий несколько
        else:
            await query.edit_message_text(
                text="Здесь будет логика выбора конкретной кнопки (Сценарии 2 и 3). Скоро напишем!"
            )
            return ConversationHandler.END

    return state


# --- ТОЧЕЧНЫЙ ХЭНДЛЕР ВОЗВРАТА К КАЛЕНДАРЮ ---
async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Гасим часики
    await update.callback_query.answer()
    await calendar_command(update, context)

    return ConversationHandler.END
