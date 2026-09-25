import os
from datetime import timedelta
from django.utils import timezone
from telegram import Update
from telegram.ext import ContextTypes

from events.models import User


async def api_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Выдает пользователю API-токен. 
    Если токен существует и не истек — показывает его.
    Если истек или отсутствует — генерирует новый.
    """
    telegram_id = update.effective_user.id
    
    try:
        user = await User.objects.aget(telegram_id=telegram_id)
    except User.DoesNotExist:
        await update.message.reply_text("Сначала зарегистрируйтесь в боте (введите /start).")
        return

    # Получаем время жизни из .env (по умолчанию 30 минут)
    lifetime_minutes = int(os.getenv("API_TOKEN_LIFETIME_MINUTES", 30))
    now = timezone.now()

    # Проверяем валидность текущего токена
    is_valid = False
    if user.api_token and user.api_token_created_at:
        expiration_time = user.api_token_created_at + timedelta(minutes=lifetime_minutes)
        if now < expiration_time:
            is_valid = True
            minutes_left = int((expiration_time - now).total_seconds() // 60)

    if is_valid:
        text = (
            f"🔑 <b>Ваш текущий API-токен:</b>\n\n"
            f"<code>{user.api_token}</code>\n\n"
            f"⏳ Истекает через: <b>{minutes_left} мин.</b>\n"
            f"<i>Никому не передавайте этот ключ!</i>"
        )
    else:
        new_token = await user.aroll_api_token()
        text = (
            f"✅ <b>Сгенерирован новый API-токен:</b>\n\n"
            f"<code>{new_token}</code>\n\n"
            f"⏳ Срок действия: <b>{lifetime_minutes} мин.</b>\n"
            f"<i>Никому не передавайте этот ключ!</i>"
        )

    await update.message.reply_text(text, parse_mode="HTML")