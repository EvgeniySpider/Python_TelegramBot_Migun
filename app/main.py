from app.core.users.repositories import UserRepository
from app.core.users.services import UserService
from telegram.ext import Application as PTBApplication, ApplicationBuilder
from settings.config import AppSettings
from app.handlers import HANDLERS
from app.infra.postgres.db import Database


class Application(PTBApplication):
    def __init__(self, app_settings: AppSettings, **kwargs):
        super().__init__(**kwargs)
        self._settings = app_settings
        self._register_handlers()

        self.database = Database(dsn=app_settings.secret_dsn)
        user_repository = UserRepository(database=self.database)
        self.user_service = UserService(repository=user_repository)

    @staticmethod
    async def initialize_dependencies(application: "Application") -> None:
        await application.database.initialize()

    @staticmethod
    async def shutdown_dependencies(application: "Application") -> None:
        await application.database.shutdown()

    def run(self) -> None:
        self.run_polling()

    def _register_handlers(self):
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
        .post_init(Application.initialize_dependencies)  # type: ignore[arg-type]
        .post_shutdown(Application.shutdown_dependencies)  # type: ignore[arg-type]
        .token(app_settings.telegram_api_key.get_secret_value())
        .build()
    )
    return application  # type: ignore[return-value]


if __name__ == '__main__':
    configure_logging()
    settings = AppSettings()
    app = create_app(settings)
    app.run()
