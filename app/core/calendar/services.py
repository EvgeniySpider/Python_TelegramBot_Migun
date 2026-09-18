import asyncpg
from app.core.calendar.repositories import CalendarRepository


class CalendarService:
    """Бизнес-логика для работы с календарем."""

    @staticmethod
    async def get_user_busy_days(conn: asyncpg.Connection, user_id: int, year: int, month: int) -> dict[int, str]:
        """
        Получает из репозитория список дней со статусами занятости
        и упаковывает их в словарь {day: status} для моментального поиска.
        """
        # Дёргаем жесткую логику условной агрегации из репозитория
        busy_days_records = await CalendarRepository.get_busy_days(conn, user_id, year, month)

        # Собираем словарь: ключ — день (int), значение — статус 'full' или 'partial' (str)
        return {row["day"]: row["status"] for row in busy_days_records}
