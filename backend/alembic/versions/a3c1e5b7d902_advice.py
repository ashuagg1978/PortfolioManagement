"""Add saved AI advice."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c1e5b7d902"
down_revision: Union[str, Sequence[str], None] = "d8f39043a2bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "advice",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "scope", name="uq_advice_user_kind_scope"),
    )
    with op.batch_alter_table("advice", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_advice_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("advice", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_advice_user_id"))
    op.drop_table("advice")