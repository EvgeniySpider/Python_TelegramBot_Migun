import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from events.models import Event, User, Appointment


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


@pytest.mark.django_db
def test_patch_alien_event_returns_404(
    auth_client: APIClient,
    alien_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': alien_event.id})
    payload = {'title': 'Взлом чужого события'}

    response: Response = auth_client.patch(url, data=payload, format='json')

    # DRF возвращает 404, защищая приватность чужих записей
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Убеждаемся, что в базе запись не изменилась
    alien_event.refresh_from_db()
    assert alien_event.title != payload['title']


@pytest.mark.django_db
def test_patch_event_with_appointment_forbidden(
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
    payload = {'title': 'Попытка изменить встречу'}

    response: Response = auth_client.patch(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors

    # Проверяем, что название в БД осталось исходным
    private_event.refresh_from_db()
    assert private_event.title != payload['title']


@pytest.mark.django_db
def test_patch_invitee_event_forbidden(
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
    payload = {'title': 'Попытка ребенка изменить встречу'}

    response: Response = auth_client.patch(url, data=payload, format='json')

    # 4. Проверяем отсечку валидатором EventUpdateSerializer
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors
    assert 'Вас пригласили на встречу' in errors['non_field_errors'][0]

    # 5. Убеждаемся, что событие в БД не изменилось
    private_event.refresh_from_db()
    assert private_event.title != payload['title']


@pytest.mark.django_db
def test_patch_event_time_collision(
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
    payload = {'start_time': '14:30'}

    response: Response = auth_client.patch(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors
    assert 'Конфликт времён' in errors['non_field_errors'][0]


@pytest.mark.django_db
def test_patch_event_type_is_ignored(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    payload = {'event_type': Event.EventType.ALL_DAY}

    response: Response = auth_client.patch(url, data=payload, format='json')

    # DRF не падает на лишних read-only полях, а молча их отбрасывает
    assert response.status_code == status.HTTP_200_OK

    private_event.refresh_from_db()
    # Тип не должен был измениться
    assert private_event.event_type != Event.EventType.ALL_DAY


@pytest.mark.django_db
def test_patch_interval_event_invalid_chronology(
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
    payload = {'end_time': '09:00'}

    response: Response = auth_client.patch(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert 'non_field_errors' in errors
    assert 'Время начала должно быть строго раньше' in errors['non_field_errors'][0]