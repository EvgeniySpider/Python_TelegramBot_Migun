from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.handlers.calendar_callbacks import handle_time_selection_option
from app.handlers.commands import calendar_command
from app.handlers.states import CHOOSING_ACTION, CHOOSING_EVENT_TO_DELETE, CONFIRMING_DELETE
from app.handlers.calendar_keyboard import generate_confirm_keyboard, generate_numbered_events_keyboard


async def handle_options_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    selected_date = context.user_data.get('selected_date')
    current_day_events = context.user_data.get('current_day_events', [])
    events_text = context.user_data.get('events_text', None)

    # Проверяем, какая именно кнопка была нажата
    if query.data == "action_create":
        month_busy_days = context.user_data.get('month_busy_days', {})

        if month_busy_days.get(selected_date.day) == 'full':
            await query.answer(
                text=f'❌ Ошибка: этот день полностью занят.\n'
                f'Выберите другую дату\n',
                show_alert=False
            )
            return CHOOSING_ACTION

        args = (query, selected_date.day,
                selected_date.month, selected_date.year)

        # Напрямую вызываем корутину и возвращаем её стейт (CHOOSING_TIME)
        state = await handle_time_selection_option(args, events_text)
        return state

    # Заглушки под остальные кнопки на будущее
    elif query.data == "action_edit":
        pass

    elif query.data == "action_delete":
        event_count = len(current_day_events)
        # СЦЕНАРИЙ 1: Событие ровно одно и это "Весь день"
        # Проверяем либо через структуру данных, либо через твою идею с текстом: "(весь день)" in events_text
        if event_count == 1:
            event_rec = current_day_events[0]

            # Сохраняем ID этого единственного события в контекст для будущего SQL-запроса DELETE
            context.user_data['delete_event_id'] = event_rec['id']
            context.user_data['column_name'] = 'id'
            first_sent = 'мероприятие на весь день?' if current_day_events[0]['event_type'] == 'all_day' else 'мероприятие?'
            delete_text = first_sent, 'заметку.'
            event = f'📌 *Событие*: {event_rec['title']}\n' 

            # async def confirm_to_delete(query, event, selected_date, delete_text):
            state = await confirm_to_delete(query, event, selected_date, delete_text)
            return state

        # СЦЕНАРИИ 2 и 3: Событий несколько
        else:
            if event_count < 11:
                numbered_events = []
                for i, rec in enumerate(current_day_events):
                    st_time = f'{rec["start_time"].hour:02d}:{rec["start_time"].minute:02d}'
                    end_time = f'{rec["end_time"].hour:02d}:{rec["end_time"].minute:02d}'
                    st = f'[ {i+1} ]    {st_time} - {end_time} {rec['title']}'

                    numbered_events.append(st)

                await query.edit_message_text(
                    text="Нажмите на номер события который хотите удалить\n\n"
                    f'{'\n'.join(numbered_events)}',
                    reply_markup=generate_numbered_events_keyboard(event_count)
                )

                return CHOOSING_EVENT_TO_DELETE
            else:
                pass


# --- ТОЧЕЧНЫЙ ХЭНДЛЕР ВОЗВРАТА К КАЛЕНДАРЮ ---
async def handle_back_to_calendar_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Гасим часики
    await update.callback_query.answer()
    await calendar_command(update, context)
    return ConversationHandler.END


async def confirm_to_delete(query, event, selected_date, delete_text):
    await query.edit_message_text(
        text=f"❓ *Вы уверены, что хотите удалить {delete_text[0]}*\n\n"
        f"{event}"
        f"📅 *Дата*: {selected_date.day:02d}.{selected_date.month:02d}.{selected_date.year}\n\n"
        f"⚠️ Это действие полностью сотрёт {delete_text[1]}",
        reply_markup=generate_confirm_keyboard(),
        parse_mode="Markdown"
    )
    return CONFIRMING_DELETE
