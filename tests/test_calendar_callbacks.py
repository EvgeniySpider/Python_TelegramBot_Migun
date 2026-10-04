import pytest
import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import date, time

from app.handlers.calendar_act_with_options import handle_options_click
from app.handlers.calendar_callbacks import handle_calendar_click
from app.handlers.calendar_set_event import handle_desc_choice, handle_time_input_exact, handle_time_input_interval, handle_title_input
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_TIME,
    WAITING_FOR_DESCRIPTION,
    WAITING_FOR_TIME_INPUT_EXACT,
    WAITING_FOR_TITLE,
    WAITING_FOR_TIME_INPUT_INTERVAL,
    WAITING_FOR_DESC_CHOICE
)

@pytest.mark.asyncio
@patch('app.handlers.calendar_callbacks.CalendarRepository.get_events_by_date')
@patch('app.handlers.calendar_callbacks.generate_time_options_keyboard')
async def test_handle_calendar_click_free_day(mock_generate_keyboard, mock_get_events):
    # 1. ПОДГОТОВКА МОКОВ
    # Возвращаем пустой список (или falsy значение), имитируя отсутствие событий на этот день
    mock_get_events.return_value = []
    mock_generate_keyboard.return_value = "fake_time_keyboard"

    update_mock = AsyncMock()
    # Имитируем callback_data от клика по 1 октября 2026 года
    update_mock.callback_query.data = "calendar_day:2026:10:1"
    update_mock.effective_user.id = 12345
    
    context_mock = MagicMock()
    # Исходное состояние user_data — пустое или без флага редактирования
    context_mock.user_data = {}
    
    # Мокаем статистику (это асинхронный вызов)
    context_mock.application.stats_repository.increment_metric = AsyncMock()

    # Шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    # 2. ВЫЗОВ ХЭНДЛЕРА
    result = await handle_calendar_click(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    # Проверяем инкремент метрики
    context_mock.application.stats_repository.increment_metric.assert_called_once_with('calendar_clicks')

    # Проверяем сохранение даты в ОЗУ
    expected_date = datetime.date(2026, 10, 1)
    assert context_mock.user_data['selected_date'] == expected_date
    assert context_mock.user_data['event_text_record'] == []

    # Проверяем, что часики загрузки погашены
    update_mock.callback_query.answer.assert_called_once()

    # Проверяем корректность параметров запроса к БД
    mock_get_events.assert_called_once_with(connection_mock, 12345, expected_date)

    # Проверяем, что генератор клавиатуры был вызван с is_adding=False (по дефолту)
    mock_generate_keyboard.assert_called_once_with(False)

    # Проверяем, что сообщение было изменено, и проверяем его содержимое
    update_mock.callback_query.edit_message_text.assert_called_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert "На этот день ничего не запланировано" in kwargs['text']
    assert "01.10.2026" in kwargs['text']
    assert kwargs['reply_markup'] == "fake_time_keyboard"

    # Гарантируем, что ConversationHandler получил правильный сигнал перехода в следующее состояние
    assert result == CHOOSING_TIME


@pytest.mark.asyncio
@patch('app.handlers.calendar_callbacks.CalendarRepository.get_events_by_date')
@patch('app.handlers.calendar_callbacks.generate_options_keyboard')
async def test_handle_calendar_click_busy_day(mock_generate_keyboard, mock_get_events):
    fake_event = [
        {
            'title': 'День рождения',
            'start_time': None,  # Триггерит 'Весь день'
            'end_time': None,
            'description': None, # Триггерит 'Не указано'
            'is_public': True,   # Триггерит '👁 Публичное'
            'event_date': datetime.date(2026, 10, 20)
        }
    ]

    # Возвращаем пустой список (или falsy значение), имитируя отсутствие событий на этот день
    mock_get_events.return_value = fake_event

    mock_generate_keyboard.return_value = "fake_options_keyboard"

    update_mock = AsyncMock()
    update_mock.callback_query.data = "calendar_day:2026:10:20"
    update_mock.effective_user.id = 12345
    update_mock.callback_query.edit_message_text = AsyncMock()
    
    context_mock = MagicMock()
    # Исходное состояние user_data — пустое или без флага редактирования
    context_mock.user_data = {}
    
    # Мокаем статистику (это асинхронный вызов)
    context_mock.application.stats_repository.increment_metric = AsyncMock()

    # Шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock
    
    # ВЫЗОВ
    result = await handle_calendar_click(update_mock, context_mock)

    context_mock.application.stats_repository.increment_metric.assert_called_once_with('calendar_clicks')

    expected_date = datetime.date(2026, 10, 20)
    assert context_mock.user_data['selected_date'] == expected_date
    assert context_mock.user_data['event_text_record'] == fake_event
    update_mock.callback_query.answer.assert_called_once()

    # Проверяем корректность параметров запроса к БД
    mock_get_events.assert_called_once_with(connection_mock, 12345, expected_date)

    # Проверяем, что генератор клавиатуры был вызван с is_adding=False (по дефолту)
    mock_generate_keyboard.assert_called_once()


    update_mock.callback_query.edit_message_text.assert_called_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
  
    assert "📅 *Выбранная дата*: 20.10.2026" in kwargs['text']
    assert "День рождения" in kwargs['text']
    assert "20.10.2026" in kwargs['text']
    assert kwargs['reply_markup'] == "fake_options_keyboard"

    assert result == CHOOSING_ACTION


@pytest.mark.asyncio
@patch('app.handlers.calendar_set_event.CalendarRepository.has_time_conflict')
async def test_handle_time_input_interval_success(mock_has_conflict: AsyncMock):
    # 1. ПОДГОТОВКА МОКОВ
    # Имитируем, что выбранное время свободно (нет конфликтов)
    mock_has_conflict.return_value = False

    update_mock = AsyncMock()
    # Имитируем текстовое сообщение от пользователя. 
    # Специально добавляем пробелы, чтобы проверить работу .strip().replace(' ', '')
    update_mock.message.text = " 14:00 - 16:30 "
    update_mock.effective_user.id = 12345
    
    # Точечно делаем reply_text асинхронным
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    test_date = datetime.date(2026, 10, 14)
    # Кладём в ОЗУ дату, которую "выбрали" на предыдущем шаге
    context_mock.user_data = {'selected_date': test_date}

    # Стандартный шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    # 2. ВЫЗОВ ХЭНДЛЕРА
    result = await handle_time_input_interval(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    expected_start = datetime.time(14, 0)
    expected_end = datetime.time(16, 30)

    # Убеждаемся, что хэндлер правильно распарсил время и передал его в проверку конфликтов
    mock_has_conflict.assert_called_once_with(
        connection_mock,
        12345,
        test_date,
        expected_start,
        expected_end
    )

    # Убеждаемся, что распарсенное время сохранилось в кэш для следующих шагов
    assert context_mock.user_data['start_time'] == expected_start
    assert context_mock.user_data['end_time'] == expected_end

    # Проверяем, что бот ответил правильным текстом
    update_mock.message.reply_text.assert_called_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs
    assert "Время начала: 14:00" in kwargs['text']
    assert "Время окончания: 16:30" in kwargs['text']
    assert "Укажите название мероприятия" in kwargs['text']

    # Гарантируем переход на следующий стейт
    assert result == WAITING_FOR_TITLE


@pytest.mark.asyncio
@pytest.mark.parametrize("input_text, db_conflict, expected_error_fragment", [
    # 1. Провал регулярки
    ("абвгд", False, "Неверный формат времени"),
    # 2. Несуществующее время (ValueError)
    ("25:00-26:00", False, "некорректное время суток"),
    # 3. Конец раньше начала
    ("16:00-14:00", False, "время начала не может быть позже"),
    # 4. Конфликт в базе данных
    ("14:00-16:00", True, "это время занято"),
])
@patch('app.handlers.calendar_set_event.CalendarRepository.has_time_conflict')
async def test_handle_time_input_interval_negative(
    mock_has_conflict: AsyncMock,
    input_text: str,
    db_conflict: bool,
    expected_error_fragment: str
):
    # 1. ПОДГОТОВКА
    mock_has_conflict.return_value = db_conflict

    update_mock = AsyncMock()
    # Подставляем текст из параметров
    update_mock.message.text = input_text
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.user_data = {'selected_date': datetime.date(2026, 10, 14)}

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    # 2. ВЫЗОВ
    result = await handle_time_input_interval(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    # Проверяем, что во всех негативных сценариях мы остаемся на том же стейте
    assert result == WAITING_FOR_TIME_INPUT_INTERVAL

    # Проверяем, что бот ответил сообщением
    update_mock.message.reply_text.assert_called_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs
    
    # Проверяем, что в ответе есть нужный кусок текста ошибки из параметров
    assert expected_error_fragment in kwargs['text']

    # Если мы тестируем БД-конфликт, проверяем, что запрос вообще ушел
    if db_conflict:
        mock_has_conflict.assert_called_once()
    else:
        # Для ошибок валидации база дергаться не должна
        mock_has_conflict.assert_not_called()


@pytest.mark.asyncio
async def test_handle_title_input():
    update_mock = MagicMock()
    context_mock = MagicMock()
    title = 'Погулять с хорошим мальчиком'
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
    assert title in kwargs['text']

    # Проверяем что в контекст было записано название события
    assert context_mock.user_data['event_title'] == title

    # Обращение к первой строке [0], первой кнопке [0]
    assert kwargs['reply_markup'].inline_keyboard[0][0].callback_data == "desc_yes"
    assert kwargs['reply_markup'].inline_keyboard[0][0].text == "✅ Да"

    # Обращение к первой строке [0], второй кнопке [1]
    assert kwargs['reply_markup'].inline_keyboard[0][1].callback_data == "desc_no"
    assert kwargs['reply_markup'].inline_keyboard[0][1].text == "❌ Нет"
        

@pytest.mark.asyncio
@patch('app.handlers.calendar_set_event._save_event_to_db')
async def test_handle_cancel_add_description(mock_save_event_to_db: AsyncMock):
    # state который возвращается в случае callback data 'desc_no'
    mock_save_event_to_db.return_value = CHOOSING_ACTION

    update_mock = AsyncMock()
    context_mock = MagicMock()

    update_mock.callback_query.data = 'desc_no'
    context_mock.user_data = {}

    result: int = await handle_desc_choice(update_mock, context_mock)
    # Все проверки
    assert result == CHOOSING_ACTION
    update_mock.callback_query.answer.assert_awaited_once()
    assert context_mock.user_data['description'] is None
    mock_save_event_to_db.assert_called_once_with(update_mock, context_mock)


@pytest.mark.asyncio
async def test_handle_approve_add_description():
    update_mock = AsyncMock()
    context_mock = MagicMock()

    update_mock.callback_query.data = 'desc_yes'

    result: int = await handle_desc_choice(update_mock, context_mock)

    # Все проверки
    assert result == WAITING_FOR_DESCRIPTION 
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    assert '📝 Введите текст описания (заметки) для мероприятия:'\
        in update_mock.callback_query.edit_message_text.call_args.kwargs['text']


@pytest.mark.asyncio
@patch('app.handlers.calendar_set_event.CalendarRepository.has_time_conflict')
async def test_handle_time_input_exact_success(mock_has_conflict: AsyncMock):
    # ПОДГОТОВКА МОКОВ
    # Имитируем, что выбранное время свободно (нет конфликтов)
    mock_has_conflict.return_value = False

    update_mock = AsyncMock()
    # Имитируем текстовое сообщение от пользователя. 
    # Специально добавляем пробелы, чтобы проверить работу .strip().replace(' ', '')
    update_mock.message.text = " 12:30 "
    update_mock.effective_user.id = 12345
    
    # Точечно делаем reply_text асинхронным
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    test_date = datetime.date(2026, 10, 20)
    # Кладём в ОЗУ дату, которую "выбрали" на предыдущем шаге
    context_mock.user_data = {'selected_date': test_date}

    # Стандартный шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    result: int = await handle_time_input_exact(update_mock, context_mock)

    # ПРОВЕРКИ
    expected_start = datetime.time(12, 30)
    expected_end = datetime.time(13)

    # Убеждаемся, что хэндлер правильно распарсил время и передал его в проверку конфликтов
    mock_has_conflict.assert_called_once_with(
        connection_mock,
        12345,
        test_date,
        expected_start,
        expected_end
    )

    # Сохранения времени в КЭШ для следующего шага
    assert context_mock.user_data['start_time'] == expected_start
    assert context_mock.user_data['end_time'] == expected_end

    # Проверяем, что бот ответил правильным текстом
    update_mock.message.reply_text.assert_called_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs
    assert "Время начала: 12:30" in kwargs['text']
    assert "Время окончания (авто): 13:00" in kwargs['text']
    assert "Укажите название мероприятия" in kwargs['text']

    assert result == WAITING_FOR_TITLE


@pytest.mark.asyncio
@pytest.mark.parametrize("input_text, db_conflict, expected_error_fragment", [
    # 1. Провал регулярки
    ("абвгд", False, "Неверный формат времени"),
    # 2. Несуществующее время (ValueError)
    ("25:00", False, "некорректное время суток"),
    # 3. Конфликт в базе данных
    ("14:00", True, "это время занято"),
])
@patch('app.handlers.calendar_set_event.CalendarRepository.has_time_conflict')
async def test_handle_time_input_exact_negative(
    mock_has_conflict: AsyncMock,
    input_text: str,
    db_conflict: bool,
    expected_error_fragment: str
):
    # 1. ПОДГОТОВКА
    mock_has_conflict.return_value = db_conflict

    update_mock = AsyncMock()
    # Подставляем текст из параметров
    update_mock.message.text = input_text
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.user_data = {'selected_date': datetime.date(2026, 10, 20)}

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    # 2. ВЫЗОВ
    result = await handle_time_input_exact(update_mock, context_mock)

    # 3. ПРОВЕРКИ
    # Проверяем, что во всех негативных сценариях мы остаемся на том же стейте
    assert result == WAITING_FOR_TIME_INPUT_EXACT

    # Проверяем, что бот ответил сообщением
    update_mock.message.reply_text.assert_called_once()
    kwargs: dict = update_mock.message.reply_text.call_args.kwargs

    assert expected_error_fragment in kwargs['text']

    # Если мы тестируем БД-конфликт, проверяем, что запрос вообще ушел
    if db_conflict:
        mock_has_conflict.assert_called_once()
    else:
        # Для ошибок валидации база дергаться не должна
        mock_has_conflict.assert_not_called()


@pytest.mark.asyncio
@patch('app.handlers.calendar_set_event.CalendarRepository.has_time_conflict')
async def test_handle_time_input_exact_midnight_boundary(mock_has_conflict: AsyncMock):
    mock_has_conflict.return_value = False
    update_mock = AsyncMock()
    update_mock.message.text = " 23:50 "
    update_mock.effective_user.id = 12345
    
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    test_date = datetime.date(2026, 10, 20)

    context_mock.user_data = {'selected_date': test_date}

    # Стандартный шашлык для контекстного менеджера БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    result: int = await handle_time_input_exact(update_mock, context_mock)

    assert result == WAITING_FOR_TITLE
    start_time = datetime.time(23, 50)
    end_time = datetime.time(23, 59, 59)

    args: tuple = mock_has_conflict.call_args.args

    assert start_time == args[-2]
    assert end_time == args[-1]

    assert 'Время окончания (авто): 23:59' in update_mock.message.reply_text.call_args.kwargs['text']

    assert context_mock.user_data['start_time'] == start_time
    assert context_mock.user_data['end_time'] == end_time


@pytest.mark.asyncio
async def test_handle_options_click_create_full_day():
    update_mock = AsyncMock()
    update_mock.callback_query.data = "action_create"
    
    context_mock = MagicMock()
    # Имитируем, что день полностью забит ('full')
    context_mock.user_data = {
        'selected_date': date(2026, 10, 20),
        'month_busy_days': {20: 'full'}
    }

    result: int = await handle_options_click(update_mock, context_mock)

    # Проверяем, что хэндлер отбил нас назад
    assert result == CHOOSING_ACTION
    
    # Проверяем текст алерта
    update_mock.callback_query.answer.assert_awaited_once()
    kwargs = update_mock.callback_query.answer.call_args.kwargs
    assert '❌ Ошибка: этот день полностью занят' in kwargs['text']
    assert kwargs['show_alert'] is False


@pytest.mark.asyncio
@patch('app.handlers.calendar_callbacks.generate_time_options_keyboard')
async def test_handle_options_click_create_success(mock_keyboard):
    mock_keyboard.return_value = "fake_keyboard"
    
    update_mock = AsyncMock()
    update_mock.callback_query.data = "action_create"
    
    context_mock = MagicMock()

    context_mock.user_data = {
        'selected_date': date(2026, 10, 20),
        'month_busy_days': {}, # Нет метки 'full'
        'event_text_record': [
            {'title': 'Уборка', 'start_time': time(8, 0), 'end_time': time(9, 0), 'event_type': 'interval'}
        ]
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
    assert '📅 *Выбранная дата*: 20.10.2026' in kwargs['text']
    assert '08:00 - 09:00 Уборка' in kwargs['text'] # Убеждаемся, что build_events_list_text вшил заметку
    assert 'Укажите формат времени проведения события:' in kwargs['text']
    
    # Убеждаемся, что клавиатура прикрепилась и формат Markdown включен
    assert kwargs['reply_markup'] == "fake_keyboard"
    assert kwargs['parse_mode'] == "Markdown"
    
    # Проверяем, что в клавиатуру ушел правильный флаг is_adding=True
    mock_keyboard.assert_called_once_with(True)