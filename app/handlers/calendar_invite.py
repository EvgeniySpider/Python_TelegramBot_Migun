from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError

from app.handlers.calendar_keyboard import generate_back_to_menu_button
from app.handlers.commands import calendar_command
from app.handlers.states import TYPING_INVITE_NUM, TYPING_INVITEE_ID
from app.handlers.utils import get_validated_event_index
from events.models import User, Event, Appointment
from app.core.calendar.services import check_user_availability
from app.handlers.calendar_keyboard import generate_confirm_invite_keyboard


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
            "❌ Пользователь с таким ID *не зарегистрирован* в нашем боте.\n"
            "Проверьте ID и попробуйте еще раз:",
            parse_mode="Markdown"
        )
        return TYPING_INVITEE_ID

    # 2. Достаем целевое событие
    target_event = await Event.objects.aget(id=event_id)
    # 3. Валидация пересечения временных интервалов
    is_busy = await check_user_availability(invitee_id, target_event)
    
    
    if is_busy:
        await update.message.reply_text(
            "⚠️ К сожалению, в это время пользователь *уже занят* (у него запланировано другое событие).\n\n"
            "Встреча не назначена. Выберите другое время или пригласите кого-то еще.",
            parse_mode="Markdown"
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
        # Собираем красивый текст для гостя
        inviter_name = update.effective_user.first_name or f"Пользователь {inviter_id}"
        invite_text = (
            f"🔔 *Новое приглашение!*\n\n"
            f"*{inviter_name}* приглашает вас на событие:\n"
            f"📌 *{target_event.title}*\n"
            f"📅 Дата: {target_event.event_date}\n"
        )
        if target_event.start_time:
            # Если есть время, отсекаем секунды
            invite_text += f"⏰ Время: {target_event.start_time.strftime('%H:%M')}\n"
        
        invite_text += "\nПримете приглашение?"

        try:
            # Отправляем сообщение ГОСТЮ
            await context.bot.send_message(
                chat_id=invitee_id,
                text=invite_text,
                reply_markup=generate_confirm_invite_keyboard(appointment.id),
                parse_mode="Markdown"
            )
            # Отвечаем ОРГАНИЗАТОРУ
            await update.message.reply_text(
                f"✅ Приглашение успешно создано!\n"
                f"Пользователю *{invitee_id}* отправлено уведомление для подтверждения.",
                parse_mode="Markdown"
            )
        except TelegramError:
            # Если гость заблокировал бота или не начинал с ним диалог
            await update.message.reply_text(
                "⚠️ Не удалось отправить приглашение. Возможно, пользователь заблокировал бота или ни разу его не запускал."
            )
            # Удаляем "зависшее" приглашение
            await appointment.adelete()
    
    context.user_data.pop('invite_event_id', None)
    return ConversationHandler.END


async def handle_invite_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатие кнопок Принять/Отклонить в сообщении-приглашении.
    """
    query = update.callback_query
    await query.answer()

    # Разбираем callback_data (пример: "invite:accept:15")
    _, action, appointment_id_str = query.data.split(':')
    appointment_id = int(appointment_id_str)

    try:
        # Достаем встречу вместе с объектом события через JOIN
        appointment = await Appointment.objects.select_related('event').aget(id=appointment_id)
    except Appointment.DoesNotExist:
        await query.edit_message_text("⚠️ Это приглашение больше не существует или было отменено.")
        return

    # Защита от повторного нажатия кнопок
    if appointment.status != Appointment.Status.PENDING:
        await query.edit_message_text("ℹ️ Вы уже дали ответ на это приглашение.")
        return

    inviter_id = appointment.event.user_id
    original_event = appointment.event

    if action == 'accept':
        # 1. Повторная валидация времени гостя
        is_busy = await check_user_availability(query.from_user.id, appointment.event)
        
        if is_busy:
            await query.edit_message_text(
                "⚠️ Вы не можете принять приглашение: на это время у вас уже запланировано другое событие."
            )
            return

        # 2. Подтверждаем встречу в промежуточной таблице
        appointment.status = Appointment.Status.CONFIRMED
        await appointment.asave()
        
        guest_description = f"🤝 Встреча с пользователем {inviter_id}.\n"
        if original_event.description:
            guest_description += f"\nОригинальное описание: {original_event.description}"

        # 3. Создаем физическую копию
        await Event.objects.acreate(
            user_id=query.from_user.id,
            event_type=original_event.event_type,
            title=f"Встреча: {original_event.title}",
            description=guest_description,
            event_date=original_event.event_date,
            start_time=original_event.start_time,
            end_time=original_event.end_time
        )

        # 4. Меняем сообщение у гостя
        await query.edit_message_text(
            f"✅ Вы *приняли* приглашение на событие: {original_event.title}",
            parse_mode="Markdown"
        )

        # 5. Уведомляем организатора
        await context.bot.send_message(
            chat_id=inviter_id,
            text=f"✅ Пользователь *{query.from_user.id}* принял ваше приглашение на событие *{original_event.title}*.",
            parse_mode="Markdown"
        )

    elif action == 'reject':
        await query.edit_message_text(
            f"❌ Вы *отказались* от приглашения на событие: {original_event.title}",
            parse_mode="Markdown"
        )

        await context.bot.send_message(
            chat_id=inviter_id,
            text=f"❌ Пользователь *{query.from_user.id}* отказался от приглашения на событие *{original_event.title}*.",
            parse_mode="Markdown"
        )

        appointment.status = Appointment.Status.CANCELLED
        await appointment.asave()