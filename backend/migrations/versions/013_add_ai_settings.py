"""Add ai_settings and ai_usage_log tables, extend ai_analyses

Revision ID: 013_add_ai_settings
Revises: 012_add_deployments
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_add_ai_settings"
down_revision: Union[str, None] = "012_add_deployments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ai_settings singleton table ---
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("feature_general_analysis", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("feature_one_on_one_prep", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("feature_team_health", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("feature_work_categorization", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("monthly_token_budget", sa.Integer(), nullable=True),
        sa.Column("budget_warning_threshold", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("input_token_price_per_million", sa.Float(), nullable=False, server_default="3.0"),
        sa.Column("output_token_price_per_million", sa.Float(), nullable=False, server_default="15.0"),
        sa.Column("pricing_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )
    # Insert default singleton row
    op.execute(
        "INSERT INTO ai_settings (id) VALUES (1)"
    )

    # --- ai_usage_log table ---
    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature", sa.String(50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("items_classified", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_log_created_at", "ai_usage_log", ["created_at"])

    # --- extend ai_analyses ---
    op.add_column("ai_analyses", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_analyses", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_analyses", sa.Column("estimated_cost_usd", sa.Float(), nullable=True))
    op.add_column("ai_analyses", sa.Column("reused_from_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "reused_from_id")
    op.drop_column("ai_analyses", "estimated_cost_usd")
    op.drop_column("ai_analyses", "output_tokens")
    op.drop_column("ai_analyses", "input_tokens")
    op.drop_index("ix_ai_usage_log_created_at", table_name="ai_usage_log")
    op.drop_table("ai_usage_log")
    op.drop_table("ai_settings")
