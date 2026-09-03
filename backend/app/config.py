from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Цех Склад"
    environment: Literal["development", "production"] = "development"
    database_url: str = "postgresql+asyncpg://ceh:ceh_dev@localhost:5432/ceh_sklad"
    jwt_secret: str = "change-me-in-production"
    access_token_minutes: int = 720
    bootstrap_admin_login: str | None = None
    bootstrap_admin_password: str | None = None
    integration_1c_api_key: str | None = None
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment != "production":
            return self

        if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
            raise ValueError("В production JWT_SECRET должен быть отдельным секретом длиной не менее 32 символов")
        if self.bootstrap_admin_login and self.bootstrap_admin_password == "change-me":
            raise ValueError("В production запрещен стандартный пароль bootstrap-администратора")
        if self.integration_1c_api_key == "change-me-1c":
            raise ValueError("В production запрещен стандартный ключ интеграции 1С")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("В production CORS_ORIGINS должны содержать только HTTPS-адреса")
        return self


settings = Settings()
