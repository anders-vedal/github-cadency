"""Add developer relationships, collaboration scores, office, and mentions columns.

Revision ID: 018
Revises: 017_add_sync_granular_progress
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "018"
down_revision = "017_add_sync_granular_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add office to developers
    op.add_column("developers", sa.Column("office", sa.String(255), nullable=True))

    # Add mentions JSONB to comment tables
    op.add_column("pr_review_comments", sa.Column("mentions", JSONB, nullable=True))
    op.add_column("issue_comments", sa.Column("mentions", JSONB, nullable=True))

    # Create developer_relationships table
    op.create_table(
        "developer_relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_id", "target_id", "relationship_type", name="uq_dev_rel_source_target_type"),
        sa.CheckConstraint("source_id != target_id", name="ck_dev_rel_no_self"),
        sa.Index("ix_dev_rel_source", "source_id"),
        sa.Index("ix_dev_rel_target", "target_id"),
        sa.Index("ix_dev_rel_type", "relationship_type"),
    )

    # Create developer_collaboration_scores table
    op.create_table(
        "developer_collaboration_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_a_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("developer_b_id", sa.Integer(), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_score", sa.Float(), server_default="0"),
        sa.Column("coauthor_score", sa.Float(), server_default="0"),
        sa.Column("issue_comment_score", sa.Float(), server_default="0"),
        sa.Column("mention_score", sa.Float(), server_default="0"),
        sa.Column("co_assigned_score", sa.Float(), server_default="0"),
        sa.Column("total_score", sa.Float(), server_default="0"),
        sa.Column("interaction_count", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "developer_a_id", "developer_b_id", "period_start", "period_end",
            name="uq_collab_score_pair_period",
        ),
        sa.CheckConstraint("developer_a_id < developer_b_id", name="ck_collab_score_canonical"),
        sa.Index("ix_collab_score_a", "developer_a_id"),
        sa.Index("ix_collab_score_b", "developer_b_id"),
        sa.Index("ix_collab_score_total", "total_score"),
    )


def downgrade() -> None:
    op.drop_table("developer_collaboration_scores")
    op.drop_table("developer_relationships")
    op.drop_column("issue_comments", "mentions")
    op.drop_column("pr_review_comments", "mentions")
    op.drop_column("developers", "office")
