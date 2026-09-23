from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from typing import Union

from app.handlers.calendar_callbacks import handle_time_selection_option, handle_options_with_exist_notes_in_day
from app.handlers.commands import calendar_command
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_EVENT_TO_DELETE,
    CONFIRMING_DELETE,
    SELECTING_INVITE_EVENT,
    TYPING_EVENT_NUMBER_TO_DELETE,
    CHOOSING_EDIT_FIELD,
    SELECTING_EDIT_EVENT,
    TYPING_EDIT_NUM,
    TYPING_INVITE_NUM,
    TYPING_INVITEE_ID
)
from app.handlers.calendar_keyboard import (
    generate_back_to_menu_button,
    generate_confirm_keyboard,
    generate_numbered_action_keyboard,
    generate_edit_fields_keyboard
)
from app.core.calendar.utils import format_event_time, build_events_list_text, build_detailed_event_text
from app.handlers.utils import get_validated_event_index, is_user_invitee_for_event


async def show_event_selection_list(query: CallbackQuery, event_text_record: list, action: str) -> int:
    """Отрисовывает список событий (от 2 шт.) для выбора и возвращает нужный стейт."""
    event_count = len(event_text_record)
    
    # Генерация карточек происходит один раз
    cards = [build_detailed_event_text(event_text_record, index=i, numbered=True) for i in range(event_count)]

    # Настраиваем тексты и стейты в зависимости от действия
    if action == "edit":
        prefix = "edit_num"
        prompt_inline = "Выберите номер события для редактирования:\n\n"
        prompt_text_input = "Отправьте номер события в чат, чтобы его изменить:\n\n"
        state_inline = SELECTING_EDIT_EVENT
        state_text = TYPING_EDIT_NUM
        
    elif action == "delete":
        prefix = "del_num"
        prompt_inline = "Выберите номер события для удаления:\n\n"
        prompt_text_input = "Отправьте номер события в чат, чтобы его удалить:\n\n"
        state_inline = CHOOSING_EVENT_TO_DELETE
        state_text = TYPING_EVENT_NUMBER_TO_DELETE

    elif action == 'invite':
        prefix = "invite_num"
        prompt_inline = "Выберите номер события для назначения встречи:\n\n"
        prompt_text_input = "Отправьте номер события в чат, чтобы назначить на него встречу:\n\n"
        state_inline = SELECTING_INVITE_EVENT
        state_text = TYPING_INVITE_NUM

    # СЦЕНАРИЙ 2: Инлайн-кнопки (от 2 до 10)
    if event_count < 11:
        full_text = prompt_inline + "\n".join(cards)
        await query.edit_message_text(
            text=full_text,
            reply_markup=generate_numbered_action_keyboard(event_count, prefix=prefix),
            parse_mode="Markdown"
        )
        return state_inline

    # СЦЕНАРИЙ 3: Ввод текста (больше 10)
    else:
        full_text = (
            "⚠️ Событий слишком много для отображения кнопок-номеров.\n\n"
            f"{prompt_text_input}"
        ) + "\n".join(cards)
        await query.edit_message_text(
            text=full_text,
            reply_markup=generate_numbered_action_keyboard(count=None, prefix=prefix),
            parse_mode="Markdown"
        )
        return state_text


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    selected_date = context.user_data.get('selected_date')
    event_text_record = context.user_data.get('event_text_record', [])
    event_count = len(event_text_record)

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
        state = await handle_time_selection_option(args, current_events_text, is_adding=True)
        return state

    elif query.data == "action_edit":
        if event_count == 1:
            event_rec = event_text_record[0]
            selected_date = context.user_data.get('selected_date')
            user_id = update.effective_user.id
            
            is_invitee = await is_user_invitee_for_event(
                user_id=user_id,
                selected_date=selected_date,
                start_time=event_rec['start_time'],
                end_time=event_rec['end_time']
            )

            if is_invitee:
                await query.answer(
                    "❌ Редактировать встречу может только организатор. Вы можете только удалить её (отменить участие).", 
                    show_alert=False
                )
                return CHOOSING_ACTION

            detailed_event_text = build_detailed_event_text(event_text_record, index=0, numbered=False)
            
            context.user_data['current_event_time'] = (event_rec['start_time'], event_rec['end_time'])
            context.user_data['edit_event_id'] = event_rec['id']
            context.user_data['edit_event_index'] = 0

            text = f"У вас 1 заметка. Выберите опцию, чтобы отредактировать её\n\n{detailed_event_text}"
            await query.edit_message_text(
                text=text,
                reply_markup=generate_edit_fields_keyboard(),
                parse_mode="Markdown"
            )
            return CHOOSING_EDIT_FIELD

        return await show_event_selection_list(query, event_text_record, action="edit")

    elif query.data == "action_invite":
        # ---- СЦЕНАРИЙ 1: Всего одна заметка в дне ----
        if event_count == 1:
            # Фиксируем в ОЗУ ID события, на которое будем приглашать
            context.user_data['invite_event_id'] = event_text_record[0]['id']
            
            # Вытаскиваем название для красивого отображения
            event_title = event_text_record[0]['title']

            text = (
                f"Выбрано событие: **{event_title}**\n\n"
                "Пожалуйста, **отправьте Telegram ID** пользователя, которого хотите пригласить:"
            )
            
            await query.edit_message_text(
                text=text,
                reply_markup=generate_back_to_menu_button(),
                parse_mode="Markdown"
            )
            return TYPING_INVITEE_ID

        # ---- СЦЕНАРИИ 2 и 3: Если заметок больше одной ----
        return await show_event_selection_list(query, event_text_record, action="invite")

    elif query.data == "action_delete":
        # Уникальная логика, если заметка всего одна (например, сразу кнопки Да/Нет)
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


        # Если заметок больше одной — отдаем отрисовку списка помощнику
        return await show_event_selection_list(query, event_text_record, action="delete")


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

    is_valid, result, event_text_record = await get_validated_event_index(
        update, context, TYPING_EVENT_NUMBER_TO_DELETE
    )
    if not is_valid:
        return result
    
    index_record = result
    event_rec = event_text_record[index_record]

    context.user_data['delete_event_id'] = event_rec['id']
    context.user_data['column_name'] = 'id'

    selected_date = context.user_data.get('selected_date')
    delete_text = f"событие № {index_record - 1}?", "эту заметку."

    event_time = format_event_time(
        event_rec["start_time"], event_rec["end_time"])
    event = f"📌 *Событие*: \\[{event_time}] {event_rec['title']}\n"

    state = await confirm_to_delete(update, event, selected_date, delete_text)
    return state


async def handle_back_to_day_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_text_record = context.user_data['event_text_record']
    event_count = len(event_text_record)
    cards = [build_detailed_event_text(
            event_text_record, index=i, numbered=True) for i in range(event_count)]
    events_text = "\n".join(cards) + '\n'

    source = update.callback_query if update.callback_query else update
    date = context.user_data['selected_date']
    header = context.user_data.get('edit_success_status', '')

    return await handle_options_with_exist_notes_in_day(events_text,(source, date.day, date.month, date.year), header=header)
