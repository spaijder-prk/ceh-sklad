"""Разрешить нулевую денежную проводку продажи.

Revision ID: 0003_allow_zero_money_posting
Revises: 0002_current_balances
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_allow_zero_money_posting"
down_revision: str | None = "0002_current_balances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("money_postings") as batch_op:
        batch_op.drop_constraint(
            "ck_money_posting_nonzero_amount",
            type_="check",
        )


def downgrade() -> None:
    with op.batch_alter_table("money_postings") as batch_op:
        batch_op.create_check_constraint(
            "ck_money_posting_nonzero_amount",
            "amount <> 0",
        )
