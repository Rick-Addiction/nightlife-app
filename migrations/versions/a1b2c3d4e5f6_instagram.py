"""instagram: venue social fields + ig_profile_states

Revision ID: a1b2c3d4e5f6
Revises: 6db320547b8b
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6db320547b8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('venues', sa.Column('instagram', sa.String(length=200), nullable=True))
    op.add_column('venues', sa.Column('website', sa.String(length=500), nullable=True))
    op.create_table(
        'ig_profile_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('handle', sa.String(length=200), nullable=False),
        sa.Column('last_shortcode', sa.String(length=50), nullable=True),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('handle'),
    )


def downgrade() -> None:
    op.drop_table('ig_profile_states')
    op.drop_column('venues', 'website')
    op.drop_column('venues', 'instagram')
