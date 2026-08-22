"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import db.types  # custom Money/Nav/Units column types used across models
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema.

    NOTE if autogenerate added a new foreign key on SQLite: batch_op.create_foreign_key(None, ...)
    fails with "Constraint must have a name" - SQLite's batch-rebuild mode requires every
    constraint to be named. Give it one explicitly, e.g.
    batch_op.create_foreign_key('fk_<table>_<column>_<referred_table>', ...), and match that
    same name in the corresponding drop_constraint() in downgrade() below.
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}
