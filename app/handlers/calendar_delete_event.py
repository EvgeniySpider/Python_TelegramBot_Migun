from app.handlers.calendar_callbacks import handle_options_with_exist_notes_in_day
from telegram import Update
from telegram.ext import ContextTypes,  ConversationHandler
from app.handlers.commands import calendar_command
from app.handlers.states import CHOOSING_ACTION
from app.core.calendar.repositories import CalendarRepository
from app.handlers.calendar_act_with_options import confirm_to_delete


async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # Если пользователь нажал "Да, удалить"
    if query.data == "confirm_delete_yes":

        event_id = context.user_data.get('delete_event_id')
        selected_date = context.user_data.get('selected_date')
        column_name = context.user_data.get('column_name', 'id')

        await del_event_on_info(context, column_name, event_id)
        state = await prepare_after_delete(update, context, query)
        return state

    # Если пользователь нажал "Нет, назад"
    else:
        # Чистим только ID удаления, массив событий оставляем
        context.user_data.pop('delete_event_id', None)
        events_text = context.user_data.get('events_text', "")
        selected_date = context.user_data.get('selected_date')
        # Возвращаем меню из 3-х кнопок ("Добавить", "Изменить", "Удcaалить")
        args = (query, selected_date.day,
                selected_date.month, selected_date.year)
        await handle_options_with_exist_notes_in_day(events_text, args)
        return CHOOSING_ACTION


async def prepare_after_delete(update, context, query):
    # Подчищаем за собой оперативку
    context.user_data.pop('delete_event_id', None)
    context.user_data.pop('current_day_events', None)
    context.user_data.pop('events_text', None)
    # Оповещаем пользователя и сразу вызываем календарь, чтобы обновить интерфейс
    # Для этого вызываем твой готовый calendar_command
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
    current_day_events = context.user_data.get('current_day_events', [])

    if query.data == 'del_num:cancel':
        state = await handle_delete_confirmation(update, context)
        return state
    elif query.data == 'del_num:everything':
        pass
    else:
        # 1. Получаем индекс кликнутой цифровой кнопки (0, 1, 2...)
        id_event = int(query.data.split(':')[1])

        # 2. Забираем конкретный Record-объект из нашего списка в ОЗУ по этому индексу
        event_rec = current_day_events[id_event]

        # 3. Сохраняем точечные данные для удаления в контекст (для будущей корутины подтверждения)
        context.user_data['delete_event_id'] = event_rec['id']
        context.user_data['column_name'] = 'id'

        # 4. Забираем дату из контекста
        selected_date = context.user_data.get('selected_date')

        # 5. Формируем динамический текст: какое именно событие удаляем
        delete_text = f"событие № {id_event + 1}?"

        # 6. Красиво форматируем время для вывода на экран подтверждения через strftime
        st_time = event_rec["start_time"].strftime("%H:%M")
        end_time = event_rec["end_time"].strftime("%H:%M")
        event = f"📌 *Событие*: [{st_time} - {end_time}] {event_rec['title']}\n"

        state = await confirm_to_delete(query, event, selected_date, delete_text)

        # 8. Возвращаем стейт CONFIRMING_DELETE, который прилетел из корутины
        return state
