import asyncpg
from app.core.calendar.repositories import CalendarRepository
from events.models import Event, Appointment


class CalendarService:
    """Бизнес-логика для работы с календарем."""

    @staticmethod
    async def get_user_busy_days(conn: asyncpg.Connection, user_id: int, year: int, month: int) -> dict[int, str]:
        """
        Получает из репозитория список дней со статусами занятости
        и упаковывает их в словарь {day: status} для моментального поиска.
        """
        # Дёргаем жесткую логику условной агрегации из репозитория
        busy_days_records = await CalendarRepository.get_busy_days(conn, user_id, year, month)

        # Собираем словарь: ключ — день (int), значение — статус 'full' или 'partial' (str)
        return {row["day"]: row["status"] for row in busy_days_records}


async def check_user_availability(invitee_id: int, target_event: Event) -> bool:
    """
    Проверяет, занят ли пользователь в дату и время целевого события.
    Возвращает True, если время ЗАНЯТО (есть пересечения), и False, если СВОБОДЕН.
    """
    # 1. Запрашиваем личные события гостя на эту дату
    own_events = [
        e async for e in Event.objects.filter(
            user_id=invitee_id, 
            event_date=target_event.event_date
        )
    ]
    
    # 2. Запрашиваем подтвержденные встречи гостя на эту дату
    confirmed_appointments = [
        a async for a in Appointment.objects.select_related('event').filter(
            invitee_id=invitee_id,
            status=Appointment.Status.CONFIRMED,
            event__event_date=target_event.event_date
        )
    ]
    # Извлекаем объекты событий из встреч
    invited_events = [app.event for app in confirmed_appointments]
    
    # Объединяем расписание гостя на день
    all_guest_events = own_events + invited_events
    
    # 3. Алгоритм проверки временных пересечений
    for guest_event in all_guest_events:
        # A. Если хотя бы одно из событий "на весь день" — это 100% конфликт
        if target_event.event_type == 'all_day' or guest_event.event_type == 'all_day':
            return True
            
        # B. Пересечение точного времени (exact) и интервала (interval)
        if target_event.event_type == 'exact' and guest_event.event_type == 'interval':
            if guest_event.start_time <= target_event.start_time < guest_event.end_time:
                return True
        if target_event.event_type == 'interval' and guest_event.event_type == 'exact':
            if target_event.start_time <= guest_event.start_time < target_event.end_time:
                return True
                
        # C. Пересечение двух точных времен
        if target_event.event_type == 'exact' and guest_event.event_type == 'exact':
            if target_event.start_time == guest_event.start_time:
                return True
                
        # D. Пересечение двух интервалов (Условие: Start_1 < End_2 И Start_2 < End_1)
        if target_event.event_type == 'interval' and guest_event.event_type == 'interval':
            if target_event.start_time < guest_event.end_time and guest_event.start_time < target_event.end_time:
                return True
                
    return False