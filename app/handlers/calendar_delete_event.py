from app.handlers.calendar_callbacks import handle_options_with_exist_notes_in_day
from telegram import Update
from telegram.ext import ContextTypes,  ConversationHandler
from app.handlers.commands import calendar_command


async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Если пользователь нажал "Да, удалить"
    if query.data == "confirm_delete_yes":
        event_id = context.user_data.get('delete_event_id')
        selected_date = context.user_data.get('selected_date')

        if event_id:
            # Выполняем физическое удаление из базы данных
            async with context.application.database.connection() as conn:
                await conn.execute("DELETE FROM events WHERE id = $1;", event_id)

        # Подчищаем за собой оперативку
        context.user_data.pop('delete_event_id', None)
        context.user_data.pop('current_day_events', None)
        context.user_data.pop('events_text', None)

        # Оповещаем пользователя и сразу вызываем календарь, чтобы обновить интерфейс
        # Для этого вызываем твой готовый calendar_command
        await query.edit_message_text(text="🗑️ Мероприятие успешно удалено!")

        # Вызываем календарь заново, чтобы юзер видел актуальную сетку месяца
        await calendar_command(update, context)
        return ConversationHandler.END

    # Если пользователь нажал "Нет, назад"
    elif query.data == "confirm_delete_no":
        # Чистим только ID удаления, массив событий оставляем
        context.user_data.pop('delete_event_id', None)

        events_text = context.user_data.get('events_text', "")
        selected_date = context.user_data.get('selected_date')

        # Возвращаем меню из 3-х кнопок ("Добавить", "Изменить", "Удcaалить")
        args = (query, selected_date.day,
                selected_date.month, selected_date.year)
        from app.handlers.states import CHOOSING_ACTION

        await handle_options_with_exist_notes_in_day(events_text, args)
        return CHOOSING_ACTION

    return ConversationHandler.END
