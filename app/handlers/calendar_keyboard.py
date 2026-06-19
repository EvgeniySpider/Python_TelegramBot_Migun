import calendar
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def generate_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    # 1. Получаем текстовое название месяца (пока на английском, потом русифицируем)
    month_name = calendar.month_name[month]

    keyboard = []

    # РЯД 1: Заголовок календаря (Месяц и Год)
    # Коллбэк ставим пустой ("ignore"), чтобы при нажатии на заголовок ничего не происходило
    keyboard.append([
        InlineKeyboardButton(
            text=f"{month_name} {year}", callback_data="calendar_ignore")
    ])

    # РЯД 2: Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([
        InlineKeyboardButton(text=day, callback_data="calendar_ignore") for day in week_days
    ])

    # РЯДЫ 3-8: Сами числа месяца
    # Функция monthcalendar возвращает матрицу недель, например: [0, 0, 1, 2, 3, 4, 5]
    month_matrix = calendar.monthcalendar(year, month)

    for week in month_matrix:
        row = []
        for day in week:
            if day == 0:
                # Если день равен 0 — это пустая клетка (соседний месяц), делаем её некликабельной
                row.append(InlineKeyboardButton(
                    text=" ", callback_data="calendar_ignore"))
            else:
                # Обычный день. В коллбэк зашиваем дату, чтобы хэндлер понял, какой день выбрал юзер
                row.append(InlineKeyboardButton(
                    text=str(day),
                    callback_data=f"calendar_day:{year}:{month}:{day}"
                ))
        keyboard.append(row)

    # РЯД 9: Кнопки навигации (Стрелочки)
    # Вычисляем прошлый и следующий месяц для коллбэков стрелочек
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    keyboard.append([
        InlineKeyboardButton(
            text="« Пред", callback_data=f"calendar_nav:{prev_year}:{prev_month}"),
        InlineKeyboardButton(
            text="След »", callback_data=f"calendar_nav:{next_year}:{next_month}")
    ])

    return InlineKeyboardMarkup(keyboard)
