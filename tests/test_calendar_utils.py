import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.calendar.utils import build_detailed_event_text, build_events_list_text
from app.handlers.utils import get_validated_event_index

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