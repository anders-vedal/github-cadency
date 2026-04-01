"""Add notification center tables.

Revision ID: 033
Revises: 032
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Materialized notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("alert_key", sa.String(200), nullable=False, unique=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("link_path", sa.String(500), nullable=True),
        sa.Column("developer_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_alert_type", "notifications", ["alert_type"])
    op.create_index("ix_notifications_severity", "notifications", ["severity"])
    op.create_index("ix_notifications_resolved_at", "notifications", ["resolved_at"])
    op.create_index("ix_notifications_developer_id", "notifications", ["developer_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_type_resolved", "notifications", ["alert_type", "resolved_at"])

    # Read tracking
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_read"),
    )
    op.create_index("ix_notification_reads_user", "notification_reads", ["user_id"])

    # Per-instance dismissals
    op.create_table(
        "notification_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("dismiss_type", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_dismissal"),
    )
    op.create_index("ix_notification_dismissals_user", "notification_dismissals", ["user_id"])
    op.create_index("ix_notification_dismissals_expires", "notification_dismissals", ["expires_at"])

    # Per-type dismissals
    op.create_table(
        "notification_type_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("dismiss_type", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("alert_type", "user_id", name="uq_notification_type_dismissal"),
    )
    op.create_index("ix_notification_type_dismissals_user", "notification_type_dismissals", ["user_id"])

    # Singleton config
    op.create_table(
        "notification_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_stale_pr_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_review_bottleneck_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_underutilized_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_uneven_assignment_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_merged_without_approval_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_revert_spike_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_high_risk_pr_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_bus_factor_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_declining_trends_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_issue_linkage_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_ai_budget_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_sync_failure_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_unassigned_roles_enabled", sa.Boolean(), server_default="true"),
        sa.Column("alert_missing_config_enabled", sa.Boolean(), server_default="true"),
        sa.Column("stale_pr_threshold_hours", sa.Integer(), server_default="48"),
        sa.Column("review_bottleneck_multiplier", sa.Float(), server_default="2.0"),
        sa.Column("revert_spike_threshold_pct", sa.Float(), server_default="5.0"),
        sa.Column("high_risk_pr_min_level", sa.String(20), server_default="high"),
        sa.Column("issue_linkage_threshold_pct", sa.Float(), server_default="20.0"),
        sa.Column("declining_trend_pr_drop_pct", sa.Float(), server_default="30.0"),
        sa.Column("declining_trend_quality_drop_pct", sa.Float(), server_default="20.0"),
        sa.Column("exclude_contribution_categories", JSONB(), server_default='["system", "non_contributor"]'),
        sa.Column("evaluation_interval_minutes", sa.Integer(), server_default="15"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )

    # Seed singleton row
    op.execute("INSERT INTO notification_config (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("notification_config")
    op.drop_table("notification_type_dismissals")
    op.drop_table("notification_dismissals")
    op.drop_table("notification_reads")
    op.drop_table("notifications")
