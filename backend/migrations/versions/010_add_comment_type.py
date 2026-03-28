"""Add comment_type column to pr_review_comments.

Revision ID: 010_add_comment_type
Revises: 009_add_pr_files_and_repo_tree
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "010_add_comment_type"
down_revision = "009_add_pr_files_and_repo_tree"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pr_review_comments",
        sa.Column("comment_type", sa.String(30), server_default="general", nullable=True),
    )


def downgrade():
    op.drop_column("pr_review_comments", "comment_type")
