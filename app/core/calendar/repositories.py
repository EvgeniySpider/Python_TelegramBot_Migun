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
    ) -> List[asyncpg.Record]:
        """
        Вытаскивает из БД список дней месяца с их статусом занятости ('full' или 'partial').
        """
        query = """
            SELECT 
                EXTRACT(DAY FROM event_date)::INTEGER AS day,
                CASE 
                    WHEN COUNT(*) FILTER (WHERE event_type = 'all_day') > 0 
                         OR SUM(end_time - start_time) >= INTERVAL '24 hours' THEN 'full'
                    ELSE 'partial'
                END AS status
            FROM events
            WHERE user_id = $1 
              AND EXTRACT(YEAR FROM event_date) = $2
              AND EXTRACT(MONTH FROM event_date) = $3
            GROUP BY event_date;
        """

        # Выполняем асинхронный запрос. fetch возвращает Record-объекты.
        return await conn.fetch(query, user_id, year, month)

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
            SELECT id, title, start_time, end_time, event_type
            FROM events
            WHERE user_id = $1 AND event_date = $2
            ORDER BY start_time NULLS FIRST;
        """
        # Возвращаем «сырые» записи из базы
        return await conn.fetch(query, user_id, event_date)

    @staticmethod
    async def has_time_conflict(
        conn, 
        user_id: int, 
        event_date:datetime.date, 
        start_time:datetime.time, 
        end_time:datetime.time
    ) -> bool:
        """
        Проверяет наличие конфликтов (пересечений) времени для новых событий.
        Ищет пересечения среди существующих записей типов 'interval' и 'exact'.
        """
        query = """
            WITH target_events AS (
                SELECT start_time, end_time 
                FROM events 
                WHERE user_id = $1 
                  AND event_date = $2
                  AND event_type IN ('interval', 'exact')
            )
            SELECT EXISTS (
                SELECT 1 
                FROM target_events
                WHERE $3::TIME < end_time 
                  AND $4::TIME > start_time
            );
        """
        return await conn.fetchval(query, user_id, event_date, start_time, end_time)