"""GitHub PR timeline enrichment — timeline events + derived PR aggregates.

Revision ID: 043
Revises: 042
Create Date: 2026-04-22

Adds:
- pr_timeline_events — rows for GitHub timelineItems (force pushes, ready for review,
  review requests, merge queue, auto-merge, etc.)

Extends:
- pull_requests: force_push_count_after_first_review, review_requested_count,
  ready_for_review_at, draft_flip_count, renamed_title_count,
  dismissed_review_count, merge_queue_waited_s, auto_merge_waited_s,
  codeowners_bypass
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extend pull_requests ---
    op.add_column(
        "pull_requests",
        sa.Column(
            "force_push_count_after_first_review",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "review_requested_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "ready_for_review_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "draft_flip_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "renamed_title_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "dismissed_review_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "merge_queue_waited_s",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "auto_merge_waited_s",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "pull_requests",
        sa.Column(
            "codeowners_bypass",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # --- pr_timeline_events ---
    op.create_table(
        "pr_timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "actor_developer_id",
            sa.Integer(),
            sa.ForeignKey("developers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_github_username", sa.String(255), nullable=True),
        sa.Column(
            "subject_developer_id",
            sa.Integer(),
            sa.ForeignKey("developers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject_github_username", sa.String(255), nullable=True),
        sa.Column("before_sha", sa.String(40), nullable=True),
        sa.Column("after_sha", sa.String(40), nullable=True),
        sa.Column("data", JSONB, nullable=True),
        sa.UniqueConstraint("external_id", name="uq_pr_timeline_event_ext_id"),
    )
    op.create_index(
        "ix_pr_timeline_events_pr_type_created",
        "pr_timeline_events",
        ["pr_id", "event_type", "created_at"],
    )
    op.create_index(
        "ix_pr_timeline_events_type_created",
        "pr_timeline_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_pr_timeline_events_actor_created",
        "pr_timeline_events",
        ["actor_developer_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pr_timeline_events_actor_created", table_name="pr_timeline_events"
    )
    op.drop_index(
        "ix_pr_timeline_events_type_created", table_name="pr_timeline_events"
    )
    op.drop_index(
        "ix_pr_timeline_events_pr_type_created", table_name="pr_timeline_events"
    )
    op.drop_table("pr_timeline_events")

    op.drop_column("pull_requests", "codeowners_bypass")
    op.drop_column("pull_requests", "auto_merge_waited_s")
    op.drop_column("pull_requests", "merge_queue_waited_s")
    op.drop_column("pull_requests", "dismissed_review_count")
    op.drop_column("pull_requests", "renamed_title_count")
    op.drop_column("pull_requests", "draft_flip_count")
    op.drop_column("pull_requests", "ready_for_review_at")
    op.drop_column("pull_requests", "review_requested_count")
    op.drop_column("pull_requests", "force_push_count_after_first_review")
