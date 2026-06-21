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

# 2. Запрос для создания таблицы событий календаря
CREATE_EVENTS_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    
    -- 3 временных формата с жестким CHECK
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('all_day', 'interval', 'exact')), 
    
    title VARCHAR(255) NOT NULL,
    
    -- ТУТ БУДЕТ ХРАНИТЬСЯ ДОП. ИНФОРМАЦИЯ ОТ ПОЛЬЗОВАТЕЛЯ ДЛЯ СОБЫТИЯ
    description TEXT NULL, 
    
    event_date DATE NOT NULL,
    start_time TIME NULL,
    end_time TIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
