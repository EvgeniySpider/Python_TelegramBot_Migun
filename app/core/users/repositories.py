from dataclasses import dataclass
from app.infra.postgres.db import Database
from datetime import datetime


@dataclass
class UserRepository:
    database: Database

    async def create_user_if_not_exists(self, user_id: int) -> None:
        current_time = datetime.now()
        current_date = current_time.date()
        
        async with self.database.connection() as conn:

            user_exists = await conn.fetchval(
                "SELECT 1 FROM users WHERE telegram_id = $1", 
                user_id
            )

            if not user_exists:
                await conn.execute(
                    "INSERT INTO users (telegram_id, registered_at) VALUES ($1, $2)",
                    user_id,
                    current_time
                )

                await conn.execute(
                    """
                    INSERT INTO events_botstatistics (date, new_users_count, calendar_clicks, 
                                                events_created_all_day, events_created_exact, 
                                                events_created_interval, events_edited, events_deleted)
                    VALUES ($1, 1, 0, 0, 0, 0, 0, 0)
                    ON CONFLICT (date) DO UPDATE 
                    SET new_users_count = events_botstatistics.new_users_count + 1
                    """,
                    current_date
                )