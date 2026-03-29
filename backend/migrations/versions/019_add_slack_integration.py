"""Add slack_config, slack_user_settings, and notification_log tables.

Revision ID: 019
Revises: 018
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Global Slack configuration (singleton)
    op.create_table(
        "slack_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slack_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bot_token", sa.Text(), nullable=True),
        sa.Column("default_channel", sa.String(255), nullable=True),
        sa.Column("notify_stale_prs", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_high_risk_prs", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_workload_alerts", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_sync_failures", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_sync_complete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notify_weekly_digest", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("stale_pr_days_threshold", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("risk_score_threshold", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("digest_day_of_week", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("digest_hour_utc", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("stale_check_hour_utc", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )
    # Seed singleton row
    op.execute("INSERT INTO slack_config (id) VALUES (1)")

    # Per-developer Slack preferences
    op.create_table(
        "slack_user_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("slack_user_id", sa.String(50), nullable=True),
        sa.Column("notify_stale_prs", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_high_risk_prs", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_workload_alerts", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_weekly_digest", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("developer_id", name="uq_slack_user_dev"),
    )
    op.create_index("ix_slack_user_dev", "slack_user_settings", ["developer_id"])

    # Notification audit log
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(255), nullable=True),
        sa.Column("recipient_developer_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notification_log_type", "notification_log", ["notification_type"])
    op.create_index("ix_notification_log_created", "notification_log", ["created_at"])
    op.create_index("ix_notification_log_status", "notification_log", ["status"])


def downgrade() -> None:
    op.drop_index("ix_notification_log_status", table_name="notification_log")
    op.drop_index("ix_notification_log_created", table_name="notification_log")
    op.drop_index("ix_notification_log_type", table_name="notification_log")
    op.drop_table("notification_log")
    op.drop_index("ix_slack_user_dev", table_name="slack_user_settings")
    op.drop_table("slack_user_settings")
    op.drop_table("slack_config")
