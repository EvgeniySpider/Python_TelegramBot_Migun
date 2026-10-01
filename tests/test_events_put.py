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


@pytest.mark.django_db
def test_put_event_with_appointment_forbidden(
    auth_client: APIClient,
    test_user: User,
    alien_user: User,
    private_event: Event
):
    # Создаем привязанную встречу, где test_user является организатором
    Appointment.objects.create(
        event=private_event,
        invitee=alien_user
    )

    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '11:00',
        'is_public': True
    }
    response: Response = auth_client.put(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors

    private_event.refresh_from_db()
    assert private_event.title != payload['title']


@pytest.mark.django_db
def test_put_invitee_event_forbidden(
    auth_client: APIClient,
    test_user: User,
    alien_user: User,
    private_event: Event,
    alien_event: Event
):
    # 1. Синхронизируем параметры событий, чтобы сработал фильтр is_invitee_meeting
    alien_event.event_date = private_event.event_date
    alien_event.start_time = private_event.start_time
    alien_event.end_time = private_event.end_time
    alien_event.event_type = private_event.event_type
    alien_event.save()

    # 2. Создаем встречу: alien_user пригласил test_user
    Appointment.objects.create(
        event=alien_event,
        invitee=test_user,
        status=Appointment.Status.CONFIRMED
    )

    # 3. test_user (клиент auth_client) пытается изменить СВОЮ копию события
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '11:00',
        'is_public': True
    }

    response: Response = auth_client.put(url, data=payload, format='json')

    # 4. Проверяем отсечку валидатором EventUpdateSerializer
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors
    assert 'Вас пригласили на встречу' in errors['non_field_errors'][0]

    # 5. Убеждаемся, что событие в БД не изменилось
    private_event.refresh_from_db()
    assert private_event.title != payload['title']


@pytest.mark.django_db
def test_put_event_time_collision(
    auth_client: APIClient,
    test_user: User,
    private_event: Event
):
    # Создаем второе событие пользователя в этот же день
    Event.objects.create(
        user=test_user,
        event_type=Event.EventType.INTERVAL,
        title='Второе событие',
        event_date=private_event.event_date,
        start_time='14:00',
        end_time='16:00',
        is_public=False
    )

    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    # Пытаемся сдвинуть private_event на 14:30 (попадает внутрь второго события)
    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': str(private_event.event_date),
        'start_time': '15:00',
        'is_public': True
    }

    response: Response = auth_client.put(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors
    assert 'Конфликт времён' in errors['non_field_errors'][0]


@pytest.mark.django_db
def test_put_event_type_is_ignored(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    payload = {
        'title': 'Новое название',
        'event_type': Event.EventType.ALL_DAY,
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '15:00',
        'is_public': True
    }

    response: Response = auth_client.put(url, data=payload, format='json')

    # DRF не падает на лишних read-only полях, а молча их отбрасывает
    assert response.status_code == status.HTTP_200_OK

    private_event.refresh_from_db()
    # Тип не должен был измениться
    assert private_event.event_type != Event.EventType.ALL_DAY


@pytest.mark.django_db
def test_put_interval_event_invalid_chronology(
    auth_client: APIClient,
    test_user: User
):
    interval_event = Event.objects.create(
        user=test_user,
        event_type=Event.EventType.INTERVAL,
        title='Интервальное событие',
        event_date='2026-09-09',
        start_time='10:00',
        end_time='12:00',
        is_public=False
    )

    url: str = reverse('api:private-events-detail', kwargs={'pk': interval_event.id})
    # Делаем конец интервала раньше начала (10:00 > 09:00)
    payload = {
        'title': 'Новое название',
        'description': 'Новое описание',
        'event_date': '2026-10-01',
        'start_time': '15:00',
        'end_time': '14:00',
        'is_public': True
    }

    response: Response = auth_client.put(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors
    assert 'Время начала должно быть строго раньше' in errors['non_field_errors'][0]