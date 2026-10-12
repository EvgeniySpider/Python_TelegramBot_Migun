from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from app.core.calendar.repositories import CalendarRepository
from app.core.calendar.utils import build_detailed_event_text
from app.handlers.calendar_delete_event import (
    del_event_on_info,
    handle_delete_choice,
    handle_delete_confirmation,
    prepare_after_delete,
)
from app.handlers.states import CHOOSING_ACTION, CONFIRMING_DELETE


# --- ТЕСТ 1: Удаление по инлайн-кнопке конкретного события ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_delete_event.confirm_to_delete")
async def test_handle_delete_choice_specific_event(mock_confirm_to_delete: AsyncMock):
    mock_confirm_to_delete.return_value = CONFIRMING_DELETE

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Имитируем клик по второй кнопке (индекс 1)
    update_mock.callback_query.data = "del_num:1"

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

    context_mock.user_data = {"selected_date": test_date, "event_text_record": event_records}

    result: int = await handle_delete_choice(update_mock, context_mock)

    assert result == CONFIRMING_DELETE

    # Проверяем, что в context легли правильные параметры для удаления
    assert context_mock.user_data["delete_event_id"] == 778
    assert context_mock.user_data["column_name"] == "id"

    expected_card = build_detailed_event_text(
        event_records, index=1, numbered=True, is_show_date=True
    )
    expected_event = f"{expected_card}\n"

    # Проверяем правильный вызов confirm_to_delete
    mock_confirm_to_delete.assert_awaited_once_with(
        update_mock.callback_query, expected_event, ("событие № 2?", "заметку.")
    )


@pytest.mark.asyncio
@patch("app.handlers.calendar_delete_event.handle_delete_confirmation")
async def test_handle_delete_choice_prepare_delete_all(mock_handle_delete_confirmation: AsyncMock):
    update_mock = MagicMock()
    context_mock = MagicMock()

    mock_handle_delete_confirmation.return_value = CHOOSING_ACTION
    update_mock.callback_query.data = "del_num:cancel"

    result: int = await handle_delete_choice(update_mock, context_mock)

    assert result == CHOOSING_ACTION


@pytest.mark.asyncio
@patch("app.handlers.calendar_delete_event.confirm_to_delete")
async def test_handle_delete_all_events(mock_confirm_to_delete: AsyncMock):
    update_mock = MagicMock()
    context_mock = MagicMock()

    mock_confirm_to_delete.return_value = CONFIRMING_DELETE
    update_mock.callback_query.data = "del_num:everything"

    context_mock.user_data = {
        "event_text_record": [
            {
                "title": "Уборка",
                "start_time": time(7, 0),
                "end_time": time(8, 0),
                "event_type": "interval",
            },
            {
                "title": "Перекур",
                "start_time": time(8, 0),
                "end_time": time(8, 30),
                "event_type": "exact",
            },
        ],
        "selected_date": date(2026, 10, 1),
    }

    result: int = await handle_delete_choice(update_mock, context_mock)

    assert result == CONFIRMING_DELETE

    assert context_mock.user_data["delete_alert_text"] == "🗑️ Все мероприятия успешно удалены!"
    assert context_mock.user_data["delete_event_id"] == date(2026, 10, 1)
    assert context_mock.user_data["column_name"] == "event_date"

    mock_confirm_to_delete.assert_awaited_once()
    args = mock_confirm_to_delete.call_args.args
    text_with_events = args[1]
    delete_text: tuple = args[2]

    assert "07:00 - 08:00 Уборка" in text_with_events
    assert "08:00 - 08:30 Перекур" in text_with_events

    assert "*АБСОЛЮТНО ВСЕ* мероприятия на этот день?" in delete_text[0]
    assert (
        "**все существующие заметки** на эту дату! Восстановление будет невозможно"
        in delete_text[1]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("column_name", ["id", "event_date"])
@patch("app.handlers.calendar_delete_event.notify_and_cancel_appointments")
@patch("app.handlers.calendar_delete_event.del_event_on_info")
@patch("app.handlers.calendar_delete_event.prepare_after_delete")
async def test_handle_delete_confirmation_for_one_event_and_all_events(
    mock_prepare_after_delete: AsyncMock,
    mock_del_event_on_info: AsyncMock,
    mock_notify_and_cancel_appointments: AsyncMock,
    column_name: str,
):
    mock_prepare_after_delete.return_value = ConversationHandler.END

    update_mock, context_mock = MagicMock(), MagicMock()

    update_mock.callback_query.data = "confirm_delete_yes"
    context_mock.user_data = {"delete_event_id": 123, "column_name": column_name}
    update_mock.effective_user.id = 12345

    result: int = await handle_delete_confirmation(update_mock, context_mock)

    assert result == ConversationHandler.END

    mock_notify_and_cancel_appointments.assert_awaited_once_with(
        12345, column_name, 123, context_mock.bot
    )

    mock_del_event_on_info.assert_awaited_once_with(context_mock, update_mock, column_name, 123)

    mock_prepare_after_delete.assert_awaited_once_with(
        update_mock, context_mock, update_mock.callback_query
    )


@pytest.mark.asyncio
@patch("app.handlers.calendar_delete_event.handle_back_to_day_menu_click")
async def test_handle_delete_confirmation_no(mock_handle_back_to_day_menu: AsyncMock):
    # Мокаем возврат из функции возврата в меню
    mock_handle_back_to_day_menu.return_value = CHOOSING_ACTION

    update_mock, context_mock = MagicMock(), MagicMock()
    # Любая data, отличная от "confirm_delete_yes", отправит нас в ветку else
    update_mock.callback_query.data = "confirm_delete_no"

    # Наполняем контекст ключами, которые должны быть удалены, и ключом-свидетелем
    context_mock.user_data = {"delete_event_id": 123, "column_name": "id", "safe_key": "im_safe"}

    result: int = await handle_delete_confirmation(update_mock, context_mock)

    assert result == CHOOSING_ACTION

    # Валидируем, что нужные ключи стерты
    assert "delete_event_id" not in context_mock.user_data
    assert "column_name" not in context_mock.user_data

    # Валидируем, что контекст не очистили целиком
    assert context_mock.user_data.get("safe_key") == "im_safe"

    # Проверяем, что хэндлер возврата вызвался правильно
    mock_handle_back_to_day_menu.assert_awaited_once_with(update_mock, context_mock)


@pytest.mark.asyncio
@patch("app.handlers.calendar_delete_event.CalendarRepository.delete_events_by_filter")
async def test_del_event_on_info(mock_delete_events_by_filter: AsyncMock):
    context_mock, update_mock = MagicMock(), AsyncMock()

    mock_conn = AsyncMock()

    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    mock_delete_events_by_filter.return_value = 1

    context_mock.application.stats_repository.increment_metric = AsyncMock()
    context_mock.application.stats_repository.increment_user_metric = AsyncMock()

    update_mock.effective_user.id = 12345

    await del_event_on_info(context_mock, update_mock, "id", 999)

    mock_delete_events_by_filter.assert_awaited_once_with(mock_conn, "id", 999)

    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        "events_deleted", amount=1
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        12345, "events_cancelled", 1
    )


# --- ПОЗИТИВНЫЕ СЦЕНАРИИ ---
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "column_name, db_response, expected_count",
    [
        ("id", "DELETE 1", 1),
        ("event_date", "DELETE 5", 5),
    ],
)
async def test_delete_events_by_filter_positive(
    column_name: str, db_response: str, expected_count: int
):
    mock_con = AsyncMock()
    # Мокаем ответ от базы данных (например, "DELETE 1")
    mock_con.execute = AsyncMock(return_value=db_response)

    result = await CalendarRepository.delete_events_by_filter(mock_con, column_name, 999)

    # Проверяем, что метод вернул правильное число
    assert result == expected_count

    # Проверяем, что SQL-запрос сформирован с нужной колонкой
    assert column_name in mock_con.execute.call_args.args[0]
    # Проверяем, что значение подставилось правильно
    assert mock_con.execute.call_args.args[1] == 999


# --- НЕГАТИВНЫЙ СЦЕНАРИЙ (ПРОВЕРКА ИСКЛЮЧЕНИЯ) ---
@pytest.mark.asyncio
async def test_delete_events_by_filter_raises_value_error():
    mock_con = AsyncMock()
    bad_column = "incorrect_value"

    # Оборачиваем вызов в контекстный менеджер pytest.raises
    with pytest.raises(ValueError) as exc_info:
        await CalendarRepository.delete_events_by_filter(mock_con, bad_column, 999)

    # exc_info.value содержит сам объект перехваченной ошибки
    assert str(exc_info.value) == f"Недопустимое имя столбца для удаления: {bad_column}"

    # Дополнительно убеждаемся, что до базы данных запрос даже не дошел
    mock_con.execute.assert_not_called()


@pytest.mark.asyncio
@patch("app.handlers.calendar_delete_event.calendar_command")
async def test_prepare_after_delete(mock_calendar_command: AsyncMock):
    context_mock, update_mock, query = MagicMock(), MagicMock(), MagicMock()

    context_mock.user_data = {
        "delete_event_id": 999,
        "event_text_record": "text_record",
        "delete_alert_text": "🗑️ Мероприятие успешно удалено!",
        "save_data": "save_data",
    }

    query.answer = AsyncMock()

    result: int = await prepare_after_delete(update_mock, context_mock, query)

    assert result == ConversationHandler.END

    assert context_mock.user_data["save_data"] == "save_data"
    assert "delete_event_id" not in context_mock.user_data
    assert "event_text_record" not in context_mock.user_data
    assert "delete_alert_text" not in context_mock.user_data

    query.answer.assert_awaited_once_with(text="🗑️ Мероприятие успешно удалено!")
    mock_calendar_command.assert_awaited_once_with(update_mock, context_mock)
