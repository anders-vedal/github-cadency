"""Change github_id columns from Integer to BigInteger

Revision ID: 014_github_id_bigint
Revises: 013_add_ai_settings
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_github_id_bigint"
down_revision: Union[str, None] = "013_add_ai_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("repositories", "github_id", type_=sa.BigInteger())
    op.alter_column("pull_requests", "github_id", type_=sa.BigInteger())
    op.alter_column("pr_reviews", "github_id", type_=sa.BigInteger())
    op.alter_column("pr_review_comments", "github_id", type_=sa.BigInteger())
    op.alter_column("issues", "github_id", type_=sa.BigInteger())
    op.alter_column("issue_comments", "github_id", type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("repositories", "github_id", type_=sa.Integer())
    op.alter_column("pull_requests", "github_id", type_=sa.Integer())
    op.alter_column("pr_reviews", "github_id", type_=sa.Integer())
    op.alter_column("pr_review_comments", "github_id", type_=sa.Integer())
    op.alter_column("issues", "github_id", type_=sa.Integer())
    op.alter_column("issue_comments", "github_id", type_=sa.Integer())
