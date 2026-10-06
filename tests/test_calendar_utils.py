import datetime
from datetime import date, time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


from app.core.calendar.utils import build_detailed_event_text, build_events_list_text
from app.handlers.calendar_act_with_options import confirm_to_delete
from app.handlers.states import CONFIRMING_DELETE
from app.handlers.utils import get_validated_event_index, notify_and_cancel_appointments


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



