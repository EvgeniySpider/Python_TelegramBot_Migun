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
            time_str = "(весь день)"
        else:
            time_str = format_event_time(el['start_time'], el['end_time'])

        # 2. Формируем строку в зависимости от режима
        if numbered:
            # Формат для удаления: [ 1 ]  • Весь день Тестовая задача №1
            line = f"\\[ {i+1} ]  • {time_str} {el['title']}"
        else:
            # Обычный формат главного меню: • Весь день Тестовая задача №1
            line = f"• {el['title']} {time_str}" if time_str == '(весь день)' \
                else f"• {time_str} {el['title']}"

        raw_lines.append(line)

    return "Запланированные дела: \n" + "\n".join(raw_lines) + "\n\n"


def build_detailed_event_text(
    events: List[Union[Record, dict]],
    index: int = 0,
    numbered: bool = False,
    is_show_date: bool = False
) -> str:
    """
    Генерирует детальный текстовый профиль (карточку) конкретного события для просмотра и изменения.
    """
    if not events or index >= len(events):
        return "❌ Ошибка: Событие не найдено.\n\n"

    el = events[index]

    time_str = 'Весь день' if el['start_time'] is None else \
        format_event_time(el['start_time'], el['end_time'])

    desc_str = el.get('description') or "Не указано"

    # Обработка флага публичности
    is_public = el.get('is_public', False)
    status_str = "👁 Публичное (Видно другим)" if is_public else "🔒 Приватное (Только вы)"

    header = f"📝 *Просмотр события №{index + 1}*" if numbered else "📝 *Детальный просмотр события*"

    card_lines = [
        header,
        f"📌 *Название*: {el['title']}",
        f"⏳ *Время*: {time_str}",
        f"📖 *Описание*: {desc_str}",
        f"🛡 *Доступ*: {status_str}\n"
    ]

    # Если нужен вывод даты, вставляем её на 2-ю строчку (индекс 1)
    if is_show_date:
        date_str = el['event_date'].strftime('%d.%m.%Y')
        card_lines.insert(1, f"📅 *Дата*: {date_str}")

    return "\n".join(card_lines)

def normalize_time_str(t_str: str) -> str:
    if ":" not in t_str:
        return f"{int(t_str):02d}:00"
    else:
        hours, minutes = t_str.split(":")
        return f"{int(hours):02d}:{minutes}"