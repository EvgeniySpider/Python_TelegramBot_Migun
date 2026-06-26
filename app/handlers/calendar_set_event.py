from datetime import datetime, timedelta, time
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.states import (
    WAITING_FOR_TITLE,
    WAITING_FOR_DESC_CHOICE,
    WAITING_FOR_DESCRIPTION,
    WAITING_FOR_TIME_INPUT_EXACT,
    CHOOSING_TIME,
    WAITING_FOR_TIME_INPUT_INTERVAL
)
from app.handlers.calendar_keyboard import generate_yes_no_keyboards
from app.core.calendar.repositories import CalendarRepository
import re


async def handle_set_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    parts = query.data.split(":")
    data = context.user_data['selected_date']

    if parts[1] == "all_day":
        context.user_data['event_type'] = 'all_day'
        async with context.application.database.connection() as conn:
            is_event = await CalendarRepository.get_events_by_date(
                conn,
                update.effective_user.id,
                data
            )
            if is_event:
                await query.answer(
                    text=f'❌ Ошибка: этот день частично занят\n'
                    f'Выберите другую дату\n',
                    show_alert=False
                )
                return CHOOSING_TIME

        await query.edit_message_text(
            text=f"Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n"
            f"Тип события: [ ☀️ Весь день ]\n\n"
            f"Укажите название мероприятия:\n"
            f"Например: [Поездка на дачу]"
        )
        return WAITING_FOR_TITLE

    elif parts[1] == "exact":
        context.user_data['event_type'] = 'exact'

        await query.edit_message_text(
            text=f"📅 Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n"
            f"Тип события: [ ⏱️ Точное время ]\n\n"
            f"⌨️ Введите время начала мероприятия в формате ЧЧ:ММ\n"
            f"Например: [ 14:00 ] или [ 09:30 ]"
        )
        return WAITING_FOR_TIME_INPUT_EXACT

    elif parts[1] == "interval":
        context.user_data['event_type'] = 'interval'
        await query.edit_message_text(
            text=f"📅 Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n"
            f"Тип события: [ ⏳ Интервал ]\n\n"
            f"⌨️ Введите время начала и конца мероприятия в формате ЧЧ:ММ-ЧЧ:ММ\n"
            f"Например: [ 9-10 ], [ 6:30-8:30 ] или [ 14-16:30 ]"
        )
        return WAITING_FOR_TIME_INPUT_INTERVAL


async def handle_time_input_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_time = update.message.text.strip().replace(' ', '')
    selected_date = context.user_data['selected_date']

    time_pattern = re.compile(r'^(\d{1,2}(?::\d{2})?)-(\d{1,2}(?::\d{2})?)$')
    match_object = time_pattern.fullmatch(raw_time)

    if match_object is None:
        await update.message.reply_text(
            text="❌ Неверный формат времени!\n"
                 "Пожалуйста, введите интервал (например: 9-10, 09:30-11 или 15:00-16:30):"
        )
        return WAITING_FOR_TIME_INPUT_INTERVAL

    raw_start, raw_end = match_object[1], match_object[2]
    # Вспомогательная функция для превращения "9" в "09:00", а "14:30" в "14:30"

    def normalize_time_str(t_str: str) -> str:
        if ":" not in t_str:
            # Перевод в int уберёт проблемы с "09" -> "09:00"
            return f"{int(t_str):02d}:00"
        else:
            hours, minutes = t_str.split(":")
            return f"{int(hours):02d}:{minutes}"

    try:
        start_clean = normalize_time_str(raw_start)
        end_clean = normalize_time_str(raw_end)

        start_time = datetime.strptime(start_clean, "%H:%M").time()
        end_time = datetime.strptime(end_clean, "%H:%M").time()
    except ValueError:
        # Сработает, если юзер ввёл несуществующее время, например "25:00-29:00" или "12:65"
        await update.message.reply_text(
            text="❌ Введено некорректное время суток (максимум 23:59)!\n"
            "Попробуйте ещё раз:"
        )
        return WAITING_FOR_TIME_INPUT_INTERVAL

    if end_time < start_time:
        await update.message.reply_text(
            text="❌ Ошибка: время начала не может быть позже времени окончания\n"
            "Попробуйте ещё раз:"
        )
        return WAITING_FOR_TIME_INPUT_INTERVAL

    async with context.application.database.connection() as conn:
        is_busy_time = await CalendarRepository.has_time_conflict(
            conn,
            update.effective_user.id,
            selected_date,
            start_time,
            end_time
        )
        if is_busy_time:
            await update.message.reply_text(
                text="❌ Ошибка: это время занято\n"
                "Попробуйте ещё раз:"
            )
            return WAITING_FOR_TIME_INPUT_INTERVAL

    context.user_data['start_time'] = start_time
    context.user_data['end_time'] = end_time

    await update.message.reply_text(
        text=f"⏰ Время начала: {start_time.strftime('%H:%M')}\n"
        f"⏳ Время окончания: {end_time.strftime('%H:%M')}\n\n"
        f"Укажите название мероприятия:\n"
        f"Например: [ Выбросить мусор ]"
    )
    return WAITING_FOR_TITLE


async def handle_time_input_exact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит строку времени, проверяет её формат, рассчитывает интервал +30 минут."""
    raw_time = update.message.text.strip()
    selected_date = context.user_data['selected_date']

    # 1. Валидируем формат ЧЧ:ММ
    try:
        # Пытаемся распарсить время
        parsed_time = datetime.strptime(raw_time, "%H:%M")
        # Превращаем в чистый объект time для БД
        start_time = parsed_time.time()
    except ValueError:
        # Если юзер ввёл херню — не меняем стейт, просим ввести заново
        await update.message.reply_text(
            text="❌ Неверный формат времени!\n"
                 "Пожалуйста, введите время строго в формате ЧЧ:ММ (например, 15:30):"
        )
        return WAITING_FOR_TIME_INPUT_EXACT

    # 2. Логика интервала по умолчанию (+30 минут)
    # Переводим в datetime для удобного математического сдвига через timedelta
    dt_start = datetime.combine(selected_date, start_time)
    dt_end = dt_start + timedelta(minutes=30)
    end_time = dt_end.time()

    if dt_end.date() != selected_date:
        end_time = time(23, 59, 59)
    else:
        end_time = dt_end.time()

    async with context.application.database.connection() as conn:
        is_busy_time = await CalendarRepository.has_time_conflict(
            conn,
            update.effective_user.id,
            selected_date,
            start_time,
            end_time
        )
        if is_busy_time:
            await update.message.reply_text(
                text="❌ Ошибка: это время занято\n"
                "Попробуйте ещё раз"
            )
            return WAITING_FOR_TIME_INPUT_EXACT

    # 3. Сохраняем расчеты в оперативку (user_data)
    context.user_data['start_time'] = start_time
    context.user_data['end_time'] = end_time

    # Переводим на следующий шаг — ввод названия
    await update.message.reply_text(
        text=f"⏰ Время начала: {start_time.strftime('%H:%M')}\n"
        f"⏳ Время окончания (авто): {end_time.strftime('%H:%M')}\n\n"
        f"Укажите название мероприятия:\n"
        f"Например: [ Выбросить мусор ]"
    )
    return WAITING_FOR_TITLE


async def handle_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит название, сохраняет в контекст и предлагает инлайн-кнопки описания."""
    event_title = update.message.text
    context.user_data['event_title'] = event_title

    await update.message.reply_text(
        text=f"📌 Название «{event_title}» записано.\n\n"
        f"Хотите ли вы добавить описание (заметку) к этому мероприятию?",
        reply_markup=generate_yes_no_keyboards()
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
