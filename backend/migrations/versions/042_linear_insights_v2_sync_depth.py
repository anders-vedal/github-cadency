"""Linear insights v2 sync depth — comments, history, attachments, relations, project updates.

Revision ID: 042
Revises: 041
Create Date: 2026-04-22

Adds:
- external_issue_comments — metadata + 280-char preview
- external_issue_history — structured IssueHistory transitions (all from/to columns)
- external_issue_attachments — Linear attachments (GitHub PR links, Slack, Figma, etc.)
- external_issue_relations — blocks/blocked_by/related/duplicate (bidirectional)
- external_project_updates — Linear ProjectUpdate (health narrative)

Extends:
- external_issues: SLA fields (sla_started_at, sla_breaches_at, sla_high_risk_at,
  sla_medium_risk_at, sla_type, sla_status), triage fields (triaged_at,
  triage_responsibility_team_id, triage_auto_assigned), subscribers_count, reaction_data
- pr_external_issue_links: link_confidence (high/medium/low, default 'low')
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extend external_issues ---
    op.add_column("external_issues", sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("external_issues", sa.Column("sla_breaches_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("external_issues", sa.Column("sla_high_risk_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("external_issues", sa.Column("sla_medium_risk_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("external_issues", sa.Column("sla_type", sa.String(30), nullable=True))
    op.add_column("external_issues", sa.Column("sla_status", sa.String(30), nullable=True))
    op.add_column("external_issues", sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("external_issues", sa.Column("triage_responsibility_team_id", sa.String(255), nullable=True))
    op.add_column("external_issues", sa.Column("triage_auto_assigned", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("external_issues", sa.Column("subscribers_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("external_issues", sa.Column("reaction_data", JSONB, nullable=True))

    # --- Extend pr_external_issue_links ---
    op.add_column(
        "pr_external_issue_links",
        sa.Column("link_confidence", sa.String(10), nullable=False, server_default="low"),
    )

    # --- external_issue_comments ---
    op.create_table(
        "external_issue_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("parent_comment_id", sa.Integer(), sa.ForeignKey("external_issue_comments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_developer_id", sa.Integer(), sa.ForeignKey("developers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_email", sa.String(320), nullable=True),
        sa.Column("external_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body_preview", sa.String(280), nullable=True),
        sa.Column("reaction_data", JSONB, nullable=True),
        sa.Column("is_system_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bot_actor_type", sa.String(50), nullable=True),
        sa.UniqueConstraint("external_id", name="uq_ext_issue_comment_ext_id"),
    )
    op.create_index("ix_ext_issue_comments_issue_created", "external_issue_comments", ["issue_id", "created_at"])
    op.create_index("ix_ext_issue_comments_author", "external_issue_comments", ["author_developer_id", "created_at"])
    op.create_index("ix_ext_issue_comments_parent", "external_issue_comments", ["parent_comment_id"])

    # --- external_issue_history ---
    op.create_table(
        "external_issue_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("actor_developer_id", sa.Integer(), sa.ForeignKey("developers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email", sa.String(320), nullable=True),
        sa.Column("bot_actor_type", sa.String(50), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_state", sa.String(100), nullable=True),
        sa.Column("to_state", sa.String(100), nullable=True),
        sa.Column("from_state_category", sa.String(30), nullable=True),
        sa.Column("to_state_category", sa.String(30), nullable=True),
        sa.Column("from_assignee_id", sa.Integer(), sa.ForeignKey("developers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_assignee_id", sa.Integer(), sa.ForeignKey("developers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_estimate", sa.Float(), nullable=True),
        sa.Column("to_estimate", sa.Float(), nullable=True),
        sa.Column("from_priority", sa.Integer(), nullable=True),
        sa.Column("to_priority", sa.Integer(), nullable=True),
        sa.Column("from_cycle_id", sa.Integer(), sa.ForeignKey("external_sprints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_cycle_id", sa.Integer(), sa.ForeignKey("external_sprints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_project_id", sa.Integer(), sa.ForeignKey("external_projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_project_id", sa.Integer(), sa.ForeignKey("external_projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_parent_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_parent_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("added_label_ids", JSONB, nullable=True),
        sa.Column("removed_label_ids", JSONB, nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_closed", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("external_id", name="uq_ext_issue_history_ext_id"),
    )
    op.create_index("ix_ext_issue_history_issue_changed", "external_issue_history", ["issue_id", "changed_at"])
    op.create_index("ix_ext_issue_history_category", "external_issue_history", ["to_state_category", "changed_at"])
    op.create_index("ix_ext_issue_history_actor", "external_issue_history", ["actor_developer_id", "changed_at"])

    # --- external_issue_attachments ---
    op.create_table(
        "external_issue_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("normalized_source_type", sa.String(30), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_developer_id", sa.Integer(), sa.ForeignKey("developers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_system_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("external_id", name="uq_ext_issue_attachment_ext_id"),
    )
    op.create_index("ix_ext_issue_attachments_issue_type", "external_issue_attachments", ["issue_id", "normalized_source_type"])
    op.create_index("ix_ext_issue_attachments_url", "external_issue_attachments", ["url"])

    # --- external_issue_relations ---
    op.create_table(
        "external_issue_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("related_issue_id", sa.Integer(), sa.ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_id", "relation_type", "issue_id", name="uq_ext_issue_relation_ext_id_type"),
    )
    op.create_index("ix_ext_issue_relations_issue_type", "external_issue_relations", ["issue_id", "relation_type"])
    op.create_index("ix_ext_issue_relations_related_type", "external_issue_relations", ["related_issue_id", "relation_type"])

    # --- external_project_updates ---
    op.create_table(
        "external_project_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("external_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("author_developer_id", sa.Integer(), sa.ForeignKey("developers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_email", sa.String(320), nullable=True),
        sa.Column("body_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body_preview", sa.String(280), nullable=True),
        sa.Column("diff_length", sa.Integer(), nullable=True),
        sa.Column("health", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reaction_data", JSONB, nullable=True),
        sa.UniqueConstraint("external_id", name="uq_ext_project_update_ext_id"),
    )
    op.create_index("ix_ext_project_updates_project_created", "external_project_updates", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ext_project_updates_project_created", table_name="external_project_updates")
    op.drop_table("external_project_updates")

    op.drop_index("ix_ext_issue_relations_related_type", table_name="external_issue_relations")
    op.drop_index("ix_ext_issue_relations_issue_type", table_name="external_issue_relations")
    op.drop_table("external_issue_relations")

    op.drop_index("ix_ext_issue_attachments_url", table_name="external_issue_attachments")
    op.drop_index("ix_ext_issue_attachments_issue_type", table_name="external_issue_attachments")
    op.drop_table("external_issue_attachments")

    op.drop_index("ix_ext_issue_history_actor", table_name="external_issue_history")
    op.drop_index("ix_ext_issue_history_category", table_name="external_issue_history")
    op.drop_index("ix_ext_issue_history_issue_changed", table_name="external_issue_history")
    op.drop_table("external_issue_history")

    op.drop_index("ix_ext_issue_comments_parent", table_name="external_issue_comments")
    op.drop_index("ix_ext_issue_comments_author", table_name="external_issue_comments")
    op.drop_index("ix_ext_issue_comments_issue_created", table_name="external_issue_comments")
    op.drop_table("external_issue_comments")

    op.drop_column("pr_external_issue_links", "link_confidence")

    op.drop_column("external_issues", "reaction_data")
    op.drop_column("external_issues", "subscribers_count")
    op.drop_column("external_issues", "triage_auto_assigned")
    op.drop_column("external_issues", "triage_responsibility_team_id")
    op.drop_column("external_issues", "triaged_at")
    op.drop_column("external_issues", "sla_status")
    op.drop_column("external_issues", "sla_type")
    op.drop_column("external_issues", "sla_medium_risk_at")
    op.drop_column("external_issues", "sla_high_risk_at")
    op.drop_column("external_issues", "sla_breaches_at")
    op.drop_column("external_issues", "sla_started_at")
