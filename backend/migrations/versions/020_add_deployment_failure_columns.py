"""Add failure tracking columns to deployments for CFR and MTTR.

Revision ID: 020
Revises: 019
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deployments", sa.Column("is_failure", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("deployments", sa.Column("failure_detected_via", sa.String(30), nullable=True))
    op.add_column("deployments", sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deployments", sa.Column("recovery_deployment_id", sa.Integer(), sa.ForeignKey("deployments.id"), nullable=True))
    op.add_column("deployments", sa.Column("recovery_time_s", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_constraint("deployments_recovery_deployment_id_fkey", "deployments", type_="foreignkey")
    op.drop_column("deployments", "recovery_time_s")
    op.drop_column("deployments", "recovery_deployment_id")
    op.drop_column("deployments", "recovered_at")
    op.drop_column("deployments", "failure_detected_via")
    op.drop_column("deployments", "is_failure")
