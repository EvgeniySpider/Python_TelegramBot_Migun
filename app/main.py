import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from telegram import Update
from telegram.ext import Application as PTBApplication
from telegram.ext import ApplicationBuilder, TypeHandler
from django.db import close_old_connections

from app.core.stats.repositories import StatsRepository
from app.core.users.repositories import UserRepository
from app.core.users.services import UserService
from settings.config import AppSettings
from app.handlers import HANDLERS
from app.infra.postgres.db import Database


async def close_db_connections(update: Update, context) -> None:
    """Глобальный middleware для очистки протухших соединений Django ORM."""
    close_old_connections()


class Application(PTBApplication):
    def __init__(self, app_settings: AppSettings, **kwargs):
        super().__init__(**kwargs)
        self._settings = app_settings
        self._register_handlers()

        self.database = Database(dsn=app_settings.secret_dsn)
        user_repository = UserRepository(database=self.database)
        self.user_service = UserService(repository=user_repository)

        self.stats_repository = StatsRepository(db=self.database)

    @staticmethod
    async def initialize_dependencies(application: "Application") -> None:
        await application.database.initialize()
        await application.bot.set_my_commands([
            ("calendar", "📅 Открыть интерактивный календарь")
        ])

    @staticmethod
    async def shutdown_dependencies(application: "Application") -> None:
        await application.database.shutdown()

    def run(self) -> None:
        self.run_polling()

    def _register_handlers(self):
        # Перехватываем ВСЕ апдейты до основной логики (group=-1)
        self.add_handler(TypeHandler(Update, close_db_connections), group=-1)
        
        for handler in HANDLERS:
            self.add_handler(handler)


def configure_logging():
    import logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(app_settings: AppSettings) -> Application:
    application = (
        ApplicationBuilder()
        .application_class(Application, kwargs={"app_settings": app_settings})
        .post_init(Application.initialize_dependencies)
        .post_shutdown(Application.shutdown_dependencies)
        .token(app_settings.telegram_api_key.get_secret_value())
        .build()
    )
    return application

settings = AppSettings()
if __name__ == '__main__':
    configure_logging()
    app = create_app(settings)
    app.run()
