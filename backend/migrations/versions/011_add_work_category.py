"""Add work_category to pull_requests and issues

Revision ID: 011_add_work_category
Revises: 5449ba551698
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_add_work_category"
down_revision: Union[str, None] = "5449ba551698"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pull_requests", sa.Column("work_category", sa.String(20), nullable=True))
    op.add_column("issues", sa.Column("work_category", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("issues", "work_category")
    op.drop_column("pull_requests", "work_category")
