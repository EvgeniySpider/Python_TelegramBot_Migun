import datetime
from datetime import date, time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from telegram.ext import ConversationHandler


from app.core.calendar.repositories import CalendarRepository
from app.core.calendar.utils import build_detailed_event_text, build_events_list_text
from app.handlers.calendar_act_with_options import confirm_to_delete
from app.handlers.calendar_delete_event import del_event_on_info, prepare_after_delete
from app.handlers.calendar_edit_flow import _refresh_day_menu_after_edit
from app.handlers.states import CHOOSING_ACTION, CONFIRMING_DELETE
from app.handlers.utils import get_validated_event_index, notify_and_cancel_appointments, validate_telegram_id_input


def test_build_detailed_event_text_basic():
    # 1. ПОДГОТОВКА ФЕЙКОВЫХ ДАННЫХ (Обычные словари)
    fake_events = [
        {
            'title': 'Созвон по проекту',
            'start_time': datetime.time(9, 0),
            'end_time': datetime.time(10, 0),
            'description': 'Погулять с хорошим мальчиком',
            'is_public': False,
            'event_date': datetime.date(2026, 10, 18)
        }
    ]

    # 2. ВЫЗОВ ФУНКЦИИ
    result: str = build_detailed_event_text(
        events=fake_events,
        index=0,
        numbered=True,
        is_show_date=True
    )

    # 3. ПРОВЕРКИ
    assert "📝 *Просмотр события №1*" in result
    assert "📌 *Название*: Созвон по проекту" in result
    assert "⏳ *Время*: 09:00 - 10:00" in result
    assert "📖 *Описание*: Погулять с хорошим мальчиком" in result
    assert "🔒 Приватное (Только вы)" in result
    assert "📅 *Дата*: 18.10.2026" in result

def test_build_detailed_event_text_all_day_and_public():
    # Проверяем альтернативные ветки (весь день, публичное, нет описания)
    fake_events = [
        {
            'title': 'День рождения',
            'start_time': None,  # Триггерит 'Весь день'
            'end_time': None,
            'description': None, # Триггерит 'Не указано'
            'is_public': True,   # Триггерит '👁 Публичное'
            'event_date': datetime.date(2026, 10, 20)
        }
    ]

    result: str = build_detailed_event_text(events=fake_events, index=0)

    assert "⏳ *Время*: Весь день" in result
    assert "📖 *Описание*: Не указано" in result
    assert "👁 Публичное (Видно другим)" in result


def test_build_events_list_text_empty():
    # Пустой список (свободный день)
    result: str = build_events_list_text([])
    assert "Запланированные дела:" in result
    assert "весь день" not in result
    

def test_build_events_list_text_with_data():
    # Имитация списка дел
    fake_events = [
        {'title': 'Уборка', 'start_time': None, 'end_time': None, 'event_type': 'all_day'}
    ]
    result: str = build_events_list_text(fake_events, numbered=False)
    assert "Запланированные дела:" in result
    assert "• Уборка (весь день)" in result


# --- ТЕСТ 1: Негативный (Ввели текст вместо числа) ---
@pytest.mark.asyncio
async def test_get_validated_event_index_not_digit():
    update_mock = AsyncMock()
    update_mock.message.text = "какой-то текст"
    
    context_mock = MagicMock()
    context_mock.user_data = {'event_text_record': [1, 2, 3]}
    
    error_state = 999

    is_valid, result, record = await get_validated_event_index(update_mock, context_mock, error_state)

    assert is_valid is False
    assert result == error_state
    assert record == []

    update_mock.message.reply_text.assert_awaited_once()
    
    # Достаем позиционные (args) и именованные (kwargs) аргументы
    args, kwargs = update_mock.message.reply_text.call_args
    sent_text = args[0]
    
    assert "❌ Ошибка: введите только *число* (цифру)." in sent_text
    assert "Попробуйте еще раз (от 1 до 3):" in sent_text
    assert kwargs.get('parse_mode') == "Markdown"


# --- ТЕСТ 2: Негативный (Ввели число вне диапазона) ---
@pytest.mark.asyncio
async def test_get_validated_event_index_out_of_range():
    update_mock = AsyncMock()
    update_mock.message.text = "5"
    
    context_mock = MagicMock()
    context_mock.user_data = {'event_text_record': [1, 2, 3]}
    
    error_state = 999

    is_valid, result, record = await get_validated_event_index(update_mock, context_mock, error_state)

    assert is_valid is False
    assert result == error_state
    assert record == []

    update_mock.message.reply_text.assert_awaited_once()
    
    # Достаем позиционные (args) и именованные (kwargs) аргументы
    args, kwargs = update_mock.message.reply_text.call_args
    sent_text = args[0]
    
    assert "❌ Ошибка: события под номером 5 не существует." in sent_text
    assert "Введите число в диапазоне от 1 до 3:" in sent_text
    assert 'parse_mode' not in kwargs


# --- ТЕСТ 3: Позитивный (Ввели корректное число) ---
@pytest.mark.asyncio
async def test_get_validated_event_index_success():
    update_mock = AsyncMock()
    # Имитируем случайное нажатие пробелов пользователем
    update_mock.message.text = "  2  "
    
    context_mock = MagicMock()
    event_list = [{'id': 10}, {'id': 11}, {'id': 12}]
    context_mock.user_data = {'event_text_record': event_list}
    
    error_state = 999

    is_valid, result, record = await get_validated_event_index(update_mock, context_mock, error_state)

    # Проверяем возвращаемые значения
    assert is_valid is True
    # Ввели 2, индекс должен быть 1 (2 - 1 = 1)
    assert result == 1
    assert record == event_list

    # Убеждаемся, что бот ничего не ответил в чат (так как ошибки нет)
    update_mock.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
@patch('app.handlers.calendar_act_with_options.generate_confirm_keyboard')
async def test_confirm_to_delete_from_callback(mock_gen_keyboard: AsyncMock):
    # ТЕСТ 1: Имитируем вызов из инлайн-кнопки (CallbackQuery)
    mock_gen_keyboard.return_value = "keyboard_mock"
    
    source_mock = AsyncMock()
    # У source_mock по умолчанию есть любой атрибут, так что hasattr вернет True
    
    event_text = "📌 *Событие*: \\[10:00 - 11:00] Встреча 1\n"
    selected_date = date(2026, 10, 20)
    delete_text = ("событие № 1?", "эту заметку.")

    result = await confirm_to_delete(source_mock, event_text, selected_date, delete_text)

    # Проверяем возврат стейта
    assert result == CONFIRMING_DELETE
    
    # Проверяем, что вызвался edit_message_text, а не reply_text
    source_mock.edit_message_text.assert_awaited_once()
    source_mock.message.reply_text.assert_not_awaited()

    # Проверяем аргументы и форматирование текста
    kwargs = source_mock.edit_message_text.call_args.kwargs
    text = kwargs['text']
    
    assert "❓ *Вы уверены, что хотите удалить событие № 1?*" in text
    assert "📌 *Событие*: \\[10:00 - 11:00] Встреча 1" in text
    assert "📅 *Дата*: 20.10.2026" in text
    assert "⚠️ Это действие полностью сотрёт эту заметку." in text
    
    assert kwargs['reply_markup'] == "keyboard_mock"
    assert kwargs['parse_mode'] == "Markdown"


@pytest.mark.asyncio
@patch('app.handlers.calendar_act_with_options.generate_confirm_keyboard')
async def test_confirm_to_delete_from_text_update(mock_gen_keyboard: AsyncMock):
    # ТЕСТ 2: Имитируем вызов из текстового ввода (Update)
    mock_gen_keyboard.return_value = "keyboard_mock"
    
    source_mock = AsyncMock()
    # Жестко удаляем атрибут, чтобы hasattr(source, "edit_message_text") выдало False
    del source_mock.edit_message_text
    
    event_text = "📌 *Событие*: \\[12:00 - 13:00] Встреча 2\n"
    selected_date = date(2026, 1, 5) # Берем дату с однозначным числом месяца/дня для проверки нулей
    delete_text = ("все мероприятия?", "вообще всё.")

    result = await confirm_to_delete(source_mock, event_text, selected_date, delete_text)

    # Проверяем возврат стейта
    assert result == CONFIRMING_DELETE
    
    # Проверяем, что вызвался reply_text, так как это текстовое сообщение
    source_mock.message.reply_text.assert_awaited_once()
    
    # Проверяем форматирование (особенно работу форматирования даты с ведущими нулями: 05.01.2026)
    kwargs = source_mock.message.reply_text.call_args.kwargs
    text = kwargs['text']
    
    assert "❓ *Вы уверены, что хотите удалить все мероприятия?*" in text
    assert "📌 *Событие*: \\[12:00 - 13:00] Встреча 2" in text
    assert "📅 *Дата*: 05.01.2026" in text
    assert "⚠️ Это действие полностью сотрёт вообще всё." in text
    
    assert kwargs['reply_markup'] == "keyboard_mock"
    assert kwargs['parse_mode'] == "Markdown"



# Вспомогательный класс для имитации асинхронного QuerySet из Django ORM
class AsyncMockQuerySet:
    def __init__(self, items=None):
        self.items = items or []
        self.adelete_mock = AsyncMock()
        self.afirst_mock = AsyncMock(return_value=self.items[0] if self.items else None)

    async def __aiter__(self):
        for item in self.items:
            yield item

    async def adelete(self):
        return await self.adelete_mock()

    async def afirst(self):
        return await self.afirst_mock()

    def filter(self, *args, **kwargs):
        return self


# --- ТЕСТ 1: Обычный пользователь (не организатор и не приглашенный) ---
@pytest.mark.asyncio
@patch('app.handlers.utils.Event')
@patch('app.handlers.utils.Appointment')
async def test_notify_and_cancel_appointments_no_roles(mock_Appointment, mock_Event):
    bot_mock = AsyncMock()
    
    # Мокаем удаляемое событие
    mock_event = MagicMock()
    mock_event.id = 10
    mock_event.event_date = date(2026, 10, 20)
    mock_event.start_time = time(10, 0)
    mock_event.end_time = time(11, 0)

    # 1. Отдаем событие в первый цикл (events_to_delete)
    mock_Event.objects.filter.return_value = AsyncMockQuerySet([mock_event])
    
    # 2. Мокаем отсутствие встреч как организатор (пустой QuerySet)
    mock_Appointment.objects.filter.return_value = AsyncMockQuerySet([])
    
    # 3. Мокаем отсутствие приглашений (afirst() вернет None)
    mock_Appointment.objects.select_related.return_value.filter.return_value = AsyncMockQuerySet([])

    # ВЫЗОВ
    await notify_and_cancel_appointments(12345, 'id', 10, bot_mock)

    # ПРОВЕРКА
    # Убеждаемся, что бот никому ничего не отправлял
    bot_mock.send_message.assert_not_called()


# --- ТЕСТ 2: Пользователь - ОРГАНИЗАТОР (2 приглашенных) ---
@pytest.mark.asyncio
@patch('app.handlers.utils.Event')
@patch('app.handlers.utils.Appointment')
async def test_notify_and_cancel_appointments_as_organizer(mock_Appointment, mock_Event):
    bot_mock = AsyncMock()
    
    mock_event = MagicMock()
    mock_event.id = 10
    mock_event.title = "Супер Встреча"
    mock_event.event_date = date(2026, 10, 20)
    mock_event.start_time = time(10, 0)
    mock_event.end_time = time(11, 0)
    
    # Настраиваем логику Event.objects.filter, чтобы она возвращала разные QuerySet'ы
    # Первый раз - для цикла, второй раз - для удаления заметки ребенка
    child_delete_qs = AsyncMockQuerySet([])
    
    def event_filter_side_effect(*args, **kwargs):
        # Если фильтр вызван для организатора (ID 999) - возвращаем родительское событие
        if kwargs.get('user_id') == 999:
            return AsyncMockQuerySet([mock_event])
        
        # Если фильтр вызван для детей (ID 111 или 222) - возвращаем мок для удаления
        return child_delete_qs
    
    mock_Event.objects.filter.side_effect = event_filter_side_effect

    # Мокаем двух приглашенных детей
    mock_appt1 = AsyncMock()
    mock_appt1.invitee_id = 111
    
    mock_appt2 = AsyncMock()
    mock_appt2.invitee_id = 222

    mock_Appointment.objects.filter.return_value = AsyncMockQuerySet([mock_appt1, mock_appt2])
    
    # Юзер не ребенок, поэтому select_related (СЦЕНАРИЙ Б) возвращает пустоту
    mock_Appointment.objects.select_related.return_value.filter.return_value = AsyncMockQuerySet([])
    
    # ВЫЗОВ
    await notify_and_cancel_appointments(999, 'id', 10, bot_mock)

    # ПРОВЕРКИ СЦЕНАРИЯ А
    # 1. Проверяем, что бот отправил ровно 2 сообщения (по одному каждому ребенку)
    assert bot_mock.send_message.call_count == 2
    
    
    # Проверяем, кому ушли сообщения
    calls = bot_mock.send_message.call_args_list
    assert calls[0].kwargs['chat_id'] == 111
    assert calls[1].kwargs['chat_id'] == 222
    
    # Проверяем текст в сообщении
    assert "Организатор (ID: `999`) отменил мероприятие:" in calls[0].kwargs['text']
    assert "Супер Встреча" in calls[0].kwargs['text']

    # 2. Проверяем, что локальные копии заметок удалены дважды (Event...adelete())
    assert child_delete_qs.adelete_mock.call_count == 2
    
    # 3. Проверяем, что связи (Appointment) тоже удалились дважды
    mock_appt1.adelete.assert_awaited_once()
    mock_appt2.adelete.assert_awaited_once()


# --- ТЕСТ 3: Пользователь - РЕБЕНОК (отменяет участие) ---
@pytest.mark.asyncio
@patch('app.handlers.utils.Event')
@patch('app.handlers.utils.Appointment')
async def test_notify_and_cancel_appointments_as_child(mock_Appointment, mock_Event):
    bot_mock = AsyncMock()
    
    # Локальная заметка ребенка
    mock_event = MagicMock()
    mock_event.id = 10
    mock_event.event_date = date(2026, 10, 20)
    mock_event.start_time = None # Проверим как отрабатывает "Весь день"
    
    mock_Event.objects.filter.return_value = AsyncMockQuerySet([mock_event])
    
    # Пользователь не организатор, встреч в которых он хозяин нет
    mock_Appointment.objects.filter.return_value = AsyncMockQuerySet([])

    # Мокаем встречу, где он приглашенный
    mock_appt_as_invitee = AsyncMock()
    mock_appt_as_invitee.status = "CONFIRMED" # Только не CANCELLED
    mock_appt_as_invitee.event.user_id = 888 # ID организатора
    mock_appt_as_invitee.event.title = "Праздник"

    mock_Appointment.objects.select_related.return_value.filter.return_value = AsyncMockQuerySet([mock_appt_as_invitee])

    # ВЫЗОВ
    await notify_and_cancel_appointments(111, 'id', 10, bot_mock)

    # ПРОВЕРКИ СЦЕНАРИЯ Б
    # 1. Бот должен уведомить организатора (ID 888) один раз
    bot_mock.send_message.assert_awaited_once()
    call_kwargs = bot_mock.send_message.call_args.kwargs
    
    assert call_kwargs['chat_id'] == 888
    assert "Пользователь (ID: `111`) отменил свое участие" in call_kwargs['text']
    assert "Весь день" in call_kwargs['text'] # Проверка формата времени

    # 2. Связь (Appointment) должна быть удалена
    mock_appt_as_invitee.adelete.assert_awaited_once()


@pytest.mark.asyncio
@patch('app.handlers.calendar_delete_event.CalendarRepository.delete_events_by_filter')
async def test_del_event_on_info(mock_delete_events_by_filter: AsyncMock):
    context_mock, update_mock = MagicMock(), AsyncMock()

    mock_conn = AsyncMock()

    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn


    mock_delete_events_by_filter.return_value = 1

    context_mock.application.stats_repository.increment_metric = AsyncMock()
    context_mock.application.stats_repository.increment_user_metric = AsyncMock()

    update_mock.effective_user.id = 12345

    await del_event_on_info(context_mock, update_mock, 'id', 999)

    mock_delete_events_by_filter.assert_awaited_once_with(mock_conn, 'id', 999)

    context_mock.application.stats_repository.increment_metric.assert_awaited_once_with(
        'events_deleted', amount=1
    )
    context_mock.application.stats_repository.increment_user_metric.assert_awaited_once_with(
        12345, 'events_cancelled', 1
    )

# --- ПОЗИТИВНЫЕ СЦЕНАРИИ ---
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "column_name, db_response, expected_count",
    [
        ('id', 'DELETE 1', 1),
        ('event_date', 'DELETE 5', 5),
    ]
)
async def test_delete_events_by_filter_positive(
    column_name: str,
    db_response: str,
    expected_count: int
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
    bad_column = 'incorrect_value'

    # Оборачиваем вызов в контекстный менеджер pytest.raises
    with pytest.raises(ValueError) as exc_info:
        await CalendarRepository.delete_events_by_filter(mock_con, bad_column, 999)

    # exc_info.value содержит сам объект перехваченной ошибки
    assert str(exc_info.value) == f"Недопустимое имя столбца для удаления: {bad_column}"
    
    # Дополнительно убеждаемся, что до базы данных запрос даже не дошел
    mock_con.execute.assert_not_called()

@pytest.mark.asyncio
@patch('app.handlers.calendar_delete_event.calendar_command')
async def test_prepare_after_delete(mock_calendar_command: AsyncMock):
    context_mock, update_mock, query = MagicMock(), MagicMock(), MagicMock()

    context_mock.user_data = {
        'delete_event_id': 999,
        'event_text_record': 'text_record',
        'delete_alert_text': '🗑️ Мероприятие успешно удалено!',
        'save_data': 'save_data'
    }

    query.answer = AsyncMock()

    result: int = await prepare_after_delete(update_mock, context_mock, query)

    assert result == ConversationHandler.END

    assert context_mock.user_data['save_data'] == 'save_data'
    assert 'delete_event_id' not in context_mock.user_data
    assert 'event_text_record' not in context_mock.user_data
    assert 'delete_alert_text' not in context_mock.user_data

    query.answer.assert_awaited_once_with(text='🗑️ Мероприятие успешно удалено!')
    mock_calendar_command.assert_awaited_once_with(update_mock, context_mock)




@pytest.mark.asyncio
@patch('app.handlers.calendar_edit_flow.handle_options_with_exist_notes_in_day')
@patch('app.handlers.calendar_edit_flow.build_detailed_event_text')
@patch('app.handlers.calendar_edit_flow.CalendarRepository.get_events_by_date')
async def test_refresh_day_menu_after_edit(
    mock_get_events: AsyncMock,
    mock_build_card: MagicMock,
    mock_handle_options: AsyncMock
):
    # 1. Подготовка данных
    update_mock, context_mock = MagicMock(), MagicMock()
    update_mock.effective_user.id = 123
    update_mock.message = MagicMock()  # source будет update

    test_date = date(2026, 10, 20)
    context_mock.user_data = {
        'selected_date': test_date,
        'edit_success_status': '✅ Название успешно изменено!'
    }

    mock_conn = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = mock_conn

    # Имитируем 2 записи в базе
    mock_records = [{'id': 1}, {'id': 2}]
    mock_get_events.return_value = mock_records
    mock_build_card.side_effect = lambda records, index, numbered: f"Card {index}"
    mock_handle_options.return_value = CHOOSING_ACTION

    # 2. Вызов
    result: int = await _refresh_day_menu_after_edit(update_mock, context_mock)

    # 3. Проверки
    assert result == CHOOSING_ACTION

    # Проверка синхронизации с базой и обновления ОЗУ
    mock_get_events.assert_awaited_once_with(mock_conn, 123, test_date)
    assert context_mock.user_data['event_text_record'] == mock_records

    # Проверка, что статус успеха извлечен и удален из user_data
    assert 'edit_success_status' not in context_mock.user_data

    # Проверка отрисовки карточек для каждой записи
    assert mock_build_card.call_count == 2

    # Проверка вызова меню с итоговым текстом, кортежем даты и баннером успеха
    expected_text = "Card 0\nCard 1\n"
    expected_header = "✅ Название успешно изменено!\n\n"
    mock_handle_options.assert_awaited_once_with(
        expected_text,
        (update_mock, test_date.day, test_date.month, test_date.year),
        header=expected_header
    )


@pytest.mark.parametrize(
    "input_text, current_user_id, expected",
    [
        # Happy path: обычный ID, пробелы по краям режутся
        ("  987654321  ", 11111, (True, 987654321)),
        # Happy path: без пробелов
        ("123456789", 11111, (True, 123456789)),
        # Ошибка: не цифры
        ("abc123", 11111, (False, "❌ Telegram ID должен состоять только из цифр. Попробуйте еще раз:")),
        # Ошибка: пустая строка (после strip тоже не digit)
        ("   ", 11111, (False, "❌ Telegram ID должен состоять только из цифр. Попробуйте еще раз:")),
        # Ошибка: свой ID
        ("11111", 11111, (False, "custom_self_error")),
    ]
)
def test_validate_telegram_id_input(
    input_text: str,
    current_user_id: int,
    expected: tuple[bool, int | str]
):
    result = validate_telegram_id_input(
        input_text=input_text,
        current_user_id=current_user_id,
        self_error_msg="custom_self_error"
    )

    assert result == expected