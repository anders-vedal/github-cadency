"""Add ai_analysis_schedules table.

Revision ID: 035
Revises: 034
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_analysis_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("analysis_type", sa.String(50), nullable=False),
        sa.Column("general_type", sa.String(50), nullable=True),
        sa.Column("scope_type", sa.String(30), nullable=False),
        sa.Column("scope_id", sa.String(255), nullable=False),
        sa.Column("repo_ids", JSONB(), nullable=True),
        sa.Column("time_range_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("frequency", sa.String(30), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("minute", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_analysis_id", sa.Integer(), nullable=True),
        sa.Column("last_run_status", sa.String(30), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ai_analysis_schedules_is_enabled",
        "ai_analysis_schedules",
        ["is_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_analysis_schedules_is_enabled", table_name="ai_analysis_schedules")
    op.drop_table("ai_analysis_schedules")
