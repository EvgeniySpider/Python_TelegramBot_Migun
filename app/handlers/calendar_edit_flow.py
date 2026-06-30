from telegram import Update
from telegram.ext import ContextTypes
from app.handlers.states import (
    CHOOSING_EDIT_FIELD,
    TYPING_EDIT_TITLE,
    TYPING_EDIT_DESC,
    TYPING_EDIT_NUM
)
from app.core.calendar.utils import build_events_list_text, build_detailed_event_text
from app.handlers.calendar_callbacks import handle_options_with_exist_notes_in_day
from app.handlers.calendar_keyboard import generate_edit_fields_keyboard

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


async def handle_edit_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    index_record = int(query.data.split(':')[1])
    event_text_record = context.user_data.get('event_text_record')

    context.user_data['edit_event_id'] = event_text_record[index_record]['id']
    detailed_event_text = build_detailed_event_text(
        event_text_record, index=index_record, numbered=False)

    await query.edit_message_text(
        text='Ваша заметка, которую вы собираетесь менять:\n\n'
        f'{detailed_event_text}',
        # Кнопки: Название, Время, Описание, Дата
        reply_markup=generate_edit_fields_keyboard(),
        parse_mode="Markdown"
    )
    return CHOOSING_EDIT_FIELD


async def handle_edit_event_by_text_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Логика выбора события по его текстовому номеру в чате (когда задач > 10).
    Валидирует ввод и переводит человеческий номер в индекс ОЗУ.
    """
    event_text_record = context.user_data.get('event_text_record', [])
    event_count = len(event_text_record)
    user_text = update.message.text.strip()

    # 1. Проверяем, что прислали именно число
    if not user_text.isdigit():
        await update.message.reply_text(
            f"❌ Ошибка: введите только **число** (цифру).\n"
            f"Попробуйте еще раз (от 1 до {event_count}):",
            parse_mode="Markdown"
        )
        return TYPING_EDIT_NUM

    # 2. Проверяем границы диапазона
    chosen_number = int(user_text)
    if chosen_number < 1 or chosen_number > event_count:
        await update.message.reply_text(
            f"❌ Ошибка: события под номером {chosen_number} не существует.\n"
            f"Введите число в диапазоне от 1 до {event_count}:"
        )
        return TYPING_EDIT_NUM

    # 3. Переводим человеческий шаг в машинный индекс (смещение на -1)
    index_record = chosen_number - 1
    event_rec = event_text_record[index_record]

    # 4. Фиксируем таргет в ОЗУ для будущих UPDATE-запросов
    context.user_data['edit_event_id'] = event_rec['id']
    
    # 5. Генерируем чистую карточку без номера и выводим меню полей
    detailed_text = build_detailed_event_text(event_text_record, index=index_record, numbered=False)

    await update.message.reply_text(
        text='Ваша заметка, которую вы собираетесь менять:\n\n'
             f'{detailed_text}',
        reply_markup=generate_edit_fields_keyboard(),
        parse_mode="Markdown"
    )
    return CHOOSING_EDIT_FIELD