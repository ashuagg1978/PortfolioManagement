"""Multi-user auth: is_admin/is_active on users, bootstrap accounts.

Data step: the pre-auth single user (owner@portfolio.local) is renamed to the
configured seed user and given a password, so all existing portfolio data
stays linked to them; an admin account is added.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from core.config import settings
from core.security import hash_password

revision: str = "b7e2f4a1c9d3"
down_revision: Union[str, Sequence[str], None] = "a3c1e5b7d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_EMAIL = "owner@portfolio.local"


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))

    conn = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("email", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("is_admin", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )

    def find(email: str):
        return conn.execute(sa.select(users.c.id).where(users.c.email == email)).first()

    # Existing data's owner -> the real user (rename in place so every FK still points at them).
    if find(settings.seed_user_email) is None:
        legacy = find(LEGACY_EMAIL)
        values = {
            "name": settings.seed_user_name,
            "email": settings.seed_user_email,
            "password_hash": hash_password(settings.seed_user_password),
        }
        if legacy is not None:
            conn.execute(sa.update(users).where(users.c.id == legacy[0]).values(**values))
        else:
            conn.execute(sa.insert(users).values(**values, is_admin=False, is_active=True))

    if find(settings.admin_username) is None:
        conn.execute(
            sa.insert(users).values(
                name=settings.admin_name,
                email=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
                is_active=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_active")
        batch_op.drop_column("is_admin")
