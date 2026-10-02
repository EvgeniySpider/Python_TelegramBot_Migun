import pytest
from unittest.mock import MagicMock, patch

from app.core.calendar.services import CalendarService


@pytest.mark.asyncio
@patch('app.core.calendar.services.CalendarRepository.get_busy_days')
async def test_get_user_busy_days(mock_get_busy_days):
    mock_conn = MagicMock()
    
    # Имитируем ответ от БД (список словарей-подобных объектов asyncpg.Record)
    # Предположим, 5-го числа день забит полностью, а 10-го — частично.
    mock_get_busy_days.return_value = [
        {"day": 5, "status": "full"},
        {"day": 10, "status": "partial"}
    ]

    # ВЫЗОВ ТЕСТИРУЕМОГО МЕТОДА
    result = await CalendarService.get_user_busy_days(
        conn=mock_conn, 
        user_id=123, 
        year=2026, 
        month=10
    )

    # ПРОВЕРКИ
    # Проверяем, что репозиторий был вызван с правильными аргументами
    mock_get_busy_days.assert_called_once_with(mock_conn, 123, 2026, 10)
    
    # Проверяем, что сервис корректно конвертировал список в словарь
    assert isinstance(result, dict)
    assert len(result) == 2
    assert result[5] == "full"
    assert result[10] == "partial"


