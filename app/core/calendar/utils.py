def format_event_time(start_time, end_time, event_type: str = None) -> str:
    """Единая точка форматирования времени для всего бота."""
    if event_type == 'all_day':
        return 'Весь день'
        
    if not start_time or not end_time:
        return ''
        
    # Если объекты пришли из БД или контекста как datetime.time
    st = start_time.strftime("%H:%M")
    end = end_time.strftime("%H:%M")
    return f"{st} - {end}"