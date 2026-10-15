from collections.abc import Sequence
from datetime import time

from asyncpg import Record
from telegram.helpers import escape_markdown


def format_event_time(start_time: time, end_time: time) -> str:
    """Единая точка форматирования времени для всего бота."""
    # Если объекты пришли из БД или контекста как datetime.time
    st = start_time.strftime("%H:%M")
    end = end_time.strftime("%H:%M")
    return f"{st} - {end}"


def build_events_list_text(events: list[Record | dict], numbered: bool = False) -> str:
    """
    Генерирует текстовый список событий.
    Безопасно обрабатывает события на весь день (у которых start_time равен None).
    """
    raw_lines = []
    for i, el in enumerate(events):
        # Экранируем название от спецсимволов Markdown
        safe_title = escape_markdown(str(el["title"]), version=1)

        if el["start_time"] is None or el.get("event_type") == "all_day":
            time_str = "(весь день)"
        else:
            time_str = format_event_time(el["start_time"], el["end_time"])

        if numbered:
            line = f"\\[ {i + 1} ]  • {time_str} {safe_title}"
        else:
            line = (
                f"• {safe_title} {time_str}"
                if time_str == "(весь день)"
                else f"• {time_str} {safe_title}"
            )
        raw_lines.append(line)

    return "Запланированные дела: \n" + "\n".join(raw_lines) + "\n\n"


def build_detailed_event_text(
    events: Sequence[Record | dict],
    index: int = 0,
    numbered: bool = False,
    is_show_date: bool = False,
) -> str:
    """
    Генерирует детальный текстовый профиль (карточку) конкретного события для просмотра и изменения.
    """
    if not events or index >= len(events):
        return "❌ Ошибка: Событие не найдено.\n\n"

    el = events[index]

    time_str = (
        "Весь день"
        if el["start_time"] is None
        else format_event_time(el["start_time"], el["end_time"])
    )

    raw_title = el.get("title", "")
    safe_title = escape_markdown(str(raw_title), version=1)

    raw_desc = el.get("description")
    safe_desc = escape_markdown(str(raw_desc), version=1) if raw_desc else "Не указано"

    # Обработка флага публичности
    is_public = el.get("is_public", False)
    status_str = "👁 Публичное (Видно другим)" if is_public else "🔒 Приватное (Только вы)"

    header = (
        f"📝 *Просмотр события №{index + 1}*" if numbered else "📝 *Детальный просмотр события*"
    )

    card_lines = [
        header,
        f"📌 *Название*: {safe_title}",
        f"⏳ *Время*: {time_str}",
        f"📖 *Описание*: {safe_desc}",
        f"🛡 *Доступ*: {status_str}\n",
    ]

    # Если нужен вывод даты, вставляем её на 2-ю строчку (индекс 1)
    if is_show_date:
        date_str = el["event_date"].strftime("%d.%m.%Y")
        card_lines.insert(1, f"📅 *Дата*: {date_str}")

    return "\n".join(card_lines)


def normalize_time_str(t_str: str) -> str:
    if ":" not in t_str:
        return f"{int(t_str):02d}:00"
    else:
        hours, minutes = t_str.split(":")
        return f"{int(hours):02d}:{minutes}"
