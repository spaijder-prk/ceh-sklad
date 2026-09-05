from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Цех — склад"
    api_prefix: str = "/api/v1"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
