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
):
    # Создаем чужого пользователя и его публичное событие
    other_user = User.objects.create(telegram_id=999999999)
    Event.objects.create(
        user=other_user,
        event_type='all_day',
        title='Событие другого пользователя',
        event_date=public_event.event_date,
        is_public=True
    )

    url: str = reverse('api:user-public-events-list', kwargs={'telegram_id': test_user.telegram_id})
    response: Response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK

    data: list[dict] = response.json()

    assert len(data) == 1
    assert data[0]['title'] == 'Тестовое публичное событие'
    assert data[0]['is_public'] is True
    assert data[0]['user'] == test_user.telegram_id