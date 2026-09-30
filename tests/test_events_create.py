import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.response import Response
from events.models import Event, User
from rest_framework import status



@pytest.mark.django_db
def test_create_event(auth_client: APIClient, test_user: User):
    url: str = reverse('api:private-events-list')

    payload = {
        'event_type': 'interval',
        'title': 'лучшее название',
        'description': 'лучшее описание',
        'event_date': '2026-09-09',
        'start_time': '10:00',
        'end_time': '12:00',
        'is_public': False
    }

    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED

    created_event: dict = response.json()

    assert created_event['user'] == test_user.telegram_id
    assert created_event['event_type'] == payload['event_type']
    assert created_event['title'] == payload['title']
    assert created_event['description'] == payload['description']
    assert created_event['event_date'] == payload['event_date']
    assert created_event['start_time'] == payload['start_time'] + ':00'
    assert created_event['end_time'] == payload['end_time'] + ':00'
    assert created_event['is_public'] == payload['is_public']

    db_event = Event.objects.get(id=created_event['id'])
    assert db_event.user == test_user
    assert db_event.title == payload['title']
    assert db_event.event_type == payload['event_type']



@pytest.mark.django_db
@pytest.mark.parametrize(
    'missing_field', ['title', 'event_type', 'event_date']
)
def test_create_event_missing_required_fields(
    auth_client: APIClient, 
    missing_field: str
) -> None:
    url: str = reverse('api:private-events-list')

    payload  = {
        'event_type': 'interval',
        'title': 'Рабочая встреча',
        'event_date': '2026-09-09',
        'start_time': '10:00',
        'end_time': '12:00',
        'is_public': False,
    }
    # Вырезаем проверяемое поле из полезной нагрузки
    del payload[missing_field]

    response: Response = auth_client.post(url, data=payload, format='json')

    # 1. Сервер обязан вернуть 400 Bad Request
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Сериализатор должен указать ошибку именно на отсутствующее поле
    errors: dict = response.json()
    assert missing_field in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'key, value',
    [
        ('event_type', 'unexist'),
        ('event_date', 'not-a-date'),
        ('start_time', 'not-a-time'),
        ('is_public', 'not-a-boolean'),
    ]
)
def test_create_event_with_invalid_fields(
    auth_client: APIClient,
    key: str,
    value: str
):
    url: str = reverse('api:private-events-list')
    payload = {
        'event_type': 'interval',
        'title': 'Рабочая встреча',
        'event_date': '2026-09-09',
        'start_time': '10:00',
        'end_time': '12:00',
        'is_public': False,
    }

    payload[key] = value

    response: Response = auth_client.post(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors: dict = response.json()
    assert key in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'event_type, start_time, end_time',
    [
        # Сценарии для 'all_day': время передавать запрещено
        ('all_day', '10:00', None),
        ('all_day', None, '12:00'),
        ('all_day', '10:00', '12:00'),
        
        # Сценарии для 'exact': обязателен start_time, запрещен end_time
        ('exact', None, None),
        ('exact', '10:00', '12:00'),
        ('exact', None, '12:00'),
        
        # Сценарии для 'interval': обязательны оба поля
        ('interval', '10:00', None),
        ('interval', None, '12:00'),
        ('interval', None, None),
    ]
)
def test_create_event_business_logic_conflicts(
    auth_client: APIClient,
    event_type: str,
    start_time: str | None,
    end_time: str | None
) -> None:
    url: str = reverse('api:private-events-list')
    
    payload: dict = {
        'title': 'Бизнес-логика проверка',
        'event_date': '2026-09-09',
        'is_public': False,
        'event_type': event_type,
    }
    
    # Добавляем ключи времени только если они не None, 
    # чтобы сымитировать реальное отсутствие полей в запросе
    if start_time:
        payload['start_time'] = start_time
    if end_time:
        payload['end_time'] = end_time

    response: Response = auth_client.post(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    errors: dict = response.json()
    # Поскольку в serializers.py исключения вызываются как raise ValidationError("текст ошибки"), 
    # DRF автоматически складывает их в массив по ключу 'non_field_errors'
    assert 'non_field_errors' in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'payload_override, expected_error_key',
    [
        # Невалидные даты (отбивает встроенный DateField)
        ({'event_date': '2026-09-31'}, 'event_date'),  # В сентябре 30 дней
        ({'event_date': '2026-02-29'}, 'event_date'),  # 2026 - не високосный
        ({'event_date': '2026-13-01'}, 'event_date'),  # Нет 13-го месяца

        # Невалидное время (отбивает встроенный TimeField)
        ({'start_time': '25:00'}, 'start_time'),       # В сутках 24 часа
        ({'end_time': '12:61'}, 'end_time'),           # В минуте 60 секунд

        # Нарушение хронологии (отбивает validate)
        (
            {'event_type': 'interval', 'start_time': '12:00', 'end_time': '10:00'},
            'non_field_errors' 
        ),
    ]
)
def test_create_event_datetime_boundaries(
    auth_client: APIClient,
    payload_override: dict,
    expected_error_key: str
):
    url: str = reverse('api:private-events-list')
    payload = {
        'title': 'Тест форматов',
        'event_date': '2026-09-09',
        'is_public': False,
        'event_type': 'interval',
        'start_time': '10:00',
        'end_time': '12:00'
    }
    payload.update(payload_override)
    
    response: Response = auth_client.post(url, data=payload, format='json')
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert expected_error_key in response.json()


@pytest.mark.django_db
def test_create_event_time_collisions(auth_client: APIClient, test_user: User):
    # 1. Бронируем время в БД (12:00 - 14:00)
    Event.objects.create(
        user=test_user,
        event_type='interval',
        title='Уже занятый слот',
        event_date='2026-10-10',
        start_time='12:00',
        end_time='14:00',
        is_public=False
    )
    
    url: str = reverse('api:private-events-list')
    base_payload = {
        'title': 'Попытка вклиниться',
        'event_date': '2026-10-10',
        'is_public': False,
    }

    # Сценарий А: Пересечение интервалов (внахлест слева 11:00-13:00)
    payload = {**base_payload, 'event_type': 'interval', 'start_time': '11:00', 'end_time': '13:00'}
    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.json()

    # Сценарий Б: Точное время (exact) падает прямо внутрь занятого интервала (в 13:00)
    payload = {**base_payload, 'event_type': 'exact', 'start_time': '13:00'}
    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.json()

    # Сценарий В: Попытка объявить весь день (all_day) занятым, хотя внутри уже есть интервал
    payload = {**base_payload, 'event_type': 'all_day'}
    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.json()