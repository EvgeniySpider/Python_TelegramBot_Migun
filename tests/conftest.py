import pytest
from datetime import date, time
from rest_framework.test import APIClient

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