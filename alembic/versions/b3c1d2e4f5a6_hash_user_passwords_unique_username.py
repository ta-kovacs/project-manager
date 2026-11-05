"""store password hashes and make usernames unique

Revision ID: b3c1d2e4f5a6
Revises: a97f8fa98cda
Create Date: 2026-11-05 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a97f8fa98cda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing rows hold plain-text passwords, which can't be turned into hashes:
    # those users will not be able to log in and need to register again.
    op.alter_column('users', 'password', new_column_name='password_hash')
    op.create_unique_constraint('uq_users_username', 'users', ['username'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.alter_column('users', 'password_hash', new_column_name='password')
