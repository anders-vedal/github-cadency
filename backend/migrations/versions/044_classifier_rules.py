"""Admin-editable classifier rules (Phase 10 C3).

Revision ID: 044
Revises: 043
Create Date: 2026-04-22

Adds a single table ``classifier_rules`` that backs three kinds of admin-editable
classification: incident/hotfix detection, AI reviewer detection, and AI author
detection. A ``kind`` discriminator column separates concerns; services merge
these rows on top of the hard-coded defaults in
``services/incident_classification.py`` and ``services/ai_cohort.py``.

No data migration — defaults remain in code. Rows here add to the defaults.
"""
from alembic import op
import sqlalchemy as sa

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classifier_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_hotfix", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_incident", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_classifier_rules_kind", "classifier_rules", ["kind", "enabled"]
    )


def downgrade() -> None:
    op.drop_index("ix_classifier_rules_kind", table_name="classifier_rules")
    op.drop_table("classifier_rules")
