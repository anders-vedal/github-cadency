"""merge heads

Revision ID: 5449ba551698
Revises: 010_add_comment_type, 010_add_pr_check_runs
Create Date: 2026-03-28 21:03:28.403108
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5449ba551698'
down_revision: Union[str, None] = ('010_add_comment_type', '010_add_pr_check_runs')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
