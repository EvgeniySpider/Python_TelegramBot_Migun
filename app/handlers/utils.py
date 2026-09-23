from telegram import Update
from telegram.ext import ContextTypes
import datetime
from typing import Optional

from events.models import Appointment


async def get_validated_event_index(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    error_state: int
) -> tuple[bool, int, list]:
    """
    Извлекает данные из контекста, валидирует ввод номера события и вычисляет индекс.
    Возвращает (is_valid, result, event_text_record).
    - Если False: result = error_state (STATE для возврата).
    - Если True: result = index_record (индекс для списка), event_text_record = сам список.
    """
    event_text_record = context.user_data.get('event_text_record', [])
    event_count = len(event_text_record)
    user_text = update.message.text.strip()

    if not user_text.isdigit():
        await update.message.reply_text(
            f"❌ Ошибка: введите только *число* (цифру).\n"
            f"Попробуйте еще раз (от 1 до {event_count}):",
            parse_mode="Markdown"
        )
        return False, error_state, []

    chosen_number = int(user_text)
    if chosen_number < 1 or chosen_number > event_count:
        await update.message.reply_text(
            f"❌ Ошибка: события под номером {chosen_number} не существует.\n"
            f"Введите число в диапазоне от 1 до {event_count}:"
        )
        return False, error_state, []

    return True, chosen_number - 1, event_text_record




async def is_user_invitee_for_event(
    user_id: int,
    selected_date: datetime.date,
    start_time: Optional[datetime.time],
    end_time: Optional[datetime.time]
) -> bool:
    """
    Проверяет, является ли пользователь приглашенным на мероприятие (ребенком),
    сопоставляя дату и время события организатора.
    """

    return await Appointment.objects.filter(
        invitee_id=user_id,
        event__event_date=selected_date,
        event__start_time=start_time,
        event__end_time=end_time
    ).aexists()