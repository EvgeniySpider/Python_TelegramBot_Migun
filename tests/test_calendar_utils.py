import datetime

from app.core.calendar.utils import build_detailed_event_text, build_events_list_text

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
    