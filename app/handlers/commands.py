from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.core.calendar.services import CalendarService
from app.handlers.calendar_keyboard import generate_calendar_keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_user:
        # type: ignore[attr-defined]
        await context.application.user_service.register_visitor(update.effective_user.id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Добро пожаловать!")


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Глобальный диспетчер вывода инлайн-календаря.
    Автоматически адаптируется под тип вызова: текстовая команда или инлайн-клик.
    """
    # Защита от пустых апдейтов
    if not update.effective_chat or not update.effective_user:
        return ConversationHandler.END

    user_id = update.effective_user.id

    # 1. АДАПТИВНОЕ ОПРЕДЕЛЕНИЕ ЦЕЛЕВОЙ ДАТЫ
    # Если вызов прилетел из инлайн-кнопки и в ОЗУ есть ранее выбранная дата
    if update.callback_query and 'selected_date' in context.user_data:
        extracted_date = context.user_data['selected_date']
        year = extracted_date.year
        month = extracted_date.month
    else:
        # Падение в дефолт (команда /calendar или чистый запуск)
        now = datetime.now()
        year = now.year
        month = now.month

    # 2. ПОЛУЧЕНИЕ ДАННЫХ ИЗ БД
    async with context.application.database.connection() as conn:
        busy_days = await CalendarService.get_user_busy_days(
            conn=conn,
            user_id=user_id,
            year=year,
            month=month
        )

    # Синхронизируем кэш занятых дней в ОЗУ
    context.user_data['month_busy_days'] = busy_days

    # 3. ГЕНЕРАЦИЯ ИНТЕРФЕЙСА
    calendar_markup = generate_calendar_keyboard(
        year=year,
        month=month,
        busy_days=busy_days
    )

    text_content = "📅 Инлайн-Календарь\n\nВыберите день:"

    # 4. РАЗВЕТВЛЕНИЕ МЕТОДА ОТПРАВКИ
    if update.callback_query:
        # Вызов из инлайн-кнопки (например, "Изменить дату" или после удаления)
        # Редактируем старое сообщение, чтобы интерфейс не прыгал
        await update.callback_query.edit_message_text(
            text=text_content,
            reply_markup=calendar_markup
        )
    else:
        # Прямой вызов через текстовую команду /calendar
        # Отправляем новое чистое сообщение в чат
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text_content,
            reply_markup=calendar_markup
        )

    return ConversationHandler.END
