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
from app.handlers.calendar_keyboard import generate_yes_no_keyboard
from app.core.calendar.repositories import CalendarRepository
import re
from app.core.calendar.utils import (
    format_event_time,
    build_events_list_text,
    normalize_time_str
)


async def handle_set_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    parts = query.data.split(":")
    data = context.user_data.get('selected_date')
    event_text_record = context.user_data.get('event_text_record', [])

    if parts[1] == "all_day":
        context.user_data['event_type'] = 'all_day'
        month_busy_days = context.user_data.get('month_busy_days', {})

        if data.day in month_busy_days:
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
        # Магия: генерируем актуальный список на лету из первоисточника
        events_text = build_events_list_text(event_text_record, numbered=False)

        await query.edit_message_text(
            text=f"📅 Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n\n"
            f"{events_text}"
            f"Тип события: [ ⏱️ Точное время ]\n\n"
            f"⌨️ Введите время начала мероприятия в формате ЧЧ:ММ\n"
            f"Например: [ 14:00 ] или [ 09:30 ]"
        )
        return WAITING_FOR_TIME_INPUT_EXACT

    elif parts[1] == "interval":
        context.user_data['event_type'] = 'interval'
        # Магия: генерируем актуальный список на лету из первоисточника
        events_text = build_events_list_text(event_text_record, numbered=False)

        await query.edit_message_text(
            text=f"📅 Выбрана дата: {data.day:02d}.{data.month:02d}.{data.year}\n\n"
            f"{events_text}"
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

    try:
        start_clean = normalize_time_str(raw_start)
        end_clean = normalize_time_str(raw_end)

        start_time = datetime.strptime(start_clean, "%H:%M").time()
        end_time = datetime.strptime(end_clean, "%H:%M").time()
    except ValueError:
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
    raw_time = update.message.text.strip().replace(' ', '')
    selected_date = context.user_data['selected_date']

    time_pattern = re.compile(r'^(\d{1,2})(?::(\d{2}))?$')
    match_object = time_pattern.fullmatch(raw_time)

    if match_object is None:
        await update.message.reply_text(
            text="❌ Неверный формат времени!\n"
                 "Пожалуйста, введите время (например: 9, 09:30 или 15:00):"
        )
        return WAITING_FOR_TIME_INPUT_EXACT

    hours, minutes = match_object[1], match_object[2]

    if minutes is None:
        clean_time = f"{int(hours):02d}:00"
    else:
        clean_time = f"{int(hours):02d}:{minutes}"

    try:
        start_time = datetime.strptime(clean_time, "%H:%M").time()
    except ValueError:
        await update.message.reply_text(
            text="❌ Введено некорректное время суток (максимум 23:59)!\n"
                 "Попробуйте ещё раз:"
        )
        return WAITING_FOR_TIME_INPUT_EXACT

    dt_start = datetime.combine(selected_date, start_time)
    dt_end = dt_start + timedelta(minutes=30)

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
                     "Попробуйте ещё раз:"
            )
            return WAITING_FOR_TIME_INPUT_EXACT

    context.user_data['start_time'] = start_time
    context.user_data['end_time'] = end_time

    await update.message.reply_text(
        text=f"⏰ Время начала: {start_time.strftime('%H:%M')}\n"
        f"⏳ Время окончания (авто): {end_time.strftime('%H:%M')}\n\n"
        f"Укажите название мероприятия:\n"
        f"Например: [ Выбросить мусор ]"
    )
    return WAITING_FOR_TITLE


async def handle_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_title = update.message.text
    context.user_data['event_title'] = event_title

    await update.message.reply_text(
        text=f"📌 Название «{event_title}» записано.\n\n"
        f"Хотите ли вы добавить описание (заметку) к этому мероприятию?",
        reply_markup=generate_yes_no_keyboard()
    )
    return WAITING_FOR_DESC_CHOICE


async def handle_desc_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "desc_no":
        context.user_data['description'] = None
        state = await _save_event_to_db(update, context)
        return state

    if query.data == "desc_yes":
        await query.edit_message_text(
            text="📝 Введите текст описания (заметки) для мероприятия:"
        )
        return WAITING_FOR_DESCRIPTION


async def handle_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['description'] = update.message.text
    state = await _save_event_to_db(update, context)
    return state


async def _save_event_to_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    selected_date = context.user_data.get('selected_date')
    event_type = context.user_data.get('event_type')
    event_title = context.user_data.get('event_title')
    start_time = context.user_data.get('start_time')
    end_time = context.user_data.get('end_time')
    description = context.user_data.get('description')

    async with context.application.database.connection() as conn:
        await conn.execute(
            """
            INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            user_id, event_type, event_title, selected_date, start_time, end_time, description
        )

    if event_type == 'all_day':
        duration_text = 'Весь день'
    else:
        duration_text = format_event_time(start_time, end_time)

    report_text = (
        f"*🎉 Мероприятие успешно добавлено!*\n"
        f"📅 Дата: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n"
        f"📌 Событие: {event_title}\n"
        f"⏰ Время: {duration_text}\n"
    )

    if description:
        report_text += f"📝 Описание: {description}\n\n"

    context.user_data['edit_success_status'] = report_text

    # --- ТОТАЛЬНАЯ СИНХРОНИЗАЦИЯ ОЗУ С БД ---
    from app.core.calendar.repositories import CalendarRepository
    # Импортируем сервис, который считает занятые дни
    from app.core.calendar.services import CalendarService

    async with context.application.database.connection() as conn:
        # 1. Обновляем список текстовых записей дня (чтобы удалить/изменить видели всё)
        updated_records = await CalendarRepository.get_events_by_date(conn, user_id, selected_date)
        
        # 2. Пересчитываем занятые дни месяца (чтобы кнопка "Добавить" знала про лимиты)
        busy_days = await CalendarService.get_user_busy_days(
            conn=conn,
            user_id=user_id,
            year=selected_date.year,
            month=selected_date.month
        )
    
    # Записываем свежие данные в ОЗУ
    context.user_data['event_text_record'] = updated_records
    context.user_data['month_busy_days'] = busy_days

    from app.handlers.calendar_act_with_options import handle_back_to_day_menu_click
    state = await handle_back_to_day_menu_click(update, context)

    # Чистим только временный мусор конструктора
    for key in ['event_type', 'event_title', 'start_time', 'end_time', 'description']:
        context.user_data.pop(key, None)

    return state
