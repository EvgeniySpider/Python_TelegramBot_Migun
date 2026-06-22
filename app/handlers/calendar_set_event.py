from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.states import WAITING_FOR_TITLE, WAITING_FOR_DESC_CHOICE, WAITING_FOR_DESCRIPTION

async def handle_set_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    data = context.user_data['selected_date']

    if parts[1] == "all_day":
        # Сразу запоминаем тип события в контекст
        context.user_data['event_type'] = 'all_day'
        context.user_data['start_time'] = None
        context.user_data['end_time'] = None

        await query.edit_message_text(
            text=f"Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n"
                 f"Тип события: [ ☀️ Весь день ]\n\n"
                 f"Укажите название мероприятия:\n"
                 f"Например: [Поездка на дачу]"
        )
        return WAITING_FOR_TITLE


async def handle_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит название, сохраняет в контекст и предлагает инлайн-кнопки описания."""
    event_title = update.message.text
    context.user_data['event_title'] = event_title

    # Готовим инлайн-кнопки
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="desc_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="desc_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=f"📌 Название «{event_title}» записано.\n\n"
             f"Хотите ли вы добавить описание (заметку) к этому мероприятию?",
        reply_markup=reply_markup
    )
    return WAITING_FOR_DESC_CHOICE


async def handle_desc_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает клик по кнопкам [Да] или [Нет]."""
    query = update.callback_query
    await query.answer()

    if query.data == "desc_no":
        # Юзер отказался от описания. Описание = None.
        context.user_data['description'] = None
        
        # Переходим к финальной точке — сохранению в базу
        await _save_event_to_db(update, context)
        return ConversationHandler.END

    if query.data == "desc_yes":
        # Юзер хочет ввести описание. Переводим стейт и просим текст.
        await query.edit_message_text(
            text="📝 Введите текст описания (заметки) для мероприятия:"
        )
        return WAITING_FOR_DESCRIPTION


async def handle_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит текст описания, сохраняет его и вызывает запись в базу."""
    context.user_data['description'] = update.message.text
    
    await _save_event_to_db(update, context)
    return ConversationHandler.END


# ВНУТРЕННЯЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ (Единая для всех веток)
async def _save_event_to_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Берет все накопленные данные из контекста и делает один чистый INSERT."""
    user_id = update.effective_user.id
    
    # Достаем всё, что накопили на прошлых шагах
    selected_date = context.user_data.get('selected_date')
    event_type = context.user_data.get('event_type')
    event_title = context.user_data.get('event_title')
    start_time = context.user_data.get('start_time')
    end_time = context.user_data.get('end_time')
    description = context.user_data.get('description')

    # Атомарный INSERT в базу
    async with context.application.database.connection() as conn:
        await conn.execute(
            """
            INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            user_id, event_type, event_title, selected_date, start_time, end_time, description
        )

    # Формируем финальный красивый рапорт пользователю
    report_text = (
        f"🎉 Мероприятие успешно добавлено!\n\n"
        f"📅 Дата: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n"
        f"📌 Событие: {event_title}\n"
        f"⏰ Время: {'Весь день' if event_type == 'all_day' else f'{start_time} - {end_time}'}\n"
    )
    
    if description:
        report_text += f"📝 Описание: {description}"

    # Отправляем рапорт. Физика отправки зависит от того, как завершился шаг:
    # Если юзер нажал "Нет" — отправляем через query.edit_message_text (так как это был CallbackQuery)
    # Если юзер ввел текст — отправляем через обычный reply_text
    if update.callback_query:
        await update.callback_query.edit_message_text(text=report_text)
    else:
        await update.message.reply_text(text=report_text)

    # Очищаем ОЗУ сервера для этого юзера
    context.user_data.clear()