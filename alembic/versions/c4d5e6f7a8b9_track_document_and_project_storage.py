"""track document sizes and each project's storage usage

Revision ID: c4d5e6f7a8b9
Revises: b3c1d2e4f5a6
Create Date: 2026-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c1d2e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing documents get NULL: their size is unknown until the storage-usage Lambda measures
    # their project (invoke it once with {"recompute_all": true} after deploying it).
    op.add_column('documents', sa.Column('size_bytes', sa.BigInteger(), nullable=True))
    op.add_column(
        'projects',
        sa.Column('storage_used_bytes', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    )
    op.add_column('projects', sa.Column('storage_measured_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'storage_measured_at')
    op.drop_column('projects', 'storage_used_bytes')
    op.drop_column('documents', 'size_bytes')
