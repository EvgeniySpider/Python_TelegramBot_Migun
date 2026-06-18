import psycopg2
from settings.config import AppSettings


settings = AppSettings()

# 1. Запрос для создания таблицы пользователей
CREATE_USERS_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# 2. Запрос для создания таблицы событий календаря (Тип 1, 2, 3)
CREATE_EVENTS_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- 'purchase', 'meeting', 'custom'
    title TEXT NOT NULL,
    event_date DATE NOT NULL,
    start_time TIME NULL,
    end_time TIME NULL,
    details TEXT NULL,
    
    -- Жесткая связь: нельзя создать событие для несуществующего пользователя
    CONSTRAINT fk_event_user FOREIGN KEY (user_id) REFERENCES users (telegram_id) ON DELETE CASCADE
);
"""


def create_tables() -> None:
    """Функция для разовой инициализации таблиц при старте базы данных."""
    print("Запуск инициализации таблиц БД...")

    with psycopg2.connect(settings.secret_dsn.get_secret_value()) as conn:
        with conn.cursor() as cursor:
            # Создаем сначала пользователей
            cursor.execute(CREATE_USERS_TABLE_QUERY)
            print("Таблица 'users' успешно проверена / создана.")

            # Создаем таблицу событий
            cursor.execute(CREATE_EVENTS_TABLE_QUERY)
            print("Таблица 'events' успешно проверена / создана.")

            conn.commit()

    print("Все таблицы успешно подготовлены в базе данных!")


if __name__ == "__main__":
    create_tables()
