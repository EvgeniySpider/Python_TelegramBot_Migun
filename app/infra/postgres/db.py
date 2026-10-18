from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from pydantic import PostgresDsn, Secret


class Database:
    def __init__(self, dsn: Secret[PostgresDsn]):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        dns_string = str(self._dsn.get_secret_value())

        self._pool = await asyncpg.create_pool(
            dsn=dns_string,
            timeout=5.0,  # Ждать освобождения коннекта максимум 5 секунд
        )

    async def shutdown(self) -> None:
        if self._pool:
            await self._pool.close()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy, None]:
        """Асинхронный контекстный менеджер для выдачи соединения из пула."""
        if self._pool is None:
            raise Exception("Pool has not been created")

        async with self._pool.acquire() as connection:
            yield connection
