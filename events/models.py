from django.db import models


class User(models.Model):
    """Модель пользователя Telegram."""

    telegram_id = models.BigIntegerField(primary_key=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self) -> str:
        return f"User {self.telegram_id}"


class Event(models.Model):
    """Модель календарного события."""

    class EventType(models.TextChoices):
        ALL_DAY = "all_day", "Весь день"
        INTERVAL = "interval", "Интервал"
        EXACT = "exact", "Точное время"

    # Связь с пользователем (FOREIGN KEY users(telegram_id) ON DELETE CASCADE)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        to_field="telegram_id",
        db_column="user_id",
        related_name="events",
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    event_date = models.DateField()
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "events"
        verbose_name = "Событие"
        verbose_name_plural = "События"

    def __str__(self) -> str:
        return f"[{self.event_type}] {self.title} ({self.event_date})"


class BotStatistics(models.Model):
    date = models.DateField(unique=True, verbose_name="Дата")

    # Слой 1: Пользователи и Активность
    new_users_count = models.PositiveIntegerField(
        default=0, verbose_name="Новых пользователей"
    )
    calendar_clicks = models.PositiveIntegerField(
        default=0, verbose_name="Кликов по календарю"
    )

    # Слой 2: Создание событий
    events_created_all_day = models.PositiveIntegerField(
        default=0, verbose_name="Событий 'Весь день'"
    )
    events_created_exact = models.PositiveIntegerField(
        default=0, verbose_name="Событий 'Точное время'"
    )
    events_created_interval = models.PositiveIntegerField(
        default=0, verbose_name="Событий 'Интервал'"
    )

    # Слой 3: Действия над событиями
    events_edited = models.PositiveIntegerField(
        default=0, verbose_name="Изменено событий"
    )
    events_deleted = models.PositiveIntegerField(
        default=0, verbose_name="Удалено событий"
    )

    class Meta:
        verbose_name = "Статистика бота"
        verbose_name_plural = "Статистика бота"
        ordering = ["-date"]

    def __str__(self):
        return f"Статистика за {self.date}"

    @property
    def total_events_created(self):
        """Вспомогательное свойство: общее кол-во созданных событий за день"""
        return (
            self.events_created_all_day
            + self.events_created_exact
            + self.events_created_interval
        )