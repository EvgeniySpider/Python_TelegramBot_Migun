from datetime import date, time

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from events.models import Event, User


@pytest.mark.django_db
def test_get_user_event_list(
    auth_client: APIClient,
    test_user: User,
    public_event: Event,
    private_event: Event,
    alien_event: Event,
):

    url: str = reverse("api:private-events-list")
    response: Response = auth_client.get(url)

    # 1. Сначала статус
    assert response.status_code == status.HTTP_200_OK

    # 2. Затем парсинг и валидация
    data: list[dict] = response.json()
    assert len(data) == 2

    # 3. Безопасная проверка без жесткой привязки к порядку
    assert {item["is_public"] for item in data} == {True, False}
    assert all(item["user"] == test_user.telegram_id for item in data)


@pytest.mark.django_db
def test_get_late_night_event_does_not_contain_warning(auth_client: APIClient, test_user: User):
    """
    Проверяет, что при GET-запросах (чтении) поле warning НЕ попадает в ответ,
    даже если событие exact начинается позже 23:29.
    """
    # 1. Создаем ночное событие в базе
    late_event = Event.objects.create(
        user=test_user,
        event_type=Event.EventType.EXACT,
        title="Ночное событие",
        event_date=date.today(),
        start_time=time(23, 45),
        end_time=time(23, 59),
        is_public=False,
    )

    # 2. Проверяем список (GET /api/my-events/)
    list_url: str = reverse("api:private-events-list")
    list_response: Response = auth_client.get(list_url)
    assert list_response.status_code == status.HTTP_200_OK
    list_data = list_response.json()
    assert len(list_data) == 1
    assert "warning" not in list_data[0]

    # 3. Проверяем детальный просмотр (GET /api/my-events/<id>/)
    detail_url: str = reverse("api:private-events-detail", kwargs={"pk": late_event.id})
    detail_response: Response = auth_client.get(detail_url)
    assert detail_response.status_code == status.HTTP_200_OK
    detail_data = detail_response.json()
    assert "warning" not in detail_data
