import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            cors_origins=["https://sklad.example.ru"],
            bootstrap_admin_login=None,
            bootstrap_admin_password=None,
            integration_1c_api_key=None,
        )


def test_production_accepts_secure_configuration():
    settings = Settings(
        environment="production",
        jwt_secret="a-very-long-random-production-secret-1234567890",
        cors_origins=["https://sklad.example.ru"],
        bootstrap_admin_login=None,
        bootstrap_admin_password=None,
        integration_1c_api_key="another-long-secret-for-1c",
    )
    assert settings.environment == "production"
    assert settings.cors_origins == ["https://sklad.example.ru"]
