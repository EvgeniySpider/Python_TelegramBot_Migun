import os
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        
        env_file_encoding="utf-8",
        extra="ignore"  # Игнор лишних переменных в .env, если они там появятся
    )

    
    telegram_api_key: SecretStr = Field(alias="TELEGRAM_API_KEY")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Вот она — наша автоматическая труба до .env!
    db_host: str = Field(alias="DB_HOST")
    db_port: int = Field(alias="DB_PORT")
    db_user: str = Field(alias="DB_USER")
    db_password: str = Field(alias="DB_PASSWORD")
    db_name: str = Field(alias="DB_NAME")

    @property
    def secret_dsn(self) -> SecretStr:
        return SecretStr(f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}")
