"""Add server_default to non-nullable columns that only had Python defaults.

Revision ID: 021
Revises: 020
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # developers
    op.alter_column("developers", "app_role", server_default="developer")
    op.alter_column("developers", "is_active", server_default=sa.text("true"))
    op.alter_column("developers", "created_at", server_default=sa.func.now())
    op.alter_column("developers", "updated_at", server_default=sa.func.now())

    # repositories
    op.alter_column("repositories", "is_tracked", server_default=sa.text("true"))
    op.alter_column("repositories", "created_at", server_default=sa.func.now())

    # developer_goals
    op.alter_column("developer_goals", "target_direction", server_default="above")
    op.alter_column("developer_goals", "created_at", server_default=sa.func.now())

    # developer_relationships
    op.alter_column("developer_relationships", "created_at", server_default=sa.func.now())
    op.alter_column("developer_relationships", "updated_at", server_default=sa.func.now())

    # developer_collaboration_scores
    for col in [
        "review_score", "coauthor_score", "issue_comment_score",
        "mention_score", "co_assigned_score", "total_score",
    ]:
        op.alter_column("developer_collaboration_scores", col, server_default="0.0")
    op.alter_column("developer_collaboration_scores", "interaction_count", server_default="0")
    op.alter_column("developer_collaboration_scores", "updated_at", server_default=sa.func.now())

    # ai_analyses
    op.alter_column("ai_analyses", "created_at", server_default=sa.func.now())

    # ai_usage_log
    op.alter_column("ai_usage_log", "created_at", server_default=sa.func.now())


def downgrade() -> None:
    # developers
    op.alter_column("developers", "app_role", server_default=None)
    op.alter_column("developers", "is_active", server_default=None)
    op.alter_column("developers", "created_at", server_default=None)
    op.alter_column("developers", "updated_at", server_default=None)

    # repositories
    op.alter_column("repositories", "is_tracked", server_default=None)
    op.alter_column("repositories", "created_at", server_default=None)

    # developer_goals
    op.alter_column("developer_goals", "target_direction", server_default=None)
    op.alter_column("developer_goals", "created_at", server_default=None)

    # developer_relationships
    op.alter_column("developer_relationships", "created_at", server_default=None)
    op.alter_column("developer_relationships", "updated_at", server_default=None)

    # developer_collaboration_scores
    for col in [
        "review_score", "coauthor_score", "issue_comment_score",
        "mention_score", "co_assigned_score", "total_score",
    ]:
        op.alter_column("developer_collaboration_scores", col, server_default=None)
    op.alter_column("developer_collaboration_scores", "interaction_count", server_default=None)
    op.alter_column("developer_collaboration_scores", "updated_at", server_default=None)

    # ai_analyses
    op.alter_column("ai_analyses", "created_at", server_default=None)

    # ai_usage_log
    op.alter_column("ai_usage_log", "created_at", server_default=None)
