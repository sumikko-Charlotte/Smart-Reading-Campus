"""activity_checkout

Revision ID: b7c41d9e2a10
Revises: fed2ee3aa5d4
Create Date: 2026-10-19 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c41d9e2a10'
down_revision: Union[str, None] = 'fed2ee3aa5d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('activity_signups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('checked_out_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('activity_signups', schema=None) as batch_op:
        batch_op.drop_column('checked_out_at')
