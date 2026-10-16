from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import TelegramError
from telegram.ext import ConversationHandler

from app.handlers.calendar_invite import (
    handle_ask_telegram_id_for_public_events,
    handle_invite_event_by_text_number,
    handle_invite_event_selection,
    handle_invitee_id_input,
    handle_show_meetings,
    handle_show_public_events_another_user,
)
from app.handlers.states import TYPING_INVITEE_ID, TYPING_PUBLIC_EVENTS_USER_ID


# --- ТЕСТ 1: Приглашение через инлайн-кнопку ---
@pytest.mark.asyncio
@patch('app.handlers.calendar_invite.is_user_invitee_for_event')
async def test_handle_invite_event_selection_success(
    mock_is_user_invitee_for_event: AsyncMock
):
    update_mock, context_mock = AsyncMock(), MagicMock()
    mock_is_user_invitee_for_event.return_value = False
    # Имитируем клик по второй кнопке (индекс 1)
    update_mock.callback_query.data = "invite_num:1"
    update_mock.effective_user.id = 12345

    context_mock.user_data = {
        "event_text_record": [
            {"id": 100, "title": "Секретное собрание", 'start_time': time(1), 'end_time': time(2)},
            {"id": 200, "title": "Корпоратив", 'start_time': time(5), 'end_time': time(9)},
        ],
        'selected_date': date(2026, 10, 10)
    }

    result = await handle_invite_event_selection(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID

    mock_is_user_invitee_for_event.assert_awaited_once_with(
        user_id=12345,
        selected_date=date(2026, 10, 10),
        start_time=time(5, 0),
        end_time=time(9, 0),
    )

    # Проверяем, что ID правильного события сохранен в контекст
    assert context_mock.user_data["invite_event_id"] == 200

    # Проверяем, что бот ответил на callback (чтобы часики не крутились)
    update_mock.callback_query.answer.assert_awaited_once()

    # Проверяем текст сообщения
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs


    assert "*Выбрано событие*: Корпоратив" in kwargs["text"]
    
    assert "*отправьте Telegram ID*" in kwargs["text"]
    assert kwargs["parse_mode"] == "Markdown"


# --- ТЕСТ 2: Приглашение через текстовый ввод номера ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.is_user_invitee_for_event")
@patch("app.handlers.calendar_invite.get_validated_event_index")
async def test_handle_invite_event_by_text_number_success(
    mock_get_validated: AsyncMock,
    mock_is_user_invitee_for_event: AsyncMock,
):
    mock_is_user_invitee_for_event.return_value = False

    event_list = [
        {"id": 100, "title": "Секретное собрание", "start_time": time(1), "end_time": time(2)},
        {"id": 200, "title": "Корпоратив", "start_time": time(5), "end_time": time(9)},
    ]

    # Мокаем успешное прохождение валидатора: возвращаем индекс 1
    mock_get_validated.return_value = (True, 1, event_list)

    update_mock, context_mock = AsyncMock(), MagicMock()
    update_mock.effective_user.id = 12345
    context_mock.user_data = {"selected_date": date(2026, 10, 10)}

    result = await handle_invite_event_by_text_number(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID

    mock_is_user_invitee_for_event.assert_awaited_once_with(
        user_id=12345,
        selected_date=date(2026, 10, 10),
        start_time=time(5, 0),
        end_time=time(9, 0),
    )

    # Проверяем запись в контекст
    assert context_mock.user_data["invite_event_id"] == 200

    # Проверяем текст ответа (reply_text)
    update_mock.message.reply_text.assert_awaited_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs

    # Проверяем актуальную разметку (вынесено из-под звёздочек)
    assert "📌 *Выбрано событие*: Корпоратив" in kwargs["text"]
    assert "*отправьте Telegram ID*" in kwargs["text"]
    assert kwargs["parse_mode"] == "Markdown"


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
@patch("app.handlers.calendar_invite.User")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.Appointment")
@patch("app.handlers.calendar_invite.check_user_availability")
@patch("app.handlers.calendar_invite.generate_confirm_invite_keyboard")
async def test_handle_invitee_id_input_positive(
    mock_gen_keyboard: MagicMock,
    mock_check_avail: AsyncMock,
    mock_Appointment: MagicMock,
    mock_Event: MagicMock,
    mock_User: MagicMock,
    mock_validate: MagicMock,
):
    # 1. Настройка входных данных (Update, Context)
    update_mock = MagicMock()
    update_mock.message.text = "987654321"
    update_mock.effective_user.id = 11111
    update_mock.effective_user.first_name = "Шеф"
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.user_data = {"invite_event_id": 999}
    context_mock.bot.send_message = AsyncMock()

    # 2. Мокаем вспомогательные функции
    mock_validate.return_value = (True, 987654321)
    mock_check_avail.return_value = False
    mock_gen_keyboard.return_value = "fake_keyboard"

    # 3. Мокаем Django ORM
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)

    target_event = MagicMock()
    target_event.id = 999
    target_event.title = "Секретное совещание"
    target_event.event_date = date(2026, 10, 20)
    target_event.start_time = time(15, 0)
    target_event.end_time = time(16, 0)
    target_event.description = None
    mock_Event.objects.aget = AsyncMock(return_value=target_event)

    # Имитируем отсутствие старой записи (человек зовётся впервые)
    mock_Appointment.objects.filter.return_value.afirst = AsyncMock(return_value=None)
    
    # Имитируем создание новой записи
    created_appointment = MagicMock()
    created_appointment.id = 777
    mock_Appointment.objects.acreate = AsyncMock(return_value=created_appointment)
    mock_Appointment.Status.PENDING = "PENDING"

    # 4. Вызов хэндлера
    result: int = await handle_invitee_id_input(update_mock, context_mock)

    # 5. Проверки маршрутизации и стейта
    assert result == TYPING_INVITEE_ID
    assert "invite_event_id" in context_mock.user_data

    # 6. Валидация вызовов БД
    mock_User.objects.filter.assert_called_once_with(telegram_id=987654321)
    mock_Event.objects.aget.assert_awaited_once_with(id=999)
    mock_check_avail.assert_awaited_once_with(987654321, target_event)
    
    # Проверяем, что была вызвана новая связка filter + acreate
    mock_Appointment.objects.filter.assert_called_once_with(
        event_id=999, invitee_id=987654321
    )
    mock_Appointment.objects.acreate.assert_awaited_once_with(
        event_id=999, invitee_id=987654321, status="PENDING"
    )

    # 7. Валидация отправки сообщений (Гостю)
    context_mock.bot.send_message.assert_awaited_once()
    send_msg_kwargs = context_mock.bot.send_message.call_args.kwargs
    assert send_msg_kwargs["chat_id"] == 987654321
    assert "📌 Секретное совещание" in send_msg_kwargs["text"]
    assert 'Шеф' in send_msg_kwargs["text"]
    assert 'Дата: 20.10.2026' in send_msg_kwargs['text']
    assert 'Время: 15:00 - 16:00' in send_msg_kwargs['text']
    assert send_msg_kwargs["reply_markup"] == "fake_keyboard"

    # 8. Валидация сообщения (Организатору)
    update_mock.message.reply_text.assert_awaited_once()
    assert "987654321" in update_mock.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
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
@patch("app.handlers.calendar_invite.calendar_command")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_invitee_id_input_with_deleted_event(
    mock_validate: MagicMock, mock_calendar_command: AsyncMock
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
    assert (
        "Сессия устарела. Возвращаю вас в календарь"
        in update_mock.message.reply_text.call_args.args[0]
    )

    # Проверка что сообщение о приглашении не улетело приглашаемому (его не существует)
    context_mock.bot.assert_not_called()


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.User")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_invitee_unexited_telegram_id(
    mock_validate: MagicMock,
    mock_User: MagicMock,
):
    # Подготовка данных
    mock_validate.return_value = (True, 987654321)
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=False)

    context_mock.user_data = {"invite_event_id": 400}

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    # Проверка что выкинуло в календарь
    assert result == TYPING_INVITEE_ID

    assert (
        "Пользователь с таким ID *не зарегистрирован* в нашем боте."
        in update_mock.message.reply_text.call_args.args[0]
    )

    # Проверка что сообщение о приглашении не улетело приглашаемому (его не существует)
    context_mock.bot.assert_not_called()


# --- ТЕСТ 1: Пользователь занят (is_busy = True) ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.check_user_availability")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.User")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_invitee_id_input_is_busy(
    mock_validate: MagicMock,
    mock_User: MagicMock,
    mock_Event: MagicMock,
    mock_check_avail: AsyncMock,
):
    # Успешная начальная валидация
    mock_validate.return_value = (True, 987654321)
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)
    mock_Event.objects.aget = AsyncMock(return_value=MagicMock())

    # Симулируем, что пользователь занят в это время
    mock_check_avail.return_value = True

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {"invite_event_id": 999}

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID
    assert (
        "К сожалению, в это время пользователь *уже занят*"
        in update_mock.message.reply_text.call_args.args[0]
    )

    # Гарантируем, что сообщение не улетело
    context_mock.bot.send_message.assert_not_called()


# --- ТЕСТ 2: Приглашение уже отправлялось (created = False) ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.Appointment")
@patch("app.handlers.calendar_invite.check_user_availability")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.User")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_invitee_id_input_already_invited(
    mock_validate: MagicMock,
    mock_User: MagicMock,
    mock_Event: MagicMock,
    mock_check_avail: AsyncMock,
    mock_Appointment: MagicMock,
):
    mock_validate.return_value = (True, 987654321)
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)
    mock_Event.objects.aget = AsyncMock(return_value=MagicMock())
    mock_check_avail.return_value = False

    # Симулируем, что запись уже есть в БД (created = False)
    mock_Appointment.objects.aget_or_create = AsyncMock(return_value=(MagicMock(), False))

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {"invite_event_id": 999}

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID
    assert (
        "Вы уже отправляли приглашение этому пользователю"
        in update_mock.message.reply_text.call_args.args[0]
    )

    context_mock.bot.send_message.assert_not_called()


# --- ТЕСТ 3: Пользователь заблокировал бота (TelegramError) ---
@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.generate_confirm_invite_keyboard")
@patch("app.handlers.calendar_invite.Appointment")
@patch("app.handlers.calendar_invite.check_user_availability")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.User")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_invitee_id_input_telegram_error(
    mock_validate: MagicMock,
    mock_User: MagicMock,
    mock_Event: MagicMock,
    mock_check_avail: AsyncMock,
    mock_Appointment: MagicMock,
    mock_gen_keyboard: MagicMock,
):
    mock_validate.return_value = (True, 987654321)
    mock_User.objects.filter.return_value.aexists = AsyncMock(return_value=True)

    target_event = MagicMock()
    target_event.start_time = None  # Чтобы не заморачиваться с форматом времени
    mock_Event.objects.aget = AsyncMock(return_value=target_event)
    mock_check_avail.return_value = False

    # Запись успешно создается (created = True)
    mock_appointment = AsyncMock()  # Делаем именно AsyncMock, чтобы проверить adelete()
    mock_Appointment.objects.aget_or_create = AsyncMock(return_value=(mock_appointment, True))

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.reply_text = AsyncMock()
    context_mock.user_data = {"invite_event_id": 999}

    # Имитируем падение телеграма
    context_mock.bot.send_message = AsyncMock(
        side_effect=TelegramError("Forbidden: bot was blocked by the user")
    )

    result: int = await handle_invitee_id_input(update_mock, context_mock)

    assert result == TYPING_INVITEE_ID
    assert "Не удалось отправить приглашение" in update_mock.message.reply_text.call_args.args[0]

    # ГЛАВНАЯ ПРОВЕРКА: убеждаемся, что мы "подмели" за собой в базе данных
    mock_appointment.adelete.assert_awaited_once()


class AsyncMockQuerySet:
    """Универсальный мок-генератор для асинхронных запросов Django ORM."""

    def __init__(self, items):
        self.items = items
        self.aexists = AsyncMock(return_value=bool(items))

    async def __aiter__(self):
        for item in self.items:
            yield item


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.generate_back_calendar_button")
@patch("app.handlers.calendar_invite.Appointment")
async def test_handle_show_meetings_as_host_and_guest(
    mock_Appointment: MagicMock, mock_gen_button: MagicMock
):
    # 1. Подготовка данных пользователя
    my_telegram_id = 111111111
    friend_telegram_id = 8915759698

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.from_user.id = my_telegram_id
    update_mock.callback_query.edit_message_text = AsyncMock()
    mock_gen_button.return_value = "fake_back_button"

    # --- Встреча 1: Я организатор ---
    event_host = MagicMock()
    event_host.user_id = my_telegram_id
    event_host.title = "Созвон по проекту"
    event_host.event_date = date(2026, 10, 18)
    event_host.start_time = time(14, 0)
    event_host.end_time = time(15, 0)

    meeting_as_host = MagicMock()
    meeting_as_host.event = event_host
    meeting_as_host.invitee_id = friend_telegram_id
    meeting_as_host.get_status_display.return_value = "✅ Подтверждено"

    # --- Встреча 2: Я приглашенный ---
    event_guest = MagicMock()
    event_guest.user_id = friend_telegram_id
    event_guest.title = "Перекур"
    event_guest.event_date = date(2026, 10, 21)
    event_guest.start_time = time(10, 0)
    event_guest.end_time = time(10, 30)

    meeting_as_guest = MagicMock()
    meeting_as_guest.event = event_guest
    meeting_as_guest.invitee_id = my_telegram_id
    meeting_as_guest.get_status_display.return_value = "✅ Подтверждено"

    # Настраиваем цепочку ORM: select_related('event').filter(...)
    mock_Appointment.objects.select_related.return_value.filter.return_value = AsyncMockQuerySet(
        [meeting_as_host, meeting_as_guest]
    )

    # 2. Вызов хэндлера
    await handle_show_meetings(update_mock, context_mock)

    # 3. Проверки
    update_mock.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update_mock.callback_query.edit_message_text.call_args.kwargs
    result_text = kwargs["text"]

    # Проверяем блок "Назначенные мною встречи"
    assert "*🤝 Назначенные мною встречи:*" in result_text
    assert "*1. Созвон по проекту*" in result_text
    assert "📅 Дата: 18.10.2026 | ⏰ Время: 14:00 - 15:00" in result_text
    assert f"👤 Приглашенный: ID {friend_telegram_id}" in result_text
    assert "📊 Статус: ✅ Подтверждено" in result_text

    # Проверяем визуальный разделитель
    assert "➖➖➖➖➖➖➖➖➖➖" in result_text

    # Проверяем блок "Приглашения для меня"
    assert "*📩 Приглашения для меня:*" in result_text
    assert "*1. Перекур*" in result_text
    assert "📅 Дата: 21.10.2026 | ⏰ Время: 10:00 - 10:30" in result_text
    assert f"👑 Организатор: ID {friend_telegram_id}" in result_text

    # Проверяем параметры вызова Telegram API
    assert kwargs["parse_mode"] == "Markdown"
    assert kwargs["reply_markup"] == "fake_back_button"


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.generate_back_calendar_button")
@patch("app.handlers.calendar_invite.Appointment")
async def test_handle_show_meetings_no_meetings(
    mock_Appointment: MagicMock, mock_gen_button: MagicMock
):
    telegram_id = 111111111

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.callback_query.from_user.id = telegram_id
    update_mock.callback_query.edit_message_text = AsyncMock()
    mock_gen_button.return_value = "fake_back_button"

    # Пустой queryset
    mock_Appointment.objects.select_related.return_value.filter.return_value = AsyncMockQuerySet([])

    await handle_show_meetings(update_mock, context_mock)

    update_mock.callback_query.edit_message_text.assert_awaited_once()
    text = update_mock.callback_query.edit_message_text.call_args.kwargs["text"]

    assert "*🤝 Назначенные мною встречи:*\nВы никого не приглашали." in text
    assert "*📩 Приглашения для меня:*\nВас никто не приглашал." in text


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.generate_back_calendar_button")
async def test_handle_ask_telegram_id_for_public_events(mock_gen_back_button: MagicMock):
    # 1. ПОДГОТОВКА МОКОВ
    mock_gen_back_button.return_value = "fake_back_calendar_button"

    update_mock = MagicMock()
    update_mock.callback_query.edit_message_text = AsyncMock()

    context_mock = MagicMock()

    # 2. ВЫЗОВ ХЭНДЛЕРА
    result: int = await handle_ask_telegram_id_for_public_events(update_mock, context_mock)

    # 3. ПРОВЕРКА СТЕЙТА
    assert result == TYPING_PUBLIC_EVENTS_USER_ID

    # 4. ПРОВЕРКА ВЫЗОВА edit_message_text
    update_mock.callback_query.edit_message_text.assert_awaited_once_with(
        text="Отправьте *Telegram ID* пользователя, события которого хотите посмотреть:",
        parse_mode="Markdown",
        reply_markup="fake_back_calendar_button",
    )


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_show_public_events_another_user_invalid_input(
    mock_validate: MagicMock,
):
    # 1. Подготовка
    error_msg = "❌ Telegram ID должен состоять только из цифр. Попробуйте еще раз:"
    mock_validate.return_value = (False, error_msg)

    update_mock = MagicMock()
    update_mock.message.text = "abc"
    update_mock.effective_user.id = 11111
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()

    # 2. Вызов
    result: int = await handle_show_public_events_another_user(update_mock, context_mock)

    # 3. Проверки
    assert result == TYPING_PUBLIC_EVENTS_USER_ID

    update_mock.message.reply_text.assert_awaited_once_with(error_msg)


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.generate_back_calendar_button")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_show_public_events_another_user_no_events(
    mock_validate: MagicMock,
    mock_Event: MagicMock,
    mock_gen_back_button: MagicMock,
):
    # 1. Подготовка
    mock_validate.return_value = (True, 987654321)
    mock_gen_back_button.return_value = "fake_back_calendar_button"

    # Пустой queryset с aexists=False
    mock_qs = AsyncMockQuerySet([])
    mock_qs.aexists = AsyncMock(return_value=False)
    mock_Event.objects.filter.return_value.order_by.return_value = mock_qs

    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.message.text = "987654321"
    update_mock.effective_user.id = 11111
    update_mock.message.reply_text = AsyncMock()

    # 2. Вызов
    result: int = await handle_show_public_events_another_user(update_mock, context_mock)

    # 3. Проверки
    assert result == TYPING_PUBLIC_EVENTS_USER_ID

    update_mock.message.reply_text.assert_awaited_once_with(
        "❌ У пользователя с таким Telegram ID нет публичных событий.",
        reply_markup="fake_back_calendar_button",
    )


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.generate_back_calendar_button")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_show_public_events_another_user_positive(
    mock_validate: MagicMock, mock_Event: MagicMock, mock_gen_back_button: MagicMock
):
    # 1. Подготовка
    mock_validate.return_value = (True, 987654321)
    mock_gen_back_button.return_value = "fake_back_calendar_button"

    # Реальные объекты событий (не голые MagicMock), чтобы проверить сборку dict'ов
    event_1, event_2 = MagicMock(), MagicMock()
    event_1.title, event_1.description = "Событие 1", "Описание 1"
    event_1.start_time, event_1.end_time = time(10, 0), time(11, 0)
    event_1.is_public, event_1.event_date = True, date(2026, 10, 20)

    event_2.title, event_2.description = "Событие 2", "Описание 2"
    event_2.start_time, event_2.end_time = time(15, 0), time(16, 0)
    event_2.is_public, event_2.event_date = True, date(2026, 10, 21)

    # Мок ORM-цепочки с aexists=True
    mock_qs = AsyncMockQuerySet([event_1, event_2])
    mock_qs.aexists = AsyncMock(return_value=True)
    mock_Event.objects.filter.return_value.order_by.return_value = mock_qs

    update_mock = MagicMock()
    update_mock.message.text = " 987654321 "
    update_mock.effective_user.id = 11111
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()

    # 2. Вызов
    result: int = await handle_show_public_events_another_user(update_mock, context_mock)

    # 3. Проверка стейта
    assert result == ConversationHandler.END

    # 4. Проверка валидации (передан сырой текст с пробелами)
    mock_validate.assert_called_once_with(
        input_text=" 987654321 ",
        current_user_id=11111,
        self_error_msg="❌ В этом меню Вы не можете смотреть свои заметки. "
        "Введите ID другого пользователя:",
    )

    # 5. Проверка ORM-цепочки
    mock_Event.objects.filter.assert_called_once_with(user_id=987654321, is_public=True)
    mock_Event.objects.filter.return_value.order_by.assert_called_once_with(
        "event_date", "start_time"
    )

    # 7. Проверка финального сообщения
    update_mock.message.reply_text.assert_awaited_once()
    kwargs = update_mock.message.reply_text.call_args.kwargs
    text_public_events = kwargs["text"]
    assert "🌐 *Публичные события пользователя 987654321" in text_public_events

    # Проверка текста первого события
    assert "📝 *Просмотр события №1*" in text_public_events
    assert "📅 *Дата*: 20.10.2026" in text_public_events
    assert "📌 *Название*: Событие 1" in text_public_events
    assert "⏳ *Время*: 10:00 - 11:00" in text_public_events
    assert "🛡 *Доступ*: 👁 Публичное (Видно другим)" in text_public_events

    # Проверка текста второго события
    assert "📝 *Просмотр события №2*" in text_public_events
    assert "📅 *Дата*: 21.10.2026" in text_public_events
    assert "📌 *Название*: Событие 2" in text_public_events
    assert "⏳ *Время*: 15:00 - 16:00" in text_public_events
    assert "🛡 *Доступ*: 👁 Публичное (Видно другим)" in text_public_events


@pytest.mark.asyncio
@patch("app.handlers.calendar_invite.build_detailed_event_text")
@patch("app.handlers.calendar_invite.generate_back_calendar_button")
@patch("app.handlers.calendar_invite.Event")
@patch("app.handlers.calendar_invite.validate_telegram_id_input")
async def test_handle_show_public_events_another_user_truncation(
    mock_validate: MagicMock,
    mock_Event: MagicMock,
    mock_gen_back_button: MagicMock,
    mock_build_detailed_text: MagicMock,
):
    # 1. Подготовка
    mock_validate.return_value = (True, 987654321)
    mock_gen_back_button.return_value = "fake_button"

    # Каждое событие даёт 3000 символов -> суммарно > 4000 -> должна сработать обрезка
    mock_build_detailed_text.side_effect = ["X" * 3000, "Y" * 3000]

    event_1, event_2 = MagicMock(), MagicMock()
    mock_qs = AsyncMockQuerySet([event_1, event_2])
    mock_qs.aexists = AsyncMock(return_value=True)
    mock_Event.objects.filter.return_value.order_by.return_value = mock_qs

    update_mock = MagicMock()
    update_mock.message.text = "987654321"
    update_mock.effective_user.id = 11111
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()

    # 2. Вызов
    result: int = await handle_show_public_events_another_user(update_mock, context_mock)

    # 3. Проверки
    assert result == ConversationHandler.END

    kwargs = update_mock.message.reply_text.call_args.kwargs
    text: str = kwargs["text"]

    assert len(text) < 4100  # 4000 + суффикс обрезки
    assert text.endswith("... (показана только часть событий)")
