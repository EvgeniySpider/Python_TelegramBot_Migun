import psycopg2
from datetime import date, time
from settings.config import AppSettings

settings = AppSettings()

def seed_test_data() -> None:
    # Твой реальный ID
    YOUR_TELEGRAM_ID = 489090401 

    print("Запуск заполнения тестовыми данными с учётом реформы таблицы...")

    # Переименовали details -> description и подогнали под новые типы времени
    insert_query = """
    INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    # Создаем 3 тестовых события на Июнь 2026 года под новые CHECK CONSTRAINTS
    test_events = [
        # 1. Событие на весь день
        (YOUR_TELEGRAM_ID, 'all_day', 'Купить продукты в Ленте', date(2026, 6, 6), None, None, 'Молоко, хлеб, сыр'),
        
        # 2. Событие со строгим интервалом времени
        (YOUR_TELEGRAM_ID, 'interval', 'Созвон по проекту', date(2026, 6, 18), time(14, 0, 0), time(15, 0, 0), 'Обсудить архитектуру бота'),
        
        # 3. Событие на конкретное (точное) время
        (YOUR_TELEGRAM_ID, 'exact', 'Погулять долго с Греем', date(2026, 6, 25), time(19, 30, 0), None, 'Парк победы, взять мячик')
    ]

    with psycopg2.connect(settings.secret_dsn.get_secret_value()) as conn:
        with conn.cursor() as cursor:
            # Убедимся, что юзер существует для Foreign Key
            cursor.execute(
                "INSERT INTO users (telegram_id) VALUES (%s) ON CONFLICT DO NOTHING;", 
                (YOUR_TELEGRAM_ID,)
            )
            
            # Заливаем новые структурированные события
            cursor.executemany(insert_query, test_events)
            conn.commit()

    print("Тестовые события на Июнь 2026 года успешно добавлены (6, 18, 25 числа)!")

if __name__ == "__main__":
    seed_test_data()