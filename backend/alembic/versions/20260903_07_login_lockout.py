"""Защита учетных записей от перебора паролей.

Идентификатор: 20260903_07
Предыдущая версия: 20260903_06
Дата: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_07"
down_revision = "20260903_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("login_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_users_failed_login_attempts_nonnegative",
        "users",
        "failed_login_attempts >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_failed_login_attempts_nonnegative", "users", type_="check")
    op.drop_column("users", "login_locked_until")
    op.drop_column("users", "failed_login_attempts")
