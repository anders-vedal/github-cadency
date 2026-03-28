"""Add head_sha to pull_requests and create pr_check_runs table.

Revision ID: 010_add_pr_check_runs
Revises: 009_add_pr_files_and_repo_tree
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "010_add_pr_check_runs"
down_revision = "009_add_pr_files_and_repo_tree"
branch_labels = None
depends_on = None


def upgrade():
    # Add head_sha to pull_requests
    op.add_column(
        "pull_requests", sa.Column("head_sha", sa.String(40), nullable=True)
    )

    # Create pr_check_runs table
    op.create_table(
        "pr_check_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id"),
            nullable=False,
        ),
        sa.Column("check_name", sa.String(255), nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("run_attempt", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint(
            "pr_id", "check_name", "run_attempt",
            name="uq_pr_check_run_pr_name_attempt",
        ),
    )
    op.create_index("ix_pr_check_run_pr_id", "pr_check_runs", ["pr_id"])
    op.create_index("ix_pr_check_run_check_name", "pr_check_runs", ["check_name"])


def downgrade():
    op.drop_index("ix_pr_check_run_check_name", table_name="pr_check_runs")
    op.drop_index("ix_pr_check_run_pr_id", table_name="pr_check_runs")
    op.drop_table("pr_check_runs")
    op.drop_column("pull_requests", "head_sha")
