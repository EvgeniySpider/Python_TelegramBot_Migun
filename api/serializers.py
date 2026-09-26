from datetime import datetime, timedelta
from rest_framework import serializers

from app.core.calendar.utils import format_event_time
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


    def validate(self, attrs: dict) -> dict:
        user = self.context['request'].user
        event_type = attrs.get('event_type')
        event_date = attrs.get('event_date')
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        # Проверка: не занят ли весь день уже существующим событием all_day
        if Event.objects.filter(user=user, event_date=event_date, event_type=Event.EventType.ALL_DAY).exists():
            raise serializers.ValidationError('Этот день весь занят')

        if event_type == Event.EventType.ALL_DAY:
            if start_time or end_time:
                raise serializers.ValidationError("Для события 'Весь день' поля времени не указываются.")
            
            # Добавлен user=user
            conflict_event = Event.objects.filter(user=user, event_date=event_date)
            if conflict_event.exists():
                times_events = [
                    format_event_time(event.start_time, event.end_time) 
                    for event in conflict_event 
                    if event.start_time and event.end_time
                ] or ['Весь день']
                
                raise serializers.ValidationError(
                    f'В этом дне уже есть события со следующими временами: {times_events}. '
                    'Целый день из-за наличия событий занять невозможно'
                )
            return attrs

        elif event_type == Event.EventType.EXACT:
            if not start_time:
                raise serializers.ValidationError('Для события с типом "точное время" необходимо указать start_time')
            if end_time:
                raise serializers.ValidationError('Для события с типом "точное время" end_time не указывается')
            
            # Корректное прибавление 30 минут через комбинирование даты и времени
            start_dt = datetime.combine(event_date, start_time)
            end_time = (start_dt + timedelta(minutes=30)).time()
            # Сохраняем вычисленное время, чтобы оно не было None в нижнем фильтре и ушло в БД
            attrs['end_time'] = end_time
            
        elif event_type == Event.EventType.INTERVAL:
            if not start_time or not end_time:
                raise serializers.ValidationError('Для события с типом "интервал" необходимо время начала и конца мероприятия')

        # Исключены тернарные операторы, так как end_time теперь гарантированно определен
        conflict_event = Event.objects.filter(
            user=user,
            event_date=event_date,
            start_time__isnull=False,
            end_time__isnull=False,
            start_time__lt=end_time,
            end_time__gt=start_time
        )

        if conflict_event.exists():
            conflict_events = [
                format_event_time(event.start_time, event.end_time) 
                for event in conflict_event 
            ]
            raise serializers.ValidationError(
                f'Конфликт времени, в этот день у вас занято следующее время: {conflict_events}'
            )
            
        return attrs