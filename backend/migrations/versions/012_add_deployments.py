"""Add deployments table for DORA metrics

Revision ID: 012_add_deployments
Revises: 011_add_work_category
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012_add_deployments"
down_revision: Union[str, None] = "011_add_work_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("environment", sa.String(100), nullable=True),
        sa.Column("sha", sa.String(40), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workflow_name", sa.String(255), nullable=True),
        sa.Column("workflow_run_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("lead_time_s", sa.Integer(), nullable=True),
    )
    op.create_index("ix_deployment_repo_id", "deployments", ["repo_id"])
    op.create_index("ix_deployment_deployed_at", "deployments", ["deployed_at"])
    op.create_unique_constraint(
        "uq_deployment_repo_run", "deployments", ["repo_id", "workflow_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_deployed_at", table_name="deployments")
    op.drop_index("ix_deployment_repo_id", table_name="deployments")
    op.drop_constraint("uq_deployment_repo_run", "deployments", type_="unique")
    op.drop_table("deployments")
