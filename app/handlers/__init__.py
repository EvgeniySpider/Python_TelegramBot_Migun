from telegram.ext import (
    BaseHandler, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ConversationHandler, 
    filters
)
from app.handlers.commands import start, calendar_command
from app.handlers.calendar_act_with_options import handle_options_click, handle_back_to_calendar_click
from app.handlers.calendar_callbacks import handle_calendar_click
from app.handlers.calendar_set_event import (
    handle_set_event,
    handle_title_input,
    handle_desc_choice,
    handle_description_input,
    handle_time_input_exact,
    handle_time_input_interval
)
from app.handlers.states import (
    CHOOSING_TIME,
    WAITING_FOR_TITLE,
    WAITING_FOR_DESC_CHOICE,
    WAITING_FOR_DESCRIPTION,
    CHOOSING_ACTION,
    WAITING_FOR_TIME_INPUT_EXACT,
    WAITING_FOR_TIME_INPUT_INTERVAL
)

calendar_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_day:")
    ],
    
    states={
        CHOOSING_ACTION : [
            CallbackQueryHandler(handle_options_click, pattern=r"^(action_create|action_edit|action_delete)$"),
            CallbackQueryHandler(handle_back_to_calendar_click, pattern=r"^action_back_to_calendar$")
        ],
        CHOOSING_TIME: [
            # Ловим ТОЛЬКО кнопки времени (Весь день, Интервал, Точное время)
            CallbackQueryHandler(handle_set_event, pattern=r"^event_time:.+$"),

            # Точечный перехватчик кнопки "Назад"! Он сработает ТОЛЬКО на неё.
            CallbackQueryHandler(handle_back_to_calendar_click, pattern=r"^action_back_to_calendar$")
        ],
        WAITING_FOR_TIME_INPUT_EXACT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input_exact)
        ],
        WAITING_FOR_TIME_INPUT_INTERVAL : [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input_interval)
        ],
        WAITING_FOR_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_input)
        ],
        
        # Шаг 2: Ждем клика по инлайн-кнопкам [Да] или [Нет]
        WAITING_FOR_DESC_CHOICE: [
            CallbackQueryHandler(handle_desc_choice, pattern=r"^desc_(yes|no)$")
        ],
        
        # Шаг 3: Ждем текст описания от пользователя
        WAITING_FOR_DESCRIPTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description_input)
        ]
    },
    
    fallbacks=[
        CommandHandler("cancel", lambda u, c: ConversationHandler.END) 
    ],
    
    per_message=False,
    per_chat=True,
    per_user=True,
    allow_reentry=True
)

HANDLERS: tuple[BaseHandler, ...] = (
    CommandHandler("start", start),
    CommandHandler("calendar", calendar_command),
    CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_nav:"), 
    calendar_conversation,
)