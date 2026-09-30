import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.response import Response
from events.models import Event, User
from rest_framework import status


@pytest.mark.django_db
def test_get_public_events_list(
    api_client: APIClient, 
    public_event: Event, 
    private_event: Event,
    test_user: User
):
    url: str = reverse('api:public-events-list')
    response: Response = api_client.get(url)
    
    assert response.status_code == status.HTTP_200_OK
    
    data: list[dict] = response.json()
    assert len(data) == 1
    assert data[0]['title'] == 'Тестовое публичное событие'
    assert data[0]['is_public'] is True


@pytest.mark.django_db
def test_get_public_user_event_list(
    api_client: APIClient,
    test_user: User,
    public_event: Event,
    private_event: Event,
    alien_event: Event
):

    url: str = reverse('api:user-public-events-list', kwargs={'telegram_id': test_user.telegram_id})
    response: Response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK

    data: list[dict] = response.json()

    assert len(data) == 1
    assert data[0]['title'] == 'Тестовое публичное событие'
    assert data[0]['is_public'] is True
    assert data[0]['user'] == test_user.telegram_id


@pytest.mark.django_db
def test_get_user_event_list(
    auth_client: APIClient,
    test_user: User,
    public_event: Event,
    private_event: Event,
    alien_event: Event
):
    
    url: str = reverse('api:private-events-list')
    response: Response = auth_client.get(url)

    # 1. Сначала статус
    assert response.status_code == status.HTTP_200_OK

    # 2. Затем парсинг и валидация
    data: list[dict] = response.json()
    assert len(data) == 2

    # 3. Безопасная проверка без жесткой привязки к порядку
    assert {item['is_public'] for item in data} == {True, False}
    assert all(item['user'] == test_user.telegram_id for item in data)



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

    payload: dict = {
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


