"""Add html_url to pr_check_runs.

Revision ID: 041
Revises: 040
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pr_check_runs", sa.Column("html_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pr_check_runs", "html_url")
