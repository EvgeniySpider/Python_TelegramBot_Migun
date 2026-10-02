import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient
from unittest.mock import patch

from events.models import Appointment, Event, User


@pytest.mark.django_db
def test_delete_own_event_success(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})

    response: Response = auth_client.delete(url)

    # DRF при успешном удалении возвращает 204 No Content
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Проверяем, что записи физически больше нет в базе
    assert not Event.objects.filter(id=private_event.id).exists()


@pytest.mark.django_db
def test_delete_alien_event_returns_404(
    auth_client: APIClient,
    alien_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': alien_event.id})

    response: Response = auth_client.delete(url)

    # DRF скрывает чужие ресурсы, выдавая 404
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Убеждаемся, что чужое событие осталось в целости
    assert Event.objects.filter(id=alien_event.id).exists()


@pytest.mark.django_db
@patch('requests.post')  # Перехватываем все вызовы requests.post в рамках этого теста
def test_delete_organizer_event_removes_children_and_notifies(
    mock_post,  # Мок всегда передается аргументом после фикстур
    auth_client: APIClient,
    test_user: User,
    alien_user: User,
    private_event: Event
):
    # 1. Создаем локальную копию события в календаре ребенка (alien_user)
    child_event = Event.objects.create(
        user=alien_user,
        event_type=private_event.event_type,
        title='Копия для ребенка',
        event_date=private_event.event_date,
        start_time=private_event.start_time,
        end_time=private_event.end_time,
        is_public=False
    )
    
    # 2. Создаем саму встречу
    Appointment.objects.create(
        event=private_event,
        invitee=alien_user,
        status=Appointment.Status.CONFIRMED
    )

    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    response: Response = auth_client.delete(url)

    # 3. Базовые проверки статуса и удаления оригинала
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Event.objects.filter(id=private_event.id).exists()

    # 4. Проверка бизнес-логики: удалилась ли копия ребенка и запись Appointment
    assert not Event.objects.filter(id=child_event.id).exists()
    assert not Appointment.objects.filter(event=private_event).exists()

    # 5. Проверка отправки уведомления в Telegram
    mock_post.assert_called_once()  # Убеждаемся, что requests.post был вызван ровно 1 раз
    
    # Проверяем, что запрос ушел правильному адресату (ребенку)
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs['json']['chat_id'] == alien_user.telegram_id
    assert "Отмена встречи" in call_kwargs['json']['text']


@pytest.mark.django_db
@patch('requests.post')
def test_delete_invitee_event_keeps_organizer_and_notifies(
    mock_post,
    auth_client: APIClient,
    test_user: User,
    alien_user: User,
    private_event: Event,
    alien_event: Event
):
    # 1. Синхронизируем поля оригинала, чтобы сработал фильтр is_invitee_meeting
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

    # 3. test_user (ребенок) удаляет СВОЮ копию
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    response: Response = auth_client.delete(url)

    # 4. Проверяем статусы и удаление копии
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Event.objects.filter(id=private_event.id).exists()

    # 5. Главная проверка бизнес-логики: оригинал организатора ДОЛЖЕН остаться
    assert Event.objects.filter(id=alien_event.id).exists()
    assert not Appointment.objects.filter(invitee=test_user, event=alien_event).exists()

    # 6. Проверка отправки уведомления организатору
    mock_post.assert_called_once()
    
    call_kwargs = mock_post.call_args.kwargs
    # Уведомление должно уйти организатору (alien_user)
    assert call_kwargs['json']['chat_id'] == alien_user.telegram_id
    assert "Отмена участия" in call_kwargs['json']['text']


@pytest.mark.django_db
def test_delete_unexistent_event(auth_client: APIClient):
    url: str = reverse('api:private-events-detail', kwargs={'pk': 999})
    response: Response = auth_client.delete(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_double_delete_event(
    auth_client: APIClient,
    private_event: Event
):
    url: str = reverse('api:private-events-detail', kwargs={'pk': private_event.id})
    response: Response = auth_client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Event.objects.filter(id=private_event.id).exists()

    response: Response = auth_client.delete(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND