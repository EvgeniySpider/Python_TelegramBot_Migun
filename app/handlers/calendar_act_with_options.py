from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.handlers.commands import calendar_command
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_EVENT_TO_DELETE,
    CONFIRMING_DELETE,
    TYPING_EVENT_NUMBER_TO_DELETE)
from app.handlers.calendar_keyboard import generate_confirm_keyboard, generate_numbered_events_keyboard
from app.core.calendar.utils import format_event_time, build_events_list_text
from typing import Union


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    selected_date = context.user_data.get('selected_date')
    event_text_record = context.user_data.get('event_text_record', [])

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

        # Генерируем обычный текст списка задач "на лету" без засорения context.user_data
        current_events_text = build_events_list_text(
            event_text_record, numbered=False)
        state = await handle_time_selection_option(args, current_events_text)
        return state

    elif query.data == "action_edit":
        pass

    elif query.data == "action_delete":
        event_count = len(event_text_record)

        # СЦЕНАРИЙ 1: Событие ровно одно
        if event_count == 1:
            event_rec = event_text_record[0]

            context.user_data['delete_event_id'] = event_rec['id']
            context.user_data['column_name'] = 'id'

            first_sent = 'мероприятие на весь день?' if event_rec[
                'event_type'] == 'all_day' else 'мероприятие?'
            delete_text = first_sent, 'заметку.'
            event = f'📌 *Событие*: {event_rec["title"]}\n'

            state = await confirm_to_delete(query, event, selected_date, delete_text)
            return state

        # СЦЕНАРИИ 2 и 3: Событий несколько
        else:
            # Магия: генерируем строго пронумерованный список одной строчкой кода!
            events_list_text = build_events_list_text(
                event_text_record, numbered=True)

            if event_count < 11:
                # Сценарий 2: Кнопок немного — выводим inline-клавиатуру номеров
                await query.edit_message_text(
                    text="Нажмите на номер события, которое хотите удалить:\n\n"
                         f"{events_list_text}",
                    reply_markup=generate_numbered_events_keyboard(
                        event_count),
                    parse_mode="Markdown"
                )
                return CHOOSING_EVENT_TO_DELETE
            else:
                # Сценарий 3: Событий > 10 — вызываем клавиатуру без аргументов (только нижний ряд)
                await query.edit_message_text(
                    text="⚠️ Событий слишком много для отображения кнопок-номеров.\n\n"
                         "1️⃣ **Пришлите цифру (номер) события** в ответном сообщении, чтобы удалить его отдельно.\n"
                         "2️⃣ Либо нажмите кнопку ниже, чтобы очистить весь день разом:\n\n"
                         f"{events_list_text}",
                    reply_markup=generate_numbered_events_keyboard(),
                    parse_mode="Markdown"
                )
                return TYPING_EVENT_NUMBER_TO_DELETE


async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await calendar_command(update, context)
    return ConversationHandler.END


async def confirm_to_delete(
    source: Union[CallbackQuery, Update],
    event: str,
    selected_date,
    delete_text: tuple
) -> int:
    """
    Универсальный фабричный хэндлер для рендеринга и отправки окна подтверждения удаления.
    Динамически адаптируется под тип входящего события (клик по кнопке или текстовое сообщение).

    Механика отправки:
    - Проверяет через hasattr наличие метода 'edit_message_text'.
    - Если True (вход по CallbackQuery): выполняет изменение старого сообщения «на лету»
      без спама в чат.
    - Если False (вход по Update через текст): отправляет новое сообщение ответом (reply_text).

    Args:
        source (Union[CallbackQuery, Update]): Источник вызова.
        event (str): Сформированное строковое превью удаляемого события (или пачки событий).
        selected_date (datetime.date): Целевая дата проведения мероприятия.
        delete_text (tuple): Двухэлементный кортеж строк для динамической подстановки склонений 
                             (например: ("событие №1?", "эту заметку.")).

    Returns:
        int: Состояние CONFIRMING_DELETE для перехвата следующего клика пользователя (Да/Нет).
    """

    text_to_send = (
        f"❓ *Вы уверены, что хотите удалить {delete_text[0]}*\n\n"
        f"{event}"
        f"📅 *Дата*: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n\n"
        f"⚠️ Это действие полностью сотрёт {delete_text[1]}"
    )

    kwargs = {
        "text": text_to_send,
        "reply_markup": generate_confirm_keyboard(),
        "parse_mode": "Markdown"
    }

    if hasattr(source, "edit_message_text"):
        await source.edit_message_text(**kwargs)
    else:
        await source.message.reply_text(**kwargs)

    return CONFIRMING_DELETE


async def handle_delete_event_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Логика удаления событий, когда их в выбранном дне больше 10 штук.
    Инлайн-кнопки не генерируются. Хэндлер перехватывает текстовое сообщение от юзера.

    Пошаговая магия трансляции интерфейса в индекс:
    1. Валидация строки (.isdigit()): проверяет, что прислали именно цифру, а не текст.
    2. Валидация диапазона (от 1 до len(records)): защищает от ввода несуществующих номеров.
       - При любых ошибках валидации возвращает юзера в текущий стейт TYPING_EVENT_NUMBER_TO_DELETE.
    3. Вычисление индекса в Python (Смещение на -1):
       - id_event = chosen_number - 1 (из человеческого "номер 1" получаем компьютерный индекс "0").
    4. Захват первоисточника: выдергивает конкретный Record из ОЗУ по вычисленному индексу.
    5. Фиксация таргетов удаления в ОЗУ для будущего SQL-запроса:
       - context.user_data['column_name'] = 'id'
       - context.user_data['delete_event_id'] = event_rec['id'] (первичный ключ Postgres).
    6. Вызывает универсальный экран подтверждения confirm_to_delete.

    Возвращает стейт CONFIRMING_DELETE.
    """

    event_text_record = context.user_data.get('event_text_record', [])
    event_count = len(event_text_record)
    user_text = update.message.text.strip()

    if not user_text.isdigit():
        await update.message.reply_text(
            f"❌ Ошибка: введите только **число** (цифру).\n"
            f"Попробуйте еще раз (от 1 до {event_count}):",
            parse_mode="Markdown"
        )
        return TYPING_EVENT_NUMBER_TO_DELETE

    chosen_number = int(user_text)
    if chosen_number < 1 or chosen_number > event_count:
        await update.message.reply_text(
            f"❌ Ошибка: события под номером {chosen_number} не существует.\n"
            f"Введите число в диапазоне от 1 до {event_count}:"
        )
        return TYPING_EVENT_NUMBER_TO_DELETE

    id_event = chosen_number - 1
    event_rec = event_text_record[id_event]

    context.user_data['delete_event_id'] = event_rec['id']
    context.user_data['column_name'] = 'id'

    selected_date = context.user_data.get('selected_date')
    delete_text = f"событие № {chosen_number}?", "эту заметку."

    event_time = format_event_time(
        event_rec["start_time"], event_rec["end_time"])
    event = f"📌 *Событие*: \\[{event_time}] {event_rec['title']}\n"

    state = await confirm_to_delete(update, event, selected_date, delete_text)
    return state
