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
    Если numbered=True, то вместо '• [Время]' выведет '[ 1 ]   Время'
    """
    from app.core.calendar.utils import format_event_time  # локальный импорт во избежание циклов

    raw_lines = []
    for i, el in enumerate(events):
        # 1. Определяем время
        if el['start_time'] is None:
            time_str = "(весь день)"
        else:
            time_str = f"{format_event_time(el['start_time'], el['end_time'])}"

        # 2. Формируем префикс: либо маркер, либо индекс для удаления
        if numbered:
            prefix = f"[ {i+1} ]    "
            time_clean = time_str.replace("\\[", "").replace("\\]", "")
            line = f"{prefix}{time_clean} {el['title']}"
        else:
            prefix = "• "
            line = f"{prefix}{time_str} {el['title']}"

        raw_lines.append(line)  # Вот теперь строго по ГОСТу

    return "\n".join(raw_lines)
