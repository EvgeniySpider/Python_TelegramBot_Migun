from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.handlers.calendar_keyboard import generate_back_to_menu_button
from app.handlers.commands import calendar_command
from app.handlers.states import TYPING_INVITE_NUM, TYPING_INVITEE_ID
from app.handlers.utils import get_validated_event_index


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
    Ловит и валидирует текстовое сообщение с Telegram ID для приглашения на встречу.
    Проверяет корректность ввода (числовой формат, защита от приглашения самого себя) 
    и наличие привязанного события в сессии. Подготавливает данные для дальнейшей 
    бизнес-логики (проверка пересечений расписания, запись в БД).
    """
    # 1. Получаем ввод пользователя
    invitee_id_str = update.message.text.strip()
    inviter_id = update.effective_user.id
    
    # 2. Достаем ID целевого события из памяти
    event_id = context.user_data.get('invite_event_id')
    
    if not event_id:
        await update.message.reply_text(
            "⚠️ Сессия устарела или событие потерялось из памяти. Возвращаю вас в календарь"
        )
        # Возвращаем пользователя в календарь
        return await calendar_command(update, context) 

    # 3. Базовая валидация ввода
    if not invitee_id_str.isdigit():
        await update.message.reply_text("❌ Telegram ID должен состоять только из цифр. Попробуйте еще раз:")
        return TYPING_INVITEE_ID # Оставляем пользователя в этом же стейте для повторного ввода

    invitee_id = int(invitee_id_str)
    
    if inviter_id == invitee_id:
        await update.message.reply_text("❌ Вы не можете пригласить самого себя. Введите ID другого пользователя:")
        return TYPING_INVITEE_ID

    # TODO: Здесь будет вызов сервисного слоя для работы с БД (проверка занятости, создание Appointment)
    
    # Заглушка для проверки
    await update.message.reply_text(f"✅ Введен валидный ID: {invitee_id} для события {event_id}")
    
    context.user_data.pop('invite_event_id', None)
    return ConversationHandler.END