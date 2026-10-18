from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone

from events.models import User
from app.main import settings


@pytest.mark.django_db
def test_authentication_success(api_client: APIClient, test_user: User):
    """Проверка успешной авторизации по живому токену."""
    test_user.api_token = "valid_secret_token"
    test_user.api_token_created_at = timezone.now()
    test_user.save()

    url = reverse("api:private-events-list")
    # Передаем реальный заголовок, как это сделает фронтенд
    response = api_client.get(url, HTTP_AUTHORIZATION="Token valid_secret_token")
    
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_authentication_expired_token(api_client: APIClient, test_user: User):
    """Проверка отсечения протухшего токена."""
    test_user.api_token = "expired_secret_token"
    # Имитируем, что токен был создан давно (больше лимита из настроек)
    lifetime = settings.api_token_lifetime_minutes
    test_user.api_token_created_at = timezone.now() - timedelta(minutes=lifetime + 5)
    test_user.save()

    url = reverse("api:private-events-list")
    response = api_client.get(url, HTTP_AUTHORIZATION="Token expired_secret_token")
    
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_authentication_invalid_header_format(api_client: APIClient, test_user: User):
    """Проверка защиты от неверного формата заголовка."""
    url = reverse("api:private-events-list")
    # Например, просто передали токен без префикса Token/Bearer
    response = api_client.get(url, HTTP_AUTHORIZATION="just_token_without_prefix")
    
    assert response.status_code == status.HTTP_403_FORBIDDEN