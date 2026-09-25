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
        read_only_fields = ['id', 'user']