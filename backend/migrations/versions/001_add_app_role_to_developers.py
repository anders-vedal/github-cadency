"""Add app_role column to developers table.

Revision ID: 001_add_app_role
Revises: 000_initial_schema
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa

revision = "001_add_app_role"
down_revision = "000_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "developers",
        sa.Column("app_role", sa.String(20), nullable=False, server_default="developer"),
    )


def downgrade() -> None:
    op.drop_column("developers", "app_role")
