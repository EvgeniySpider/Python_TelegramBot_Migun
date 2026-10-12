import datetime
from datetime import date, time
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.handlers.calendar_set_event import (
    _save_event_to_db,
    handle_desc_choice,
    handle_description_input,
    handle_set_event,
    handle_time_input_exact,
    handle_time_input_interval,
    handle_title_input,
)
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_TIME,
    WAITING_FOR_DESC_CHOICE,
    WAITING_FOR_DESCRIPTION,
    WAITING_FOR_TIME_INPUT_EXACT,
    WAITING_FOR_TIME_INPUT_INTERVAL,
    WAITING_FOR_TITLE,
)


@pytest.mark.asyncio
@patch("app.handlers.calendar_set_event.CalendarRepository.has_time_conflict")
async def test_handle_time_input_interval_success(mock_has_conflict: AsyncMock):
    # 1. ПОДГОТОВКА МОКОВ
    # Имитируем, что выбранное время свободно (нет конфликтов)
    mock_has_conflict.return_value = False

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Имитируем текстовое сообщение от пользователя.
    # Специально добавляем пробелы, чтобы проверить работу .strip().replace(' ', '')
    update_mock.message.text = " 14:00 - 16:30 "
    update_mock.effective_user.id = 12345

    # Точечно делаем reply_text асинхронным
    update_mock.message.reply_text = AsyncMock()

    test_date = datetime.date(2026, 10, 14)
    # Кладём в ОЗУ дату, которую "выбрали" на предыдущем шаге
    context_mock.user_data = {"selected_date": test_date}

    # Стандартный шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    # 2. ВЫЗОВ ХЭНДЛЕРА
    result = await handle_time_input_interval(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    expected_start = datetime.time(14, 0)
    expected_end = datetime.time(16, 30)

    # Убеждаемся, что хэндлер правильно распарсил время и передал его в проверку конфликтов
    mock_has_conflict.assert_called_once_with(
        connection_mock, 12345, test_date, expected_start, expected_end
    )

    # Убеждаемся, что распарсенное время сохранилось в кэш для следующих шагов
    assert context_mock.user_data["start_time"] == expected_start
    assert context_mock.user_data["end_time"] == expected_end

    # Проверяем, что бот ответил правильным текстом
    update_mock.message.reply_text.assert_called_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs
    assert "Время начала: 14:00" in kwargs["text"]
    assert "Время окончания: 16:30" in kwargs["text"]
    assert "Укажите название мероприятия" in kwargs["text"]

    # Гарантируем переход на следующий стейт
    assert result == WAITING_FOR_TITLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_text, db_conflict, expected_error_fragment",
    [
        # 1. Провал регулярки
        ("абвгд", False, "Неверный формат времени"),
        # 2. Несуществующее время (ValueError)
        ("25:00-26:00", False, "некорректное время суток"),
        # 3. Конец раньше начала
        ("16:00-14:00", False, "время начала должно быть строго раньше времени окончания"),
        # 4. Конфликт в базе данных
        ("14:00-16:00", True, "это время занято"),
    ],
)
@patch("app.handlers.calendar_set_event.CalendarRepository.has_time_conflict")
async def test_handle_time_input_interval_negative(
    mock_has_conflict: AsyncMock, input_text: str, db_conflict: bool, expected_error_fragment: str
):
    # 1. ПОДГОТОВКА
    mock_has_conflict.return_value = db_conflict

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Подставляем текст из параметров
    update_mock.message.text = input_text
    update_mock.message.reply_text = AsyncMock()

    context_mock.user_data = {"selected_date": datetime.date(2026, 10, 14)}

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    # 2. ВЫЗОВ
    result = await handle_time_input_interval(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    # Проверяем, что во всех негативных сценариях мы остаемся на том же стейте
    assert result == WAITING_FOR_TIME_INPUT_INTERVAL

    # Проверяем, что бот ответил сообщением
    update_mock.message.reply_text.assert_called_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs

    # Проверяем, что в ответе есть нужный кусок текста ошибки из параметров
    assert expected_error_fragment in kwargs["text"]

    # Если мы тестируем БД-конфликт, проверяем, что запрос вообще ушел
    if db_conflict:
        mock_has_conflict.assert_called_once()
    else:
        # Для ошибок валидации база дергаться не должна
        mock_has_conflict.assert_not_called()


@pytest.mark.asyncio
async def test_handle_title_input():
    update_mock, context_mock = MagicMock(), MagicMock()
    title = "Погулять с хорошим мальчиком"
    update_mock.message.text = title

    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {}

    result = await handle_title_input(update_mock, context_mock)

    # Проверка что вернулся правильный state
    assert result == WAITING_FOR_DESC_CHOICE

    # Проверка что метод reply_text был вызван 1 раз
    update_mock.message.reply_text.assert_called_once()

    # Достаём все kwargs-ы из reply_text
    kwargs = update_mock.message.reply_text.call_args.kwargs

    # Проверяем что название события лежит в сообщении пользователю
    assert title in kwargs["text"]

    # Проверяем что в контекст было записано название события
    assert context_mock.user_data["event_title"] == title

    # Обращение к первой строке [0], первой кнопке [0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "desc_yes"
    assert kwargs["reply_markup"].inline_keyboard[0][0].text == "✅ Да"

    # Обращение к первой строке [0], второй кнопке [1]
    assert kwargs["reply_markup"].inline_keyboard[0][1].callback_data == "desc_no"
    assert kwargs["reply_markup"].inline_keyboard[0][1].text == "❌ Нет"


@pytest.mark.asyncio
@patch("app.handlers.calendar_set_event._save_event_to_db")
async def test_handle_cancel_add_description(mock_save_event_to_db: AsyncMock):
    # state который возвращается в случае callback data 'desc_no'
    mock_save_event_to_db.return_value = CHOOSING_ACTION

    update_mock, context_mock = AsyncMock(), MagicMock()

    update_mock.callback_query.data = "desc_no"
    context_mock.user_data = {}

    result: int = await handle_desc_choice(update_mock, context_mock)
    # Все проверки
    assert result == CHOOSING_ACTION
    update_mock.callback_query.answer.assert_awaited_once()
    assert context_mock.user_data["description"] is None
    mock_save_event_to_db.assert_called_once_with(update_mock, context_mock)


@pytest.mark.asyncio
async def test_handle_approve_add_description():
    update_mock, context_mock = AsyncMock(), MagicMock()

    update_mock.callback_query.data = "desc_yes"

    result: int = await handle_desc_choice(update_mock, context_mock)

    # Все проверки
    assert result == WAITING_FOR_DESCRIPTION
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    assert (
        "📝 Введите текст описания (заметки) для мероприятия:"
        in update_mock.callback_query.edit_message_text.call_args.kwargs["text"]
    )


@pytest.mark.asyncio
@patch("app.handlers.calendar_set_event.CalendarRepository.has_time_conflict")
async def test_handle_time_input_exact_success(mock_has_conflict: AsyncMock):
    # ПОДГОТОВКА МОКОВ
    # Имитируем, что выбранное время свободно (нет конфликтов)
    mock_has_conflict.return_value = False

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Имитируем текстовое сообщение от пользователя.
    # Специально добавляем пробелы, чтобы проверить работу .strip().replace(' ', '')
    update_mock.message.text = " 12:30 "
    update_mock.effective_user.id = 12345

    # Точечно делаем reply_text асинхронным
    update_mock.message.reply_text = AsyncMock()

    test_date = datetime.date(2026, 10, 20)
    # Кладём в ОЗУ дату, которую "выбрали" на предыдущем шаге
    context_mock.user_data = {"selected_date": test_date}

    # Стандартный шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    result: int = await handle_time_input_exact(update_mock, context_mock)

    # ПРОВЕРКИ
    expected_start = datetime.time(12, 30)
    expected_end = datetime.time(13)

    # Убеждаемся, что хэндлер правильно распарсил время и передал его в проверку конфликтов
    mock_has_conflict.assert_called_once_with(
        connection_mock, 12345, test_date, expected_start, expected_end
    )

    # Сохранения времени в КЭШ для следующего шага
    assert context_mock.user_data["start_time"] == expected_start
    assert context_mock.user_data["end_time"] == expected_end

    # Проверяем, что бот ответил правильным текстом
    update_mock.message.reply_text.assert_called_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs
    assert "Время начала: 12:30" in kwargs["text"]
    assert "Время окончания (авто): 13:00" in kwargs["text"]
    assert "Укажите название мероприятия" in kwargs["text"]

    assert result == WAITING_FOR_TITLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_text, db_conflict, expected_error_fragment",
    [
        # 1. Провал регулярки
        ("абвгд", False, "Неверный формат времени"),
        # 2. Несуществующее время (ValueError)
        ("25:00", False, "некорректное время суток"),
        # 3. Граничное время (схлопывание в нулевую длительность)
        ("23:59", False, "время начала события не может быть позже 23:58"),
        # 4. Конфликт в базе данных
        ("14:00", True, "это время занято"),
    ],
)
@patch("app.handlers.calendar_set_event.CalendarRepository.has_time_conflict")
async def test_handle_time_input_exact_negative(
    mock_has_conflict: AsyncMock, input_text: str, db_conflict: bool, expected_error_fragment: str
):
    # 1. ПОДГОТОВКА
    mock_has_conflict.return_value = db_conflict

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Подставляем текст из параметров
    update_mock.message.text = input_text
    update_mock.message.reply_text = AsyncMock()

    context_mock.user_data = {"selected_date": datetime.date(2026, 10, 20)}

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    # 2. ВЫЗОВ
    result = await handle_time_input_exact(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    # Проверяем, что во всех негативных сценариях мы остаемся на том же стейте
    assert result == WAITING_FOR_TIME_INPUT_EXACT

    # Проверяем, что бот ответил сообщением
    update_mock.message.reply_text.assert_called_once()
    kwargs: dict = update_mock.message.reply_text.call_args.kwargs

    assert expected_error_fragment in kwargs["text"]

    # Если мы тестируем БД-конфликт, проверяем, что запрос вообще ушел
    if db_conflict:
        mock_has_conflict.assert_called_once()
    else:
        # Для ошибок валидации база дергаться не должна
        mock_has_conflict.assert_not_called()


@pytest.mark.asyncio
@patch("app.handlers.calendar_set_event.CalendarRepository.has_time_conflict")
async def test_handle_time_input_exact_midnight_boundary(mock_has_conflict: AsyncMock):
    mock_has_conflict.return_value = False
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.message.text = " 23:50 "
    update_mock.effective_user.id = 12345

    update_mock.message.reply_text = AsyncMock()

    test_date = datetime.date(2026, 10, 20)

    context_mock.user_data = {"selected_date": test_date}

    # Стандартный шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    result: int = await handle_time_input_exact(update_mock, context_mock)

    assert result == WAITING_FOR_TITLE
    start_time = datetime.time(23, 50)
    end_time = datetime.time(23, 59)

    args: tuple = mock_has_conflict.call_args.args

    assert start_time == args[-2]
    assert end_time == args[-1]

    assert (
        "Время окончания (авто): 23:59" in update_mock.message.reply_text.call_args.kwargs["text"]
    )

    assert context_mock.user_data["start_time"] == start_time
    assert context_mock.user_data["end_time"] == end_time


@pytest.mark.asyncio
@patch("app.handlers.calendar_act_with_options.handle_back_to_day_menu_click")
@patch("app.core.calendar.services.CalendarService.get_user_busy_days")
@patch("app.core.calendar.repositories.CalendarRepository.get_events_by_date")
async def test_save_event_to_db(
    mock_get_events: AsyncMock, mock_get_busy_days: AsyncMock, mock_handle_back: AsyncMock
):
    # 1. ПОДГОТОВКА МОКОВ СЕРВИСОВ И РЕПОЗИТОРИЕВ
    mock_get_events.return_value = ["fake_record_1"]
    mock_get_busy_days.return_value = {14: True}
    mock_handle_back.return_value = "SOME_STATE"

    # Подготавливаем входящие объекты
    update_mock = AsyncMock()
    update_mock.effective_user.id = 12345

    context_mock = MagicMock()

    # Имитируем ОЗУ пользователя, заполненную на предыдущих шагах
    context_mock.user_data = {
        "selected_date": date(2026, 10, 14),
        "event_type": "interval",
        "event_title": "Сходить в магазин",
        "start_time": time(10, 0),
        "end_time": time(11, 0),
        "description": "Купить молока",
    }

    # Мокаем подключение к БД
    conn_mock = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = conn_mock

    # Мокаем репозиторий статистики
    stats_mock = AsyncMock()
    context_mock.application.stats_repository = stats_mock

    # 2. ВЫЗОВ ФУНКЦИИ
    result = await _save_event_to_db(update_mock, context_mock)

    # 3. ПРОВЕРКИ

    # Блок 1: База данных
    args = conn_mock.execute.call_args.args
    assert "INSERT INTO events" in args[0]
    # args содержит: [query, user_id, event_type, title, date, start, end, created_at, desc, is_public]
    # Используем ANY для created_at, так как там генерируется datetime.now() прямо внутри функции
    conn_mock.execute.assert_called_once_with(
        ANY,
        12345,
        "interval",
        "Сходить в магазин",
        date(2026, 10, 14),
        time(10, 0),
        time(11, 0),
        ANY,
        "Купить молока",
        False,
    )

    # Блок 2: Статистика
    stats_mock.increment_metric.assert_called_once_with("events_created_interval")
    stats_mock.increment_user_metric.assert_called_once_with(12345, "events_created")

    # Блок 3: Синхронизация (свежие данные из БД)
    mock_get_events.assert_called_once_with(conn_mock, 12345, date(2026, 10, 14))
    mock_get_busy_days.assert_called_once_with(conn=conn_mock, user_id=12345, year=2026, month=10)

    # Блок 4: Обновление ОЗУ (user_data)
    # Проверяем, что отчет сформирован
    assert "Мероприятие успешно добавлено!" in context_mock.user_data["edit_success_status"]
    assert "Время: 10:00 - 11:00" in context_mock.user_data["edit_success_status"]
    assert "Дата: 14.10.2026" in context_mock.user_data["edit_success_status"]
    assert "Купить молока" in context_mock.user_data["edit_success_status"]

    # Проверяем, что кэш обновился новыми данными
    assert context_mock.user_data["event_text_record"] == ["fake_record_1"]
    assert context_mock.user_data["month_busy_days"] == {14: True}

    # Проверяем очистку мусора: ключи-билдеры должны быть удалены
    for key in ["event_type", "event_title", "start_time", "end_time", "description"]:
        assert key not in context_mock.user_data

    # Блок 5: Возврат стейта
    mock_handle_back.assert_called_once_with(update_mock, context_mock)
    assert result == "SOME_STATE"


@pytest.mark.asyncio
@patch("app.handlers.calendar_set_event._save_event_to_db")
async def test_apply_description_input_before_saving_to_db(mock_save_event_to_db: AsyncMock):
    # Преамбула данных
    mock_save_event_to_db.return_value = CHOOSING_ACTION
    update_mock = MagicMock()
    context_mock = MagicMock()
    description = "Описание для заметки"

    # Фабула данных
    context_mock.user_data = {}
    update_mock.message.text = description

    # Вызов подопытного
    result = await handle_description_input(update_mock, context_mock)

    # Тесты
    assert result == CHOOSING_ACTION
    assert context_mock.user_data["description"] == description
    mock_save_event_to_db.assert_awaited_once_with(update_mock, context_mock)


@pytest.mark.asyncio
async def test_handle_set_event_interval_free_day():
    update_mock = AsyncMock()
    # Имитируем callback_data, где parts[1] == "interval"
    update_mock.callback_query.data = "some_prefix:interval"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()
    # Имитируем состояние ОЗУ после клика по свободному дню
    context_mock.user_data = {
        "selected_date": date(2026, 10, 21),
        "event_text_record": [],  # День полностью свободен
    }

    # ВЫЗОВ
    result = await handle_set_event(update_mock, context_mock)

    # ПРОВЕРКИ
    # 1. Проверяем, что в ОЗУ записался правильный тип события
    assert context_mock.user_data["event_type"] == "interval"

    # 2. Проверяем, что текст изменился и содержит нужные куски интерфейса
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    assert "Выбрана дата: 21.10.2026" in kwargs["text"]
    assert "Запланированные дела:" in kwargs["text"]  # Пришло из нашей утилиты
    assert "Тип события: [ ⏳ Интервал ]" in kwargs["text"]
    assert "Введите время начала и конца" in kwargs["text"]

    # 3. Гарантируем, что ConversationHandler получил команду ждать время
    assert result == WAITING_FOR_TIME_INPUT_INTERVAL


@pytest.mark.asyncio
async def test_handle_set_event_all_day_free_day():
    update_mock = AsyncMock()
    update_mock.callback_query.data = "some_prefix:all_day"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()
    # Имитируем состояние ОЗУ после клика по свободному дню
    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [],  # День полностью свободен
    }

    # ВЫЗОВ
    result = await handle_set_event(update_mock, context_mock)

    assert result == WAITING_FOR_TITLE

    assert context_mock.user_data["event_type"] == "all_day"

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    assert "Выбрана дата: 20.10.2026" in kwargs["text"]
    assert "Тип события: [ ☀️ Весь день ]" in kwargs["text"]
    assert "Укажите название мероприятия:" in kwargs["text"]
    assert "Например: [Поездка на дачу]" in kwargs["text"]


@pytest.mark.asyncio
async def test_handle_set_event_all_day_busy_day():
    update_mock = AsyncMock()
    update_mock.callback_query.data = "some_prefix:all_day"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "title": "Уборка",
                "start_time": time(8, 0),
                "end_time": time(9, 0),
                "event_type": "interval",
            }
        ],
        "month_busy_days": {20: "interval"},
    }

    result = await handle_set_event(update_mock, context_mock)

    assert result == CHOOSING_TIME
    update_mock.callback_query.answer.assert_awaited_once()

    kwargs: dict = update_mock.callback_query.answer.call_args.kwargs
    assert "❌ Ошибка: этот день частично занят" in kwargs["text"]
    assert "Выберите другую дату" in kwargs["text"]
    assert kwargs["show_alert"] is False

    update_mock.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_set_event_exact_busy_day():
    update_mock = AsyncMock()
    update_mock.callback_query.data = "some_prefix:exact"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()

    context_mock.user_data = {
        "selected_date": date(2026, 10, 20),
        "event_text_record": [
            {
                "title": "Уборка",
                "start_time": time(8, 0),
                "end_time": time(9, 0),
                "event_type": "interval",
            }
        ],
    }

    result = await handle_set_event(update_mock, context_mock)

    assert result == WAITING_FOR_TIME_INPUT_EXACT
    assert context_mock.user_data["event_type"] == "exact"

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    assert "Выбрана дата: 20.10.2026" in kwargs["text"]
    assert "Запланированные дела:" in kwargs["text"]
    assert "08:00 - 09:00 Уборка" in kwargs["text"]  # Событие которое есть в этом дне (events_text)
    assert "Тип события: [ ⏱️ Точное время ]" in kwargs["text"]  # Тип события которое добавляем
