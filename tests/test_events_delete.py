import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from events.models import Event


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