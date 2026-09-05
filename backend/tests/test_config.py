import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://ceh:secret@db:5432/ceh_sklad",
            jwt_secret="change-me-in-production",
        )


def test_production_rejects_sqlite_and_auto_schema():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            database_url="sqlite:///./ceh_sklad.db",
            jwt_secret="x" * 64,
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://ceh:secret@db:5432/ceh_sklad",
            jwt_secret="x" * 64,
            auto_create_schema=True,
        )


def test_production_accepts_postgresql_and_strong_secret():
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://ceh:secret@db:5432/ceh_sklad",
        jwt_secret="x" * 64,
        auto_create_schema=False,
    )
    assert settings.environment == "production"
