import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.response import Response
from rest_framework import status
from unittest.mock import patch, MagicMock, AsyncMock, ANY
from datetime import date, time

from app.handlers.calendar_set_event import _save_event_to_db, handle_description_input
from app.handlers.states import CHOOSING_ACTION
from events.models import Event, User


@pytest.mark.django_db
def test_create_event(auth_client: APIClient, test_user: User):
    url: str = reverse('api:private-events-list')

    payload = {
        'event_type': 'interval',
        'title': 'лучшее название',
        'description': 'лучшее описание',
        'event_date': '2026-09-09',
        'start_time': '10:00',
        'end_time': '12:00',
        'is_public': False
    }

    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED

    created_event: dict = response.json()

    assert created_event['user'] == test_user.telegram_id
    assert created_event['event_type'] == payload['event_type']
    assert created_event['title'] == payload['title']
    assert created_event['description'] == payload['description']
    assert created_event['event_date'] == payload['event_date']
    assert created_event['start_time'] == payload['start_time'] + ':00'
    assert created_event['end_time'] == payload['end_time'] + ':00'
    assert created_event['is_public'] == payload['is_public']

    db_event = Event.objects.get(id=created_event['id'])
    assert db_event.user == test_user
    assert db_event.title == payload['title']
    assert db_event.event_type == payload['event_type']



@pytest.mark.django_db
@pytest.mark.parametrize(
    'missing_field', ['title', 'event_type', 'event_date']
)
def test_create_event_missing_required_fields(
    auth_client: APIClient, 
    missing_field: str
) -> None:
    url: str = reverse('api:private-events-list')

    payload  = {
        'event_type': 'interval',
        'title': 'Рабочая встреча',
        'event_date': '2026-09-09',
        'start_time': '10:00',
        'end_time': '12:00',
        'is_public': False,
    }
    # Вырезаем проверяемое поле из полезной нагрузки
    del payload[missing_field]

    response: Response = auth_client.post(url, data=payload, format='json')

    # 1. Сервер обязан вернуть 400 Bad Request
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Сериализатор должен указать ошибку именно на отсутствующее поле
    errors: dict = response.json()
    assert missing_field in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'key, value',
    [
        ('event_type', 'unexist'),
        ('event_date', 'not-a-date'),
        ('start_time', 'not-a-time'),
        ('is_public', 'not-a-boolean'),
    ]
)
def test_create_event_with_invalid_fields(
    auth_client: APIClient,
    key: str,
    value: str
):
    url: str = reverse('api:private-events-list')
    payload = {
        'event_type': 'interval',
        'title': 'Рабочая встреча',
        'event_date': '2026-09-09',
        'start_time': '10:00',
        'end_time': '12:00',
        'is_public': False,
    }

    payload[key] = value

    response: Response = auth_client.post(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    errors: dict = response.json()
    assert key in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'event_type, start_time, end_time',
    [
        # Сценарии для 'all_day': время передавать запрещено
        ('all_day', '10:00', None),
        ('all_day', None, '12:00'),
        ('all_day', '10:00', '12:00'),
        
        # Сценарии для 'exact': обязателен start_time, запрещен end_time
        ('exact', None, None),
        ('exact', '10:00', '12:00'),
        ('exact', None, '12:00'),
        
        # Сценарии для 'interval': обязательны оба поля
        ('interval', '10:00', None),
        ('interval', None, '12:00'),
        ('interval', None, None),
    ]
)
def test_create_event_business_logic_conflicts(
    auth_client: APIClient,
    event_type: str,
    start_time: str | None,
    end_time: str | None
) -> None:
    url: str = reverse('api:private-events-list')
    
    payload: dict = {
        'title': 'Бизнес-логика проверка',
        'event_date': '2026-09-09',
        'is_public': False,
        'event_type': event_type,
    }
    
    # Добавляем ключи времени только если они не None, 
    # чтобы сымитировать реальное отсутствие полей в запросе
    if start_time:
        payload['start_time'] = start_time
    if end_time:
        payload['end_time'] = end_time

    response: Response = auth_client.post(url, data=payload, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    errors: dict = response.json()
    # Поскольку в serializers.py исключения вызываются как raise ValidationError("текст ошибки"), 
    # DRF автоматически складывает их в массив по ключу 'non_field_errors'
    assert 'non_field_errors' in errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    'payload_override, expected_error_key',
    [
        # Невалидные даты (отбивает встроенный DateField)
        ({'event_date': '2026-09-31'}, 'event_date'),  # В сентябре 30 дней
        ({'event_date': '2026-02-29'}, 'event_date'),  # 2026 - не високосный
        ({'event_date': '2026-13-01'}, 'event_date'),  # Нет 13-го месяца

        # Невалидное время (отбивает встроенный TimeField)
        ({'start_time': '25:00'}, 'start_time'),       # В сутках 24 часа
        ({'end_time': '12:61'}, 'end_time'),           # В минуте 60 секунд

        # Нарушение хронологии (отбивает validate)
        (
            {'event_type': 'interval', 'start_time': '12:00', 'end_time': '10:00'},
            'non_field_errors' 
        ),
    ]
)
def test_create_event_datetime_boundaries(
    auth_client: APIClient,
    payload_override: dict,
    expected_error_key: str
):
    url: str = reverse('api:private-events-list')
    payload = {
        'title': 'Тест форматов',
        'event_date': '2026-09-09',
        'is_public': False,
        'event_type': 'interval',
        'start_time': '10:00',
        'end_time': '12:00'
    }
    payload.update(payload_override)
    
    response: Response = auth_client.post(url, data=payload, format='json')
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert expected_error_key in response.json()


@pytest.mark.django_db
def test_create_event_time_collisions(auth_client: APIClient, test_user: User):
    # 1. Бронируем время в БД (12:00 - 14:00)
    Event.objects.create(
        user=test_user,
        event_type='interval',
        title='Уже занятый слот',
        event_date='2026-10-10',
        start_time='12:00',
        end_time='14:00',
        is_public=False
    )
    
    url: str = reverse('api:private-events-list')
    base_payload = {
        'title': 'Попытка вклиниться',
        'event_date': '2026-10-10',
        'is_public': False,
    }

    # Сценарий А: Пересечение интервалов (внахлест слева 11:00-13:00)
    payload = {**base_payload, 'event_type': 'interval', 'start_time': '11:00', 'end_time': '13:00'}
    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.json()

    # Сценарий Б: Точное время (exact) падает прямо внутрь занятого интервала (в 13:00)
    payload = {**base_payload, 'event_type': 'exact', 'start_time': '13:00'}
    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.json()

    # Сценарий В: Попытка объявить весь день (all_day) занятым, хотя внутри уже есть интервал
    payload = {**base_payload, 'event_type': 'all_day'}
    response: Response = auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.json()


@pytest.mark.django_db
def test_create_exact_event_late_night_truncation(auth_client: APIClient, test_user: User):
    """
    Проверяет, что при создании события 'exact' со временем начала > 23:29
    (например, 23:45), время окончания принудительно устанавливается на 23:59,
    и в ответе возвращается соответствующий warning.
    """
    url: str = reverse('api:private-events-list')

    payload = {
        'event_type': 'exact',
        'title': 'Позднее точное событие',
        'event_date': '2026-10-10',
        'start_time': '23:45',
        'is_public': False
    }

    response: Response = auth_client.post(url, data=payload, format='json')

    # Проверяем успешность создания
    assert response.status_code == status.HTTP_201_CREATED

    created_event: dict = response.json()

    # Проверяем, что start_time сохранился корректно, а end_time обрезался
    assert created_event['start_time'] == '23:45:00'
    assert created_event['end_time'] == '23:59:00'

    # Проверяем наличие кастомного поля warning, добавленного через to_representation
    assert 'warning' in created_event
    assert created_event['warning'] == "Время > 23:29, поэтому время окончания было установлено 23:59"

    # Проверяем базу данных
    db_event = Event.objects.get(id=created_event['id'])
    assert str(db_event.start_time) == '23:45:00'
    assert str(db_event.end_time) == '23:59:00'


@pytest.mark.asyncio
@patch('app.handlers.calendar_act_with_options.handle_back_to_day_menu_click')
@patch('app.core.calendar.services.CalendarService.get_user_busy_days')
@patch('app.core.calendar.repositories.CalendarRepository.get_events_by_date')
async def test_save_event_to_db(
    mock_get_events: AsyncMock,
    mock_get_busy_days: AsyncMock,
    mock_handle_back: AsyncMock
):
    # 1. ПОДГОТОВКА МОКОВ СЕРВИСОВ И РЕПОЗИТОРИЕВ
    mock_get_events.return_value = ["fake_record_1"]
    mock_get_busy_days.return_value = {14: True}
    mock_handle_back.return_value = "SOME_STATE"
    
    # Подготавливаем входящие объекты
    update_mock = AsyncMock()
    update_mock.effective_user.id = 12345

    context_mock = MagicMock()
    
    # Имитируем ОЗУ пользователя, заполненную на предыдущих шагах
    context_mock.user_data = {
        'selected_date': date(2026, 10, 14),
        'event_type': 'interval',
        'event_title': 'Сходить в магазин',
        'start_time': time(10, 0),
        'end_time': time(11, 0),
        'description': 'Купить молока'
    }

    # Мокаем подключение к БД
    conn_mock = AsyncMock()
    context_mock.application.database.connection.return_value.__aenter__.return_value = conn_mock

    # Мокаем репозиторий статистики
    stats_mock = AsyncMock()
    context_mock.application.stats_repository = stats_mock

    # 2. ВЫЗОВ ФУНКЦИИ
    result = await _save_event_to_db(update_mock, context_mock)

    # 3. ПРОВЕРКИ

    # Блок 1: База данных
    args = conn_mock.execute.call_args.args
    assert "INSERT INTO events" in args[0]
    # args содержит: [query, user_id, event_type, title, date, start, end, created_at, desc, is_public]
    # Используем ANY для created_at, так как там генерируется datetime.now() прямо внутри функции
    conn_mock.execute.assert_called_once_with(
        ANY, 12345, 'interval', 'Сходить в магазин', date(2026, 10, 14), 
        time(10, 0), time(11, 0), ANY, 'Купить молока', False
    )

    # Блок 2: Статистика
    stats_mock.increment_metric.assert_called_once_with('events_created_interval')
    stats_mock.increment_user_metric.assert_called_once_with(12345, 'events_created')

    # Блок 3: Синхронизация (свежие данные из БД)
    mock_get_events.assert_called_once_with(conn_mock, 12345, date(2026, 10, 14))
    mock_get_busy_days.assert_called_once_with(conn=conn_mock, user_id=12345, year=2026, month=10)

    # Блок 4: Обновление ОЗУ (user_data)
    # Проверяем, что отчет сформирован
    assert "Мероприятие успешно добавлено!" in context_mock.user_data['edit_success_status']
    assert "Время: 10:00 - 11:00" in context_mock.user_data['edit_success_status']
    assert 'Дата: 14.10.2026' in context_mock.user_data['edit_success_status']
    assert "Купить молока" in context_mock.user_data['edit_success_status']

    # Проверяем, что кэш обновился новыми данными
    assert context_mock.user_data['event_text_record'] == ["fake_record_1"]
    assert context_mock.user_data['month_busy_days'] == {14: True}
    

    # Проверяем очистку мусора: ключи-билдеры должны быть удалены
    for key in ['event_type', 'event_title', 'start_time', 'end_time', 'description']:
        assert key not in context_mock.user_data

    # Блок 5: Возврат стейта
    mock_handle_back.assert_called_once_with(update_mock, context_mock)
    assert result == "SOME_STATE"



@pytest.mark.asyncio
@patch('app.handlers.calendar_set_event._save_event_to_db')
async def test_apply_description_input_before_saving_to_db(mock_save_event_to_db: AsyncMock):
    # Преамбула данных
    mock_save_event_to_db.return_value = CHOOSING_ACTION
    update_mock = MagicMock()
    context_mock = MagicMock()
    description = 'Описание для заметки'

    # Фабула данных
    context_mock.user_data = {}
    update_mock.message.text = description

    # Вызов подопытного
    result = await handle_description_input(update_mock, context_mock)

    # Тесты
    assert result == CHOOSING_ACTION
    assert context_mock.user_data['description'] == description
    mock_save_event_to_db.assert_awaited_once_with(update_mock, context_mock)