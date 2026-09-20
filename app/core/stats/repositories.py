from datetime import date
from typing import Literal, get_args
from app.infra.postgres.db import Database

# Белый список колонок, чтобы защититься от SQL-инъекций
MetricColumn = Literal[
    'new_users_count',
    'calendar_clicks',
    'events_created_all_day',
    'events_created_exact',
    'events_created_interval',
    'events_edited',
    'events_deleted'
]

ALLOWED_METRICS: tuple[str] = get_args(MetricColumn)

class StatsRepository:
    def __init__(self, db: Database):
        self.db: Database = db

    async def increment_metric(self, metric_name: MetricColumn, amount: int = 1) -> None:
        if metric_name not in ALLOWED_METRICS:
            raise ValueError(f"Недопустимая метрика: {metric_name}")

        today = date.today()

        query = f"""
            INSERT INTO events_botstatistics (
                date, new_users_count, calendar_clicks, 
                events_created_all_day, events_created_exact, 
                events_created_interval, events_edited, events_deleted
            )
            VALUES ($1, 0, 0, 0, 0, 0, 0, 0)
            ON CONFLICT (date) DO UPDATE 
            SET {metric_name} = events_botstatistics.{metric_name} + $2
        """

        async with self.db.connection() as conn:
            await conn.execute(query, today, amount)





