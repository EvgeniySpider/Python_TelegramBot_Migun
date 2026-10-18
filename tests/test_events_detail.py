from datetime import date, time, timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from events.models import Appointment, Event, User


@pytest.mark.django_db
def test_patch_event_title_and_description(
    auth_client: APIClient, test_user: User, private_event: Event
):
    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})

    payload: dict = {"title": "Обновленное название", "description": "Новое описание"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    # 1. Проверяем HTTP статус
    assert response.status_code == status.HTTP_200_OK

    # 2. Проверяем возвращенный JSON: изменились только переданные поля
    data: dict = response.json()
    assert data["id"] == private_event.id
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["event_date"] == str(private_event.event_date)
    assert data["event_type"] == private_event.event_type

    # 3. Проверяем состояние в БД через перезагрузку инстанса
    private_event.refresh_from_db()
    assert private_event.title == payload["title"]
    assert private_event.description == payload["description"]


@pytest.mark.django_db
def test_patch_exact_event_start_time_recalculates_end_time(
    auth_client: APIClient, private_event: Event
):
    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})

    new_start_time = "16:00"
    expected_start_time = "16:00:00"
    expected_end_time = "16:30:00"

    payload = {"start_time": new_start_time}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK

    data: dict = response.json()
    assert data["start_time"] == expected_start_time
    # Проверяем, что сериализатор автоматически пересчитал end_time (+30 мин)
    assert data["end_time"] == expected_end_time

    private_event.refresh_from_db()
    assert str(private_event.start_time) == expected_start_time
    assert str(private_event.end_time) == expected_end_time


@pytest.mark.django_db
def test_patch_event_date(auth_client: APIClient, private_event: Event):
    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})

    new_date = "2026-11-20"
    payload = {"event_date": new_date}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK

    data: dict = response.json()
    assert data["event_date"] == new_date

    private_event.refresh_from_db()
    assert str(private_event.event_date) == new_date


@pytest.mark.django_db
def test_patch_alien_event_returns_404(auth_client: APIClient, alien_event: Event):
    url: str = reverse("api:private-events-detail", kwargs={"pk": alien_event.id})
    payload = {"title": "Взлом чужого события"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    # DRF возвращает 404, защищая приватность чужих записей
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Убеждаемся, что в базе запись не изменилась
    alien_event.refresh_from_db()
    assert alien_event.title != payload["title"]


@pytest.mark.django_db
def test_patch_event_with_appointment_forbidden(
    auth_client: APIClient, test_user: User, alien_user: User, private_event: Event
):
    # Создаем привязанную встречу, где test_user является организатором
    Appointment.objects.create(event=private_event, invitee=alien_user)

    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    payload = {"title": "Попытка изменить встречу"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors

    # Проверяем, что название в БД осталось исходным
    private_event.refresh_from_db()
    assert private_event.title != payload["title"]


@pytest.mark.django_db
def test_patch_invitee_event_forbidden(
    auth_client: APIClient,
    test_user: User,
    alien_user: User,
    private_event: Event,
    alien_event: Event,
):
    # 1. Синхронизируем параметры событий, чтобы сработал фильтр is_invitee_meeting
    alien_event.event_date = private_event.event_date
    alien_event.start_time = private_event.start_time
    alien_event.end_time = private_event.end_time
    alien_event.event_type = private_event.event_type
    alien_event.save()

    # 2. Создаем встречу: alien_user пригласил test_user
    Appointment.objects.create(
        event=alien_event, invitee=test_user, status=Appointment.Status.CONFIRMED
    )

    # 3. test_user (клиент auth_client) пытается изменить СВОЮ копию события
    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    payload = {"title": "Попытка ребенка изменить встречу"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    # 4. Проверяем отсечку валидатором EventUpdateSerializer
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors
    assert "Вас пригласили на встречу" in errors["non_field_errors"][0]

    # 5. Убеждаемся, что событие в БД не изменилось
    private_event.refresh_from_db()
    assert private_event.title != payload["title"]


@pytest.mark.django_db
def test_patch_event_time_collision(auth_client: APIClient, test_user: User, private_event: Event):
    # Создаем второе событие пользователя в этот же день
    Event.objects.create(
        user=test_user,
        event_type=Event.EventType.INTERVAL,
        title="Второе событие",
        event_date=private_event.event_date,
        start_time="14:00",
        end_time="16:00",
        is_public=False,
    )

    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    # Пытаемся сдвинуть private_event на 14:30 (попадает внутрь второго события)
    payload = {"start_time": "14:30"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors
    assert "Конфликт времён" in errors["non_field_errors"][0]


@pytest.mark.django_db
def test_patch_event_type_is_ignored(auth_client: APIClient, private_event: Event):
    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    payload = {"event_type": Event.EventType.ALL_DAY}

    response: Response = auth_client.patch(url, data=payload, format="json")

    # DRF не падает на лишних read-only полях, а молча их отбрасывает
    assert response.status_code == status.HTTP_200_OK

    private_event.refresh_from_db()
    # Тип не должен был измениться
    assert private_event.event_type != Event.EventType.ALL_DAY


@pytest.mark.django_db
def test_patch_interval_event_invalid_chronology(auth_client: APIClient, test_user: User):
    interval_event = Event.objects.create(
        user=test_user,
        event_type=Event.EventType.INTERVAL,
        title="Интервальное событие",
        event_date="2026-09-09",
        start_time="10:00",
        end_time="12:00",
        is_public=False,
    )

    url: str = reverse("api:private-events-detail", kwargs={"pk": interval_event.id})
    # Делаем конец интервала раньше начала (10:00 > 09:00)
    payload = {"end_time": "09:00"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors
    assert "Время начала должно быть строго раньше" in errors["non_field_errors"][0]


@pytest.mark.django_db
def test_patch_exact_event_late_night_truncation(auth_client: APIClient, private_event: Event):
    """
    Проверяет, что при частичном обновлении (PATCH) события 'exact',
    установка времени начала на > 23:29 приводит к обрезке end_time до 23:59
    и добавлению предупреждения в ответ.
    """
    url: str = reverse("api:private-events-detail", kwargs={"pk": private_event.id})

    # Сдвигаем время на 23:55 (что больше 23:29)
    payload = {"start_time": "23:55"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK

    updated_event: dict = response.json()

    assert updated_event["start_time"] == "23:55:00"
    assert updated_event["end_time"] == "23:59:00"
    assert "warning" in updated_event

    private_event.refresh_from_db()
    assert str(private_event.start_time) == "23:55:00"
    assert str(private_event.end_time) == "23:59:00"


@pytest.mark.django_db
def test_patch_all_day_mutates_to_exact_when_start_time_provided(
    auth_client: APIClient, public_event: Event
):
    """
    Проверяет, что при передаче только start_time событие all_day
    автоматически мутирует в exact с расчетом end_time (+30 мин).
    """
    # public_event из conftest имеет event_type='all_day'
    url: str = reverse("api:private-events-detail", kwargs={"pk": public_event.id})
    payload = {"start_time": "14:00"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK

    data: dict = response.json()
    assert data["event_type"] == Event.EventType.EXACT
    assert data["start_time"] == "14:00:00"
    assert data["end_time"] == "14:30:00"

    public_event.refresh_from_db()
    assert public_event.event_type == Event.EventType.EXACT
    assert str(public_event.start_time) == "14:00:00"
    assert str(public_event.end_time) == "14:30:00"


@pytest.mark.django_db
def test_patch_all_day_mutates_to_interval_when_both_times_provided(
    auth_client: APIClient, public_event: Event
):
    """
    Проверяет, что при передаче start_time и end_time событие all_day
    автоматически мутирует в interval.
    """
    url: str = reverse("api:private-events-detail", kwargs={"pk": public_event.id})
    payload = {"start_time": "10:00", "end_time": "12:00"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK

    data: dict = response.json()
    assert data["event_type"] == Event.EventType.INTERVAL
    assert data["start_time"] == "10:00:00"
    assert data["end_time"] == "12:00:00"

    public_event.refresh_from_db()
    assert public_event.event_type == Event.EventType.INTERVAL
    assert str(public_event.start_time) == "10:00:00"
    assert str(public_event.end_time) == "12:00:00"


@pytest.mark.django_db
def test_patch_move_interval_to_date_with_all_day_collision(
    auth_client: APIClient, test_user: User, private_event: Event
):
    """
    Проверяет, что нельзя перенести интервальное/точное событие на дату,
    где у пользователя уже запланировано событие 'all_day'.
    """
    target_date = date.today() + timedelta(days=1)
    
    # Создаем событие на весь день на целевую дату (завтра)
    Event.objects.create(
        user=test_user,
        event_type=Event.EventType.ALL_DAY,
        title="День отдыха",
        event_date=target_date,
        is_public=False,
    )

    url = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    payload = {"event_date": str(target_date)}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors
    assert "уже запланировано событие на весь день" in errors["non_field_errors"][0]


@pytest.mark.django_db
def test_patch_move_all_day_to_busy_date_collision(
    auth_client: APIClient, test_user: User, public_event: Event
):
    """
    Проверяет, что нельзя перенести событие 'all_day' на дату,
    где уже есть ЛЮБЫЕ другие события пользователя.
    """
    target_date = date.today() + timedelta(days=1)
    
    # Создаем обычное точечное событие на целевую дату (завтра)
    Event.objects.create(
        user=test_user,
        event_type=Event.EventType.INTERVAL,
        title="Обычное дело",
        event_date=target_date,
        start_time=time(10, 0),
        end_time=time(11, 0),
        is_public=False,
    )

    # public_event имеет тип all_day
    url = reverse("api:private-events-detail", kwargs={"pk": public_event.id})
    payload = {"event_date": str(target_date)}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors
    assert "Этот день уже занят" in errors["non_field_errors"][0]


@pytest.mark.django_db
def test_patch_exact_event_start_time_at_midnight_boundary_forbidden(
    auth_client: APIClient, private_event: Event
):
    """
    Проверяет запрет установки start_time на 23:59 для exact события при PATCH
    (защита от нулевой длительности).
    """
    url = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    payload = {"start_time": "23:59"}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "non_field_errors" in errors
    assert "не может быть позже 23:58" in errors["non_field_errors"][0]


@pytest.mark.django_db
def test_put_alien_event_returns_404(auth_client: APIClient, alien_event: Event):
    """
    Проверяет, что полный апдейт (PUT) чужого события отсекается с 404 Not Found (защита от IDOR).
    """
    url = reverse("api:private-events-detail", kwargs={"pk": alien_event.id})
    payload = {
        "title": "Попытка украсть событие через PUT",
        "event_date": str(alien_event.event_date),
        "start_time": "12:00",
        "is_public": False,
    }

    response: Response = auth_client.put(url, data=payload, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    alien_event.refresh_from_db()
    assert alien_event.title != payload["title"]


@pytest.mark.django_db
def test_patch_empty_title_forbidden(auth_client: APIClient, private_event: Event):
    """
    Проверяет валидацию пустого заголовка при частичном обновлении.
    """
    url = reverse("api:private-events-detail", kwargs={"pk": private_event.id})
    payload = {"title": ""}

    response: Response = auth_client.patch(url, data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors = response.json()
    assert "title" in errors