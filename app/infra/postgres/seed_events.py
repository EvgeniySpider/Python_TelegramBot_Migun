import psycopg2
from datetime import date
from settings.config import AppSettings

settings = AppSettings()

def seed_test_data() -> None:
    # ПОДСТАВЬ СВОЙ РЕАЛЬНЫЙ ID СЮДА
    YOUR_TELEGRAM_ID = 489090401  

    print("Запуск заполнения тестовыми данными...")

    insert_query = """
    INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, details)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    # Создаем 3 тестовых события на Июнь 2026 года
    test_events = [
        (YOUR_TELEGRAM_ID, 'purchase', 'Купить продукты в Ленте', date(2026, 6, 6), None, None, 'Молоко, хлеб, сыр'),
        (YOUR_TELEGRAM_ID, 'meeting', 'Собзвон по проекту', date(2026, 6, 18), '14:00:00', '15:00:00', 'Обсудить архитектуру'),
        (YOUR_TELEGRAM_ID, 'custom', 'Погулять долго с Греем', date(2026, 6, 25), None, None, 'Парк победы')
    ]

    with psycopg2.connect(settings.secret_dsn.get_secret_value()) as conn:
        with conn.cursor() as cursor:
            # Сначала убедимся, что такой пользователь зарегистрирован, 
            # иначе упадет ошибка Foreign Key Constraint
            cursor.execute(
                "INSERT INTO users (telegram_id) VALUES (%s) ON CONFLICT DO NOTHING;", 
                (YOUR_TELEGRAM_ID,)
            )
            
            # Заливаем события
            cursor.executemany(insert_query, test_events)
            conn.commit()

    print("Тестовые события на Июнь 2026 года успешно добавлены (6, 18, 25 числа)!")

if __name__ == "__main__":
    seed_test_data()