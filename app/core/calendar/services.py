import asyncpg
from app.core.calendar.repositories import CalendarRepository


class CalendarService:
    """Бизнес-логика для работы с календарем."""

    @staticmethod
    async def get_user_busy_days(conn: asyncpg.Connection, user_id: int, year: int, month: int) -> set[int]:
        """
        Получает из репозитория список дней с событиями и 
        превращает их в уникальное множество (set) для быстрой проверки.
        """
        # Дёргаем жесткую логику из репозитория
        busy_days_list = await CalendarRepository.get_busy_days(conn, user_id, year, month)
        
        # Превращаем list в set ради перфекционизма и скорости поиска
        return set(busy_days_list)