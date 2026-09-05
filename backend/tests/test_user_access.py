import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import User, UserRole
from app.security import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
)
from app.users_api import UserAccessUpdate, update_user_access


def make_user(email: str, role: UserRole, password: str = "password-123") -> User:
    return User(
        email=email,
        password_hash=hash_password(password),
        full_name=email,
        role=role,
    )


def test_user_access_update_requires_change():
    with pytest.raises(ValidationError):
        UserAccessUpdate()


def test_deactivation_revokes_old_token_and_reactivation_does_not_restore_it():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        admin = make_user("admin@example.local", UserRole.ADMIN)
        target = make_user("manager@example.local", UserRole.MANAGER)
        session.add_all([admin, target])
        session.commit()

        old_token = create_access_token(target)
        assert get_current_user(old_token, session).id == target.id

        updated = update_user_access(
            target.id,
            UserAccessUpdate(is_active=False),
            admin,
            session,
        )
        assert updated.is_active is False
        assert updated.auth_version == 2
        assert authenticate_user(session, target.email, "password-123") is None

        with pytest.raises(HTTPException) as revoked_error:
            get_current_user(old_token, session)
        assert revoked_error.value.status_code == 401

        reenabled = update_user_access(
            target.id,
            UserAccessUpdate(is_active=True),
            admin,
            session,
        )
        assert reenabled.is_active is True
        assert reenabled.auth_version == 2

        with pytest.raises(HTTPException):
            get_current_user(old_token, session)

        logged_in = authenticate_user(session, target.email, "password-123")
        assert logged_in is not None
        new_token = create_access_token(logged_in)
        assert get_current_user(new_token, session).id == target.id


def test_password_reset_revokes_tokens_and_changes_credentials():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        admin = make_user("admin@example.local", UserRole.ADMIN)
        target = make_user("rep@example.local", UserRole.REPRESENTATIVE, "old-password")
        session.add_all([admin, target])
        session.commit()

        old_token = create_access_token(target)
        updated = update_user_access(
            target.id,
            UserAccessUpdate(new_password="new-password-456"),
            admin,
            session,
        )
        assert updated.auth_version == 2
        assert authenticate_user(session, target.email, "old-password") is None
        assert authenticate_user(session, target.email, "new-password-456") is not None

        with pytest.raises(HTTPException) as revoked_error:
            get_current_user(old_token, session)
        assert revoked_error.value.status_code == 401


def test_admin_cannot_deactivate_self():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        admin = make_user("admin@example.local", UserRole.ADMIN)
        session.add(admin)
        session.commit()

        with pytest.raises(HTTPException) as error:
            update_user_access(
                admin.id,
                UserAccessUpdate(is_active=False),
                admin,
                session,
            )
        assert error.value.status_code == 409
        assert admin.is_active is True
        assert admin.auth_version == 1
