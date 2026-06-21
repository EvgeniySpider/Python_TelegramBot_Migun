from telegram.ext import (
    BaseHandler, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ConversationHandler, 
    filters
)
from app.handlers.commands import start, calendar_command
from app.handlers.calendar_callbacks import handle_calendar_click
from app.handlers.calendar_set_event import handle_set_event, handle_title_input
from app.handlers.states import CHOOSING_TIME, WAITING_FOR_TITLE

calendar_conversation = ConversationHandler(
    # Точка входа: клик по дате
    entry_points=[
        CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_day:")
    ],
    
    states={
        # Шаг 0: Ждем клика по формату времени
        CHOOSING_TIME: [
            CallbackQueryHandler(handle_set_event, pattern=r"^event_time:.+$")
        ],
        
        # Шаг 1: Ждем обычный текст от пользователя
        WAITING_FOR_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_input)
        ]
    },
    
    fallbacks=[
        CommandHandler("cancel", lambda u, c: ConversationHandler.END) 
    ],
    
    # Настройки отслеживания: по юзеру в текущем чате
    per_message=False,
    per_chat=True,
    per_user=True,
    allow_reentry=True  # Позволяет перезапустить диалог, если юзер кликнет на другую дату
)

# Глобальный кортеж хэндлеров для main.py
HANDLERS: tuple[BaseHandler, ...] = (
    CommandHandler("start", start),
    CommandHandler("calendar", calendar_command),
    # Навигация (стрелочки месяца) живет отдельно, она не ломает FSM шаги
    CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_nav:"), 
    # Запуск автомата по клику на дату
    calendar_conversation,
)