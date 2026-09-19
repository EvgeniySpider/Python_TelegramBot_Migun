from django.contrib import admin
from .models import Event, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("telegram_id",)
    search_fields = ("telegram_id",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "event_date", "event_type", "user_id")
    list_filter = ("event_type", "event_date")
    search_fields = ("title", "description")