import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from datetime import date, time
from events.models import Event, User

# ==========================================
# ФИКСТУРЫ (Подготовка данных)
# ==========================================

@pytest.fixture
def api_client() -> APIClient:
    """Возвращает стандартный клиент DRF для имитации HTTP-запросов."""
    return APIClient()

@pytest.fixture
def test_user():
    """Получает или создает тестового пользователя напрямую в БД."""
    # Используем get_or_create, чтобы избежать IntegrityError,
    # если фикстура вызовется несколько раз.
    user, _ = User.objects.get_or_create(telegram_id=123456789)
    return user

@pytest.fixture
def public_event(test_user):
    """Создает публичное событие напрямую в БД."""
    return Event.objects.create(
        user=test_user,
        event_type='all_day',
        title='Тестовое публичное событие',
        event_date=date.today(),
        is_public=True
    )

@pytest.fixture
def private_event(test_user):
    """Создает приватное событие, чтобы проверить, что ручка его НЕ отдаст."""
    return Event.objects.create(
        user=test_user,
        event_type='exact',
        title='Секретное событие',
        event_date=date.today(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        is_public=False
    )

# ==========================================
# САМ ТЕСТ
# ==========================================

@pytest.mark.django_db
def test_get_public_events_list(api_client, public_event, private_event):
    # 1. Генерируем URL по его имени (вернет '/api/events/')
    url = reverse('api:public-events-list')
    
    # 2. Делаем анонимный GET-запрос
    response = api_client.get(url)
    
    # 3. Проверяем статус-код
    assert response.status_code == 200
    
    # 4. Проверяем, что в ответе только публичное событие
    data = response.json()
    
    # Проверяем, что вернулась ровно 1 запись (приватное событие отфильтровалось)
    assert len(data) == 1
    # Проверяем значения полей
    assert data[0]['title'] == 'Тестовое публичное событие'
    assert data[0]['is_public'] is True