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
        if not 5 <= self.access_token_minutes <= 1440:
            raise ValueError("В production ACCESS_TOKEN_MINUTES должен быть от 5 до 1440 минут")
        if bool(self.bootstrap_admin_login) != bool(self.bootstrap_admin_password):
            raise ValueError("BOOTSTRAP_ADMIN_LOGIN и BOOTSTRAP_ADMIN_PASSWORD задаются только вместе")
        if self.bootstrap_admin_password and (
            self.bootstrap_admin_password == "change-me" or len(self.bootstrap_admin_password) < 12
        ):
            raise ValueError("В production bootstrap-пароль должен содержать не менее 12 символов и не быть стандартным")
        if self.integration_1c_api_key and (
            self.integration_1c_api_key == "change-me-1c" or len(self.integration_1c_api_key) < 32
        ):
            raise ValueError("В production ключ интеграции 1С должен содержать не менее 32 символов")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("В production CORS_ORIGINS должны содержать только HTTPS-адреса")
        return self


settings = Settings()
