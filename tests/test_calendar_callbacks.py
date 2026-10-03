import pytest
import datetime
from unittest.mock import patch, AsyncMock, MagicMock


from app.handlers.calendar_callbacks import handle_calendar_click
from app.handlers.states import CHOOSING_ACTION, CHOOSING_TIME


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