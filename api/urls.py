from django.urls import path
from .views import UserEventListCreateAPIView, PublicEventListView, UserPublicEventListView

app_name = 'api'

urlpatterns = [
    # Маршрут для всех публичных событий
    path('events/', PublicEventListView.as_view(), name='public-events-list'),
    
    # Маршрут для публичных событий конкретного пользователя
    path('events/<int:telegram_id>/', UserPublicEventListView.as_view(), name='user-public-events-list'),

    path('my-events/', UserEventListCreateAPIView.as_view(), name='private-events-list'),
]