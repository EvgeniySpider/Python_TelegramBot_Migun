import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient
from events.models import Event, User


@pytest.mark.django_db
def test_patch_event_title_and_description(
    auth_client: APIClient,
    test_user: User,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    
    payload: dict = {
        'title': 'Обновленное название',
        'description': 'Новое описание'
    }

    response: Response = auth_client.patch(url, data=payload, format='json')

    # 1. Проверяем HTTP статус
    assert response.status_code == status.HTTP_200_OK

    # 2. Проверяем возвращенный JSON: изменились только переданные поля
    data: dict = response.json()
    assert data['id'] == private_event.id
    assert data['title'] == payload['title']
    assert data['description'] == payload['description']
    assert data['event_date'] == str(private_event.event_date)
    assert data['event_type'] == private_event.event_type

    # 3. Проверяем состояние в БД через перезагрузку инстанса
    private_event.refresh_from_db()
    assert private_event.title == payload['title']
    assert private_event.description == payload['description']


@pytest.mark.django_db
def test_patch_exact_event_start_time_recalculates_end_time(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    
    new_start_time = '16:00'
    expected_start_time = '16:00:00'
    expected_end_time = '16:30:00'

    payload = {'start_time': new_start_time}

    response: Response = auth_client.patch(url, data=payload, format='json')

    assert response.status_code == status.HTTP_200_OK

    data: dict = response.json()
    assert data['start_time'] == expected_start_time
    # Проверяем, что сериализатор автоматически пересчитал end_time (+30 мин)
    assert data['end_time'] == expected_end_time

    private_event.refresh_from_db()
    assert str(private_event.start_time) == expected_start_time
    assert str(private_event.end_time) == expected_end_time


@pytest.mark.django_db
def test_patch_event_date(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    
    new_date = '2026-11-20'
    payload = {'event_date': new_date}

    response: Response = auth_client.patch(url, data=payload, format='json')

    assert response.status_code == status.HTTP_200_OK

    data: dict = response.json()
    assert data['event_date'] == new_date

    private_event.refresh_from_db()
    assert str(private_event.event_date) == new_date