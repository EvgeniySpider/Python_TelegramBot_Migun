from telegram.ext import BaseHandler, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, filters
from app.handlers.commands import start, calendar_command
from app.handlers.calendar_callbacks import handle_calendar_click
from app.handlers.calendar_set_event import handle_set_event, handle_title_input
from app.handlers.states import CHOOSING_TIME, WAITING_FOR_TITLE


# 2. Собираем наш Конечный Автомат (FSM)
calendar_conversation = ConversationHandler(
    # Точка входа: с чего начинается сбор данных? С клика на дату в календаре!
    entry_points=[
        CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_day:")
    ],
    
    # Матрица шагов: на каком шаге какой хэндлер слушать?
    states={
        # Шаг 0: Бот выдал кнопки времени и ждет клика [Весь день / Интервал / Точное]
        CHOOSING_TIME: [
            CallbackQueryHandler(handle_set_event, pattern=r"^event_time:")
        ],
        
        # Шаг 1: Бот попросил текст названия и ждет от пользователя сообщение
        WAITING_FOR_TITLE: [
            # filters.TEXT & ~filters.COMMAND означает: "лови любой текст, кроме команд типа /start"
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_input)
        ]
    },
    
    # Кнопка паники: если пользователь в процессе ввода напишет /cancel, диалог сбросится
    fallbacks=[
        CommandHandler("cancel", lambda u, c: ConversationHandler.END) 
    ]
)

# 3. Теперь в глобальные хэндлеры мы кладем этот "коммутатор" целиком!
HANDLERS: tuple[BaseHandler, ...] = (
    CommandHandler("start", start),
    CommandHandler("calendar", calendar_command),
    # Навигацию по календарю (стрелочки) оставляем снаружи, она не начинает диалог ввода данных
    CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_nav:"), 
    # А вот клик по дате запускает наш FSM-процесс
    calendar_conversation,
)