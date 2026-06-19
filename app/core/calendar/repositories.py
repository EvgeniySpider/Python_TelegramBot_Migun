import asyncpg
from typing import List


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