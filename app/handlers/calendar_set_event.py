from telegram import Update
from telegram.ext import ContextTypes
import re
from telegram.ext import ConversationHandler
from app.handlers.states import CHOOSING_TIME, WAITING_FOR_TITLE
# event_time:all_day, event_time:interval, event_time:exact


async def handle_set_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    data = context.user_data['selected_date']

    if parts[1] == "all_day":
        await query.edit_message_text(
            text=f"Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n"
            f"Тип события: [ ☀️ Весь день ]\n"
            f"Укажите название мероприятия:\n"
            f"Например: [Поездка на дачу]"
        )
        # ГОВОРИМ АВТОМАТУ: "Юзер выбрал 'Весь день'. Ждём от него текстовое сообщение с названием!"
        return WAITING_FOR_TITLE


async def handle_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Хэндлер ловит текст названия мероприятия и записывает всё в PostgreSQL."""
    user_id = update.effective_user.id
    # 1. Достаем текст, который написал пользователь
    event_title = update.message.text

    # 2. Достаем дату, которую мы бережно протащили через context.user_data
    selected_date = context.user_data.get('selected_date')

    # 3. Делаем жесткий, атомарный асинхронный INSERT в базу данных!
    async with context.application.database.connection() as conn:
        await conn.execute(
            """
            INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            'meeting',        # Дефолтный тип из ТЗ
            event_title,       # Название, которое юзер только что ввел
            selected_date,     # Дата, которую мы помним со вчерашнего клика
            None,              # start_time для "Весь день" равен NULL
            None               # end_time для "Весь день" равен NULL
        )

    # 4. Радуем пользователя успешным успехом
    await update.message.reply_text(
        text=f"🎉 Мероприятие успешно добавлено!\n\n"
        f"📅 Дата: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n"
        f"📌 Событие: {event_title}\n"
        f"⏰ Время: Весь день"
    )

    # 5. ОЧИЩАЕМ КОНТЕКСТ, чтобы не занимать ОЗУ сервера
    context.user_data.pop('selected_date', None)

    # 6. ГОВОРИМ АВТОМАТУ: "Всё, диалог полностью завершен, сними с юзера все ярлыки!"
    return ConversationHandler.END
