from rest_framework import generics
from events.models import Event
from .serializers import PublicEventSerializer
from rest_framework.permissions import IsAuthenticated

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


class PrivateEventListCreateView(generics.ListCreateAPIView):
    """
    GET /api/my-events/ - получить все свои события
    POST /api/my-events/ - создать новое событие
    """
    # 1. Говорим DRF проверять наш кастомный токен
    authentication_classes = [BotTokenAuthentication]
    # 2. Блокируем доступ анонимам (без токена или с невалидным токеном)
    permission_classes = [IsAuthenticated]
    
    serializer_class = EventSerializer

    def get_queryset(self):
        # request.user здесь - это тот самый юзер, которого вернул наш BotTokenAuthentication
        return Event.objects.filter(user=self.request.user).order_by('-event_date')

    def perform_create(self, serializer):
        # При POST-запросе жестко привязываем создаваемое событие к владельцу токена
        serializer.save(user=self.request.user)