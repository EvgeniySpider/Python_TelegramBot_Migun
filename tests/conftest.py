import pytest
from datetime import date, time
from rest_framework.test import APIClient
from django.utils import timezone

from events.models import Event, User


@pytest.fixture
def api_client() -> APIClient:
    """Возвращает стандартный неавторизованный клиент DRF."""
    return APIClient()


@pytest.fixture
def test_user(db) -> User:
    """
    Получает или создает тестового пользователя напрямую в БД.
    Фикстура 'db' гарантирует доступ к базе даже без явного маркера на тесте.
    """
    user, _ = User.objects.get_or_create(telegram_id=123456789)
    return user


@pytest.fixture
def public_event(test_user: User) -> Event:
    """Создает публичное событие напрямую в БД."""
    return Event.objects.create(
        user=test_user,
        event_type='all_day',
        title='Тестовое публичное событие',
        event_date=date.today(),
        is_public=True
    )


@pytest.fixture
def private_event(test_user: User) -> Event:
    """Создает приватное событие для проверки фильтрации."""
    return Event.objects.create(
        user=test_user,
        event_type='exact',
        title='Секретное событие',
        event_date=date.today(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        is_public=False
    )


@pytest.fixture
def auth_client(api_client: APIClient, test_user: User) -> APIClient:
    """Авторизует клиента в обход проверки токенов (DRF way)."""
    api_client.force_authenticate(user=test_user)
    return api_client


@pytest.fixture
def alien_user(db) -> User:
    """Создает стороннего пользователя для проверки изоляции данных."""
    return User.objects.create(telegram_id=999999999)


@pytest.fixture
def alien_event(alien_user: User) -> Event:
    """Создает публичное событие, принадлежащее чужому пользователю."""
    return Event.objects.create(
        user=alien_user,
        event_type='all_day',
        title='Событие другого пользователя',
        event_date=date.today(),
        is_public=True
    )
