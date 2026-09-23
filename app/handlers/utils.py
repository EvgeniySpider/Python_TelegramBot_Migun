from telegram import Update
from telegram.ext import ContextTypes
import datetime
from typing import Optional
from typing import Any
from telegram.ext import ExtBot

from events.models import Appointment, Event


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


async def notify_and_cancel_appointments(user_id: int, column_name: str, value: Any, bot: ExtBot) -> None:
    """
    Ищет удаляемые события пользователя и обрабатывает связанные встречи:
    - Если юзер организатор -> удаляет приглашения и копии у детей, уведомляет детей.
    - Если юзер ребенок -> удаляет свое приглашение, уведомляет организатора.
    """
    if column_name == 'id':
        events_to_delete = Event.objects.filter(id=value, user_id=user_id)
    elif column_name == 'event_date':
        events_to_delete = Event.objects.filter(event_date=value, user_id=user_id)
    else:
        return
    
    async for local_event in events_to_delete:
        date_str = local_event.event_date.strftime("%d.%m.%Y")
        time_str = f"{local_event.start_time.strftime('%H:%M')} - {local_event.end_time.strftime('%H:%M')}" if local_event.start_time else "Весь день"

        # ==========================================
        # СЦЕНАРИЙ А: Пользователь — ОРГАНИЗАТОР
        # ==========================================
        # Ищем все встречи, привязанные к этому конкретному событию
        hosted_appointments = Appointment.objects.filter(event_id=local_event.id)
        
        # Если такие есть, значит мы удаляем оригинал
        async for appt in hosted_appointments:
            invitee_id = appt.invitee_id
            
            # Находим и удаляем локальную копию в календаре ребенка.
            # aexists/afirst не нужны, метод adelete() на QuerySet удалит всё сам одним SQL-запросом
            await Event.objects.filter(
                user_id=invitee_id,
                event_date=local_event.event_date,
                start_time=local_event.start_time,
                end_time=local_event.end_time
            ).adelete()
            
            # Удаляем саму запись о встрече
            await appt.adelete()
            
            msg = (
                f"❌ *Отмена встречи*\n\n"
                f"Организатор (ID: `{user_id}`) отменил мероприятие:\n"
                f"📌 *Событие*: {local_event.title}\n"
                f"📅 *Дата*: {date_str}\n"
                f"⏰ *Время*: {time_str}"
            )
            try:
                await bot.send_message(chat_id=invitee_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления приглашённому {invitee_id}: {e}")

        # ==========================================
        # СЦЕНАРИЙ Б: Пользователь — РЕБЕНОК (приглашенный)
        # ==========================================
        appt_as_invitee = await Appointment.objects.select_related('event').filter(
            invitee_id=user_id,
            event__event_date=local_event.event_date,
            event__start_time=local_event.start_time,
            event__end_time=local_event.end_time
        ).afirst()

        if appt_as_invitee and appt_as_invitee.status != Appointment.Status.CANCELLED:
            organizer_id = appt_as_invitee.event.user_id
            msg = (
                f"❌ *Отмена участия*\n\n"
                f"Пользователь (ID: `{user_id}`) отменил свое участие:\n"
                f"📌 *Событие*: {appt_as_invitee.event.title}\n"
                f"📅 *Дата*: {date_str}\n"
                f"⏰ *Время*: {time_str}"
            )
            await appt_as_invitee.adelete()
            try:
                await bot.send_message(chat_id=organizer_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления организатору {organizer_id}: {e}")


