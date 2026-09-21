from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.handlers.commands import calendar_command
from app.handlers.states import TYPING_INVITEE_ID

async def handle_invitee_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ловит текстовое сообщение с Telegram ID для приглашения на встречу."""

    # 1. Получаем ввод пользователя
    invitee_id_str = update.message.text.strip()
    inviter_id = update.effective_user.id
    
    # 2. Достаем ID целевого события из памяти
    event_id = context.user_data.get('invite_event_id')
    
    if not event_id:
        await update.message.reply_text(
            "⚠️ Сессия устарела или событие потерялось из памяти. Возвращаю вас в календарь"
        )
        # Возвращаем пользователя в календарь
        return await calendar_command(update, context) 

    # 3. Базовая валидация ввода
    if not invitee_id_str.isdigit():
        await update.message.reply_text("❌ Telegram ID должен состоять только из цифр. Попробуйте еще раз:")
        return TYPING_INVITEE_ID # Оставляем пользователя в этом же стейте для повторного ввода

    invitee_id = int(invitee_id_str)
    
    if inviter_id == invitee_id:
        await update.message.reply_text("❌ Вы не можете пригласить самого себя. Введите ID другого пользователя:")
        return TYPING_INVITEE_ID

    # TODO: Здесь будет вызов сервисного слоя для работы с БД (проверка занятости, создание Appointment)
    
    # Заглушка для проверки
    await update.message.reply_text(f"✅ Введен валидный ID: {invitee_id} для события {event_id}")
    
    context.user_data.pop('invite_event_id', None)
    return ConversationHandler.END