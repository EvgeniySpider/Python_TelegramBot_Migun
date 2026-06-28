from app.handlers.calendar_callbacks import handle_options_with_exist_notes_in_day
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.commands import calendar_command
from app.handlers.states import CHOOSING_ACTION
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_act_with_options import confirm_to_delete
from app.core.calendar.utils import format_event_time, build_events_list_text


async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        event_text_record = context.user_data.get('event_text_record', [])
        selected_date = context.user_data.get('selected_date')
        
        # Получаем готовую строку со всеми заголовками из утилиты
        events_text = build_events_list_text(event_text_record, numbered=False)
        
        args = (query, selected_date.day, selected_date.month, selected_date.year)
        await handle_options_with_exist_notes_in_day(events_text, args)
        return CHOOSING_ACTION


async def prepare_after_delete(update, context, query):
    # Подчищаем за собой оперативку
    context.user_data.pop('delete_event_id', None)
    context.user_data.pop('event_text_record', None)

    await query.edit_message_text(text="🗑️ Мероприятие успешно удалено!")
    # Вызываем календарь заново, чтобы юзер видел актуальную сетку месяца
    await calendar_command(update, context)
    return ConversationHandler.END


async def del_event_on_info(context, column_name, value) -> None:
    async with context.application.database.connection() as conn:
        await CalendarRepository.delete_events_by_filter(
            conn,
            column_name,
            value
        )


async def handle_delete_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        event = f"📌 *Событие*: \\[{event_time}\\] {event_rec['title']}\n"

        state = await confirm_to_delete(query, event, selected_date, delete_text)
        return state
