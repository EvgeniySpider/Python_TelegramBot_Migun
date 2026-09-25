from rest_framework import serializers
from events.models import Event

class PublicEventSerializer(serializers.ModelSerializer):
    # Добавляем человекочитаемое поле типа события, используя метод get_event_type_display
    type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = Event
        fields = [
            'id',
            'user',
            'event_type',
            'type_display',
            'title',
            'description',
            'event_date',
            'start_time',
            'end_time',
            'is_public'
        ]
        read_only_fields = ['id', 'user', 'created_at']
    


class EventSerializer(serializers.ModelSerializer):
    """
    Полный сериализатор для работы с собственными событиями пользователя (CRUD).
    """
    # Добавляем человекочитаемое отображение типа события (только для чтения)
    type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 
            'user', 
            'event_type', 
            'type_display', 
            'title', 
            'description', 
            'event_date', 
            'start_time', 
            'end_time', 
            'is_public',
            'created_at'
        ]
        # Защищаем системные поля от изменения при POST/PUT запросах.
        # Поле user заполняется автоматически во вьюхе (perform_create).
        read_only_fields = ['id', 'user', 'created_at']