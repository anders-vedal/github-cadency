"""Add resumability and progress tracking to sync_events

Revision ID: 015_add_sync_resumability
Revises: 014_github_id_bigint
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015_add_sync_resumability"
down_revision: Union[str, None] = "014_github_id_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sync_events", sa.Column("repo_ids", sa.JSON(), nullable=True))
    op.add_column("sync_events", sa.Column("since_override", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_events", sa.Column("total_repos", sa.Integer(), nullable=True))
    op.add_column("sync_events", sa.Column("current_repo_name", sa.String(512), nullable=True))
    op.add_column("sync_events", sa.Column("repos_completed", sa.JSON(), server_default="[]", nullable=True))
    op.add_column("sync_events", sa.Column("repos_failed", sa.JSON(), server_default="[]", nullable=True))
    op.add_column("sync_events", sa.Column("is_resumable", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("sync_events", sa.Column("resumed_from_id", sa.Integer(), sa.ForeignKey("sync_events.id"), nullable=True))
    op.add_column("sync_events", sa.Column("log_summary", sa.JSON(), server_default="[]", nullable=True))
    op.add_column("sync_events", sa.Column("rate_limit_wait_s", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("sync_events", "rate_limit_wait_s")
    op.drop_column("sync_events", "log_summary")
    op.drop_column("sync_events", "resumed_from_id")
    op.drop_column("sync_events", "is_resumable")
    op.drop_column("sync_events", "repos_failed")
    op.drop_column("sync_events", "repos_completed")
    op.drop_column("sync_events", "current_repo_name")
    op.drop_column("sync_events", "total_repos")
    op.drop_column("sync_events", "since_override")
    op.drop_column("sync_events", "repo_ids")
