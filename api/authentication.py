import os
from datetime import timedelta
from django.utils import timezone
from events.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from settings.config import AppSettings


class BotTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        # Достаем заголовок из запроса
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return None  # DRF пойдет проверять другие классы авторизации (если они есть)
            
        # Ожидаем формат "Token <ключ>" или "Bearer <ключ>"
        try:
            prefix, token = auth_header.split()
            if prefix.lower() not in ['token', 'bearer']:
                return None
        except ValueError:
            raise AuthenticationFailed('Неверный формат заголовка. Ожидается "Token <ключ>".')

        # Ищем пользователя по токену
        try:
            user = User.objects.get(api_token=token)
        except User.DoesNotExist:
            raise AuthenticationFailed('Неверный токен.')

        # Проверяем срок годности
        lifetime_minutes: int = AppSettings.api_token_lifetime_minutes
        if user.api_token_created_at:
            expiration_time = user.api_token_created_at + timedelta(minutes=lifetime_minutes)
            if timezone.now() > expiration_time:
                raise AuthenticationFailed('Срок действия токена истек.')
        else:
            raise AuthenticationFailed('Некорректный токен (отсутствует дата создания).')

        # DRF автоматически запишет эти данные в request.user и request.auth во вьюхах
        return (user, token)