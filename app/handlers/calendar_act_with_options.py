from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.handlers.commands import calendar_command
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_EVENT_TO_DELETE,
    CONFIRMING_DELETE,
    TYPING_EVENT_NUMBER_TO_DELETE)
from app.handlers.calendar_keyboard import generate_confirm_keyboard, generate_numbered_events_keyboard
from app.core.calendar.utils import format_event_time


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
            return CHOOSING_ACTION

        args = (query, selected_date.day,
                selected_date.month, selected_date.year)

        # Напрямую вызываем корутину и возвращаем её стейт (CHOOSING_TIME)
        state = await handle_time_selection_option(args, events_text)
        return state

    # Заглушки под остальные кнопки на будущее
    elif query.data == "action_edit":
        pass

    elif query.data == "action_delete":
        event_count = len(current_day_events)
        # СЦЕНАРИЙ 1: Событие ровно одно и это "Весь день"
        # Проверяем либо через структуру данных, либо через твою идею с текстом: "(весь день)" in events_text
        if event_count == 1:
            event_rec = current_day_events[0]

            # Сохраняем ID этого единственного события в контекст для будущего SQL-запроса DELETE
            context.user_data['delete_event_id'] = event_rec['id']
            context.user_data['column_name'] = 'id'
            first_sent = 'мероприятие на весь день?' if current_day_events[
                0]['event_type'] == 'all_day' else 'мероприятие?'
            delete_text = first_sent, 'заметку.'
            event = f'📌 *Событие*: {event_rec['title']}\n'

            # async def confirm_to_delete(query, event, selected_date, delete_text):
            state = await confirm_to_delete(query, event, selected_date, delete_text)
            return state

        # СЦЕНАРИИ 2 и 3: Событий несколько
        else:
            # 1. Единый цикл сборки текстового представления событий
            numbered_events = []
            for i, rec in enumerate(current_day_events):
                event_time = format_event_time(
                    rec['start_time'], rec['end_time'])
                # Используем универсальный формат отображения списка
                st = f'[ {i+1} ]    [{event_time}] {rec["title"]}'
                numbered_events.append(st)

            events_list_text = '\n'.join(numbered_events)

            # 2. Развилка логики в зависимости от количества (лимит 10 кнопок)
            if event_count < 11:
                # Сценарий 2: Кнопок немного — выводим inline-клавиатуру
                await query.edit_message_text(
                    text="Нажмите на номер события, которое хотите удалить:\n\n"
                         f"{events_list_text}",
                    reply_markup=generate_numbered_events_keyboard(event_count)
                )
                return CHOOSING_EVENT_TO_DELETE
            else:
                # Сценарий 3: Событий > 10 — просто вызываем БЕЗ аргументов! 
                # Юзер получит только две нижние кнопки, а бот будет ждать цифру текстом.
                await query.edit_message_text(
                    text="⚠️ Событий слишком много для отображения кнопок-номеров.\n\n"
                         "1️⃣ **Пришлите цифру (номер) события** в ответном сообщении, чтобы удалить его отдельно.\n"
                         "2️⃣ Либо нажмите кнопку ниже, чтобы очистить весь день разом:\n\n"
                         f"{events_list_text}",
                    reply_markup=generate_numbered_events_keyboard(), # Вот она, магия!
                    parse_mode="Markdown"
                )
                return TYPING_EVENT_NUMBER_TO_DELETE


# --- ТОЧЕЧНЫЙ ХЭНДЛЕР ВОЗВРАТА К КАЛЕНДАРЮ ---
async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Гасим часики
    await update.callback_query.answer()
    await calendar_command(update, context)
    return ConversationHandler.END


async def confirm_to_delete(source, event, selected_date, delete_text):
    """
    Универсальная функция отправки окна подтверждения.
    source: может быть как CallbackQuery (при клике), так и Update (при вводе текста)
    """
    # 1. Формируем единый текст
    text_to_send = (
        f"❓ *Вы уверены, что хотите удалить {delete_text[0]}*\n\n"
        f"{event}"
        f"📅 *Дата*: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n\n"
        f"⚠️ Это действие полностью сотрёт {delete_text[1]}"
    )

    # 2. Общие параметры для отправки
    kwargs = {
        "text": text_to_send,
        "reply_markup": generate_confirm_keyboard(),
        "parse_mode": "Markdown"
    }

    # 3. Элегантная развилка: определяем, как именно отправлять
    # Если это CallbackQuery (есть атрибут edit_message_text)
    if hasattr(source, "edit_message_text"):
        await source.edit_message_text(**kwargs)
    else:
        # Если это Update от текстового сообщения
        await source.message.reply_text(**kwargs)

    return CONFIRMING_DELETE


async def handle_delete_event_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current_day_events = context.user_data.get('current_day_events', [])
    event_count = len(current_day_events)
    user_text = update.message.text.strip()

    # 1. Валидация: проверяем, что введена строка из цифр
    if not user_text.isdigit():
        await update.message.reply_text(
            f"❌ Ошибка: введите только **число** (цифру).\n"
            f"Попробуйте еще раз (от 1 до {event_count}):",
            parse_mode="Markdown"
        )
        return TYPING_EVENT_NUMBER_TO_DELETE  # Удерживаем в этом же стейте

    # 2. Валидация: переводим в int и проверяем границы диапазона
    chosen_number = int(user_text)
    if chosen_number < 1 or chosen_number > event_count:
        await update.message.reply_text(
            f"❌ Ошибка: события под номером {chosen_number} не существует.\n"
            f"Введите число в диапазоне от 1 до {event_count}:"
        )
        return TYPING_EVENT_NUMBER_TO_DELETE  # Удерживаем в этом же стейте

    # --- Если валидация успешна, логика полностью повторяет клик по inline-кнопке ---
    id_event = chosen_number - 1  # Переводим в индекс массива (0, 1, 2...)
    event_rec = current_day_events[id_event]

    # Сохраняем таргеты для удаления в ОЗУ
    context.user_data['delete_event_id'] = event_rec['id']
    context.user_data['column_name'] = 'id'

    selected_date = context.user_data.get('selected_date')
    delete_text = f"событие № {chosen_number}?", "эту заметку."

    event_time = format_event_time(
        event_rec["start_time"], event_rec["end_time"])
    event = f"📌 *Событие*: [{event_time}] {event_rec['title']}\n"

    state = await confirm_to_delete(update, event, selected_date, delete_text)
    return state
