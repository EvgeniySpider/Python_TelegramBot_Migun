from asyncpg import Record
from typing import Union, List
from datetime import time


def format_event_time(start_time: time, end_time: time) -> str:
    """Единая точка форматирования времени для всего бота."""
    # Если объекты пришли из БД или контекста как datetime.time
    st = start_time.strftime("%H:%M")
    end = end_time.strftime("%H:%M")
    return f"{st} - {end}"


def build_events_list_text(events: List[Union[Record, dict]], numbered: bool = False) -> str:
    """
    Генерирует текстовый список событий.
    Безопасно обрабатывает события на весь день (у которых start_time равен None).
    """
    raw_lines = []
    for i, el in enumerate(events):
        # 1. Проверяем, является ли событие полнодневным
        if el['start_time'] is None or el.get('event_type') == 'all_day':
            time_str = "Весь день"
        else:
            time_str = format_event_time(el['start_time'], el['end_time'])
            
        # 2. Формируем строку в зависимости от режима
        if numbered:
            # Формат для удаления: [ 1 ]  • Весь день Тестовая задача №1
            line = f"\\[ {i+1} ]  • {time_str} {el['title']}"
        else:
            # Обычный формат главного меню: • Весь день Тестовая задача №1
            line = f"• {time_str} {el['title']}"
            
        raw_lines.append(line)

    return "Запланированные дела: \n" + "\n".join(raw_lines) + "\n\n"
