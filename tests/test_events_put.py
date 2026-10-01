import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from events.models import Event, User, Appointment


@pytest.mark.django_db
def test_put_event_full_update(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})

    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '11:00',
        'is_public': True
    }

    response: Response = auth_client.put(url, data=payload, format='json')

    assert response.status_code == status.HTTP_200_OK

    updated_event: dict = response.json()

    assert updated_event['title'] == 'Новое название'
    assert updated_event['description'] == 'Новое описание'
    assert updated_event['event_date'] == '2026-10-01'
    assert updated_event['start_time'] == '11:00:00'
    assert updated_event['end_time'] == '11:30:00'
    assert updated_event['is_public'] is True

    private_event.refresh_from_db()

    assert private_event.title == payload['title']
    assert private_event.description == payload['description']
    assert str(private_event.event_date) == payload['event_date']
    assert str(private_event.start_time) == '11:00:00'
    assert str(private_event.end_time) == '11:30:00'
    assert private_event.is_public is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    'missing_field', ['title', 'event_date']
)
def test_put_event_without_required_fields(
    auth_client: APIClient,
    private_event: Event,
    missing_field: str
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})

    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '11:00',
        'is_public': True
    }

    del payload[missing_field]

    response: Response = auth_client.put(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors: dict = response.json()
    assert missing_field in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'key, value', [
        ('start_time', 'invalid_time'),
        ('event_date', 'invalid_date'),
        ('is_public', 'invalid_flag')
    ]
)
def test_put_event_invalid_fields(
    auth_client: APIClient,
    private_event: Event,
    key: str,
    value: str
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})

    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '11:00',
        'is_public': True
    }

    payload[key] = value

    response: Response = auth_client.put(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert key in response.json()


@pytest.mark.django_db
def test_put_event_without_optional_fields(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})

    payload = {
        'title': 'Новое название',
        'event_date': '2026-10-01',
        'start_time': '11:00'
    }

    response: Response = auth_client.put(url, data=payload, format='json')
    assert response.status_code == status.HTTP_200_OK

    partial_updated_event = response.json()

    assert partial_updated_event['title'] == 'Новое название'
    assert partial_updated_event['event_date'] == '2026-10-01'
    assert partial_updated_event['start_time'] == '11:00:00'
    assert partial_updated_event['end_time'] == '11:30:00'
    assert partial_updated_event['description'] is None
    assert partial_updated_event['is_public'] is False

    private_event.refresh_from_db()

    assert private_event.title == payload['title']
    assert str(private_event.event_date) == payload['event_date']
    assert str(private_event.start_time) == '11:00:00'
    assert str(private_event.end_time) == '11:30:00'
    assert private_event.description is None
    assert private_event.is_public is False