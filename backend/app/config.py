from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Цех Склад"
    database_url: str = "postgresql+asyncpg://ceh:ceh_dev@localhost:5432/ceh_sklad"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
