"""add projects and role-based project membership

Revision ID: 0e4816c04e9a
Revises: e1aaa0219726
Create Date: 2026-11-02 17:54:24.874902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e4816c04e9a'
down_revision: Union[str, Sequence[str], None] = 'e1aaa0219726'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=250), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('project_users',
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.Enum('owner', 'participant', name='project_role', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id', 'user_id')
    )
    op.create_index('ix_project_users_user_id', 'project_users', ['user_id'], unique=False)
    op.create_index('uq_project_users_one_owner', 'project_users', ['project_id'], unique=True,
                    postgresql_where=sa.text("role = 'owner'"), sqlite_where=sa.text("role = 'owner'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_project_users_one_owner', table_name='project_users')
    op.drop_index('ix_project_users_user_id', table_name='project_users')
    op.drop_table('project_users')
    op.drop_table('projects')
