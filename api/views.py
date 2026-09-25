from rest_framework import generics
from events.models import Event
from .serializers import PublicEventSerializer

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