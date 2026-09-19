from django.contrib import admin
from .models import Event, User, BotStatistics


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("telegram_id",)
    search_fields = ("telegram_id",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "event_date", "event_type", "user_id")
    list_filter = ("event_type", "event_date")
    search_fields = ("title", "description")


@admin.register(BotStatistics)
class BotStatisticsAdmin(admin.ModelAdmin):
    # Колонки в общем списке записей
    list_display = (
        "date",
        "new_users_count",
        "calendar_clicks",
        "total_created_events_display",
        "events_edited",
        "events_deleted",
    )

    # Фильтры в правой панели
    list_filter = ("date",)

    # Сортировка по умолчанию: сначала самые свежие даты
    ordering = ("-date",)

    # Поля только для чтения, чтобы случайно не сбить статистику вручную через админку
    readonly_fields = (
        "date",
        "new_users_count",
        "calendar_clicks",
        "events_created_all_day",
        "events_created_exact",
        "events_created_interval",
        "events_edited",
        "events_deleted",
    )

    # Группировка полей логическими блоками при детальном просмотре дня
    fieldsets = (
        ("Дата", {"fields": ("date",)}),
        (
            "Пользователи и Активность",
            {"fields": ("new_users_count", "calendar_clicks")},
        ),
        (
            "Созданные события (по типам)",
            {
                "fields": (
                    "events_created_all_day",
                    "events_created_exact",
                    "events_created_interval",
                )
            },
        ),
        (
            "Действия с событиями",
            {"fields": ("events_edited", "events_deleted")},
        ),
    )

    # Красивое отображение общего количества созданных событий в таблице
    @admin.display(description="Всего создано событий")
    def total_created_events_display(self, obj):
        return obj.total_events_created