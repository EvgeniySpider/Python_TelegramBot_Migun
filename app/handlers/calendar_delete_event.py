from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.commands import calendar_command
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_act_with_options import confirm_to_delete, handle_back_to_day_menu_click
from app.core.calendar.utils import format_event_time, build_events_list_text


async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Главный диспетчер финального экрана подтверждения удаления (стейт CONFIRMING_DELETE).
    Разводит логику в зависимости от итогового вердикта пользователя.

    Варианты разветвления:
    1. Клик по кнопке "Да, удалить" ('confirm_delete_yes'):
       - Считывает параметры фильтрации из ОЗУ ('delete_event_id' и 'column_name').
       - Передаёт их в корутину del_event_on_info для физического удаления строк из PostgreSQL.
       - Вызывает деструктор prepare_after_delete для зачистки памяти и сброса стейта.

    2. Клик по кнопке "Нет, назад" (любые другие callback-данные):
       - Безопасно вычищает точечный таргет 'delete_event_id' из ОЗУ.
       - Извлекает нетронутый первоисточник 'event_text_record' и генерирует из него
         чистый список расписания дня через утилиту build_events_list_text.
       - Возвращает пользователя в главное меню управления днем (handle_options_with_exist_notes_in_day).

    Returns:
        int: Либо ConversationHandler.END (при удалении), либо CHOOSING_ACTION (при возврате назад).
    """

    query = update.callback_query

    # Если пользователь нажал "Да, удалить"
    if query.data == "confirm_delete_yes":
        event_id = context.user_data.get('delete_event_id')
        column_name = context.user_data.get('column_name', 'id')

        await del_event_on_info(context, column_name, event_id)
        state = await prepare_after_delete(update, context, query)
        return state

    # Если пользователь нажал "Нет, назад"
    else:
        context.user_data.pop('delete_event_id', None)
        state = await handle_back_to_day_menu_click(update, context)
        return state


async def prepare_after_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, query) -> int:
    """
    Выполняет посталгоритмическую очистку контекста пользователя после успешного удаления.

    Механика работы:
    1. Хирургически удаляет через .pop() временные ключи удаления ('delete_event_id')
       и кэш записей дня ('event_text_record'), предотвращая утечку неактуальных данных в ОЗУ.
    2. Изменяет текст текущего инлайн-сообщения, информируя об успешном стирании.
    3. Вызывает команду генерации календаря (calendar_command) для отображения
       обновленной сетки месяца с пересчитанными маркерами занятых дней.

    Returns:
        int: Состояние ConversationHandler.END для полной деактивации и завершения диалога.
    """

    # Подчищаем за собой оперативку
    context.user_data.pop('delete_event_id', None)
    context.user_data.pop('event_text_record', None)

    await query.edit_message_text(text="🗑️ Мероприятие успешно удалено!")
    # Вызываем календарь заново, чтобы юзер видел актуальную сетку месяца
    await calendar_command(update, context)
    return ConversationHandler.END


async def del_event_on_info(context: ContextTypes.DEFAULT_TYPE, column_name: str, value) -> None:
    """
    Интерфейс низкоуровневого взаимодействия с СУБД для удаления записей.
    Унифицирует обращения к репозиторию, изолируя контекст транзакции.

    Args:
        context (ContextTypes.DEFAULT_TYPE): Контекст телеграм-бота для доступа к пулу соединений базы данных.
        column_name (str): Имя целевого столбца в таблице базы данных ('id' или 'event_date') 
                           для фильтрации удаляемых строк.
        value (Any): Значение фильтра (конкретный целочисленный ID записи или объект datetime.date).
    """

    async with context.application.database.connection() as conn:
        await CalendarRepository.delete_events_by_filter(
            conn,
            column_name,
            value
        )


async def handle_delete_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Маршрутизирует удаление событий по кликам на инлайн-кнопки.
    Универсально обслуживает два стейта:
    - CHOOSING_EVENT_TO_DELETE (когда кнопок от 2 до 10)
    - TYPING_EVENT_NUMBER_TO_DELETE (перехватывает системные кнопки 'Назад' и 'Удалить все' при 10+ событиях)

    Варианты разветвления логики:
    1. Отмена операции ('del_num:cancel'):
       Перенаправляет управление в handle_delete_confirmation для возврата в главное меню.
       
    2. Удаление всех событий ('del_num:everything'):
       - Фиксирует в контексте групповые параметры: column_name = 'event_date' и delete_event_id = selected_date.
       - Формирует строковое превью всех уничтожаемых записей на дату.
       - Вызывает интерфейс подтверждения транзакции (confirm_to_delete).
       
    3. Выбор конкретной записи по номеру-кнопке ('del_num:X'):
       - Извлекает индекс (0-9) из callback_data.
       - Извлекает целевой объект Record из кэша context.user_data['event_text_record'].
       - Задает точечные параметры удаления: column_name = 'id' и delete_event_id = Record['id'].
       - Передаёт сформированный текст события в confirm_to_delete.

    Returns:
        int: Состояние CONFIRMING_DELETE для ожидания окончательного подтверждения.
    """

    query = update.callback_query
    event_text_record = context.user_data.get('event_text_record', [])

    if query.data == 'del_num:cancel':
        state = await handle_delete_confirmation(update, context)
        return state

    elif query.data == 'del_num:everything':
        selected_date = context.user_data.get('selected_date')

        # 1. Готовим таргеты для SQL-запроса (удаляем пачкой по дате)
        context.user_data['delete_event_id'] = selected_date
        context.user_data['column_name'] = 'event_date'

        # Магия: генерируем обычный красивый список для превью одной строчкой!
        events_preview = build_events_list_text(
            event_text_record, numbered=False) + "\n\n"

        # 3. Задаем динамический текст склонений для нашего универсального confirm_to_delete
        delete_text = (
            "⚠️ *АБСОЛЮТНО ВСЕ* мероприятия на этот день?",
            "**все существующие заметки** на эту дату! Восстановление будет невозможно."
        )

        state = await confirm_to_delete(query, events_preview, selected_date, delete_text)
        return state

    # Если нажата inline-кнопка с номером события
    else:
        id_event = int(query.data.split(':')[1])
        event_rec = event_text_record[id_event]

        context.user_data['delete_event_id'] = event_rec['id']
        context.user_data['column_name'] = 'id'

        selected_date = context.user_data.get('selected_date')
        delete_text = f"событие № {id_event + 1}?", 'заметку.'

        event_time = format_event_time(
            event_rec["start_time"], event_rec["end_time"])
        # Корректируем экранирование под твой успешный тест (2 знака)
        event = f"📌 *Событие*: \\[{event_time}] {event_rec['title']}\n"

        state = await confirm_to_delete(query, event, selected_date, delete_text)
        return state
