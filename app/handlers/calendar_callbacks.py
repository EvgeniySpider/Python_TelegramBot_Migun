import datetime
from telegram import Update
from telegram.ext import ContextTypes
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_keyboard import generate_time_options_keyboard


async def handle_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if parts[0] != "calendar_day":
        return

    year = int(parts[1])
    month = int(parts[2])
    day = int(parts[3])
    
    # Формируем чистый объект даты Python
    selected_date = datetime.date(year, month, day)
    user_id = update.effective_user.id

    context.user_data['selected_date'] = selected_date

    # Открываем СВОЁ собственное соединение из пула!
    async with context.application.database.connection() as conn:
        # Проверяем, есть ли события на этот день
        events = await CalendarRepository.get_events_by_date(conn, user_id, selected_date)

    if not events:
        # ДЕНЬ СВОБОДЕН! 
        # 1. Генерируем наши новые инлайн-кнопки времени
        time_markup = generate_time_options_keyboard()
        
        # 2. Перерисовываем сообщение, прикрепляя кнопки к тексту
        await query.edit_message_text(
            text=f"Выбрана дата: {day:02d}.{month:02d}.{year}\n"
                f"На этот день ничего не запланировано.\n\n"
                f"Укажите формат времени проведения:",
            reply_markup=time_markup  # ВОТ ОНИ! Кнопки прилепились снизу текста
        )
    else:
        # ДЕНЬ ЗАНЯТ! Выводим список текущих дел
        events_text = "\n".join([f"- {e['title']}" for e in events])
        
        # Сюда мы тоже можем прикрутить кнопку, например "[ ➕ Добавить событие ]"
        # Но для стерильного теста пока просто выводим текст
        await query.edit_message_text(
            text=f"Выбрана дата: {day:02d}.{month:02d}.{year}\n"
                f"У вас уже запланировано:\n{events_text}\n\n"
                f"Желаете добавить ещё одно мероприятие?"
        )