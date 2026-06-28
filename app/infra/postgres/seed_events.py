import psycopg2
from datetime import date, time
from settings.config import AppSettings

settings = AppSettings()
YOUR_TELEGRAM_ID = 489090401


def seed_test_data_usual_events() -> None:

    print("Запуск заполнения тестовыми данными с учётом реформы таблицы...")

    # Переименовали details -> description и подогнали под новые типы времени
    insert_query = """
    INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    # Создаем 3 тестовых события на Июнь 2026 года под новые CHECK CONSTRAINTS
    test_events = [
        # 1. Событие на весь день
        (YOUR_TELEGRAM_ID, 'all_day', 'Поездка на дачу',
         date(2026, 6, 6), None, None, 'Шашлык машлык'),

        # 2. Событие со строгим интервалом времени
        (YOUR_TELEGRAM_ID, 'interval', 'Созвон по проекту', date(2026, 6, 18),
         time(14, 0, 0), time(15, 0, 0), 'Обсудить архитектуру бота'),

        # 3. Событие на конкретное (точное) время | Время окончания события + 30 минут от начала
        (YOUR_TELEGRAM_ID, 'exact', 'Отключить компрессор', date(
            2026, 6, 25), time(19, 30, 0), time(20, 0, 0), None)
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


def seed_test_data() -> None:

    print("Запуск заполнения тестовыми данными с учётом реформы таблицы...")

    insert_query = """
    INSERT INTO events (user_id, event_type, title, event_date, start_time, end_time, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """

    # Генерируем 11 плотных последовательных событий на 15 июня 2026 года
    test_events = []
    test_date = date(2026, 6, 15)

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
            # Убедимся, что юзер существует для Foreign Key
            cursor.execute(
                "INSERT INTO users (telegram_id) VALUES (%s) ON CONFLICT DO NOTHING;",
                (YOUR_TELEGRAM_ID,)
            )

            # Заливаем сгенерированные 11 событий
            cursor.executemany(insert_query, test_events)
            conn.commit()

    print("Успешно добавлено 11 плотных событий на 15 июня 2026 года для тестирования лимитов!")


if __name__ == "__main__":
    seed_test_data_usual_events()
    seed_test_data()
