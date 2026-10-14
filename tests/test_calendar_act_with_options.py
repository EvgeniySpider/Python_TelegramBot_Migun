from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup

from app.core.calendar.utils import build_detailed_event_text
from app.handlers.calendar_act_with_options import (
    confirm_to_delete,
    handle_delete_event_by_number,
    handle_options_click,
)
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
from events.models import Appointment


@pytest.mark.asyncio
async def test_handle_options_click_create_full_day():
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_create"

    # Имитируем, что день полностью забит ('full')
    context_mock.user_data = {"selected_date": date(2026, 10, 20), "month_busy_days": {20: "full"}}

    result: int = await handle_options_click(update_mock, context_mock)

    # Проверяем, что хэндлер отбил нас назад
    assert result == CHOOSING_ACTION

    # Проверяем текст алерта
    update_mock.callback_query.answer.assert_awaited_once()
    kwargs = update_mock.callback_query.answer.call_args.kwargs
    assert "❌ Ошибка: этот день полностью занят" in kwargs["text"]
    assert kwargs["show_alert"] is False


@pytest.mark.asyncio
@patch("app.handlers.calendar_callbacks.generate_time_options_keyboard")
async def test_handle_options_click_create_success(mock_keyboard):
    mock_keyboard.return_value = "fake_keyboard"

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_create"

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "month_busy_days": {},  # Нет метки 'full'
        "event_text_record": [
            {
                "title": "Уборка",
                "start_time": time(8, 0),
                "end_time": time(9, 0),
                "event_type": "interval",
            }
        ],
    }

    result: int = await handle_options_click(update_mock, context_mock)

    # Проверяем успешный переход к выбору типа времени
    assert result == CHOOSING_TIME

    # Проверяем, что алерт об ошибке не вызывался
    update_mock.callback_query.answer.assert_not_called()

    # Проверяем, что текст изменился через функцию handle_time_selection_option
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    # Проверяем интеграцию всех частей: даты, списка событий и текста-инструкции
    assert "📅 *Выбранная дата*: 20.10.2026" in kwargs["text"]
    assert (
        "08:00 - 09:00 Уборка" in kwargs["text"]
    )  # Убеждаемся, что build_events_list_text вшил заметку
    assert "Укажите формат времени проведения события:" in kwargs["text"]

    # Убеждаемся, что клавиатура прикрепилась и формат Markdown включен
    assert kwargs["reply_markup"] == "fake_keyboard"
    assert kwargs["parse_mode"] == "Markdown"

    # Проверяем, что в клавиатуру ушел правильный флаг is_adding=True
    mock_keyboard.assert_called_once_with(True)


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.is_user_invitee_for_event")
async def test_handle_options_click_edit_one_event_is_invitee(mock_is_invitee: AsyncMock):
    # ПОДГОТОВКА
    # Имитируем, что пользователя пригласили на эту встречу
    mock_is_invitee.return_value = True

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_edit"
    update_mock.effective_user.id = 12345

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 101,
                "title": "Встреча",
                "start_time": time(10, 0),
                "end_time": time(11, 0),
                "event_type": "interval",
            }
        ],
    }

    # ВЫЗОВ
    result = await handle_options_click(update_mock, context_mock)

    # ПРОВЕРКИ
    # Проверяем, что хэндлер отбил попытку и вернул в меню
    assert result == CHOOSING_ACTION

    # Проверяем аргументы вызова функции-проверки
    mock_is_invitee.assert_called_once_with(
        user_id=12345,
        selected_date=date(2026, 10, 20),
        start_time=time(10, 0),
        end_time=time(11, 0),
    )

    update_mock.callback_query.answer.assert_awaited_once()
    all_args = update_mock.callback_query.answer.call_args
    arg, kwarg = all_args.args[0], all_args.kwargs["show_alert"]

    assert "Нельзя редактировать встречу на которую вас пригласили" in arg
    assert kwarg is False


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.Appointment")
@patch("app.handlers.calendar_act_with_options.is_user_invitee_for_event")
async def test_handle_options_click_edit_one_event_is_organizer(
    mock_is_invitee: AsyncMock, mock_appointment: MagicMock
):
    # ПОДГОТОВКА
    # Пользователь НЕ является приглашенным...
    mock_is_invitee.return_value = False

    # ...НО он сам пригласил кого-то (мокаем цепочку Django ORM .objects.filter().aexists())
    aexists_mock = AsyncMock(return_value=True)
    mock_appointment.objects.filter.return_value.aexists = aexists_mock

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_edit"

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 102,
                "title": "Встреча 2",
                "start_time": time(12, 0),
                "end_time": time(13, 0),
                "event_type": "interval",
            }
        ],
    }

    # ВЫЗОВ
    result = await handle_options_click(update_mock, context_mock)

    # ПРОВЕРКИ
    assert result == CHOOSING_ACTION

    # Убеждаемся, что фильтрация в ORM произошла по правильному ID события
    mock_appointment.objects.filter.assert_called_once_with(event=102, status=mock_appointment.Status.CONFIRMED)
    aexists_mock.assert_awaited_once()

    update_mock.callback_query.answer.assert_awaited_once()
    arg = update_mock.callback_query.answer.call_args.args[0]
    assert "Нельзя редактировать встречу на которую Вы пригласили людей" in arg


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.Appointment")
@patch("app.handlers.calendar_act_with_options.is_user_invitee_for_event")
async def test_handle_options_click_edit_one_event(
    mock_is_invitee: AsyncMock, mock_appointment: MagicMock
):
    mock_is_invitee.return_value = False

    aexists_mock = AsyncMock(return_value=False)
    mock_appointment.objects.filter.return_value.aexists = aexists_mock

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_edit"
    update_mock.effective_user.id = 12345

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 102,
                "title": "Встреча 2",
                "start_time": time(12, 0),
                "end_time": time(13, 0),
                "event_type": "interval",
            }
        ],
    }

    result: int = await handle_options_click(update_mock, context_mock)

    assert result == CHOOSING_EDIT_FIELD

    mock_is_invitee.assert_called_once_with(
        user_id=12345,
        selected_date=date(2026, 10, 20),
        start_time=time(12, 0),
        end_time=time(13, 0),
    )

    # Убеждаемся что query.answer не вызывался
    update_mock.callback_query.answer.assert_not_awaited()

    # Проверяем что в контекст записались все поля для следующего шага
    assert context_mock.user_data["current_event_time"] == (time(12, 0), time(13, 0))
    assert context_mock.user_data["edit_event_id"] == 102
    assert context_mock.user_data["edit_event_index"] == 0

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    text = kwargs["text"]
    reply_markup: InlineKeyboardMarkup = kwargs["reply_markup"]
    parse_mode = kwargs["parse_mode"]

    # 1. Проверяем парсинг текста (ключевые маркеры)
    assert "У вас 1 заметка. Выберите опцию" in text
    assert "📌 *Название*: Встреча 2" in text
    assert "⏳ *Время*: 12:00 - 13:00" in text

    # 2. Проверяем режим разметки
    assert parse_mode == "Markdown"

    # 3. Проверяем клавиатуру (структуру и callback_data)
    # Убеждаемся, что это двухмерный кортеж/список кнопок
    keyboard = reply_markup.inline_keyboard

    # Проверяем первую кнопку (Название)
    assert keyboard[0][0].callback_data == "edit_field:title"
    assert keyboard[0][0].text == "✏️ Название"

    # Проверяем кнопку отмены (последняя строка, первая кнопка)
    assert keyboard[-1][0].callback_data == "edit_field:cancel"
    assert keyboard[-1][0].text == "🔙 Назад"


@pytest.mark.asyncio
async def test_handle_options_click_edit_multiple_events_inline():
    # ПОДГОТОВКА
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_edit"

    # Кладем 2 события, чтобы сработал сценарий event_count < 11
    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 101,
                "title": "Событие 1",
                "start_time": time(10, 0),
                "end_time": time(11, 0),
                "event_type": "interval",
            },
            {
                "id": 102,
                "title": "Событие 2",
                "start_time": time(12, 0),
                "end_time": time(13, 0),
                "event_type": "interval",
            },
        ],
    }

    # ВЫЗОВ
    result = await handle_options_click(update_mock, context_mock)

    # ПРОВЕРКИ
    # Проверяем стейт (СЦЕНАРИЙ 2 для edit -> SELECTING_EDIT_EVENT)
    assert result == SELECTING_EDIT_EVENT

    # Убеждаемся, что вызвалось редактирование сообщения
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    text = kwargs["text"]
    reply_markup: InlineKeyboardMarkup = kwargs["reply_markup"]
    parse_mode = kwargs["parse_mode"]

    # 1. Проверяем текст (присутствие промпта и данных обеих заметок)
    assert "Выберите номер события для редактирования:" in text
    assert "Событие 1" in text
    assert "Событие 2" in text
    assert parse_mode == "Markdown"

    # 2. Проверяем клавиатуру
    keyboard = reply_markup.inline_keyboard

    # Первый ряд, первая кнопка
    assert keyboard[0][0].text == "1"
    assert keyboard[0][0].callback_data == "edit_num:0"

    # Первый ряд, вторая кнопка
    assert keyboard[0][1].text == "2"
    assert keyboard[0][1].callback_data == "edit_num:1"

    # Последний ряд (кнопка Назад, так как префикс edit_num, а не del_num)
    assert keyboard[-1][0].text == "🔙 Назад"
    assert keyboard[-1][0].callback_data == "edit_num:cancel"


@pytest.mark.asyncio
async def test_handle_options_click_edit_too_many_events_text_input():
    # ПОДГОТОВКА
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_edit"

    # Генерируем 11 событий через list comprehension
    event_list = [
        {
            "id": i,
            "title": f"Массовое событие {i}",
            "start_time": time(10, 0),
            "end_time": time(11, 0),
            "event_type": "interval",
        }
        for i in range(11)
    ]

    context_mock.user_data = {"selected_date": date(2026, 10, 20), "event_text_record": event_list}

    # ВЫЗОВ
    result = await handle_options_click(update_mock, context_mock)

    # ПРОВЕРКИ
    # Проверяем стейт (СЦЕНАРИЙ 3 для edit -> TYPING_EDIT_NUM)
    assert result == TYPING_EDIT_NUM

    # Убеждаемся, что вызвалось редактирование сообщения
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    text = kwargs["text"]
    reply_markup: InlineKeyboardMarkup = kwargs["reply_markup"]
    parse_mode = kwargs["parse_mode"]

    # 1. Проверяем текст
    assert "⚠️ Событий слишком много для отображения кнопок-номеров." in text
    assert "Отправьте номер события в чат, чтобы его изменить:" in text
    # Проверяем, что первая и последняя заметки есть в тексте
    assert "Массовое событие 0" in text
    assert "Массовое событие 10" in text

    assert parse_mode == "Markdown"

    # 2. Проверяем клавиатуру (в ней не должно быть инлайн-номеров)
    keyboard = reply_markup.inline_keyboard

    # Так как count=None, первые два массива кнопок (keyboard[0] и keyboard[1]) будут пустыми
    assert len(keyboard[0]) == 0
    assert len(keyboard[1]) == 0

    # Кнопка "Назад" должна лежать в последнем ряду
    assert keyboard[-1][0].text == "🔙 Назад"
    assert keyboard[-1][0].callback_data == "edit_num:cancel"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type, expected_first_sent",
    [("interval", "мероприятие?"), ("all_day", "мероприятие на весь день?")],
)
@patch("app.handlers.calendar_act_with_options.confirm_to_delete")
async def test_handle_options_click_delete_one_event_various_types(
    mock_confirm_to_delete: AsyncMock, event_type: str, expected_first_sent: str
):
    # ПОДГОТОВКА
    mock_confirm_to_delete.return_value = CONFIRMING_DELETE

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_delete"

    test_date = date(2026, 10, 20)
    start_time = time(10, 0) if event_type == "interval" else None
    end_time = time(11, 0) if event_type == "interval" else None

    event_record = [
        {
            "id": 777,
            "title": "Ненужная встреча",
            "event_type": event_type,
            "event_date": test_date,
            "start_time": start_time,
            "end_time": end_time,
        }
    ]

    context_mock.user_data = {"selected_date": test_date, "event_text_record": event_record}

    # ВЫЗОВ
    result: int = await handle_options_click(update_mock, context_mock)

    # ПРОВЕРКИ
    # 1. Проверяем возвращаемый стейт
    assert result == CONFIRMING_DELETE

    # 2. Проверяем, что в context.user_data записались правильные данные для удаления
    assert context_mock.user_data["delete_event_id"] == 777
    assert context_mock.user_data["column_name"] == "id"

    # 3. Проверяем вызов внешней функции confirm_to_delete с точными аргументами (3 аргумента)
    expected_card = build_detailed_event_text(
        event_record, index=0, numbered=False, is_show_date=True
    )
    expected_event = f"{expected_card}\n"

    mock_confirm_to_delete.assert_awaited_once_with(
        update_mock.callback_query, expected_event, (expected_first_sent, "заметку.")
    )


@pytest.mark.asyncio
async def test_handle_options_click_delete_multiple_events_inline():
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_delete"

    # Кладем 2 события, чтобы сработал show_event_selection_list
    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 101,
                "title": "Событие 1",
                "start_time": time(10, 0),
                "end_time": time(11, 0),
                "event_type": "interval",
            },
            {
                "id": 102,
                "title": "Событие 2",
                "start_time": time(12, 0),
                "end_time": time(13, 0),
                "event_type": "interval",
            },
        ],
    }

    result: int = await handle_options_click(update_mock, context_mock)

    # Стейт для удаления из списка (до 10 заметок)
    assert result == CHOOSING_EVENT_TO_DELETE

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    text = kwargs["text"]
    reply_markup: InlineKeyboardMarkup = kwargs["reply_markup"]

    # Проверяем текст (промпт для удаления и вывод самих заметок)
    assert "Выберите номер события для удаления:" in text
    assert "Событие 1" in text
    assert "Событие 2" in text

    keyboard = reply_markup.inline_keyboard

    # 1. Проверяем цифровые кнопки с префиксом del_num
    assert keyboard[0][0].text == "1"
    assert keyboard[0][0].callback_data == "del_num:0"
    assert keyboard[0][1].text == "2"
    assert keyboard[0][1].callback_data == "del_num:1"

    # 2. Проверяем сервисный нижний ряд
    # Должна появиться кнопка "Удалить всё" (так как action == "delete") и кнопка "Назад"
    assert keyboard[-1][0].text == "❌ Удалить всё"
    assert keyboard[-1][0].callback_data == "del_num:everything"

    assert keyboard[-1][1].text == "🔙 Назад"
    assert keyboard[-1][1].callback_data == "del_num:cancel"


@pytest.mark.asyncio
async def test_handle_options_click_delete_too_many_events_text_input():
    # ПОДГОТОВКА
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_delete"

    # Генерируем 11 событий для срабатывания третьего сценария
    event_list = [
        {
            "id": i,
            "title": f"Событие под снос {i}",
            "start_time": time(10, 0),
            "end_time": time(11, 0),
            "event_type": "interval",
        }
        for i in range(11)
    ]

    context_mock.user_data = {"selected_date": date(2026, 10, 20), "event_text_record": event_list}

    # ВЫЗОВ
    result = await handle_options_click(update_mock, context_mock)

    # ПРОВЕРКИ
    # Проверяем стейт (СЦЕНАРИЙ 3 для delete)
    assert result == TYPING_EVENT_NUMBER_TO_DELETE

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    text = kwargs["text"]
    reply_markup: InlineKeyboardMarkup = kwargs["reply_markup"]

    # 1. Проверяем текст (предупреждение и правильный промпт)
    assert "⚠️ Событий слишком много для отображения кнопок-номеров." in text
    assert "Отправьте номер события в чат, чтобы его удалить:" in text
    assert "Событие под снос 0" in text
    assert "Событие под снос 10" in text

    # 2. Проверяем клавиатуру
    keyboard = reply_markup.inline_keyboard

    # Номеров быть не должно
    assert len(keyboard[0]) == 0
    assert len(keyboard[1]) == 0

    # Но сервисные кнопки "Удалить всё" и "Назад" должны быть на месте
    assert keyboard[-1][0].text == "❌ Удалить всё"
    assert keyboard[-1][0].callback_data == "del_num:everything"

    assert keyboard[-1][1].text == "🔙 Назад"
    assert keyboard[-1][1].callback_data == "del_num:cancel"


@pytest.mark.asyncio
async def test_handle_options_click_invite_one_event():
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_invite"

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 301,
                "title": "Одиночная встреча",
                "start_time": time(10, 0),
                "end_time": time(11, 0),
                "event_type": "interval",
            }
        ],
    }

    result: int = await handle_options_click(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    assert context_mock.user_data["invite_event_id"] == 301

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    assert "Выбрано событие: **Одиночная встреча**" in kwargs["text"]
    assert "**отправьте Telegram ID** пользователя, которого хотите пригласить:" in kwargs["text"]

    keyboard = kwargs["reply_markup"].inline_keyboard

    assert keyboard[0][0].text == "🔙 Назад"
    assert keyboard[0][0].callback_data == "cancel_invite"


@pytest.mark.asyncio
async def test_handle_options_click_invite_multiple_events_inline():
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_invite"

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": 301,
                "title": "Встреча 1",
                "start_time": time(10, 0),
                "end_time": time(11, 0),
                "event_type": "interval",
            },
            {
                "id": 302,
                "title": "Встреча 2",
                "start_time": time(12, 0),
                "end_time": time(13, 0),
                "event_type": "interval",
            },
        ],
    }

    result: int = await handle_options_click(update_mock, context_mock)

    assert result == SELECTING_INVITE_EVENT

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    # Проверяем текст из show_event_selection_list
    assert "Выберите номер события для назначения встречи:" in kwargs["text"]

    keyboard = kwargs["reply_markup"].inline_keyboard

    # Проверяем кнопки-номера с префиксом invite_num
    assert keyboard[0][0].text == "1"
    assert keyboard[0][0].callback_data == "invite_num:0"

    # Убеждаемся, что в сервисном ряду ТОЛЬКО кнопка "Назад" (без "Удалить всё")
    assert len(keyboard[-1]) == 1
    assert keyboard[-1][0].text == "🔙 Назад"
    assert keyboard[-1][0].callback_data == "invite_num:cancel"


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.confirm_to_delete")
@patch("app.handlers.calendar_act_with_options.get_validated_event_index")
async def test_handle_delete_event_by_number_success(
    mock_get_validated: AsyncMock, mock_confirm_to_delete: AsyncMock
):
    mock_confirm_to_delete.return_value = CONFIRMING_DELETE
    test_date = date(2026, 10, 20)

    event_records = [
        {
            "id": 777,
            "title": "Ненужная встреча №1",
            "event_type": "interval",
            "event_date": test_date,
            "start_time": time(9, 0),
            "end_time": time(10, 0),
        },
        {
            "id": 778,
            "title": "Ненужная встреча №2",
            "event_type": "interval",
            "event_date": test_date,
            "start_time": time(9, 0),
            "end_time": time(10, 0),
        },
    ]

    # Мокаем успешную валидацию (индекс 1)
    mock_get_validated.return_value = (True, 1, event_records)

    update_mock, context_mock = AsyncMock(), MagicMock()

    context_mock.user_data = {"selected_date": test_date}

    result: int = await handle_delete_event_by_number(update_mock, context_mock)

    assert result == CONFIRMING_DELETE

    # Проверяем, что зафиксировались таргенты на событие с id=11
    assert context_mock.user_data["delete_event_id"] == 778
    assert context_mock.user_data["column_name"] == "id"

    expected_card = build_detailed_event_text(
        event_records, index=1, numbered=True, is_show_date=True
    )
    expected_event = f"{expected_card}\n"

    mock_confirm_to_delete.assert_awaited_once_with(
        update_mock, expected_event, ("событие № 2?", "эту заметку.")
    )


# --- ТЕСТ 3: Приглашение (более 10 заметок, ввод текстом) ---
@pytest.mark.asyncio
async def test_handle_options_click_invite_too_many_events_text_input():
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "action_invite"

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "id": i,
                "title": f"Массовая встреча {i}",
                "start_time": time(10, 0),
                "end_time": time(11, 0),
                "event_type": "interval",
            }
            for i in range(11)
        ],
    }

    result: int = await handle_options_click(update_mock, context_mock)

    assert result == TYPING_INVITE_NUM

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    # Проверяем наличие текста-предупреждения и нужного промпта
    assert "⚠️ Событий слишком много" in kwargs["text"]
    assert "Отправьте номер события в чат, чтобы назначить на него встречу:" in kwargs["text"]

    keyboard = kwargs["reply_markup"].inline_keyboard

    # Убеждаемся, что инлайн-номера не сгенерировались
    assert len(keyboard[0]) == 0
    assert len(keyboard[1]) == 0

    # Кнопка "Назад" должна остаться
    assert len(keyboard[-1]) == 1
    assert keyboard[-1][0].text == "🔙 Назад"
    assert keyboard[-1][0].callback_data == "invite_num:cancel"


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.generate_confirm_keyboard")
async def test_confirm_to_delete_from_callback(mock_gen_keyboard: AsyncMock):
    # ТЕСТ 1: Имитируем вызов из инлайн-кнопки (CallbackQuery)
    mock_gen_keyboard.return_value = "keyboard_mock"

    source_mock = AsyncMock()
    # У source_mock по умолчанию есть любой атрибут, так что hasattr вернет True

    event_text = "📌 Событие: [10:00 - 11:00] Встреча 1\n"
    delete_text = ("событие № 1?", "эту заметку.")

    result = await confirm_to_delete(source_mock, event_text, delete_text)

    # Проверяем возврат стейта
    assert result == CONFIRMING_DELETE

    # Проверяем, что вызвался edit_message_text, а не reply_text
    source_mock.edit_message_text.assert_awaited_once()
    source_mock.message.reply_text.assert_not_awaited()

    # Проверяем аргументы и форматирование текста
    kwargs = source_mock.edit_message_text.call_args.kwargs
    text = kwargs["text"]

    assert "❓ *Вы уверены, что хотите удалить событие № 1?*" in text
    assert "Событие: [10:00 - 11:00] Встреча 1" in text
    assert "⚠️ Это действие полностью сотрёт эту заметку." in text

    assert kwargs["reply_markup"] == "keyboard_mock"
    assert kwargs["parse_mode"] == "Markdown"


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.generate_confirm_keyboard")
async def test_confirm_to_delete_from_text_update(mock_gen_keyboard: AsyncMock):
    # ТЕСТ 2: Имитируем вызов из текстового ввода (Update)
    mock_gen_keyboard.return_value = "keyboard_mock"

    source_mock = AsyncMock()
    # Жестко удаляем атрибут, чтобы hasattr(source, "edit_message_text") выдало False
    del source_mock.edit_message_text

    event_text = "📌 Событие: [12:00 - 13:00] Встреча 2\n"
    delete_text = ("все мероприятия?", "вообще всё.")

    result = await confirm_to_delete(source_mock, event_text, delete_text)

    # Проверяем возврат стейта
    assert result == CONFIRMING_DELETE

    # Проверяем, что вызвался reply_text, так как это текстовое сообщение
    source_mock.message.reply_text.assert_awaited_once()

    # Проверяем форматирование (особенно работу форматирования даты с ведущими нулями: 05.01.2026)
    kwargs = source_mock.message.reply_text.call_args.kwargs
    text = kwargs["text"]

    assert "❓ *Вы уверены, что хотите удалить все мероприятия?*" in text
    assert "Событие: [12:00 - 13:00] Встреча 2" in text
    assert "⚠️ Это действие полностью сотрёт вообще всё." in text

    assert kwargs["reply_markup"] == "keyboard_mock"
    assert kwargs["parse_mode"] == "Markdown"
