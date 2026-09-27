from django.urls import path
from .views import (
    PublicEventListView, 
    UserPublicEventListView, 
    UserEventListCreateAPIView,
    UserEventDetailAPIView
)

app_name = 'api'

urlpatterns = [
    # Маршрут для всех публичных событий
    path('events/', PublicEventListView.as_view(), name='public-events-list'),
    
    # Маршрут для публичных событий конкретного пользователя
    path('events/<int:telegram_id>/', UserPublicEventListView.as_view(), name='user-public-events-list'),

    # GET (список), POST (создание)
    path('my-events/', UserEventListCreateAPIView.as_view(), name='private-events-list'),
    
    # GET (одно событие), PUT/PATCH (изменение), DELETE (удаление)
    path('my-events/<int:pk>/', UserEventDetailAPIView.as_view(), name='private-events-detail'),
]