import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.response import Response
from events.models import Event, User
from rest_framework import status


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
