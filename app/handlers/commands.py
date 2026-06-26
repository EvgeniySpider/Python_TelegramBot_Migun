from datetime import datetime
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.core.calendar.services import CalendarService
from app.handlers.calendar_keyboard import generate_calendar_keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_user:
        # type: ignore[attr-defined]
        await context.application.user_service.register_visitor(update.effective_user.id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Добро пожаловать!")


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Защита от пустых апдейтов
    if not update.effective_chat or not update.effective_user:
        return

    user_id = update.effective_user.id
    now = datetime.now()

    async with context.application.database.connection() as conn:
        # Запрашиваем из бизнес-логики сет занятых дней
        busy_days = await CalendarService.get_user_busy_days(
            conn=conn,
            user_id=user_id,
            year=now.year,
            month=now.month
        )
    context.user_data['month_busy_days'] = busy_days
    # 3. Генерируем клавиатуру с учётом полученных галочек
    calendar_markup: InlineKeyboardMarkup = generate_calendar_keyboard(
        year=now.year,
        month=now.month,
        busy_days=busy_days
    )

    # 4. Отправляем сообщение пользователю
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📅 **Инлайн-Календарь**\nВыберите интересующую вас дату:",
        reply_markup=calendar_markup,
        parse_mode="Markdown"
    )
