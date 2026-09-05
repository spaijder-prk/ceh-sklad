from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import require_roles
from app.models import User, UserRole


async def test_representative_cannot_pass_admin_role_check():
    representative = User(
        id=uuid4(),
        name="Торговый представитель",
        login="rep-test",
        password_hash="unused",
        role=UserRole.REPRESENTATIVE,
        is_active=True,
    )
    dependency = require_roles(UserRole.ADMIN)

    with pytest.raises(HTTPException) as error:
        await dependency(representative)

    assert error.value.status_code == 403


async def test_manager_passes_manager_role_check():
    manager = User(
        id=uuid4(),
        name="Руководитель",
        login="manager-test",
        password_hash="unused",
        role=UserRole.MANAGER,
        is_active=True,
    )
    dependency = require_roles(UserRole.ADMIN, UserRole.MANAGER)

    assert await dependency(manager) is manager
