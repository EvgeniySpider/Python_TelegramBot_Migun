from datetime import datetime
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.handlers.calendar_keyboard import generate_calendar_keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_user:
        await context.application.user_service.register_visitor(update.effective_user.id)  # type: ignore[attr-defined]
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Добро пожаловать!")


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        now = datetime.now()
        # Строим JSON-инструкцию кнопок
        calendar_markup: InlineKeyboardMarkup = generate_calendar_keyboard(now.year, now.month)

        # Отправляем сообщение и прикрепляем к нему клавиатуру через reply_markup
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📅 **Инлайн-Календарь**\nВыберите интересующую вас дату:",
            reply_markup=calendar_markup,
            parse_mode="Markdown"
        )
