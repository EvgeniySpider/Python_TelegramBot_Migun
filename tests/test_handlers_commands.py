from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from app.handlers.calendar_keyboard import generate_back_calendar_button
from app.handlers.commands import calendar_command, start


@pytest.mark.asyncio
async def test_start_command_handler():
    # 1. ПОДГОТОВКА ФЕЙКОВОГО ЗАПРОСА (Update)
    mock_update = MagicMock()
    mock_update.effective_user.id = 123456789
    mock_update.effective_chat.id = 987654321

    # 2. ПОДГОТОВКА ФЕЙКОВОГО КОНТЕКСТА (Context)
    mock_context = MagicMock()

    # Мокаем асинхронный сервис регистрации (чтобы он не лез в БД)
    mock_context.application.user_service.register_visitor = AsyncMock()

    # Мокаем асинхронную отправку сообщения
    mock_context.bot.send_message = AsyncMock()

    # 3. ВЫЗОВ ХЭНДЛЕРА
    await start(mock_update, mock_context)

    # 4. ПРОВЕРКИ (Asserts)
    # Проверяем, что в сервис передан правильный telegram_id
    mock_context.application.user_service.register_visitor.assert_called_once_with(123456789)

    # Проверяем, что приветствие ушло в нужный чат с новым текстом и новой клавиатурой
    mock_context.bot.send_message.assert_called_once_with(
        chat_id=987654321,
        text="Добро пожаловать! Нажмите кнопку ниже или введите /calendar, чтобы открыть интерактивный календарь.",
        reply_markup=generate_back_calendar_button("📅 Открыть календарь"),
    )


@pytest.mark.asyncio
@patch("app.handlers.commands.CalendarService.get_user_busy_days")
@patch("app.handlers.commands.generate_calendar_keyboard")
async def test_calendar_command_inline_click(mock_calendar_keyboard, mock_busy_days):
    # 1. ПОДГОТОВКА МОКОВ
    mock_busy_days.return_value = {5: "full", 10: "partial"}
    mock_calendar_keyboard.return_value = "fake_markup"

    update_mock = AsyncMock()
    update_mock.effective_user.id = 123456789

    test_date = datetime(2026, 10, 3)
    context_mock = MagicMock()
    context_mock.user_data = {"selected_date": test_date}

    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    await calendar_command(update_mock, context_mock)

    # Проверяем, что дата взялась из selected_date
    mock_busy_days.assert_called_once_with(
        conn=connection_mock, user_id=123456789, year=2026, month=10
    )

    # Проверяем генерацию клавиатуры
    mock_calendar_keyboard.assert_called_once_with(
        year=2026, month=10, busy_days={5: "full", 10: "partial"}
    )

    # Проверяем, что кэш обновился
    assert context_mock.user_data["month_busy_days"] == {5: "full", 10: "partial"}

    # Проверяем вызов редактирования сообщения (так как это инлайн-клик)
    update_mock.callback_query.edit_message_text.assert_called_once()

    # Убеждаемся, что send_message НЕ вызывался
    context_mock.bot.send_message.assert_not_called()


@pytest.mark.asyncio
@patch("app.handlers.commands.CalendarService.get_user_busy_days")
@patch("app.handlers.commands.generate_calendar_keyboard")
async def test_calendar_command_text_command(mock_calendar_keyboard, mock_busy_days):

    mock_busy_days.return_value = {12: "full"}
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
    context_mock.application.database.connection.return_value.__aenter__.return_value = (
        connection_mock
    )

    # Запоминаем текущее время до запуска, чтобы знать, что ожидать
    current_time = datetime.now()
    expected_year = current_time.year
    expected_month = current_time.month

    await calendar_command(update_mock, context_mock)

    # ПРОВЕРКИ
    # Убеждаемся, что хэндлер откатился к текущей дате
    mock_busy_days.assert_called_once_with(
        conn=connection_mock, user_id=987654321, year=expected_year, month=expected_month
    )

    mock_calendar_keyboard.assert_called_once_with(
        year=expected_year, month=expected_month, busy_days={12: "full"}
    )

    # Убеждаемся, что кэш синхронизирован
    assert context_mock.user_data["month_busy_days"] == {12: "full"}

    # КЛЮЧЕВОЕ ОТЛИЧИЕ №3: Проверяем вызов отправки нового сообщения
    context_mock.bot.send_message.assert_called_once()

    # Мы даже можем залезть в параметры и проверить, что была передана наша клавиатура
    kwargs = context_mock.bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == update_mock.effective_chat.id
    assert kwargs["reply_markup"] == "fake_markup"


@pytest.mark.asyncio
@patch('app.handlers.commands.CalendarService.get_user_busy_days')
@patch('app.handlers.commands.generate_calendar_keyboard')
async def test_calendar_command_clears_fsm_flags(mock_calendar_keyboard: MagicMock, mock_busy_days: AsyncMock):
    """
    Проверяет, что вызов корня календаря сжигает все временные флаги машины состояний,
    предотвращая утечку контекста при экстренном прерывании диалогов.
    """
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.effective_user.id = 12345
    update_mock.callback_query = None  # Имитируем текстовый ввод команды /calendar
    
    # Делаем send_message асинхронным моком
    context_mock.bot.send_message = AsyncMock()
    
    # Мокаем БД
    connection_mock = MagicMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = connection_mock

    # Забиваем "оперативку" пользователя мусором от различных FSM-диалогов
    context_mock.user_data = {
        "is_editing_date_mode": True,
        "invite_event_id": 999,
        "edit_event_id": 777,
        "selected_date": date(2026, 10, 15)  # Используем правильный date
    }
    
    mock_busy_days.return_value = {}

    # ВЫЗОВ ХЭНДЛЕРА
    result = await calendar_command(update_mock, context_mock)

    # ПРОВЕРКИ
    assert result == ConversationHandler.END
    
    # Убеждаемся, что все временные флаги уничтожены
    assert "is_editing_date_mode" not in context_mock.user_data
    assert "invite_event_id" not in context_mock.user_data
    assert "edit_event_id" not in context_mock.user_data
    
    # Убеждаемся, что полезная дата не пострадала
    assert context_mock.user_data.get("selected_date") == date(2026, 10, 15)
    
    # Убеждаемся, что бот реально отправил сообщение
    context_mock.bot.send_message.assert_awaited_once()