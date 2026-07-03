import psycopg2
from datetime import time, datetime
from settings.config import AppSettings

settings = AppSettings()
YOUR_TELEGRAM_ID = 489090401


def get_current_year_and_month() -> tuple:
    """Вспомогательная функция: возвращает текущий год и месяц."""
    now = datetime.now()
    return now.year, now.month


def seed_test_data_usual_events() -> None:
    print("Запуск заполнения тестовыми данными (фиксированные дни 6, 18, 25)...")

    insert_query = """
    INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    year, month = get_current_year_and_month()

    # Жестко фиксируем дни, чтобы исключить любые конфликты
    day_all_day = 6
    day_interval = 18
    day_exact = 25

    test_events = [
        # 1. Событие на весь день (6 число)
        (YOUR_TELEGRAM_ID, 'all_day', 'Поездка на дачу',
         datetime(year, month, day_all_day).date(), None, None, 'Шашлык машлык'),

        # 2. Событие со строгим интервалом времени (18 число)
        (YOUR_TELEGRAM_ID, 'interval', 'Созвон по проекту',
         datetime(year, month, day_interval).date(), time(14, 0, 0), time(15, 0, 0), 'Обсудить архитектуру бота'),

        # 3. Второе событие со строгим интервалом времени (18 число)
        (YOUR_TELEGRAM_ID, 'interval', 'Созвон по проекту',
         datetime(year, month, day_interval).date(), time(9, 0, 0), time(10, 0, 0), 'Погулять с хорошим мальчиком'),

        # 4. Событие на конкретное (точное) время (25 число)
        (YOUR_TELEGRAM_ID, 'exact', 'Отключить компрессор',
         datetime(year, month, day_exact).date(), time(19, 30, 0), time(20, 0, 0), None)
    ]

    with psycopg2.connect(settings.secret_dsn.get_secret_value()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (telegram_id) VALUES (%s) ON CONFLICT DO NOTHING;",
                (YOUR_TELEGRAM_ID,)
            )
            cursor.executemany(insert_query, test_events)
            conn.commit()

    print(
        f"Тестовые события успешно добавлены на фиксированные числа: {day_all_day}, {day_interval}, {day_exact} текущего месяца!")


def seed_test_data() -> None:
    insert_query = """
    INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    year, month = get_current_year_and_month()

    # Плотный день для теста лимитов (11 задач) жестко сажаем на 15 число
    limit_test_day = 15
    test_date = datetime(year, month, limit_test_day).date()

    print(
        f"Генерация 11 плотных последовательных событий на фиксированный день лимитов: {test_date}...")

    test_events = []
    for i in range(11):
        start_hour = 8 + i
        end_hour = start_hour + 1

        event_tuple = (
            YOUR_TELEGRAM_ID,
            'interval',
            f'Тестовая задача №{i+1}',
            test_date,
            time(start_hour, 0, 0),
            time(end_hour, 0, 0),
            f'Описание для задачи {i+1}'
        )
        test_events.append(event_tuple)

    with psycopg2.connect(settings.secret_dsn.get_secret_value()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (telegram_id) VALUES (%s) ON CONFLICT DO NOTHING;",
                (YOUR_TELEGRAM_ID,)
            )
            cursor.executemany(insert_query, test_events)
            conn.commit()

    print(
        f"Успешно добавлено 11 плотных событий для тестирования лимитов на {test_date}!")


if __name__ == "__main__":
    seed_test_data_usual_events()
    seed_test_data()
