import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.main import update_representative
from app.models import Representative, User, UserRole
from app.schemas import RepresentativeUpdate


def test_representative_update_requires_user_id_field():
    with pytest.raises(ValidationError):
        RepresentativeUpdate()


def test_representative_account_can_be_linked_changed_and_unlinked():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        first_user = User(
            email="rep1@example.local",
            password_hash="hash",
            full_name="Первый представитель",
            role=UserRole.REPRESENTATIVE,
        )
        second_user = User(
            email="rep2@example.local",
            password_hash="hash",
            full_name="Второй представитель",
            role=UserRole.REPRESENTATIVE,
        )
        manager = User(
            email="manager@example.local",
            password_hash="hash",
            full_name="Руководитель",
            role=UserRole.MANAGER,
        )
        first_rep = Representative(code="REP-1", name="Представитель 1")
        second_rep = Representative(code="REP-2", name="Представитель 2")
        session.add_all([first_user, second_user, manager, first_rep, second_rep])
        session.commit()

        linked = update_representative(
            first_rep.id,
            RepresentativeUpdate(user_id=first_user.id),
            None,
            session,
        )
        assert linked.user_id == first_user.id

        with pytest.raises(HTTPException) as duplicate_error:
            update_representative(
                second_rep.id,
                RepresentativeUpdate(user_id=first_user.id),
                None,
                session,
            )
        assert duplicate_error.value.status_code == 409

        with pytest.raises(HTTPException) as role_error:
            update_representative(
                second_rep.id,
                RepresentativeUpdate(user_id=manager.id),
                None,
                session,
            )
        assert role_error.value.status_code == 409

        changed = update_representative(
            first_rep.id,
            RepresentativeUpdate(user_id=second_user.id),
            None,
            session,
        )
        assert changed.user_id == second_user.id

        unlinked = update_representative(
            first_rep.id,
            RepresentativeUpdate(user_id=None),
            None,
            session,
        )
        assert unlinked.user_id is None
