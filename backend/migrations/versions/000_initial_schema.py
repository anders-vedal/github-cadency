"""Create initial database schema.

Revision ID: 000_initial_schema
Revises: (none)
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "000_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- developers ---
    op.create_table(
        "developers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_username", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("role", sa.String(50)),
        sa.Column("skills", postgresql.JSONB),
        sa.Column("specialty", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("timezone", sa.String(50)),
        sa.Column("team", sa.String(255)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("avatar_url", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- repositories ---
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.Integer, unique=True, nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("full_name", sa.String(512), index=True),
        sa.Column("description", sa.Text),
        sa.Column("language", sa.String(100)),
        sa.Column("is_tracked", sa.Boolean, default=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # --- pull_requests ---
    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.Integer, nullable=False),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("developers.id")),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("body", sa.Text),
        sa.Column("state", sa.String(20)),
        sa.Column("is_merged", sa.Boolean),
        sa.Column("is_draft", sa.Boolean),
        sa.Column("additions", sa.Integer),
        sa.Column("deletions", sa.Integer),
        sa.Column("changed_files", sa.Integer),
        sa.Column("comments_count", sa.Integer),
        sa.Column("review_comments_count", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("merged_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("first_review_at", sa.DateTime(timezone=True)),
        sa.Column("time_to_first_review_s", sa.Integer),
        sa.Column("time_to_merge_s", sa.Integer),
        sa.Column("html_url", sa.Text),
        sa.UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),
        sa.Index("ix_pr_author_created", "author_id", "created_at"),
    )

    # --- pr_reviews ---
    op.create_table(
        "pr_reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.Integer, unique=True, nullable=False),
        sa.Column("pr_id", sa.Integer, sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("developers.id")),
        sa.Column("state", sa.String(30)),
        sa.Column("body", sa.Text),
        sa.Column("body_length", sa.Integer, server_default="0"),
        sa.Column("quality_tier", sa.String(20), server_default="minimal"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
    )

    # --- pr_review_comments ---
    op.create_table(
        "pr_review_comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.Integer, unique=True, nullable=False),
        sa.Column("pr_id", sa.Integer, sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("review_id", sa.Integer, sa.ForeignKey("pr_reviews.id")),
        sa.Column("author_github_username", sa.String(255)),
        sa.Column("body", sa.Text),
        sa.Column("path", sa.Text),
        sa.Column("line", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- issues ---
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.Integer, nullable=False),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("developers.id")),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("body", sa.Text),
        sa.Column("state", sa.String(20)),
        sa.Column("labels", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("time_to_close_s", sa.Integer),
        sa.Column("html_url", sa.Text),
        sa.UniqueConstraint("repo_id", "number", name="uq_issue_repo_number"),
    )

    # --- issue_comments ---
    op.create_table(
        "issue_comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("github_id", sa.Integer, unique=True, nullable=False),
        sa.Column("issue_id", sa.Integer, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("author_github_username", sa.String(255)),
        sa.Column("body", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # --- sync_events ---
    op.create_table(
        "sync_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sync_type", sa.String(30)),
        sa.Column("status", sa.String(30)),
        sa.Column("repos_synced", sa.Integer),
        sa.Column("prs_upserted", sa.Integer),
        sa.Column("issues_upserted", sa.Integer),
        sa.Column("errors", postgresql.JSONB),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_s", sa.Integer),
    )

    # --- ai_analyses ---
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_type", sa.String(50)),
        sa.Column("scope_type", sa.String(30)),
        sa.Column("scope_id", sa.String(255)),
        sa.Column("date_from", sa.DateTime(timezone=True)),
        sa.Column("date_to", sa.DateTime(timezone=True)),
        sa.Column("input_summary", sa.Text),
        sa.Column("result", postgresql.JSONB),
        sa.Column("raw_response", sa.Text),
        sa.Column("model_used", sa.String(100)),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("triggered_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # --- developer_goals ---
    op.create_table(
        "developer_goals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("developer_id", sa.Integer, sa.ForeignKey("developers.id"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("target_value", sa.Float, nullable=False),
        sa.Column("target_direction", sa.String(10), nullable=False, server_default="above"),
        sa.Column("baseline_value", sa.Float),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("target_date", sa.Date),
        sa.Column("achieved_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("developer_goals")
    op.drop_table("ai_analyses")
    op.drop_table("sync_events")
    op.drop_table("issue_comments")
    op.drop_table("issues")
    op.drop_table("pr_review_comments")
    op.drop_table("pr_reviews")
    op.drop_table("pull_requests")
    op.drop_table("repositories")
    op.drop_table("developers")
