from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.users.repositories import UserRepository


@pytest.mark.asyncio
async def test_create_user_if_not_exists_user_already_in_db():
    # 1. ПОДГОТОВКА МОКА БАЗЫ ДАННЫХ
    mock_db = MagicMock()

    # Создаем мок самого соединения (conn)
    mock_conn = AsyncMock()
    # Настраиваем ответ от SELECT 1 FROM users... (возвращаем 1, будто юзер найден)
    mock_conn.fetchval.return_value = 1

    # Магия для подмены 'async with self.database.connection() as conn'
    mock_db.connection.return_value.__aenter__.return_value = mock_conn

    # 2. ИНИЦИАЛИЗАЦИЯ РЕПОЗИТОРИЯ
    repository = UserRepository(database=mock_db)

    # 3. ВЫЗОВ МЕТОДА
    await repository.create_user_if_not_exists(user_id=123456789)

    # 4. ПРОВЕРКИ
    # Проверяем, что был сделан ровно один SELECT запрос
    mock_conn.fetchval.assert_called_once()
    assert "SELECT 1 FROM users WHERE telegram_id = $1" in mock_conn.fetchval.call_args.args[0]

    # ГЛАВНАЯ ПРОВЕРКА: так как юзер найден, ни одного INSERT быть не должно!
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_create_user_if_not_exists():
    mock_db = MagicMock()

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = None
    mock_conn.execute

    mock_db.connection.return_value.__aenter__.return_value = mock_conn

    repository = UserRepository(database=mock_db)

    await repository.create_user_if_not_exists(user_id=123456789)

    # Вызов conn.fetchval
    mock_conn.fetchval.assert_called_once()
    assert "SELECT 1 FROM users WHERE telegram_id = $1" in mock_conn.fetchval.call_args.args[0]

    # Убеждаемся, что INSERT-ов было ровно 2
    assert mock_conn.execute.call_count == 2

    # Достаем историю вызовов
    call_1, call_2 = mock_conn.execute.call_args_list

    # Разбираем первый вызов (добавление юзера)
    args_1 = call_1.args
    assert "INSERT INTO users" in args_1[0]
    assert args_1[1] == 123456789  # проверяем переданный telegram_id

    # Разбираем второй вызов (статистика)
    args_2 = call_2.args
    assert "INSERT INTO events_botstatistics" in args_2[0]
