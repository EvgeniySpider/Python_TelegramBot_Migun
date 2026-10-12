import pytest
import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import InlineKeyboardMarkup

from app.handlers.calendar_callbacks import handle_calendar_click, handle_calendar_nav_click
from app.handlers.states import CHOOSING_ACTION, CHOOSING_TIME


@pytest.mark.asyncio
@patch('app.handlers.calendar_callbacks.CalendarRepository.get_events_by_date')
@patch('app.handlers.calendar_callbacks.generate_time_options_keyboard')
async def test_handle_calendar_click_free_day(mock_generate_keyboard, mock_get_events):
    # 1. ПОДГОТОВКА МОКОВ
    # Возвращаем пустой список (или falsy значение), имитируя отсутствие событий на этот день
    mock_get_events.return_value = []
    mock_generate_keyboard.return_value = "fake_time_keyboard"

    update_mock, context_mock = AsyncMock(), MagicMock()
    # Имитируем callback_data от клика по 1 октября 2026 года
    update_mock.callback_query.data = "calendar_day:2026:10:1"
    update_mock.effective_user.id = 12345
    
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

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.callback_query.data = "calendar_day:2026:10:20"
    update_mock.effective_user.id = 12345
    update_mock.callback_query.edit_message_text = AsyncMock()
    
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

# ---------------------------------------------------------------------------------------------------
# ТУТ ВСЁ


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback_data, expected_year, expected_month, expected_title",
    [
        # Переход внутри года
        ("calendar_nav:2026:9", 2026, 9, "Сентябрь 2026"),
        ("calendar_nav:2026:11", 2026, 11, "Ноябрь 2026"),
        # Переход через границу года: декабрь → январь
        ("calendar_nav:2027:1", 2027, 1, "Январь 2027"),
        # Переход через границу года: январь → декабрь
        ("calendar_nav:2025:12", 2025, 12, "Декабрь 2025"),
    ]
)
@patch('app.handlers.calendar_callbacks.CalendarService.get_user_busy_days')
async def test_handle_calendar_nav_click(
    mock_get_busy_days: AsyncMock,
    callback_data: str,
    expected_year: int,
    expected_month: int,
    expected_title: str,
):
    # 1. Подготовка моков
    update_mock = MagicMock()
    update_mock.effective_user.id = 555
    update_mock.callback_query.data = callback_data
    update_mock.callback_query.answer = AsyncMock()
    update_mock.callback_query.edit_message_reply_markup = AsyncMock()

    context_mock = MagicMock()
    context_mock.user_data = {}

    mock_conn = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    fake_busy_days = {5: 'full', 10: 'partial'}
    mock_get_busy_days.return_value = fake_busy_days

    # 2. Вызов хэндлера
    await handle_calendar_nav_click(update_mock, context_mock)

    # 3. Гасим анимацию загрузки на кнопке
    update_mock.callback_query.answer.assert_awaited_once()

    # 4. Проверяем запрос busy_days именно под целевой месяц/год
    mock_get_busy_days.assert_awaited_once_with(
        conn=mock_conn,
        user_id=555,
        year=expected_year,
        month=expected_month
    )

    # 5. Проверяем синхронизацию ОЗУ
    assert context_mock.user_data['month_busy_days'] == fake_busy_days

    # 6. Распаковываем клавиатуру из edit_message_reply_markup
    update_mock.callback_query.edit_message_reply_markup.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_reply_markup.call_args.kwargs
    markup: InlineKeyboardMarkup = kwargs['reply_markup']

    # Собираем все кнопки в плоский список
    all_buttons = [btn for row in markup.inline_keyboard for btn in row]

    # 7. Проверка заголовка календаря (первый ряд, первая кнопка)
    header_button = markup.inline_keyboard[0][0]
    assert header_button.text == expected_title
    assert header_button.callback_data == "calendar_ignore"

    # 8. Проверка, что бизнес-логика правильно расставила эмодзи статусов
    assert "🔴 5" in [btn.text for btn in all_buttons]
    assert "🟡 10" in [btn.text for btn in all_buttons]

    # 9. Проверка навигации в последнем ряду
    nav_row = markup.inline_keyboard[-1]

    # Математика пред/след месяца для проверки callback_data
    prev_month = expected_month - 1 if expected_month > 1 else 12
    prev_year = expected_year if expected_month > 1 else expected_year - 1
    next_month = expected_month + 1 if expected_month < 12 else 1
    next_year = expected_year if expected_month < 12 else expected_year + 1

    assert nav_row[0].text == "« Пред"
    assert nav_row[0].callback_data == f"calendar_nav:{prev_year}:{prev_month}"

    assert nav_row[-1].text == "След »"
    assert nav_row[-1].callback_data == f"calendar_nav:{next_year}:{next_month}"

    # 10. Убеждаемся, что кнопки редактирования режима (🔙 Назад) тут НЕТ
    assert all(btn.callback_data != "back_to_edit_menu" for btn in all_buttons)
