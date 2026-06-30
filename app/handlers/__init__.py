from telegram.ext import (
    BaseHandler, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ConversationHandler, 
    filters
)
from app.handlers.commands import start, calendar_command
from app.handlers.calendar_act_with_options import (
    handle_options_click,
    handle_back_to_calendar_click,
    handle_delete_event_by_number,
    handle_back_to_day_menu_click
)
from app.handlers.calendar_callbacks import handle_calendar_click, handle_calendar_nav_click
from app.handlers.calendar_delete_event import handle_delete_confirmation, handle_delete_choice
from app.handlers.calendar_set_event import (
    handle_set_event,
    handle_title_input,
    handle_desc_choice,
    handle_description_input,
    handle_time_input_exact,
    handle_time_input_interval,
)
from app.handlers.states import (
    CHOOSING_TIME,
    WAITING_FOR_TITLE,
    WAITING_FOR_DESC_CHOICE,
    WAITING_FOR_DESCRIPTION,
    CHOOSING_ACTION,
    WAITING_FOR_TIME_INPUT_EXACT,
    WAITING_FOR_TIME_INPUT_INTERVAL,
    CONFIRMING_DELETE,
    CHOOSING_EVENT_TO_DELETE,
    TYPING_EVENT_NUMBER_TO_DELETE
)

# ============================================================================
# ГЛАВНЫЙ ДИАЛОГОВЫЙ СЦЕНАРИЙ МОДУЛЯ КАЛЕНДАРЯ (FSM)
# ============================================================================
calendar_conversation = ConversationHandler(
    # Точка входа в диалог: срабатывает исключительно при клике на конкретный день месяца
    entry_points=[
        CallbackQueryHandler(handle_calendar_click, pattern=r"^calendar_day:")
    ],
    
    states={
        # СТEЙТ 1: Главное меню выбранного дня (когда в дне уже есть события)
        CHOOSING_ACTION : [
            # Перехват действий пользователя: Создать новое, Редактировать или Удалить запись
            CallbackQueryHandler(handle_options_click, pattern=r"^(action_create|action_edit|action_delete)$"),
            # Кнопка возврата к общей сетке календаря на текущий месяц
            CallbackQueryHandler(handle_back_to_calendar_click, pattern=r"^action_back_to_calendar$")
        ],
        
        # СТEЙТ 2: Экран окончательного подтверждения деструктивных операций (Да/Нет)
        CONFIRMING_DELETE : [
            # Реагирует строго на кнопки подтверждения 'confirm_delete_yes' или отмены 'confirm_delete_no'
            CallbackQueryHandler(handle_delete_confirmation, pattern=r"^confirm_delete_(yes|no)$")
        ],
        
        # СТEЙТ 3: Меню выбора мишени удаления через инлайн-кнопки (при количестве событий от 2 до 10)
        CHOOSING_EVENT_TO_DELETE : [
            # Ловит паттерны номеров 'del_num:0', 'del_num:1', а также системные 'cancel' и 'everything'
            CallbackQueryHandler(handle_delete_choice, pattern=r"^del_num:.+$")
        ],
        
        # СТEЙТ 4: Меню удаления через клавиатуру (при количестве событий более 10)
        TYPING_EVENT_NUMBER_TO_DELETE : [
            # Хэндлер 1: Перехватывает валидный текст (цифру номера события) от пользователя
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_event_by_number),
            # Хэндлер 2: Твоя точечная регулярка для обработки системных инлайн-кнопок под списком
            CallbackQueryHandler(handle_delete_choice, pattern=r"^(del_num:everything|del_num:cancel)$")
        ],
        
        # СТEЙТ 5: Выбор типа создаваемого мероприятия (Праздный день или после клика «Создать»)
        CHOOSING_TIME: [
            # Перехват клика по кнопкам: "Весь день", "Точное время" или "Интервал"
            CallbackQueryHandler(handle_set_event, pattern=r"^event_time:.+$"),
            # Позволяет прервать сценарий создания и вернуться в сетку месяца
            CallbackQueryHandler(handle_back_to_day_menu_click, pattern=r"^back_to_day_menu$"),
            CallbackQueryHandler(handle_back_to_calendar_click, pattern=r"^action_back_to_calendar$"),
        ],
        
        # СТEЙТ 6: Ожидание ввода точного времени начала (формат ЧЧ:ММ, например 14:15)
        WAITING_FOR_TIME_INPUT_EXACT: [
            # Ловит только текст, исключая команды, для последующего расчета +30 минут к интервалу
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input_exact)
        ],
        
        # СТEЙТ 7: Ожидание ввода временного интервала (формат ЧЧ:ММ-ЧЧ:ММ, например 12:00-14:30)
        WAITING_FOR_TIME_INPUT_INTERVAL : [
            # Передаёт строку на жесткую валидацию регулярным выражением и проверку конфликтов в БД
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input_interval)
        ],
        
        # СТEЙТ 8: Сбор текстового заголовка (названия) создаваемого события
        WAITING_FOR_TITLE: [
            # Сохраняет введенную строку в контекст как event_title и предлагает добавить описание
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_input)
        ],
        
        # СТEЙТ 9: Выбор необходимости заполнения поля "Описание"
        WAITING_FOR_DESC_CHOICE: [
            # Обрабатывает инлайн-кнопки [Да] (перевод в WAITING_FOR_DESCRIPTION) или [Нет] (быстрая запись в БД)
            CallbackQueryHandler(handle_desc_choice, pattern=r"^desc_(yes|no)$")
        ],
        
        # СТEЙТ 10: Ожидание развернутого текстового описания (заметки) к событию
        WAITING_FOR_DESCRIPTION: [
            # Финальный текстовый хэндлер, после которого данные улетают в базу данных PostgreSQL
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description_input)
        ]
    },
    
    # Системные команды экстренного выхода, доступные пользователю на любом этапе диалога
    fallbacks=[
        # Принудительное закрытие диалога и сброс текущего состояния автомата
        CommandHandler("cancel", lambda u, c: ConversationHandler.END),
        # Сброс текущей ветки и вызов свежего календаря поверх старого интерфейса
        CommandHandler("calendar", calendar_command)
    ],
    
    # Архитектурные флаги изоляции контекстов
    per_message=False,  # Состояние привязано к чату/юзеру, а не к конкретному сообщению
    per_chat=True,      # Изолирует состояния внутри конкретного чата
    per_user=True,      # Гарантирует, что разные пользователи не пересекутся в одном стейте
    allow_reentry=True  # Позволяет повторно входить в ConversationHandler без конфликтов
)

# ============================================================================
# КОРНЕВОЙ НАБОР ХЭНДЛЕРОВ ПРИЛОЖЕНИЯ (Глобальный scope)
# ============================================================================
HANDLERS: tuple[BaseHandler, ...] = (
    # Первичная инициализация пользователя при первом запуске бота
    CommandHandler("start", start),
    # Главная команда вызова интерактивного календаря текущего месяца
    CommandHandler("calendar", calendar_command),
    # Навигационные кнопки календаря: переключение месяцев (<< Вперед / Назад >>)
    # Вынесено из ConversationHandler, так как навигация должна работать всегда, 
    # независимо от того, находится ли юзер внутри процесса создания/удаления заметок
    CallbackQueryHandler(handle_calendar_nav_click, pattern=r"^calendar_nav:"), 
    # Подключение основной машины состояний
    calendar_conversation,
)