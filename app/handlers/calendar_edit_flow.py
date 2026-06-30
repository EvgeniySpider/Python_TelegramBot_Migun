from telegram import Update
from telegram.ext import ContextTypes
from app.handlers.states import CHOOSING_EDIT_FIELD, TYPING_EDIT_TITLE, TYPING_EDIT_DESC
from app.core.calendar.utils import build_events_list_text
from app.handlers.calendar_callbacks import handle_options_with_exist_notes_in_day

# --- КЛИК ПО КНОПКАМ ВЫБОРА ПОЛЯ ---
async def handle_edit_field_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Перехватывает клик по кнопкам 'Название', 'Описание' или 'Назад'."""
    query = update.callback_query

    if query.data == "edit_field:title":
        await query.edit_message_text(text="📝 Введите новое название для этого события:")
        return TYPING_EDIT_TITLE

    elif query.data == "edit_field:desc":
        await query.edit_message_text(text="📖 Введите новое описание для этого события:")
        return TYPING_EDIT_DESC

    elif query.data == "edit_field:cancel":
        # Бесшовный возврат в главное меню дня
        events_text_record = context.user_data.get('event_text_record', [])
        events_text = build_events_list_text(
            events_text_record, numbered=False)
        date = context.user_data['selected_date']

        return await handle_options_with_exist_notes_in_day(
            events_text, (query, date.day, date.month, date.year)
        )


# --- ОБРАБОТКА ВВОДА ТЕКСТА ---
async def handle_typing_edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит текстовое сообщение с новым названием и пишет в БД."""
    new_title = update.message.text.strip()
    event_id = context.user_data['edit_event_id']

    # Пишем напрямую в базу
    async with context.application.database.connection() as conn:
        await conn.execute("UPDATE events SET title = $1 WHERE id = $2", new_title, event_id)

    await update.message.reply_text(text="✅ Название события успешно изменено!")

    # Сбрасываем пользователя обратно в главное меню месяца или дня
    # Для простоты пока отправляем в стейт выбора действий дня, предварительно обновив ОЗУ
    return await _refresh_day_menu_after_edit(update, context)


async def handle_typing_edit_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит текстовое сообщение с новым описанием и пишет в БД."""
    new_desc = update.message.text.strip()
    event_id = context.user_data['edit_event_id']

    async with context.application.database.connection() as conn:
        await conn.execute("UPDATE events SET description = $1 WHERE id = $2", new_desc, event_id)

    await update.message.reply_text(text="✅ Описание события успешно изменено!")
    return await _refresh_day_menu_after_edit(update, context)


# --- СЕРВИСНАЯ ФУНКЦИЯ ОБНОВЛЕНИЯ ЭКРАНА ---
async def _refresh_day_menu_after_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вспомогательная функция: перечитывает БД и возвращает юзера в меню дня."""
    user_id = update.effective_user.id
    selected_date = context.user_data['selected_date']

    # Перезапрашиваем свежие данные из базы, чтобы ОЗУ бота синхронизировалось с изменениями
    async with context.application.database.connection() as conn:
        from app.core.calendar.repositories import CalendarRepository  # Импорт по месту
        updated_records = await CalendarRepository.get_events_by_date(conn, user_id, selected_date)

    context.user_data['event_text_record'] = updated_records

    # Рендерим меню дня заново
    events_text = build_events_list_text(updated_records, numbered=False)

    # Так как мы пришли из обычного текстового сообщения (MessageHandler),
    # передаем сам update, под капотом сработает отправка нового сообщения (reply_text)
    state = await handle_options_with_exist_notes_in_day(
        events_text, (update, selected_date.day,
                      selected_date.month, selected_date.year)
    )
    return state
