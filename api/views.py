from rest_framework import generics
import requests
from rest_framework.permissions import IsAuthenticated
import logging
import threading

from app.main import settings
from events.models import Appointment, Event
from .serializers import EventUpdateSerializer, PublicEventSerializer
from .serializers import EventSerializer
from .authentication import BotTokenAuthentication


class PublicEventListView(generics.ListAPIView):
    """
    GET /api/events/
    Возвращает список ВСЕХ публичных событий всех пользователей.
    """
    serializer_class = PublicEventSerializer
    
    def get_queryset(self):
        # Фильтруем только публичные события
        return Event.objects.filter(is_public=True).order_by('-event_date')


class UserPublicEventListView(generics.ListAPIView):
    """
    GET /api/events/<telegram_id>/
    Возвращает публичные события конкретного пользователя.
    """
    serializer_class = PublicEventSerializer
    
    def get_queryset(self):
        # Извлекаем telegram_id из URL
        user_id = self.kwargs.get('telegram_id')
        # Фильтруем события по пользователю И публичности
        return Event.objects.filter(user_id=user_id, is_public=True).order_by('-event_date')


class UserEventListCreateAPIView(generics.ListCreateAPIView):
    """
    GET /api/my-events/ - получить все свои события
    POST /api/my-events/ - создать новое событие
    """
    # 1. DRF проверка кастомного токена
    authentication_classes = [BotTokenAuthentication]
    # 2. Блокируем доступ анонимам (без токена или с невалидным токеном)
    permission_classes = [IsAuthenticated]
    serializer_class = EventSerializer
    
    def get_queryset(self):
        # request.user здесь - это тот самый юзер, которого вернул наш BotTokenAuthentication
        return Event.objects.filter(user=self.request.user).order_by('-event_date')

    def perform_create(self, serializer: EventSerializer):
        # При POST-запросе жестко привязываем создаваемое событие к владельцу токена
        serializer.save(user=self.request.user)


class UserEventDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [BotTokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Жестко ограничиваем доступ: пользователь может взаимодействовать только со своими событиями
        return Event.objects.filter(user=self.request.user)
        
    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return EventUpdateSerializer
        return EventSerializer

    def perform_destroy(self, instance: Event):
        user = self.request.user
        date_str = instance.event_date.strftime("%d.%m.%Y")
        time_str = f"{instance.start_time.strftime('%H:%M')} - {instance.end_time.strftime('%H:%M')}" if instance.start_time else "Весь день"
        
        # Инициализируем логгер для текущего модуля
        logger = logging.getLogger(__name__)
        
        # Вспомогательная функция для синхронной отправки сообщений в Telegram
        def send_tg_message(chat_id: int, text: str) -> None:
            token = settings.telegram_api_key.get_secret_value()
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            
            try:
                response = requests.post(
                    url, 
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, 
                    timeout=5
                )
                
                # Если запрос дошёл, но Telegram вернул ошибку (400, 403, 404)
                if not response.ok:
                    logger.error(
                        "Ошибка Telegram API при отправке уведомления. "
                        f"Chat ID: {chat_id}, Статус: {response.status_code}, Ответ: {response.text}"
                    )
                    
            except requests.RequestException as e:
                # Ловим сетевые сбои (нет интернета, таймаут соединения)
                logger.error(f"Сетевая ошибка при отправке TG уведомления на chat_id={chat_id}: {e}")

        # ==========================================
        # СЦЕНАРИЙ А: Пользователь — ОРГАНИЗАТОР
        # ==========================================
        hosted_appointments = Appointment.objects.filter(event=instance)
        
        if hosted_appointments.exists():
            for appt in hosted_appointments:
                invitee_id = appt.invitee_id
                
                # Находим и удаляем локальную копию в календаре ребенка
                Event.objects.filter(
                    user_id=invitee_id,
                    event_date=instance.event_date,
                    start_time=instance.start_time,
                    end_time=instance.end_time
                ).delete()
                
                # Удаляем саму запись о встрече
                appt.delete()
                
                msg = (
                    f"❌ *Отмена встречи*\n\n"
                    f"Организатор (ID: `{user.telegram_id}`) отменил мероприятие:\n"
                    f"📌 *Событие*: {instance.title}\n"
                    f"📅 *Дата*: {date_str}\n"
                    f"⏰ *Время*: {time_str}"
                )
                # Запускаем отправку сообщения в фоновом потоке
                threading.Thread(
                    target=send_tg_message, 
                    args=(invitee_id, msg),
                    daemon=True  # Поток умрет вместе с основным процессом, если сервер остановят
                ).start()
                
        # ==========================================
        # СЦЕНАРИЙ Б: Пользователь — РЕБЕНОК (приглашенный)
        # ==========================================
        else:
            appt_as_invitee = Appointment.objects.filter(
                invitee=user,
                event__event_date=instance.event_date,
                event__start_time=instance.start_time,
                event__end_time=instance.end_time
            ).first()

            if appt_as_invitee and appt_as_invitee.status != Appointment.Status.CANCELLED:
                organizer_id = appt_as_invitee.event.user_id
                msg = (
                    f"❌ *Отмена участия*\n\n"
                    f"Пользователь (ID: `{user.telegram_id}`) отменил свое участие:\n"
                    f"📌 *Событие*: {appt_as_invitee.event.title}\n"
                    f"📅 *Дата*: {date_str}\n"
                    f"⏰ *Время*: {time_str}"
                )
                # Запускаем отправку сообщения в фоновом потоке
                threading.Thread(
                    target=send_tg_message, 
                    args=(organizer_id, msg),
                    daemon=True
                ).start()
                
                # Удаляем только связь, событие организатора остается
                appt_as_invitee.delete()

        # ==========================================
        # В конце физически удаляем само событие (сработает для обоих сценариев)
        # ==========================================
        instance.delete()