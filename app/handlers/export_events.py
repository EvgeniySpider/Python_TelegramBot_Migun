import json
import csv
import io
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from events.models import Event

async def handle_export_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Выгружает все события пользователя в формате JSON или CSV и отправляет файлом в чат.
    Определяет формат на основе введенной команды.
    """
    user_id = update.effective_user.id
    # Получаем текст команды, убираем слеш и приводим к нижнему регистру
    command = update.message.text.split('@')[0].strip('/').lower()
    is_csv = 'csv' in command

    # 1. Запрашиваем ТОЛЬКО события текущего пользователя
    user_events = [
        e async for e in Event.objects.filter(user_id=user_id).order_by('event_date', 'start_time')
    ]

    if not user_events:
        await update.message.reply_text("📭 У вас пока нет событий для выгрузки.")
        return

    # 2. Подготавливаем данные
    events_data = []
    for event in user_events:
        events_data.append({
            "id": event.id,
            "type": event.event_type,
            "title": event.title,
            "description": event.description or "",
            "date": str(event.event_date) if event.event_date else "",
            "start_time": event.start_time.strftime("%H:%M") if event.start_time else "",
            "end_time": event.end_time.strftime("%H:%M") if event.end_time else "",
            "is_public": event.is_public,
            "created_at": event.created_at.isoformat() if event.created_at else ""
        })

    # 3. Формируем нужный буфер
    if is_csv:
        # Для CSV сначала пишем строки в StringIO
        string_buffer = io.StringIO()
        fieldnames = ["id", "type", "title", "description", "date", "start_time", "end_time", "is_public", "created_at"]
        writer = csv.DictWriter(string_buffer, fieldnames=fieldnames, delimiter=';') # Точка с запятой лучше для русского Excel
        
        writer.writeheader()
        writer.writerows(events_data)
        
        # Переводим строку в байты с BOM (utf-8-sig) для корректного чтения в Excel
        memory_file = io.BytesIO(string_buffer.getvalue().encode('utf-8-sig'))
        filename = f"calendar_export_{user_id}.csv"
    else:
        # Для JSON
        json_string = json.dumps(events_data, ensure_ascii=False, indent=4)
        memory_file = io.BytesIO(json_string.encode('utf-8'))
        filename = f"calendar_export_{user_id}.json"

    # 4. Отправляем документ
    await update.message.reply_document(
        document=InputFile(memory_file, filename=filename),
        caption=f"📥 Ваша выгрузка готова! Формат: {filename.split('.')[-1].upper()}\nВсего событий: {len(events_data)}"
    )