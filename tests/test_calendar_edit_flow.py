from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.handlers.calendar_edit_flow import (
    _refresh_day_menu_after_edit,
    handle_edit_date_selection,
    handle_edit_event_by_text_number,
    handle_edit_event_selection,
    handle_edit_field_click,
    handle_edit_field_date,
    handle_typing_edit_desc,
    handle_typing_edit_time,
    handle_typing_edit_title,
)
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_EDIT_FIELD,
    TYPING_EDIT_DATE,
    TYPING_EDIT_DESC,
    TYPING_EDIT_TIME,
    TYPING_EDIT_TITLE,
)


# --- ТЕСТ 1: Позитивный сценарий выбора заметки через инлайн-кнопку ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.Appointment")
@patch("app.handlers.calendar_edit_flow.is_user_invitee_for_event")
async def test_handle_edit_event_selection_success(
    mock_is_invitee: AsyncMock, mock_appointment: MagicMock
):
    mock_is_invitee.return_value = False
    mock_appointment.objects.filter.return_value.aexists = AsyncMock(return_value=False)

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Имитируем клик по второй кнопке (индекс 1)
    update_mock.callback_query.data = "edit_num:1"
    update_mock.effective_user.id = 12345

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {"id": 10, "title": "Событие 0", "start_time": time(9, 0), "end_time": time(10, 0)},
            {"id": 11, "title": "Событие 1", "start_time": time(10, 0), "end_time": time(11, 0)},
        ],
    }

    result = await handle_edit_event_selection(update_mock, context_mock)

    assert result == CHOOSING_EDIT_FIELD

    # Проверяем, что в context легли данные именно второй заметки (индекс 1)
    assert context_mock.user_data["edit_event_index"] == 1
    assert context_mock.user_data["edit_event_id"] == 11
    assert context_mock.user_data["current_event_time"] == (time(10, 0), time(11, 0))

    # Убеждаемся, что вызвано редактирование сообщения
    update_mock.callback_query.edit_message_text.assert_awaited_once()


# --- ТЕСТ 2: Позитивный сценарий выбора заметки через текстовый ввод ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.Appointment")
@patch("app.handlers.calendar_edit_flow.is_user_invitee_for_event")
@patch("app.handlers.calendar_edit_flow.get_validated_event_index")
async def test_handle_edit_event_by_text_number_success(
    mock_get_validated: AsyncMock, mock_is_invitee: AsyncMock, mock_appointment: MagicMock
):
    event_list = [
        {"id": 10, "title": "Событие 0", "start_time": time(9, 0), "end_time": time(10, 0)},
        {"id": 11, "title": "Событие 1", "start_time": time(10, 0), "end_time": time(11, 0)},
    ]

    # Мокаем успешный возврат валидатора: (is_valid=True, index=1, event_list)
    mock_get_validated.return_value = (True, 1, event_list)
    mock_is_invitee.return_value = False
    mock_appointment.objects.filter.return_value.aexists = AsyncMock(return_value=False)

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.effective_user.id = 12345

    context_mock.user_data = {"selected_date": date(2026, 10, 20)}

    result = await handle_edit_event_by_text_number(update_mock, context_mock)

    assert result == CHOOSING_EDIT_FIELD

    # Снова проверяем, что контекст обновился данными заметки №1
    assert context_mock.user_data["edit_event_index"] == 1
    assert context_mock.user_data["edit_event_id"] == 11
    assert context_mock.user_data["current_event_time"] == (time(10, 0), time(11, 0))

    # Здесь уже не edit_message_text, а reply_text, так как это ответ на сообщение
    update_mock.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_edit_field_click_title():
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = "edit_field:title"
    update_mock.callback_query.edit_message_text = AsyncMock()

    result: int = await handle_edit_field_click(update_mock, context_mock)

    assert result == TYPING_EDIT_TITLE

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert "Введите новое название для этого события" in kwargs["text"]


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow._refresh_day_menu_after_edit")
async def test_handle_typing_edit_title(mock_refresh_day_menu_after_edit: AsyncMock):
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    # Проверяем, что strip() сработает (убирает пробелы по краям)
    update_mock.message.text = " Новое название для события "
    context_mock.user_data = {"edit_event_id": 999}
    update_mock.effective_user.id = 123

    # --- ПРАВИЛЬНЫЙ МОК БД ---
    con_mock = AsyncMock()
    # Контекстный менеджер возвращает именно наше соединение
    context_mock.application.database.connection.return_value.__aenter__.return_value = con_mock

    context_mock.application.stats_repository.increment_metric = AsyncMock()
    context_mock.application.stats_repository.increment_user_metric = AsyncMock()

    mock_refresh_day_menu_after_edit.return_value = CHOOSING_ACTION

    result: int = await handle_typing_edit_title(update_mock, context_mock)

    assert result == CHOOSING_ACTION

    # Проверяем вызов к базе через con_mock
    con_mock.execute.assert_awaited_once()
    args = con_mock.execute.call_args.args
    assert args[0] == "UPDATE events SET title = $1 WHERE id = $2"  # Тут title
    assert args[1] == "Новое название для события"  # Пробелы по краям удалены!
    assert args[2] == 999

    # Метрики
    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        "events_edited"
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        123, "events_edited"
    )

    # Проверяем текст статуса
    assert "Название события успешно изменено" in context_mock.user_data["edit_success_status"]


# --- 1. ПРЕАМБУЛА: Клик по кнопке "Описание" ---
@pytest.mark.asyncio
async def test_handle_edit_field_click_desc():
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = "edit_field:desc"
    update_mock.callback_query.edit_message_text = AsyncMock()

    # Вызов
    result: int = await handle_edit_field_click(update_mock, context_mock)

    # Проверки
    assert result == TYPING_EDIT_DESC

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert "Введите новое описание для этого события" in kwargs["text"]


# --- 2. МЯСО: Сохранение нового описания в БД ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow._refresh_day_menu_after_edit")
async def test_handle_typing_edit_desc(mock_refresh_day_menu_after_edit: AsyncMock):
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    # Сразу передаем текст описания (с пробелами для проверки strip)
    update_mock.message.text = " Новое крутое описание "
    context_mock.user_data = {"edit_event_id": 999}
    update_mock.effective_user.id = 123

    # Правильный мок БД
    con_mock = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = con_mock
    context_mock.application.stats_repository.increment_metric = AsyncMock()
    context_mock.application.stats_repository.increment_user_metric = AsyncMock()

    mock_refresh_day_menu_after_edit.return_value = CHOOSING_ACTION

    # ВЫЗОВ
    result: int = await handle_typing_edit_desc(update_mock, context_mock)

    # Проверки
    assert result == CHOOSING_ACTION

    args: tuple = con_mock.execute.call_args.args
    assert args[0] == "UPDATE events SET description = $1 WHERE id = $2"
    assert args[1] == "Новое крутое описание"  # Проверяем, что пробелы отрезались
    assert args[2] == 999

    # Проверка метрик
    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        "events_edited"
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        123, "events_edited"
    )

    # Проверка статуса
    assert "Описание события успешно изменено" in context_mock.user_data["edit_success_status"]


# --- 1. ПРЕАМБУЛА: Клик по кнопке "Время" ---
@pytest.mark.asyncio
async def test_handle_edit_field_click_time():
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = "edit_field:time"
    update_mock.callback_query.edit_message_text = AsyncMock()

    # Вызов
    result: int = await handle_edit_field_click(update_mock, context_mock)

    # Проверки
    assert result == TYPING_EDIT_TIME

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert "Введите новый временной интервал для этого события" in kwargs["text"]


# --- 2. Проверка валидного времени и сохранения его в БД ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.CalendarRepository.has_time_conflict")
@patch("app.handlers.calendar_edit_flow._refresh_day_menu_after_edit")
async def test_handle_typing_edit_time_positive(
    mock_refresh_day_menu_after_edit: AsyncMock, mock_has_time_conflict: AsyncMock
):
    # Подготовка данных
    mock_refresh_day_menu_after_edit.return_value = CHOOSING_ACTION
    update_mock, context_mock, mock_con = AsyncMock(), MagicMock(), AsyncMock()

    update_mock.message.text = " 12:30 - 13:30 "
    context_mock.user_data = {"selected_date": date(2026, 10, 20), "edit_event_id": "999"}
    update_mock.effective_user.id = 100

    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_con
    # Указываем что новое время события не занято
    mock_has_time_conflict.return_value = False

    context_mock.application.stats_repository.increment_metric = AsyncMock()
    context_mock.application.stats_repository.increment_user_metric = AsyncMock()

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    assert result == CHOOSING_ACTION

    mock_has_time_conflict.assert_awaited_once_with(
        mock_con, 100, date(2026, 10, 20), time(12, 30), time(13, 30), 999
    )
    # Проверяем что подключение к БД вызывалось 1 раз
    context_mock.application.database.connection.assert_called_once()

    args: tuple = mock_con.execute.call_args.args

    sql_query = args[0]
    assert "UPDATE events" in sql_query
    assert "SET start_time = $1" in sql_query
    assert "end_time = $2" in sql_query
    assert "event_type = 'interval'" in sql_query
    assert "WHERE id = $3" in sql_query

    start_time, end_time, event_id = args[1], args[2], args[3]
    assert start_time == time(12, 30)
    assert end_time == time(13, 30)
    assert event_id == 999

    assert "Время события успешно изменено" in context_mock.user_data["edit_success_status"]

    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        "events_edited"
    )

    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        100, "events_edited"
    )


@pytest.mark.asyncio
async def test_handle_typing_edit_time_incorrect_pattern():
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.message.text = "Чушь а не время"

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME

    text = update_mock.message.reply_text.call_args.kwargs["text"]

    assert "Неверный формат времени" in text
    assert "Пожалуйста, введите интервал (например: 9-10, 09:30-11 или 15:00-16:30)" in text


@pytest.mark.asyncio
async def test_handle_typing_edit_time_unexistent_time():
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    # Такого времени не существует
    update_mock.message.text = "24:30-25:30"

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME

    text = update_mock.message.reply_text.call_args.kwargs["text"]

    assert "Введено некорректное время суток (максимум 23:59)" in text


@pytest.mark.asyncio
async def test_handle_typing_edit_time_reversed_time():
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    # Время начала больше времени окончания
    update_mock.message.text = "17:30-16:30"

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME

    text = update_mock.message.reply_text.call_args.kwargs["text"]

    assert "Ошибка: время начала должно быть строго раньше времени окончания" in text


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.CalendarRepository.has_time_conflict")
async def test_handle_typing_edit_time_busy_time(mock_hast_time_conflict: AsyncMock):
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.message.text = "14:30-15:30"
    mock_hast_time_conflict.return_value = True

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME

    text = update_mock.message.reply_text.call_args.kwargs["text"]

    assert "Ошибка: это время занято" in text


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.generate_edit_fields_keyboard")
@patch("app.handlers.calendar_edit_flow.CalendarRepository.get_events_by_date")
@patch("app.handlers.calendar_edit_flow.CalendarRepository.toggle_event_privacy")
async def test_handle_click_edit_private(
    mock_toggle_event_privacy: AsyncMock,
    mock_get_events_by_date: AsyncMock,
    fake_keyboard: MagicMock,
):
    # Подготовка данных
    update_mock, context_mock, mock_con = AsyncMock(), MagicMock(), AsyncMock()

    update_mock.callback_query.data = "edit_field:private"

    updated_records = [
        {
            "title": "Созвон по проекту",
            "start_time": time(9, 0),
            "end_time": time(10, 0),
            "description": "Погулять с хорошим мальчиком",
            "is_public": False,
            "event_date": date(2026, 10, 18),
        }
    ]
    mock_get_events_by_date.return_value = updated_records
    fake_keyboard.return_value = "fake_keyboard"

    context_mock.user_data = {
        "edit_event_id": 999,
        "edit_event_index": 0,
        "selected_date": date(2026, 10, 20),
    }

    update_mock.callback_query.edit_message_text = AsyncMock()
    update_mock.effective_user.id = 123
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_con

    # ВЫЗОВ
    result: int = await handle_edit_field_click(update_mock, context_mock)

    assert result == CHOOSING_EDIT_FIELD

    mock_toggle_event_privacy.assert_awaited_once_with(mock_con, 999)
    mock_get_events_by_date.assert_awaited_once_with(mock_con, 123, date(2026, 10, 20))
    assert context_mock.user_data["event_text_record"] == updated_records
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    # Проверка текста который увидет пользователь после изменения приватности заметки
    assert "*Название*: Созвон по проекту" in kwargs["text"]
    assert "*Время*: 09:00 - 10:00" in kwargs["text"]
    assert "*Описание*: Погулять с хорошим мальчиком" in kwargs["text"]
    assert "*Доступ*: 🔒 Приватное (Только вы)" in kwargs["text"]

    assert kwargs["reply_markup"] == "fake_keyboard"
    assert kwargs["parse_mode"] == "Markdown"


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.handle_edit_field_date")
async def test_handle_edit_field_date_choice(mock_handle_edit_field_date: AsyncMock):
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    mock_handle_edit_field_date.return_value = TYPING_EDIT_DATE
    update_mock.callback_query.data = "edit_field:date"

    # ВЫЗОВ
    result: int = await handle_edit_field_click(update_mock, context_mock)

    # Проверки
    assert result == TYPING_EDIT_DATE
    mock_handle_edit_field_date.assert_awaited_once_with(update_mock, context_mock)


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.CalendarService.get_user_busy_days")
async def test_handle_edit_field_date_click_new_day(mock_get_busy_days: AsyncMock):
    # 1. Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.effective_user.id = 555

    # Выбираем дату, для которой будем проверять белый кружок
    selected_day = 15
    selected_date = date(2026, 10, selected_day)
    context_mock.user_data = {"selected_date": selected_date}

    mock_conn = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    # Имитируем занятые дни месяца (частично и полностью)
    mock_busy_days = {10: "partial", 20: "full"}
    mock_get_busy_days.return_value = mock_busy_days

    # 2. Вызов хэндлера
    result: int = await handle_edit_field_date(update_mock, context_mock)

    # 3. Базовые проверки стейта и контекста
    assert result == TYPING_EDIT_DATE
    assert context_mock.user_data["is_editing_date_mode"] is True
    assert context_mock.user_data["month_busy_days"] == mock_busy_days

    mock_get_busy_days.assert_awaited_once_with(conn=mock_conn, user_id=555, year=2026, month=10)

    # 4. Проверка текста сообщения
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert "Изменение даты события" in kwargs["text"]
    assert "15.10.2026" in kwargs["text"]
    assert kwargs["parse_mode"] == "Markdown"

    # 5. Проверка клавиатуры: ищем все кнопки на сетке
    markup: InlineKeyboardMarkup = kwargs["reply_markup"]
    all_buttons = [btn for row in markup.inline_keyboard for btn in row]

    white_index, yellow_index, red_index = 25, 20, 30

    # Проверка редактируемой даты
    changeable_day: InlineKeyboardButton = all_buttons[white_index]
    assert changeable_day.text == "⚪ 15"
    assert changeable_day.callback_data == f"calendar_day:2026:10:{selected_day}"

    # Дополнительно: проверяем, что обычные маркеры занятости тоже отрисовались
    assert all_buttons[yellow_index].text == "🟡 10"
    assert all_buttons[red_index].text == "🔴 20"

    used_buttons_text = {"🔴 20", "🟡 10", "⚪ 15"}

    unexpected_marked_buttons = [
        btn.text
        for btn in all_buttons
        if btn.text not in used_buttons_text and btn.text.startswith(("🔴", "🟡", "⚪"))
    ]
    assert unexpected_marked_buttons == []

    # Проверяем наличие кнопки возврата к редактированию
    assert any(btn.callback_data == "back_to_edit_menu" for btn in all_buttons)


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow._refresh_day_menu_after_edit")
@patch("app.handlers.calendar_edit_flow.CalendarRepository.has_time_conflict")
async def test_handle_edit_date_selection_success(
    mock_has_time_conflict: AsyncMock, mock_refresh_menu: AsyncMock
):
    # 1. Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = "calendar_day:2026:10:25"
    update_mock.callback_query.answer = AsyncMock()
    update_mock.effective_user.id = 777

    old_date = date(2026, 10, 15)
    target_date = date(2026, 10, 25)
    start = time(14, 0)
    end = time(15, 30)

    context_mock.user_data = {
        "selected_date": old_date,
        "edit_event_id": 999,
        "current_event_time": (start, end),
        "month_busy_days": {},  # Целевой день полностью свободен
        "is_editing_date_mode": True,
    }

    mock_conn = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn
    mock_has_time_conflict.return_value = False

    context_mock.application.stats_repository.increment_metric = AsyncMock()
    context_mock.application.stats_repository.increment_user_metric = AsyncMock()
    mock_refresh_menu.return_value = CHOOSING_ACTION

    # 2. Вызов
    result: int = await handle_edit_date_selection(update_mock, context_mock)

    # 3. Проверки
    assert result == CHOOSING_ACTION

    # Проверка вызова валидатора времени в БД
    mock_has_time_conflict.assert_awaited_once_with(
        mock_conn, 777, target_date, start, end, exclude_event_id=None
    )

    # Проверка SQL-запроса на обновление даты
    mock_conn.execute.assert_awaited_once_with(
        "UPDATE events SET event_date = $1 WHERE id = $2", target_date, 999
    )

    # Проверка обновления ОЗУ и удаления флага режима редактирования
    assert context_mock.user_data["selected_date"] == target_date
    assert "is_editing_date_mode" not in context_mock.user_data

    # Проверка статистики
    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        "events_edited"
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        777, "events_edited"
    )

    # Проверка ответа пользователю и вызова обновления меню
    update_mock.callback_query.answer.assert_awaited_once_with(
        text="✅ Дата успешно изменена на 25.10.2026!"
    )
    mock_refresh_menu.assert_awaited_once_with(update_mock, context_mock)


# --- 1. Клик по той же самой дате ---
@pytest.mark.asyncio
async def test_handle_edit_date_selection_choose_the_same_date():
    update_mock, context_mock = AsyncMock(), MagicMock()
    same_date = date(2026, 10, 25)

    update_mock.callback_query.data = (
        f"calendar_day:{same_date.year}:{same_date.month}:{same_date.day}"
    )
    update_mock.callback_query.answer = AsyncMock()
    context_mock.user_data = {"selected_date": same_date}

    # ВЫЗОВ
    result: int = await handle_edit_date_selection(update_mock, context_mock)

    assert result == TYPING_EDIT_DATE
    update_mock.callback_query.answer.assert_awaited_once_with(
        "❌ Вы выбрали ту же самую дату! Выберите другой день."
    )


# --- 2. Перенос события 'all_day' на занятый день ---
@pytest.mark.asyncio
async def test_handle_edit_date_selection_all_day_to_busy_day():
    update_mock, context_mock = AsyncMock(), MagicMock()
    target_date = date(2026, 10, 25)

    update_mock.callback_query.data = (
        f"calendar_day:{target_date.year}:{target_date.month}:{target_date.day}"
    )
    update_mock.callback_query.answer = AsyncMock()

    context_mock.user_data = {
        "selected_date": date(2026, 10, 15),
        "edit_event_id": 999,
        "current_event_time": (None, None),
        "month_busy_days": {target_date.day: "partial"},
    }

    # ВЫЗОВ
    result: int = await handle_edit_date_selection(update_mock, context_mock)

    assert result == TYPING_EDIT_DATE
    update_mock.callback_query.answer.assert_awaited_once_with(
        "❌ Ошибка: Нельзя перенести событие 'Весь день' на эту дату, так как день уже занят другими делами!"
    )


# --- 3. Перенос интервала на день, занятый событием 'Весь день' ---
@pytest.mark.asyncio
async def test_handle_edit_date_selection_target_has_all_day_event():
    update_mock, context_mock = AsyncMock(), MagicMock()
    user_id = 777
    target_date = date(2026, 10, 25)

    update_mock.callback_query.data = (
        f"calendar_day:{target_date.year}:{target_date.month}:{target_date.day}"
    )
    update_mock.callback_query.answer = AsyncMock()
    update_mock.effective_user.id = user_id

    context_mock.user_data = {
        "selected_date": date(2026, 10, 15),
        "edit_event_id": 999,
        "current_event_time": (time(8, 30), time(10, 0)),
        "month_busy_days": {target_date.day: "full"},
    }

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = True
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    # ВЫЗОВ
    result: int = await handle_edit_date_selection(update_mock, context_mock)

    assert result == TYPING_EDIT_DATE

    sql_query = mock_conn.fetchval.call_args.args[0]
    assert "SELECT EXISTS" in sql_query
    assert "WHERE user_id = $1 AND event_date = $2 AND event_type = 'all_day'" in sql_query
    assert mock_conn.fetchval.call_args.args[1] == user_id
    assert mock_conn.fetchval.call_args.args[2] == target_date

    update_mock.callback_query.answer.assert_awaited_once_with(
        "❌ Ошибка: Этот день полностью занят событием 'Весь день'!"
    )


# --- 4. Конфликт времени при переносе интервала ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.CalendarRepository.has_time_conflict")
async def test_handle_edit_date_selection_time_conflict(mock_has_time_conflict: AsyncMock):
    update_mock, context_mock = AsyncMock(), MagicMock()
    user_id = 777
    target_date = date(2026, 10, 25)
    start = time(8, 30)
    end = time(10, 0)

    update_mock.callback_query.data = (
        f"calendar_day:{target_date.year}:{target_date.month}:{target_date.day}"
    )
    update_mock.callback_query.answer = AsyncMock()
    update_mock.effective_user.id = user_id
    mock_has_time_conflict.return_value = True

    context_mock.user_data = {
        "selected_date": date(2026, 10, 15),
        "edit_event_id": 999,
        "current_event_time": (start, end),
        "month_busy_days": {target_date.day: "partial"},
    }

    mock_conn = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    # ВЫЗОВ
    result: int = await handle_edit_date_selection(update_mock, context_mock)

    assert result == TYPING_EDIT_DATE
    mock_has_time_conflict.assert_awaited_once_with(
        mock_conn, user_id, target_date, start, end, exclude_event_id=None
    )
    update_mock.callback_query.answer.assert_awaited_once_with(
        "❌ Ошибка: Выбранное время на этой дате уже занято другим событием!"
    )


@pytest.mark.asyncio
@patch("app.handlers.calendar_edit_flow.handle_options_with_exist_notes_in_day")
@patch("app.handlers.calendar_edit_flow.build_detailed_event_text")
@patch("app.handlers.calendar_edit_flow.CalendarService.get_user_busy_days")
@patch("app.handlers.calendar_edit_flow.CalendarRepository.get_events_by_date")
async def test_refresh_day_menu_after_edit(
    mock_get_events: AsyncMock,
    mock_get_busy_days: AsyncMock,
    mock_build_card: MagicMock,
    mock_handle_options: AsyncMock,
):
    # 1. Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.effective_user.id = 123
    update_mock.message = MagicMock()  # source будет update

    test_date = date(2026, 10, 20)
    context_mock.user_data = {
        "selected_date": test_date,
        "edit_success_status": "✅ Название успешно изменено!",
    }

    mock_conn = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    # Имитируем 2 записи в базе и кэш занятости
    mock_records = [{"id": 1}, {"id": 2}]
    mock_get_events.return_value = mock_records
    mock_get_busy_days.return_value = {20: "partial"}
    mock_build_card.side_effect = lambda records, index, numbered: f"Card {index}"
    mock_handle_options.return_value = CHOOSING_ACTION

    # 2. Вызов
    result: int = await _refresh_day_menu_after_edit(update_mock, context_mock)

    # 3. Проверки
    assert result == CHOOSING_ACTION

    # Проверка синхронизации с базой и обновления ОЗУ
    mock_get_events.assert_awaited_once_with(mock_conn, 123, test_date)
    mock_get_busy_days.assert_awaited_once_with(
        conn=mock_conn, user_id=123, year=test_date.year, month=test_date.month
    )
    assert context_mock.user_data["event_text_record"] == mock_records
    assert context_mock.user_data["month_busy_days"] == {20: "partial"}

    # Проверка, что статус успеха извлечен и удален из user_data
    assert "edit_success_status" not in context_mock.user_data

    # Проверка отрисовки карточек для каждой записи
    assert mock_build_card.call_count == 2

    # Проверка вызова меню с итоговым текстом, кортежем даты и баннером успеха
    expected_text = "Card 0\nCard 1\n"
    expected_header = "✅ Название успешно изменено!\n\n"
    mock_handle_options.assert_awaited_once_with(
        expected_text,
        (update_mock, test_date.day, test_date.month, test_date.year),
        header=expected_header,
    )