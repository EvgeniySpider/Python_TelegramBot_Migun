import asyncpg
from typing import List
import datetime


class CalendarRepository:
    """Слой работы с базой данных для модуля календаря."""

    @staticmethod
    async def get_busy_days(
        conn: asyncpg.Connection,
        user_id: int,
        year: int,
        month: int
    ) -> List[int]:
        """
        Вытаскивает из БД список дней месяца, на которые у пользователя запланированы события.
        Возвращает список чистых чисел (дней), например: [6, 18, 25].
        """
        query = """
            SELECT EXTRACT(DAY FROM event_date)::INTEGER AS day
            FROM events
            WHERE user_id = $1 
              AND EXTRACT(YEAR FROM event_date) = $2
              AND EXTRACT(MONTH FROM event_date) = $3;
        """

        # Выполняем асинхронный запрос. fetch returns Record объекты.
        rows = await conn.fetch(query, user_id, year, month)

        # Достаем из каждой строки поле 'day' и упаковываем в обычный список чисел
        return [row["day"] for row in rows]

    @staticmethod
    async def get_events_by_date(
        conn: asyncpg.Connection,
        user_id: int,
        event_date: datetime.date
    ) -> List[asyncpg.Record]:
        """
        Вытаскивает все события пользователя на конкретную дату.
        Возвращает список Record-объектов со всеми полями.
        """
        query = """
            SELECT title, start_time, end_time, event_type
            FROM events
            WHERE user_id = $1 AND event_date = $2
            ORDER BY start_time NULLS FIRST;
        """
        # Возвращаем «сырые» записи из базы
        return await conn.fetch(query, user_id, event_date)
