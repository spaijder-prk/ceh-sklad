from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Цех Склад"
    database_url: str = "postgresql+asyncpg://ceh:ceh_dev@localhost:5432/ceh_sklad"
    jwt_secret: str = "change-me-in-production"
    access_token_minutes: int = 720
    bootstrap_admin_login: str | None = None
    bootstrap_admin_password: str | None = None
    integration_1c_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
