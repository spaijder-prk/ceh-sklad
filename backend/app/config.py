from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Цех — склад"
    api_prefix: str = "/api/v1"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./ceh_sklad.db"
    auto_create_schema: bool = False
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    integration_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CEH_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment != "production":
            return self

        if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
            raise ValueError(
                "В production CEH_JWT_SECRET должен быть отдельным случайным секретом не короче 32 символов"
            )
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("В production разрешена только PostgreSQL база данных")
        if self.auto_create_schema:
            raise ValueError(
                "В production CEH_AUTO_CREATE_SCHEMA должен быть false; схема применяется Alembic"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
