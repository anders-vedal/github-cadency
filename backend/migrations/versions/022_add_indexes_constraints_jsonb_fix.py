"""Add missing indexes, github_id unique constraints, and fix repo_ids JSONB drift.

Covers M-01 (indexes), M-02 (unique constraints), M-03 (JSON→JSONB).

Revision ID: 022
Revises: 021
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # M-01: Missing indexes
    op.create_index("ix_pr_state", "pull_requests", ["state"])
    op.create_index("ix_pr_merged_at", "pull_requests", ["merged_at"])
    op.create_index("ix_pr_repo_id", "pull_requests", ["repo_id"])
    op.create_index("ix_pr_review_pr_id", "pr_reviews", ["pr_id"])
    op.create_index("ix_pr_review_submitted_at", "pr_reviews", ["submitted_at"])
    op.create_index("ix_issue_state", "issues", ["state"])
    op.create_index("ix_issue_assignee_id", "issues", ["assignee_id"])
    op.create_index("ix_sync_event_status", "sync_events", ["status"])

    # M-02: Unique constraints on github_id
    op.create_unique_constraint("uq_pr_github_id", "pull_requests", ["github_id"])
    op.create_unique_constraint("uq_issue_github_id", "issues", ["github_id"])

    # M-03: Fix repo_ids JSON→JSONB drift
    op.alter_column(
        "sync_events",
        "repo_ids",
        type_=JSONB,
        existing_type=sa.JSON(),
        existing_nullable=True,
        postgresql_using="repo_ids::jsonb",
    )


def downgrade() -> None:
    # M-03
    op.alter_column(
        "sync_events",
        "repo_ids",
        type_=sa.JSON(),
        existing_type=JSONB,
        existing_nullable=True,
    )

    # M-02
    op.drop_constraint("uq_issue_github_id", "issues", type_="unique")
    op.drop_constraint("uq_pr_github_id", "pull_requests", type_="unique")

    # M-01
    op.drop_index("ix_sync_event_status", "sync_events")
    op.drop_index("ix_issue_assignee_id", "issues")
    op.drop_index("ix_issue_state", "issues")
    op.drop_index("ix_pr_review_submitted_at", "pr_reviews")
    op.drop_index("ix_pr_review_pr_id", "pr_reviews")
    op.drop_index("ix_pr_repo_id", "pull_requests")
    op.drop_index("ix_pr_merged_at", "pull_requests")
    op.drop_index("ix_pr_state", "pull_requests")
