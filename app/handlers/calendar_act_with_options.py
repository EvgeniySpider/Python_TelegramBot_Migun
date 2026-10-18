from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.helpers import escape_markdown

from app.core.calendar.repositories import CalendarRepository
from app.core.calendar.services import CalendarService
from app.core.calendar.utils import build_detailed_event_text, build_events_list_text
from app.handlers.calendar_callbacks import (
    handle_options_with_exist_notes_in_day,
    handle_time_selection_option,
)
from app.handlers.calendar_keyboard import (
    generate_back_to_menu_button,
    generate_confirm_keyboard,
    generate_edit_fields_keyboard,
    generate_numbered_action_keyboard,
    generate_time_options_keyboard,
)
from app.handlers.commands import calendar_command
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_EDIT_FIELD,
    CHOOSING_EVENT_TO_DELETE,
    CHOOSING_TIME,
    CONFIRMING_DELETE,
    SELECTING_EDIT_EVENT,
    SELECTING_INVITE_EVENT,
    TYPING_EDIT_NUM,
    TYPING_EVENT_NUMBER_TO_DELETE,
    TYPING_INVITE_NUM,
    TYPING_INVITEE_ID,
)
from app.handlers.utils import get_organizer_edit_error_message, get_validated_event_index, is_user_invitee_for_event
from events.models import Appointment


async def show_event_selection_list(
    query: CallbackQuery, event_text_record: list, action: str
) -> int:
    """Отрисовывает список событий (от 2 шт.) для выбора и возвращает нужный стейт."""
    event_count = len(event_text_record)

    # Генерация карточек происходит один раз
    cards = [
        build_detailed_event_text(event_text_record, index=i, numbered=True)
        for i in range(event_count)
    ]

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

    elif action == "invite":
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
            parse_mode="Markdown",
        )
        return state_inline

    # СЦЕНАРИЙ 3: Ввод текста (больше 10)
    else:
        full_text = (
            f"⚠️ Событий слишком много для отображения кнопок-номеров.\n\n{prompt_text_input}"
        ) + "\n".join(cards)
        await query.edit_message_text(
            text=full_text,
            reply_markup=generate_numbered_action_keyboard(count=None, prefix=prefix),
            parse_mode="Markdown",
        )
        return state_text


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    selected_date = context.user_data.get("selected_date")
    event_text_record = context.user_data.get("event_text_record", [])
    event_count = len(event_text_record)

    # Проверяем, какая именно кнопка была нажата
    if query.data == "action_create":
        month_busy_days = context.user_data.get("month_busy_days", {})

        if month_busy_days.get(selected_date.day) == "full":
            await query.answer(
                text="❌ Ошибка: этот день полностью занят.\nВыберите другую дату\n",
                show_alert=False,
            )
            return CHOOSING_ACTION

        args = (query, selected_date.day, selected_date.month, selected_date.year)

        # Генерируем обычный текст списка задач "на лету" без засорения context.user_data
        current_events_text = build_events_list_text(event_text_record, numbered=False)
        state = await handle_time_selection_option(args, current_events_text, is_adding=True)
        return state

    elif query.data == "action_edit":
        if event_count == 1:
            event_rec = event_text_record[0]
            selected_date = context.user_data.get("selected_date")
            user_id = update.effective_user.id

            is_invitee = await is_user_invitee_for_event(
                user_id=user_id,
                selected_date=selected_date,
                start_time=event_rec["start_time"],
                end_time=event_rec["end_time"],
            )

            if is_invitee:
                await query.answer(
                    "❌ Нельзя редактировать встречу на которую вас пригласили. Вы можете только удалить её (отменить участие).",
                    show_alert=False,
                )
                return CHOOSING_ACTION

            error_msg: str | None = await get_organizer_edit_error_message(event_rec["id"])
            if error_msg:
                await query.answer(error_msg, show_alert=False)
                return CHOOSING_ACTION

            detailed_event_text = build_detailed_event_text(
                event_text_record, index=0, numbered=False
            )

            context.user_data["current_event_time"] = (
                event_rec["start_time"],
                event_rec["end_time"],
            )
            context.user_data["edit_event_id"] = event_rec["id"]
            context.user_data["edit_event_index"] = 0

            text = f"У вас 1 заметка. Выберите опцию, чтобы отредактировать её\n\n{detailed_event_text}"
            await query.edit_message_text(
                text=text, reply_markup=generate_edit_fields_keyboard(), parse_mode="Markdown"
            )
            return CHOOSING_EDIT_FIELD

        return await show_event_selection_list(query, event_text_record, action="edit")

    elif query.data == "action_invite":
        # ---- СЦЕНАРИЙ 1: Всего одна заметка в дне ----
        if event_count == 1:
            event_rec = event_text_record[0]
            selected_date = context.user_data.get("selected_date")
            user_id = update.effective_user.id

            # Проверяем: если юзер сам гость на этой встрече — запрещаем звать других
            is_invitee = await is_user_invitee_for_event(
                user_id=user_id,
                selected_date=selected_date,
                start_time=event_rec["start_time"],
                end_time=event_rec["end_time"],
            )
            if is_invitee:
                await query.answer(
                    "❌ Приглашать участников может только организатор встречи.",
                    show_alert=False,
                )
                return CHOOSING_ACTION

            # Фиксируем в ОЗУ ID события, на которое будем приглашать
            context.user_data["invite_event_id"] = event_rec["id"]

            # Вытаскиваем название для красивого отображения
            event_title = event_text_record[0]["title"]
            safe_title = escape_markdown(event_title, version=1)
            text = (
                f"*Выбрано событие:* {safe_title}\n\n"
                "Пожалуйста, *отправьте Telegram ID* пользователя, которого хотите пригласить:"
            )

            await query.edit_message_text(
                text=text, reply_markup=generate_back_to_menu_button(), parse_mode="Markdown"
            )
            return TYPING_INVITEE_ID

        # ---- СЦЕНАРИИ 2 и 3: Если заметок больше одной ----
        return await show_event_selection_list(query, event_text_record, action="invite")

    elif query.data == "action_delete":
        # Уникальная логика, если заметка всего одна
        if event_count == 1:
            event_rec = event_text_record[0]
            context.user_data["delete_event_id"] = event_rec["id"]
            context.user_data["column_name"] = "id"

            first_sent = (
                "мероприятие на весь день?"
                if event_rec["event_type"] == "all_day"
                else "мероприятие?"
            )
            delete_text = first_sent, "заметку."

            # ИЗМЕНЕНИЕ: Используем красивую карточку
            detailed_event_text = build_detailed_event_text(
                event_text_record, index=0, numbered=False, is_show_date=True
            )
            event = f"{detailed_event_text}\n"

            state = await confirm_to_delete(query, event, delete_text)
            return state

        # Если заметок больше одной — отдаем отрисовку списка помощнику
        return await show_event_selection_list(query, event_text_record, action="delete")

    return CHOOSING_ACTION


async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await calendar_command(update, context)
    return ConversationHandler.END


async def confirm_to_delete(source: CallbackQuery | Update, event: str, delete_text: tuple) -> int:
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
        f"❓ Вы уверены, что хотите удалить {delete_text[0]}\n\n"
        f"{event}"
        f"⚠️ Это действие полностью сотрёт {delete_text[1]}"
    )

    kwargs = {
        "text": text_to_send,
        "reply_markup": generate_confirm_keyboard(),
        "parse_mode": "Markdown",
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

    context.user_data["delete_event_id"] = event_rec["id"]
    context.user_data["column_name"] = "id"

    delete_text = f"событие № {index_record + 1}?", "эту заметку."

    # ИЗМЕНЕНИЕ: Используем красивую карточку с номером
    detailed_event_text = build_detailed_event_text(
        event_text_record, index=index_record, numbered=True, is_show_date=True
    )
    event = f"{detailed_event_text}\n"

    state = await confirm_to_delete(update, event, delete_text)
    return state


async def handle_back_to_day_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_date = context.user_data.get("selected_date")

    # Защита от протухшей сессии / перезапуска бота
    if not selected_date or not update.effective_user:
        await calendar_command(update, context)
        return ConversationHandler.END

    user_id = update.effective_user.id

    # 1. СИНХРОНИЗИРУЕМ И СПИСОК СОБЫТИЙ, И КАРТУ ЗАНЯТОСТИ МЕСЯЦА:
    async with context.application.database.connection() as conn:
        event_text_record = await CalendarRepository.get_events_by_date(
            conn, user_id, selected_date
        )
        busy_days = await CalendarService.get_user_busy_days(
            conn=conn, user_id=user_id, year=selected_date.year, month=selected_date.month
        )

    # Обновляем оба кэша в ОЗУ:
    context.user_data["event_text_record"] = event_text_record
    context.user_data["month_busy_days"] = busy_days

    source = update.callback_query if update.callback_query else update
    header = context.user_data.pop("edit_success_status", "")

    # 2. Если через API удалили ВСЕ события дня — переключаем экран на чистый выбор времени
    if not event_text_record:
        events_text = "На этот день ничего не запланировано.\n"
        if hasattr(source, "edit_message_text"):
            return await handle_time_selection_option(
                (source, selected_date.day, selected_date.month, selected_date.year),
                events_text,
                is_adding=False,
            )
        else:
            await source.message.reply_text(
                text=f"📅 *Выбранная дата*: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n\n"
                f"{events_text}"
                f"Укажите формат времени проведения события:",
                reply_markup=generate_time_options_keyboard(is_adding=False),
                parse_mode="Markdown",
            )
            return CHOOSING_TIME

    # 3. Если события в дне ещё остались — показываем карточки
    event_count = len(event_text_record)
    cards = [
        build_detailed_event_text(event_text_record, index=i, numbered=True)
        for i in range(event_count)
    ]
    events_text = "\n".join(cards) + "\n"

    return await handle_options_with_exist_notes_in_day(
        events_text,
        (source, selected_date.day, selected_date.month, selected_date.year),
        header=header,
    )