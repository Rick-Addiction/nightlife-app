"""ig_followed_at: marca de follow por handle (Ciclo E-3)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ig_profile_states",
                  sa.Column("followed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ig_profile_states", "followed_at")
