from datetime import datetime, date, time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.handlers.calendar_delete_event import handle_delete_choice
from app.handlers.calendar_keyboard import generate_calendar_keyboard
from app.handlers.calendar_set_event import handle_set_event
from app.handlers.commands import calendar_command
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_TIME,
    CONFIRMING_DELETE,
    WAITING_FOR_TIME_INPUT_EXACT,
    WAITING_FOR_TIME_INPUT_INTERVAL,
    WAITING_FOR_TITLE
)


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


@pytest.mark.asyncio
async def test_handle_set_event_interval_free_day():
    update_mock = AsyncMock()
    # Имитируем callback_data, где parts[1] == "interval"
    update_mock.callback_query.data = "some_prefix:interval"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()
    # Имитируем состояние ОЗУ после клика по свободному дню
    context_mock.user_data = {
        'selected_date': date(2026, 10, 21),
        'event_text_record': [] # День полностью свободен
    }

    # ВЫЗОВ
    result = await handle_set_event(update_mock, context_mock)

    # ПРОВЕРКИ
    # 1. Проверяем, что в ОЗУ записался правильный тип события
    assert context_mock.user_data['event_type'] == 'interval'

    # 2. Проверяем, что текст изменился и содержит нужные куски интерфейса
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    
    assert "Выбрана дата: 21.10.2026" in kwargs['text']
    assert "Запланированные дела:" in kwargs['text'] # Пришло из нашей утилиты
    assert "Тип события: [ ⏳ Интервал ]" in kwargs['text']
    assert "Введите время начала и конца" in kwargs['text']

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
        'selected_date': date(2026, 10, 20),
        'event_text_record': [] # День полностью свободен
    }

    # ВЫЗОВ
    result = await handle_set_event(update_mock, context_mock)

    assert result == WAITING_FOR_TITLE

    assert context_mock.user_data['event_type'] == 'all_day'

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    assert 'Выбрана дата: 20.10.2026' in kwargs['text']
    assert 'Тип события: [ ☀️ Весь день ]' in kwargs['text']
    assert 'Укажите название мероприятия:' in kwargs['text']
    assert 'Например: [Поездка на дачу]' in kwargs['text']


@pytest.mark.asyncio
async def test_handle_set_event_all_day_busy_day():
    update_mock = AsyncMock()
    update_mock.callback_query.data = "some_prefix:all_day"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()

    context_mock.user_data = {
        'selected_date': date(2026, 10, 20),
        'event_text_record':  [
            {'title': 'Уборка', 'start_time': time(8, 0), 'end_time': time(9, 0), 'event_type': 'interval'}
        ],
        'month_busy_days': {20: 'interval'}
    }

    result = await handle_set_event(update_mock, context_mock)

    assert result == CHOOSING_TIME
    update_mock.callback_query.answer.assert_awaited_once()

    kwargs: dict = update_mock.callback_query.answer.call_args.kwargs
    assert '❌ Ошибка: этот день частично занят' in kwargs['text']
    assert 'Выберите другую дату' in kwargs['text']
    assert kwargs['show_alert'] is False

    update_mock.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_set_event_exact_busy_day():
    update_mock = AsyncMock()
    update_mock.callback_query.data = "some_prefix:exact"
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()

    context_mock.user_data = {
        'selected_date': date(2026, 10, 20),
        'event_text_record':  [
            {'title': 'Уборка', 'start_time': time(8, 0), 'end_time': time(9, 0), 'event_type': 'interval'}
        ],
    }

    result = await handle_set_event(update_mock, context_mock)

    assert result == WAITING_FOR_TIME_INPUT_EXACT
    assert context_mock.user_data['event_type'] == 'exact'

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs

    assert 'Выбрана дата: 20.10.2026' in kwargs['text']
    assert 'Запланированные дела:' in kwargs['text']
    assert '08:00 - 09:00 Уборка' in kwargs['text'] # Событие которое есть в этом дне (events_text)
    assert 'Тип события: [ ⏱️ Точное время ]' in kwargs['text'] # Тип события которое добавляем


@pytest.mark.asyncio
@patch('app.handlers.calendar_delete_event.handle_delete_confirmation')
async def test_handle_delete_choice_prepare_delete_all(mock_handle_delete_confirmation: AsyncMock):
    update_mock = MagicMock()
    context_mock = MagicMock()

    mock_handle_delete_confirmation.return_value = CHOOSING_ACTION
    update_mock.callback_query.data = 'del_num:cancel'

    result: int = await handle_delete_choice(update_mock, context_mock)

    assert result == CHOOSING_ACTION



@pytest.mark.asyncio
@patch('app.handlers.calendar_delete_event.confirm_to_delete')
async def test_handle_delete_all_events(mock_confirm_to_delete: AsyncMock):
    update_mock = MagicMock()
    context_mock = MagicMock()
    
    mock_confirm_to_delete.return_value = CONFIRMING_DELETE
    update_mock.callback_query.data = 'del_num:everything'

    context_mock.user_data = {
        'event_text_record': [
            {'title': 'Уборка', 'start_time': time(7, 0), 'end_time': time(8, 0), 'event_type': 'interval'},
            {'title': 'Перекур', 'start_time': time(8, 0), 'end_time': time(8, 30), 'event_type': 'exact'}
        ],
        'selected_date': date(2026, 10, 1)
    }

    result: int = await handle_delete_choice(update_mock, context_mock)

    assert result == CONFIRMING_DELETE

    assert context_mock.user_data['delete_alert_text'] == "🗑️ Все мероприятия успешно удалены!"
    assert context_mock.user_data['delete_event_id'] == date(2026, 10, 1)
    assert context_mock.user_data['column_name'] == 'event_date'

    mock_confirm_to_delete.assert_awaited_once()
    args = mock_confirm_to_delete.call_args.args
    text_with_events = args[1]
    selected_date = args[2]
    delete_text: tuple = args[3]

    assert '07:00 - 08:00 Уборка' in text_with_events
    assert '08:00 - 08:30 Перекур' in text_with_events
    assert date(2026, 10, 1) == selected_date

    print(mock_confirm_to_delete.call_args.args)

    assert '*АБСОЛЮТНО ВСЕ* мероприятия на этот день?' in delete_text[0]
    assert '**все существующие заметки** на эту дату! Восстановление будет невозможно' in delete_text[1]
