from datetime import datetime, date, time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from telegram.ext import ConversationHandler
from telegram.error import TelegramError

from app.handlers.calendar_delete_event import handle_delete_choice, handle_delete_confirmation
from app.handlers.calendar_edit_flow import handle_edit_field_click, handle_typing_edit_desc, handle_typing_edit_time, handle_typing_edit_title
from app.handlers.calendar_invite import handle_invitee_id_input
from app.handlers.calendar_keyboard import generate_calendar_keyboard
from app.handlers.calendar_set_event import handle_set_event
from app.handlers.commands import calendar_command
from app.handlers.states import (
    CHOOSING_ACTION,
    CHOOSING_TIME,
    CONFIRMING_DELETE,
    TYPING_EDIT_DESC,
    TYPING_EDIT_TIME,
    TYPING_EDIT_TITLE,
    TYPING_INVITEE_ID,
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

    assert '*АБСОЛЮТНО ВСЕ* мероприятия на этот день?' in delete_text[0]
    assert '**все существующие заметки** на эту дату! Восстановление будет невозможно' in delete_text[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "column_name", ['id', 'event_date']
)
@patch('app.handlers.calendar_delete_event.notify_and_cancel_appointments')
@patch('app.handlers.calendar_delete_event.del_event_on_info')
@patch('app.handlers.calendar_delete_event.prepare_after_delete')
async def test_handle_delete_confirmation_for_one_event_and_all_events(
    mock_prepare_after_delete: AsyncMock,
    mock_del_event_on_info: AsyncMock,
    mock_notify_and_cancel_appointments: AsyncMock,
    column_name: str
):
    mock_prepare_after_delete.return_value = ConversationHandler.END

    update_mock, context_mock = MagicMock(), MagicMock()

    update_mock.callback_query.data = 'confirm_delete_yes'
    context_mock.user_data = {
        'delete_event_id': 123,
        'column_name': column_name
    }
    update_mock.effective_user.id = 12345
    
    result: int = await handle_delete_confirmation(update_mock, context_mock)

    assert result == ConversationHandler.END

    mock_notify_and_cancel_appointments.assert_awaited_once_with(
        12345, column_name, 123, context_mock.bot
    )

    mock_del_event_on_info.assert_awaited_once_with(
        context_mock, update_mock, column_name, 123
    )

    mock_prepare_after_delete.assert_awaited_once_with(
        update_mock, context_mock, update_mock.callback_query
    )


@pytest.mark.asyncio
@patch('app.handlers.calendar_delete_event.handle_back_to_day_menu_click')
async def test_handle_delete_confirmation_no(mock_handle_back_to_day_menu: AsyncMock):
    # Мокаем возврат из функции возврата в меню
    mock_handle_back_to_day_menu.return_value = CHOOSING_ACTION

    update_mock, context_mock = MagicMock(), MagicMock()
    # Любая data, отличная от "confirm_delete_yes", отправит нас в ветку else
    update_mock.callback_query.data = 'confirm_delete_no'

    # Наполняем контекст ключами, которые должны быть удалены, и ключом-свидетелем
    context_mock.user_data = {
        'delete_event_id': 123,
        'column_name': 'id',
        'safe_key': 'im_safe'
    }

    result: int = await handle_delete_confirmation(update_mock, context_mock)

    assert result == CHOOSING_ACTION

    # Валидируем, что нужные ключи стерты
    assert 'delete_event_id' not in context_mock.user_data
    assert 'column_name' not in context_mock.user_data
    
    # Валидируем, что контекст не очистили целиком
    assert context_mock.user_data.get('safe_key') == 'im_safe'

    # Проверяем, что хэндлер возврата вызвался правильно
    mock_handle_back_to_day_menu.assert_awaited_once_with(update_mock, context_mock)


@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
@patch('app.handlers.calendar_invite.User')
@patch('app.handlers.calendar_invite.Event')
@patch('app.handlers.calendar_invite.Appointment')
@patch('app.handlers.calendar_invite.check_user_availability')
@patch('app.handlers.calendar_invite.generate_confirm_invite_keyboard')
async def test_handle_invitee_id_input_positive(
    mock_gen_keyboard: MagicMock,
    mock_check_avail: AsyncMock,
    mock_Appointment: MagicMock,
    mock_Event: MagicMock,
    mock_User: MagicMock,
    mock_validate: MagicMock
):
    # 1. Настройка входных данных (Update, Context)
    update_mock = MagicMock()
    update_mock.message.text = "987654321"
    update_mock.effective_user.id = 11111
    update_mock.effective_user.first_name = "Шеф"
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.user_data = {'invite_event_id': 999}
    context_mock.bot.send_message = AsyncMock()

    # 2. Мокаем вспомогательные функции
    # Возвращаем (is_valid=True, validation_result=987654321)
    mock_validate.return_value = (True, 987654321)
    mock_check_avail.return_value = False
    mock_gen_keyboard.return_value = "fake_keyboard"

    # 3. Мокаем Django ORM
    # User.objects.filter(telegram_id=...).aexists()
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)

    # Event.objects.aget(id=...)
    target_event = MagicMock()
    target_event.id = 999
    target_event.title = "Секретное совещание"
    target_event.event_date = date(2026, 10, 20)
    target_event.start_time = time(15, 0)
    mock_Event.objects.aget = AsyncMock(return_value=target_event)

    # Appointment.objects.aget_or_create(...) возвращает кортеж (объект, created_bool)
    created_appointment = MagicMock()
    created_appointment.id = 777
    mock_Appointment.objects.aget_or_create = AsyncMock(return_value=(created_appointment, True))
    mock_Appointment.Status.PENDING = "PENDING"

    # 4. Вызов хэндлера
    result: int = await handle_invitee_id_input(update_mock, context_mock)

    # 5. Проверки маршрутизации и стейта
    assert result == TYPING_INVITEE_ID
    assert 'invite_event_id' in context_mock.user_data

    # 6. Валидация вызовов БД
    mock_User.objects.filter.assert_called_once_with(telegram_id=987654321)
    mock_Event.objects.aget.assert_awaited_once_with(id=999)
    mock_check_avail.assert_awaited_once_with(987654321, target_event)
    mock_Appointment.objects.aget_or_create.assert_awaited_once_with(
        event_id=999,
        invitee_id=987654321,
        defaults={'status': "PENDING"}
    )

    # 7. Валидация отправки сообщений
    context_mock.bot.send_message.assert_awaited_once()
    send_msg_kwargs = context_mock.bot.send_message.call_args.kwargs
    assert send_msg_kwargs['chat_id'] == 987654321
    assert "Секретное совещание" in send_msg_kwargs['text']
    assert "Шеф" in send_msg_kwargs['text']
    assert send_msg_kwargs['reply_markup'] == "fake_keyboard"

    # Финальное сообщение самому пользователю (содержит ID приглашенного)
    update_mock.message.reply_text.assert_awaited_once()
    assert "987654321" in update_mock.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
async def test_handle_invitee_id_input_ourself(mock_validate: MagicMock):
    # Подготовка данных
    mock_validate.return_value = (False, 987654321)
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    # Проверка что остались на том же state-е
    assert result == TYPING_INVITEE_ID

    assert update_mock.message.reply_text.call_args.args[0] == 987654321

    # Проверка что сообщение о приглашении не улетело приглашаемому (то-есть нам)
    context_mock.bot.assert_not_called()


@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.calendar_command')
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
async def test_handle_invitee_id_input_with_deleted_event(
    mock_validate: MagicMock,
    mock_calendar_command: AsyncMock
):
    # Подготовка данных
    mock_validate.return_value = (True, 987654321)
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    mock_calendar_command.return_value = TYPING_INVITEE_ID

    context_mock.user_data = {}
   
    result: int = await handle_invitee_id_input(update_mock, context_mock)

    # Проверка что выкинуло в календарь
    assert result == TYPING_INVITEE_ID

    # Проверка что НАМ прилетело корректное сообщение об ошибке
    assert 'Сессия устарела. Возвращаю вас в календарь' in update_mock.message.reply_text.call_args.args[0]

    # Проверка что сообщение о приглашении не улетело приглашаемому (его не существует)
    context_mock.bot.assert_not_called()


@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.User')
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
async def test_handle_invitee_unexited_telegram_id(
    mock_validate: MagicMock,
    mock_User: MagicMock,
):
    # Подготовка данных
    mock_validate.return_value = (True, 987654321)
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value = False)

    context_mock.user_data = {'invite_event_id': 400}
   
    result: int = await handle_invitee_id_input(update_mock, context_mock)

    # Проверка что выкинуло в календарь
    assert result == TYPING_INVITEE_ID

    assert 'Пользователь с таким ID *не зарегистрирован* в нашем боте.' \
        in update_mock.message.reply_text.call_args.args[0] 

    # Проверка что сообщение о приглашении не улетело приглашаемому (его не существует)
    context_mock.bot.assert_not_called()

# --- ТЕСТ 1: Пользователь занят (is_busy = True) ---
@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.check_user_availability')
@patch('app.handlers.calendar_invite.Event')
@patch('app.handlers.calendar_invite.User')
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
async def test_handle_invitee_id_input_is_busy(
    mock_validate: MagicMock,
    mock_User: MagicMock,
    mock_Event: MagicMock,
    mock_check_avail: AsyncMock
):
    # Успешная начальная валидация
    mock_validate.return_value = (True, 987654321)
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)
    mock_Event.objects.aget = AsyncMock(return_value=MagicMock())
    
    # Симулируем, что пользователь занят в это время
    mock_check_avail.return_value = True

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {'invite_event_id': 999}

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID
    assert "К сожалению, в это время пользователь *уже занят*" in update_mock.message.reply_text.call_args.args[0]
    
    # Гарантируем, что сообщение не улетело
    context_mock.bot.send_message.assert_not_called()


# --- ТЕСТ 2: Приглашение уже отправлялось (created = False) ---
@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.Appointment')
@patch('app.handlers.calendar_invite.check_user_availability')
@patch('app.handlers.calendar_invite.Event')
@patch('app.handlers.calendar_invite.User')
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
async def test_handle_invitee_id_input_already_invited(
    mock_validate: MagicMock,
    mock_User: MagicMock,
    mock_Event: MagicMock,
    mock_check_avail: AsyncMock,
    mock_Appointment: MagicMock
):
    mock_validate.return_value = (True, 987654321)
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)
    mock_Event.objects.aget = AsyncMock(return_value=MagicMock())
    mock_check_avail.return_value = False

    # Симулируем, что запись уже есть в БД (created = False)
    mock_Appointment.objects.aget_or_create = AsyncMock(return_value=(MagicMock(), False))

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {'invite_event_id': 999}

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID
    assert "Вы уже отправляли приглашение этому пользователю" in update_mock.message.reply_text.call_args.args[0]
    
    context_mock.bot.send_message.assert_not_called()


# --- ТЕСТ 3: Пользователь заблокировал бота (TelegramError) ---
@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.generate_confirm_invite_keyboard')
@patch('app.handlers.calendar_invite.Appointment')
@patch('app.handlers.calendar_invite.check_user_availability')
@patch('app.handlers.calendar_invite.Event')
@patch('app.handlers.calendar_invite.User')
@patch('app.handlers.calendar_invite.validate_telegram_id_input')
async def test_handle_invitee_id_input_telegram_error(
    mock_validate: MagicMock,
    mock_User: MagicMock,
    mock_Event: MagicMock,
    mock_check_avail: AsyncMock,
    mock_Appointment: MagicMock,
    mock_gen_keyboard: MagicMock
):
    mock_validate.return_value = (True, 987654321)
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)
    
    target_event = MagicMock()
    target_event.start_time = None # Чтобы не заморачиваться с форматом времени
    mock_Event.objects.aget = AsyncMock(return_value=target_event)
    mock_check_avail.return_value = False

    # Запись успешно создается (created = True)
    mock_appointment = AsyncMock() # Делаем именно AsyncMock, чтобы проверить adelete()
    mock_Appointment.objects.aget_or_create = AsyncMock(return_value=(mock_appointment, True))

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {'invite_event_id': 999}

    # Имитируем падение телеграма
    context_mock.bot.send_message = AsyncMock(side_effect=TelegramError("Forbidden: bot was blocked by the user"))

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID
    assert "Не удалось отправить приглашение" in update_mock.message.reply_text.call_args.args[0]

    # ГЛАВНАЯ ПРОВЕРКА: убеждаемся, что мы "подмели" за собой в базе данных
    mock_appointment.adelete.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_edit_field_click_title():
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = 'edit_field:title'
    update_mock.callback_query.edit_message_text = AsyncMock()

    result: int = await handle_edit_field_click(update_mock, context_mock)

    assert result == TYPING_EDIT_TITLE

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert 'Введите новое название для этого события' in kwargs['text']


@pytest.mark.asyncio
@patch('app.handlers.calendar_edit_flow._refresh_day_menu_after_edit')
async def test_handle_typing_edit_title(
    mock_refresh_day_menu_after_edit: AsyncMock
):
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    # Проверяем, что strip() сработает (убирает пробелы по краям)
    update_mock.message.text = ' Новое название для события '
    context_mock.user_data = {'edit_event_id': 999}
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
    assert args[0] == 'UPDATE events SET title = $1 WHERE id = $2' # Тут title
    assert args[1] == 'Новое название для события' # Пробелы по краям удалены!
    assert args[2] == 999

    # Метрики
    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        'events_edited'
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        123, 'events_edited'
    )

    # Проверяем текст статуса
    assert 'Название события успешно изменено' in context_mock.user_data['edit_success_status']


# --- 1. ПРЕАМБУЛА: Клик по кнопке "Описание" ---
@pytest.mark.asyncio
async def test_handle_edit_field_click_desc():
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = 'edit_field:desc'
    update_mock.callback_query.edit_message_text = AsyncMock()

    # Вызов
    result: int = await handle_edit_field_click(update_mock, context_mock)

    # Проверки
    assert result == TYPING_EDIT_DESC

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert 'Введите новое описание для этого события' in kwargs['text']


# --- 2. МЯСО: Сохранение нового описания в БД ---
@pytest.mark.asyncio
@patch('app.handlers.calendar_edit_flow._refresh_day_menu_after_edit')
async def test_handle_typing_edit_desc(
    mock_refresh_day_menu_after_edit: AsyncMock
):
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    # Сразу передаем текст описания (с пробелами для проверки strip)
    update_mock.message.text = ' Новое крутое описание '
    context_mock.user_data = {'edit_event_id': 999}
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
    assert args[0] == 'UPDATE events SET description = $1 WHERE id = $2'
    assert args[1] == 'Новое крутое описание' # Проверяем, что пробелы отрезались
    assert args[2] == 999

    # Проверка метрик
    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        'events_edited'
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        123, 'events_edited'
    )
    
    # Проверка статуса
    assert 'Описание события успешно изменено' in context_mock.user_data['edit_success_status']


# --- 1. ПРЕАМБУЛА: Клик по кнопке "Время" ---
@pytest.mark.asyncio
async def test_handle_edit_field_click_time():
    # Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.data = 'edit_field:time'
    update_mock.callback_query.edit_message_text = AsyncMock()

    # Вызов
    result: int = await handle_edit_field_click(update_mock, context_mock)

    # Проверки
    assert result == TYPING_EDIT_TIME

    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    assert 'Введите новый временной интервал для этого события' in kwargs['text']

# --- 2. Проверка валидного времени и сохранения его в БД ---
@pytest.mark.asyncio
@patch('app.handlers.calendar_edit_flow.CalendarRepository.has_time_conflict')
@patch('app.handlers.calendar_edit_flow._refresh_day_menu_after_edit')
async def test_handle_typing_edit_time_positive(
    mock_refresh_day_menu_after_edit: AsyncMock,
    mock_has_time_conflict: AsyncMock
):
    # Подготовка данных
    mock_refresh_day_menu_after_edit.return_value = CHOOSING_ACTION
    update_mock, context_mock, mock_con = AsyncMock(), MagicMock(), AsyncMock()

    update_mock.message.text = ' 12:30 - 13:30 '
    context_mock.user_data = {
        'selected_date': date(2026, 10, 20),
        'edit_event_id': '999'
    }
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
        mock_con, 100, date(2026, 10, 20), time(12, 30), time (13, 30), 999
    )
    # Проверяем что подключение к БД вызывалось 2 раза
    assert context_mock.application.database.connection.call_count == 2

    args: tuple = mock_con.execute.call_args.args

    sql_query = args[0]
    assert 'UPDATE events' in sql_query
    assert 'SET start_time = $1' in sql_query
    assert 'end_time = $2' in sql_query
    assert "event_type = 'interval'" in sql_query
    assert 'WHERE id = $3' in sql_query

    start_time, end_time, event_id = args[1], args[2], args[3]
    assert start_time == time(12, 30)
    assert end_time == time (13, 30)
    assert event_id == 999

    assert 'Время события успешно изменено' in context_mock.user_data['edit_success_status']

    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        'events_edited'
    )

    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        100, 'events_edited'
    )


@pytest.mark.asyncio
async def test_handle_typing_edit_time_incorrect_pattern():
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.message.text = 'Чушь а не время'

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME

    text = update_mock.message.reply_text.call_args.kwargs['text']

    assert 'Неверный формат времени' in text
    assert 'Пожалуйста, введите интервал (например: 9-10, 09:30-11 или 15:00-16:30)' in text


@pytest.mark.asyncio
async def test_handle_typing_edit_time_unexistent_time():
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    # Такого времени не существует
    update_mock.message.text = '24:30-25:30'

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME
    
    text = update_mock.message.reply_text.call_args.kwargs['text']

    assert 'Введено некорректное время суток (максимум 23:59)' in text


@pytest.mark.asyncio
async def test_handle_typing_edit_time_reversed_time():
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    # Время начала больше времени окончания
    update_mock.message.text = '17:30-16:30'

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME
    
    text = update_mock.message.reply_text.call_args.kwargs['text']

    assert 'Ошибка: время начала не может быть позже времени окончания' in text


@pytest.mark.asyncio
@patch('app.handlers.calendar_edit_flow.CalendarRepository.has_time_conflict')
async def test_handle_typing_edit_time_busy_time(mock_hast_time_conflict: AsyncMock):
    # Подготовка данных
    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.message.text = '14:30-15:30'
    mock_hast_time_conflict.return_value = True

    # ВЫЗОВ
    result: int = await handle_typing_edit_time(update_mock, context_mock)

    # Проверяем что остались на том же state-е
    assert result == TYPING_EDIT_TIME
    
    text = update_mock.message.reply_text.call_args.kwargs['text']

    assert 'Ошибка: это время занято' in text