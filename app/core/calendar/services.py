import asyncpg

from app.core.calendar.repositories import CalendarRepository
from events.models import Event


class CalendarService:
    """Бизнес-логика для работы с календарем."""

    @staticmethod
    async def get_user_busy_days(
        conn: asyncpg.Connection, user_id: int, year: int, month: int
    ) -> dict[int, str]:
        """
        Получает из репозитория список дней со статусами занятости
        и упаковывает их в словарь {day: status} для моментального поиска.
        """
        # Дёргаем жесткую логику условной агрегации из репозитория
        busy_days_records = await CalendarRepository.get_busy_days(conn, user_id, year, month)

        # Собираем словарь: ключ — день (int), значение — статус 'full' или 'partial' (str)
        return {row["day"]: row["status"] for row in busy_days_records}


async def check_user_availability(invitee_id: int, target_event: Event) -> bool:
    """
    Проверяет, занят ли пользователь в дату и время целевого события.
    Возвращает True, если время ЗАНЯТО (есть пересечения), и False, если СВОБОДЕН.
    """
    # 1. Запрашиваем ВСЕ события гостя на эту дату (и личные, и принятые встречи)
    guest_events = [
        e
        async for e in Event.objects.filter(user_id=invitee_id, event_date=target_event.event_date)
    ]

    # 2. Универсальный алгоритм проверки временных пересечений
    for guest_event in guest_events:
        # A. Если хотя бы одно из событий "на весь день" — это 100% конфликт
        if target_event.event_type == "all_day" or guest_event.event_type == "all_day":
            return True

        # B. Универсальная проверка пересечения двух интервалов (включая exact)
        if (
            target_event.start_time < guest_event.end_time
            and guest_event.start_time < target_event.end_time
        ):
            return True

    return False
