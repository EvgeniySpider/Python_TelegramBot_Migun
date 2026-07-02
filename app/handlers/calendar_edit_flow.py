from telegram import Update
from telegram.ext import ContextTypes
from app.handlers.states import (
    CHOOSING_EDIT_FIELD,
    TYPING_EDIT_TITLE,
    TYPING_EDIT_DESC,
    TYPING_EDIT_NUM,
    TYPING_EDIT_TIME,
    TYPING_EDIT_DATE
)
from app.core.calendar.utils import (
    build_events_list_text,
    build_detailed_event_text,
    normalize_time_str
)
from app.handlers.calendar_callbacks import handle_options_with_exist_notes_in_day
from app.handlers.calendar_keyboard import generate_edit_fields_keyboard, generate_calendar_keyboard
import re
from datetime import datetime, date
from app.core.calendar.repositories import CalendarRepository
from app.core.calendar.services import CalendarService


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

    elif query.data == "edit_field:time":
        await query.edit_message_text(
            text="⏰ Введите новый временной интервал для этого события.\n"
                 "Например: 9-10, 09:30-11 или 15:00-16:30:"
        )
        return TYPING_EDIT_TIME

    elif query.data == "edit_field:date":
        # Передаем управление специализированному хэндлеру-обертке
        return await handle_edit_field_date(update, context)


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
        updated_records = await CalendarRepository.get_events_by_date(conn, user_id, selected_date)

    context.user_data['event_text_record'] = updated_records

    # Рендерим меню дня заново
    events_text = build_events_list_text(updated_records, numbered=False)

    # Вытаскиваем статус успеха, если он есть, и тут же стираем его из ОЗУ
    success_banner = context.user_data.pop('edit_success_status', "")
    # Если баннер есть, склеиваем его с основным текстом
    full_text = f"{success_banner}\n\n{events_text}" if success_banner else events_text

    # Так как мы пришли из обычного текстового сообщения (MessageHandler),
    # передаем сам update, под капотом сработает отправка нового сообщения (reply_text)
    state = await handle_options_with_exist_notes_in_day(
        full_text, (update.callback_query, selected_date.day,
                      selected_date.month, selected_date.year)
    )
    return state


async def handle_edit_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    index_record = int(query.data.split(':')[1])
    event_text_record = context.user_data.get('event_text_record')
    event_rec = event_text_record[index_record]

    context.user_data['current_event_time'] = (event_rec['start_time'],
                                               event_rec['end_time'])
    context.user_data['edit_event_id'] = event_rec['id']
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
    context.user_data['current_event_time'] = (event_rec['start_time'],
                                               event_rec['end_time'])

    # 5. Генерируем чистую карточку без номера и выводим меню полей
    detailed_text = build_detailed_event_text(
        event_text_record, index=index_record, numbered=False)

    await update.message.reply_text(
        text='Ваша заметка, которую вы собираетесь менять:\n\n'
             f'{detailed_text}',
        reply_markup=generate_edit_fields_keyboard(),
        parse_mode="Markdown"
    )
    return CHOOSING_EDIT_FIELD


async def handle_typing_edit_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_time = update.message.text.strip().replace(' ', '')
    selected_date = context.user_data['selected_date']
    event_id = int(context.user_data['edit_event_id'])

    time_pattern = re.compile(r'^(\d{1,2}(?::\d{2})?)-(\d{1,2}(?::\d{2})?)$')
    match_object = time_pattern.fullmatch(raw_time)

    if match_object is None:
        await update.message.reply_text(
            text="❌ Неверный формат времени!\n"
                 "Пожалуйста, введите интервал (например: 9-10, 09:30-11 или 15:00-16:30):"
        )
        return TYPING_EDIT_TIME

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
        return TYPING_EDIT_TIME

    if end_time < start_time:
        await update.message.reply_text(
            text="❌ Ошибка: время начала не может быть позже времени окончания\n"
            "Попробуйте ещё раз:"
        )
        return TYPING_EDIT_TIME

    async with context.application.database.connection() as conn:
        is_busy_time = await CalendarRepository.has_time_conflict(
            conn,
            update.effective_user.id,
            selected_date,
            start_time,
            end_time,
            event_id
        )
        if is_busy_time:
            await update.message.reply_text(
                text="❌ Ошибка: это время занято\n"
                "Попробуйте ещё раз:"
            )
            return TYPING_EDIT_TIME

    async with context.application.database.connection() as conn:
        await conn.execute(
            """
            UPDATE events 
            SET start_time = $1, 
                end_time = $2, 
                event_type = 'interval' 
            WHERE id = $3
            """,
            start_time,
            end_time,
            event_id
        )

    await update.message.reply_text(
        text=f"Время события успешно изменено!\n"
        f"⏰ Время начала: {start_time.strftime('%H:%M')}\n"
        f"⏳ Время окончания: {end_time.strftime('%H:%M')}"
    )

    state = await _refresh_day_menu_after_edit(update, context)
    return state


async def handle_edit_field_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит сетку календаря для изменения даты, выполняя один чистый запрос к API."""
    query = update.callback_query
    user_id = update.effective_user.id

    extracted_date = context.user_data['selected_date']
    year, month, day = extracted_date.year, extracted_date.month, extracted_date.day

    # 2. Идем в БД за занятыми днями через готовый сервис
    async with context.application.database.connection() as conn:
        busy_days = await CalendarService.get_user_busy_days(
            conn=conn, user_id=user_id, year=year, month=month
        )

    context.user_data['month_busy_days'] = busy_days

    # 3. Генерируем клавиатуру стандартным методом
    calendar_markup = generate_calendar_keyboard(
        year=year, month=month, busy_days=busy_days, editing_day = day)
    # 4. ВЫПОЛНЯЕМ ВСЕГО ОДИН ОПРЯТНЫЙ РЕДАКТ ЭКРАНА
    await query.edit_message_text(
        text="📅 **Изменение даты события**\n\n"
             f"Изменяемая дата: {day:02d}.{month:02d}.{year}\n"
             "Выберите на календаре ниже новую дату для этого мероприятия:",
        reply_markup=calendar_markup,
        parse_mode="Markdown"
    )
    context.user_data['is_editing_date_mode'] = True # флаг-маркер
    # 5. Удерживаем пользователя в стейте ожидания клика по дню
    return TYPING_EDIT_DATE


async def handle_edit_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Выпускной экзамен: валидация конфликтов при переносе события на новую дату.
    Проверяет all_day, точечные конфликты временных интервалов и обновляет БД.
    """
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Извлекаем целевую дату из callback_data
    _, year_str, month_str, day_str = query.data.split(':')
    target_date = date(int(year_str), int(month_str), int(day_str))
    
    # --- КЕЙС: Пользователь нажал на ту же самую дату ---
    if target_date == context.user_data['selected_date']:
        await query.answer("❌ Вы выбрали ту же самую дату! Выберите другой день.")
        # ВАЖНО: Мы НЕ удаляем флаг. Мы возвращаем тот же стейт.
        # Календарь висит на экране, флаг в ОЗУ активен. Юзер может кликать дальше!
        return TYPING_EDIT_DATE

    # 3. Достаем параметры редактируемого события из ОЗУ
    event_id = context.user_data['edit_event_id']
    start_time, end_time = context.user_data['current_event_time']
    
    # Подтягиваем кэш занятых дней текущего месяца
    busy_days = context.user_data.get('month_busy_days', {})
    # Превращаем структуру в удобный словарь {day: status}, если это список Record
    busy_dict = {rec['day']: rec['status'] for rec in busy_days} if isinstance(busy_days, list) else busy_days
    target_day_status = busy_dict.get(target_date.day)


    async with context.application.database.connection() as conn:        
        # --- СЦЕНАРИЙ А: Переносим событие 'all_day' ---
        if start_time is None:
            # Если день занят хотя бы частично ('partial' или 'full') — перенос невозможен
            if target_day_status is not None:
                await query.answer(
                    "❌ Ошибка: Нельзя перенести событие 'Весь день' на эту дату, "
                    "так как день уже занят другими делами!" 
                )
                return TYPING_EDIT_DATE

        # --- СЦЕНАРИЙ Б: Переносим ИНТЕРВАЛ (interval или exact) ---
        else:
            # Если статус дня 'full', проверяем, нет ли там перекрывающего 'all_day'
            if target_day_status == 'full':
                query_all_day = """
                    SELECT EXISTS(
                        SELECT 1 FROM events 
                        WHERE user_id = $1 AND event_date = $2 AND event_type = 'all_day'
                    );
                """
                has_all_day = await conn.fetchval(query_all_day, user_id, target_date)
                if has_all_day:
                    await query.answer(
                        "❌ Ошибка: Этот день полностью занят событием 'Весь день'!"
                    )
                    return TYPING_EDIT_DATE

            # Если 'all_day' нет, проверяем пересечения по времени
            is_busy_time = await CalendarRepository.has_time_conflict(
                conn, user_id, target_date, start_time, end_time, exclude_event_id=None
            )
            if is_busy_time:
                await query.answer(
                    "❌ Ошибка: Выбранное время на этой дате уже занято другим событием!"
                )
                return TYPING_EDIT_DATE

        # --- ХЭППИ-ЭНД: Ошибок нет, делаем UPDATE ---
        await conn.execute(
            "UPDATE events SET event_date = $1 WHERE id = $2", 
            target_date, event_id
        )

    # 4. Обновляем selected_date в контексте, чтобы меню дня перерендерилось на НОВОЙ дате
    context.user_data['selected_date'] = target_date
    # Сбрасываем флаг перенаправляющий сюда по клику на день
    context.user_data.pop('is_editing_date_mode', None)
    context.user_data['edit_success_status'] = f"✅ Дата успешно изменена на {target_date.strftime('%d.%m.%Y')}!"
    
    # 5. Синхронизируем ОЗУ и возвращаем пользователя в главное меню дня
    return await _refresh_day_menu_after_edit(update, context)