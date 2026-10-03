from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.handlers.calendar_keyboard import generate_calendar_keyboard
from app.handlers.commands import calendar_command


def test_generate_calendar_keyboard_complex_state():
    # Генерируем клавиатуру на Октябрь 2026 года
    # 5-е число полностью занято, 10-е частично, 15-е мы сейчас редактируем
    markup = generate_calendar_keyboard(
        year=2026,
        month=10,
        busy_days={5: 'full', 10: 'partial'},
        editing_day=15,
        is_back_button=True
    )
    
    # Извлекаем саму матрицу кнопок из объекта разметки
    keyboard = markup.inline_keyboard

    # 1. Проверка заголовка (первый ряд, первая кнопка)
    assert keyboard[0][0].text == "Октябрь 2026"
    assert keyboard[0][0].callback_data == "calendar_ignore"
    
    # 2. Собираем тексты всех кнопок в плоский список для удобного поиска
    buttons_text = [button.text for row in keyboard for button in row]

    # Проверяем, что бизнес-логика правильно расставила эмодзи статусов
    assert "🔴 5" in buttons_text
    assert "🟡 10" in buttons_text
    assert "⚪ 15" in buttons_text
    # Проверяем, что обычный день остался без эмодзи
    assert "20" in buttons_text

    # 3. Проверка навигации (последний ряд)
    nav_row = keyboard[-1]

    # Кнопка "Назад" (мы передали is_back_button=True)
    assert "🔙 Назад" in [btn.text for btn in nav_row]

    # Проверка математики предыдущего месяца
    assert nav_row[0].text == "« Пред"
    assert nav_row[0].callback_data == "calendar_nav:2026:9"

    # Проверка математики следующего месяца
    assert nav_row[-1].text == "След »"
    assert nav_row[-1].callback_data == "calendar_nav:2026:11"


@pytest.mark.asyncio
@patch('app.handlers.commands.CalendarService.get_user_busy_days')
@patch('app.handlers.commands.generate_calendar_keyboard')
async def test_calendar_command_inline_click(mock_calendar_keyboard, mock_busy_days):
    # 1. ПОДГОТОВКА МОКОВ
    mock_busy_days.return_value = {5: 'full', 10: 'partial'}
    mock_calendar_keyboard.return_value = "fake_markup"
    
    update_mock = AsyncMock()
    update_mock.effective_user.id = 123456789
    
    test_date = datetime(2026, 10, 3)
    context_mock = MagicMock()
    context_mock.user_data = {'selected_date': test_date}

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    await calendar_command(update_mock, context_mock)

    # Проверяем, что дата взялась из selected_date
    mock_busy_days.assert_called_once_with(
        conn=connection_mock,
        user_id=123456789,
        year=2026,
        month=10
    )

    # Проверяем генерацию клавиатуры
    mock_calendar_keyboard.assert_called_once_with(
        year=2026,
        month=10,
        busy_days={5: 'full', 10: 'partial'}
    )

    # Проверяем, что кэш обновился
    assert context_mock.user_data['month_busy_days'] == {5: 'full', 10: 'partial'}

    # Проверяем вызов редактирования сообщения (так как это инлайн-клик)
    update_mock.callback_query.edit_message_text.assert_called_once()
    
    # Убеждаемся, что send_message НЕ вызывался
    context_mock.bot.send_message.assert_not_called()


@pytest.mark.asyncio
@patch('app.handlers.commands.CalendarService.get_user_busy_days')
@patch('app.handlers.commands.generate_calendar_keyboard')
async def test_calendar_command_text_command(mock_calendar_keyboard, mock_busy_days):

    mock_busy_days.return_value = {12: 'full'}
    mock_calendar_keyboard.return_value = "fake_markup"
    
    update_mock = AsyncMock()
    update_mock.effective_user.id = 987654321
    
    # КЛЮЧЕВОЕ ОТЛИЧИЕ №1: Это текстовая команда, инлайн-кнопки нет
    update_mock.callback_query = None
    
    context_mock = MagicMock()
    # КЛЮЧЕВОЕ ОТЛИЧИЕ №2: В памяти нет сохраненной даты
    context_mock.user_data = {}

    context_mock.bot.send_message = AsyncMock()

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    # Запоминаем текущее время до запуска, чтобы знать, что ожидать
    current_time = datetime.now()
    expected_year = current_time.year
    expected_month = current_time.month


    await calendar_command(update_mock, context_mock)

    # ПРОВЕРКИ
    # Убеждаемся, что хэндлер откатился к текущей дате
    mock_busy_days.assert_called_once_with(
        conn=connection_mock,
        user_id=987654321,
        year=expected_year,
        month=expected_month
    )

    mock_calendar_keyboard.assert_called_once_with(
        year=expected_year,
        month=expected_month,
        busy_days={12: 'full'}
    )

    # Убеждаемся, что кэш синхронизирован
    assert context_mock.user_data['month_busy_days'] == {12: 'full'}

    # КЛЮЧЕВОЕ ОТЛИЧИЕ №3: Проверяем вызов отправки нового сообщения
    context_mock.bot.send_message.assert_called_once()
    
    # Мы даже можем залезть в параметры и проверить, что была передана наша клавиатура
    kwargs = context_mock.bot.send_message.call_args.kwargs
    assert kwargs['chat_id'] == update_mock.effective_chat.id
    assert kwargs['reply_markup'] == "fake_markup"
