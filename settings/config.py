import os
from pydantic import Field, PostgresDsn, SecretStr, Secret
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        
        env_file_encoding="utf-8",
        extra="ignore"  # Игнор лишних переменных в .env, если они там появятся
    )

    telegram_api_key: SecretStr = Field(alias="TELEGRAM_API_KEY")
    telegram_id: int | None = Field(default=None, alias="TELEGRAM_ID")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    db_host: str = Field(alias="DB_HOST")
    db_port: int = Field(alias="DB_PORT")
    db_user: str = Field(alias="DB_USER")
    db_password: str = Field(alias="DB_PASSWORD")
    db_name: str = Field(alias="DB_NAME")
    api_token_lifetime_minutes: int = Field(default=30, alias="API_TOKEN_LIFETIME_MINUTES")

    @property
    def secret_dsn(self) -> Secret[PostgresDsn]:
        built_url = MultiHostUrl.build(
            scheme="postgresql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            path=self.db_name,
        )
        return Secret(built_url)