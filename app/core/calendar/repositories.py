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
            SELECT id, title, description, start_time, end_time, event_type, event_date
            FROM events
            WHERE user_id = $1 AND event_date = $2
            ORDER BY start_time NULLS FIRST;
        """
        # Возвращаем «сырые» записи из базы
        return await conn.fetch(query, user_id, event_date)

    @staticmethod
    async def has_time_conflict(
        conn: asyncpg.Connection,
        user_id: int,
        event_date: datetime.date,
        start_time: datetime.time,
        end_time: datetime.time,
        exclude_event_id: int | None = None
    ) -> bool:
        """
        Проверяет наличие конфликтов (пересечений) времени для событий.
        При редактировании принимает exclude_event_id, чтобы не конфликтовать с самим собой.
        """
        query = """
            WITH target_events AS (
                SELECT start_time, end_time 
                FROM events 
                WHERE user_id = $1 
                AND event_date = $2
                AND event_type IN ('interval', 'exact')
                -- Если $5 (exclude_event_id) передан, исключаем эту запись. 
                -- Если он равен NULL, условие ($5 IS NULL) вернет True и фильтр не сработает.
                AND ($5::INT IS NULL OR id != $5::INT)
            )
            SELECT EXISTS (
                SELECT 1 
                FROM target_events
                WHERE $3::TIME < end_time 
                AND $4::TIME > start_time
            );
        """
        return await conn.fetchval(query, user_id, event_date, start_time, end_time, exclude_event_id)

    @staticmethod
    async def delete_events_by_filter(
        conn: asyncpg.Connection,
        column_name: str,  # Сюда передаем строго строку "id" или "event_date"
        # Сюда передаем конкретный int (ID) или datetime.date
        value
    ):
        # Валидация для защиты от SQL-инъекций (перфекционизм и безопасность!)
        if column_name not in ('id', 'event_date'):
            raise ValueError(
                f"Недопустимое имя столбца для удаления: {column_name}")

        # Формируем строку запроса динамически, подставляя имя столбца безопасным путем
        query = f'''
            DELETE FROM events
            WHERE {column_name} = $1;
        '''
        await conn.execute(query, value)
