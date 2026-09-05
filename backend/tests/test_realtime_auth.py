from uuid import uuid4

import pytest
from jwt import InvalidTokenError

from app.models import User, UserRole
from app.realtime_auth import (
    consume_realtime_ticket,
    create_realtime_ticket,
    reset_used_realtime_tickets_for_tests,
)
from app.security import create_access_token


def make_user(role: UserRole) -> User:
    return User(
        id=uuid4(),
        email=f"{role.value}@example.local",
        password_hash="test",
        full_name=role.value,
        role=role,
    )


def test_realtime_ticket_is_single_use_for_admin_and_manager():
    reset_used_realtime_tickets_for_tests()
    for role in (UserRole.ADMIN, UserRole.MANAGER):
        user = make_user(role)
        ticket = create_realtime_ticket(user)
        assert consume_realtime_ticket(ticket) == user.id
        with pytest.raises(InvalidTokenError):
            consume_realtime_ticket(ticket)


def test_realtime_ticket_is_not_issued_to_representative():
    reset_used_realtime_tickets_for_tests()
    with pytest.raises(ValueError):
        create_realtime_ticket(make_user(UserRole.REPRESENTATIVE))


def test_access_token_cannot_be_used_as_realtime_ticket():
    reset_used_realtime_tickets_for_tests()
    access_token = create_access_token(make_user(UserRole.ADMIN))
    with pytest.raises(InvalidTokenError):
        consume_realtime_ticket(access_token)
