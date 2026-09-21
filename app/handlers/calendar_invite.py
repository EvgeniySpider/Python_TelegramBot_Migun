from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.handlers.calendar_keyboard import generate_back_to_menu_button
from app.handlers.commands import calendar_command
from app.handlers.states import TYPING_INVITE_NUM, TYPING_INVITEE_ID
from app.handlers.utils import get_validated_event_index
from events.models import User, Event, Appointment
from app.core.calendar.services import check_user_availability


async def handle_invite_event_by_text_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор события для приглашения через текстовый ввод номера (когда задач > 10).
    Делегирует проверку ввода и вычисление машинного индекса функции get_validated_event_index.
    При успешной валидации сохраняет ID выбранного события в ОЗУ (invite_event_id) 
    и переводит диалог в режим ожидания ввода Telegram ID гостя.

    Возвращает стейт TYPING_INVITEE_ID при успехе, либо стейт повторного ввода при ошибке.
    """
    # Одной строкой извлекаем и статус, и индекс, и сам массив событий
    is_valid, result, event_text_record = await get_validated_event_index(
        update, context, TYPING_INVITE_NUM
    )
    
    if not is_valid:
        return result
    index_record = result

    context.user_data['invite_event_id'] = event_text_record[index_record]['id']
    event_title = event_text_record[index_record]['title']

    text = (
        f"Выбрано событие: *{event_title}*\n\n"
        "Пожалуйста, *отправьте Telegram ID* пользователя, которого хотите пригласить:"
    )

    await update.message.reply_text(
        text=text,
        reply_markup=generate_back_to_menu_button(),
        parse_mode="Markdown"
    )
    return TYPING_INVITEE_ID


async def handle_invite_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор события для приглашения через инлайн-кнопку (когда задач <= 10).
    Извлекает индекс из callback_data, фиксирует целевой ID события в ОЗУ (invite_event_id)
    и переводит диалог в режим ожидания ввода Telegram ID гостя.
    
    Возвращает стейт TYPING_INVITEE_ID.
    """
    query = update.callback_query
    await query.answer()

    raw_click_data: str = query.data
    index_record: int = int(raw_click_data.split(':')[-1])

    event_text_record = context.user_data.get('event_text_record')

    context.user_data['invite_event_id'] = event_text_record[index_record]['id']
    event_title = event_text_record[index_record]['title']

    text = (
        f"Выбрано событие: *{event_title}*\n\n"
        "Пожалуйста, *отправьте Telegram ID* пользователя, которого хотите пригласить:"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=generate_back_to_menu_button(),
        parse_mode="Markdown"
    )
    return TYPING_INVITEE_ID


async def handle_invitee_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Ловит и валидирует Telegram ID. Проверяет наличие пользователя в БД и его 
    занятость. При успехе создает приглашение со статусом PENDING.
    """
    invitee_id_str = update.message.text.strip()
    inviter_id = update.effective_user.id
    
    event_id = context.user_data.get('invite_event_id')
    if not event_id:
        await update.message.reply_text("⚠️ Сессия устарела. Возвращаю вас в календарь.")
        return await calendar_command(update, context) 

    if not invitee_id_str.isdigit():
        await update.message.reply_text("❌ Telegram ID должен состоять только из цифр. Попробуйте еще раз:")
        return TYPING_INVITEE_ID

    invitee_id = int(invitee_id_str)
    
    if inviter_id == invitee_id:
        await update.message.reply_text("❌ Вы не можете пригласить самого себя. Введите ID другого пользователя:")
        return TYPING_INVITEE_ID

    # 1. Проверяем, существует ли пользователь в базе (Django ORM)
    user_exists = await User.objects.filter(telegram_id=invitee_id).aexists()
    if not user_exists:
        await update.message.reply_text(
            "❌ Пользователь с таким ID не зарегистрирован в нашем боте.\n"
            "Проверьте ID и попробуйте еще раз:"
        )
        return TYPING_INVITEE_ID

    # 2. Достаем целевое событие
    target_event = await Event.objects.aget(id=event_id)

    # 3. Валидация пересечения временных интервалов
    is_busy = await check_user_availability(invitee_id, target_event)
    
    if is_busy:
        await update.message.reply_text(
            "⚠️ К сожалению, в это время пользователь **уже занят** (у него запланировано другое событие).\n\n"
            "Встреча не назначена. Выберите другое время или пригласите кого-то еще."
        )
        context.user_data.pop('invite_event_id', None)
        return await calendar_command(update, context) # Возвращаем в календарь при неудаче

    # 4. Если свободен — создаем запись в таблице appointments
    # get_or_create защищает от дублирования приглашения на одно и то же событие
    appointment, created = await Appointment.objects.aget_or_create(
        event_id=target_event.id,
        invitee_id=invitee_id,
        defaults={'status': Appointment.Status.PENDING}
    )

    if not created:
        await update.message.reply_text("ℹ️ Вы уже отправляли приглашение этому пользователю на данное событие.")
    else:
        # TODO: Добавить логику отправки сообщения (inline-кнопок) самому гостю
        await update.message.reply_text(
            f"✅ Приглашение успешно создано!\n"
            f"Пользователю **{invitee_id}** будет отправлено уведомление для подтверждения."
        )
    
    context.user_data.pop('invite_event_id', None)
    return ConversationHandler.END