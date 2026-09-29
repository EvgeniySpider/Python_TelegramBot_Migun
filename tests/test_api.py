import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.response import Response
from events.models import Event


@pytest.mark.django_db
def test_get_public_events_list(
    api_client: APIClient, 
    public_event: Event, 
    private_event: Event
) -> None:
    url: str = reverse('api:public-events-list')
    
    response: Response = api_client.get(url)
    
    assert response.status_code == 200
    
    data: list[dict] = response.json()
    assert len(data) == 1
    assert data[0]['title'] == 'Тестовое публичное событие'
    assert data[0]['is_public'] is True