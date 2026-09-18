from dataclasses import dataclass
from app.infra.postgres.db import Database
from datetime import datetime


@dataclass
class UserRepository:
    database: Database

    async def create_user_if_not_exists(self, user_id: int) -> None:
        current_time = datetime.now()
        async with self.database.connection() as conn:
            await conn.execute(
                "INSERT INTO users (telegram_id, registered_at) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                user_id,
                current_time
            )
