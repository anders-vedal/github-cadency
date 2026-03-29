from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(50))
    skills: Mapped[list | None] = mapped_column(JSONB)
    specialty: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str | None] = mapped_column(String(50))
    team: Mapped[str | None] = mapped_column(String(255))
    app_role: Mapped[str] = mapped_column(String(20), nullable=False, default="developer", server_default="developer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    office: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="author")
    reviews: Mapped[list["PRReview"]] = relationship(back_populates="reviewer")
    assigned_issues: Mapped[list["Issue"]] = relationship(back_populates="assignee")
    goals: Mapped[list["DeveloperGoal"]] = relationship(back_populates="developer")
    relationships_as_source: Mapped[list["DeveloperRelationship"]] = relationship(
        back_populates="source", foreign_keys="DeveloperRelationship.source_id"
    )
    relationships_as_target: Mapped[list["DeveloperRelationship"]] = relationship(
        back_populates="target", foreign_keys="DeveloperRelationship.target_id"
    )


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(512), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    default_branch: Mapped[str | None] = mapped_column(String(255))
    tree_truncated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repo")
    issues: Mapped[list["Issue"]] = relationship(back_populates="repo")
    tree_files: Mapped[list["RepoTreeFile"]] = relationship(back_populates="repo")
    deployments: Mapped[list["Deployment"]] = relationship(back_populates="repo")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),
        Index("ix_pr_author_created", "author_id", "created_at"),
        Index("ix_pr_state", "state"),
        Index("ix_pr_merged_at", "merged_at"),
        Index("ix_pr_repo_id", "repo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(20))
    is_merged: Mapped[bool | None] = mapped_column(Boolean)
    is_draft: Mapped[bool | None] = mapped_column(Boolean)
    additions: Mapped[int | None] = mapped_column(Integer)
    deletions: Mapped[int | None] = mapped_column(Integer)
    changed_files: Mapped[int | None] = mapped_column(Integer)
    comments_count: Mapped[int | None] = mapped_column(Integer)
    review_comments_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_to_first_review_s: Mapped[int | None] = mapped_column(Integer)
    time_to_merge_s: Mapped[int | None] = mapped_column(Integer)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    time_to_approve_s: Mapped[int | None] = mapped_column(Integer)
    time_after_approve_s: Mapped[int | None] = mapped_column(Integer)
    merged_without_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    review_round_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    closes_issue_numbers: Mapped[list | None] = mapped_column(JSONB)
    labels: Mapped[list | None] = mapped_column(JSONB)
    merged_by_username: Mapped[str | None] = mapped_column(String(255))
    head_branch: Mapped[str | None] = mapped_column(String(255))
    base_branch: Mapped[str | None] = mapped_column(String(255))
    is_self_merged: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_revert: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    reverted_pr_number: Mapped[int | None] = mapped_column(Integer)
    html_url: Mapped[str | None] = mapped_column(Text)
    head_sha: Mapped[str | None] = mapped_column(String(40))
    work_category: Mapped[str | None] = mapped_column(String(20))
    author_github_username: Mapped[str | None] = mapped_column(String(255))

    repo: Mapped["Repository"] = relationship(back_populates="pull_requests")
    author: Mapped["Developer | None"] = relationship(back_populates="pull_requests")
    reviews: Mapped[list["PRReview"]] = relationship(back_populates="pr")
    review_comments: Mapped[list["PRReviewComment"]] = relationship(back_populates="pr")
    files: Mapped[list["PRFile"]] = relationship(back_populates="pr")
    check_runs: Mapped[list["PRCheckRun"]] = relationship(back_populates="pr")


class PRReview(Base):
    __tablename__ = "pr_reviews"
    __table_args__ = (
        Index("ix_pr_review_pr_id", "pr_id"),
        Index("ix_pr_review_submitted_at", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id"), nullable=False
    )
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    state: Mapped[str | None] = mapped_column(String(30))
    body: Mapped[str | None] = mapped_column(Text)
    body_length: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quality_tier: Mapped[str] = mapped_column(
        String(20), default="minimal", server_default="minimal"
    )
    reviewer_github_username: Mapped[str | None] = mapped_column(String(255))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pr: Mapped["PullRequest"] = relationship(back_populates="reviews")
    reviewer: Mapped["Developer | None"] = relationship(back_populates="reviews")
    comments: Mapped[list["PRReviewComment"]] = relationship(back_populates="review")


class PRReviewComment(Base):
    __tablename__ = "pr_review_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id"), nullable=False
    )
    review_id: Mapped[int | None] = mapped_column(ForeignKey("pr_reviews.id"))
    author_github_username: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    comment_type: Mapped[str | None] = mapped_column(String(30), server_default="general")
    mentions: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pr: Mapped["PullRequest"] = relationship(back_populates="review_comments")
    review: Mapped["PRReview | None"] = relationship(back_populates="comments")


class PRFile(Base):
    __tablename__ = "pr_files"
    __table_args__ = (
        UniqueConstraint("pr_id", "filename", name="uq_pr_file_pr_filename"),
        Index("ix_pr_file_filename", "filename"),
        Index("ix_pr_file_pr_id", "pr_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    additions: Mapped[int] = mapped_column(Integer, server_default="0")
    deletions: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str | None] = mapped_column(String(20))
    previous_filename: Mapped[str | None] = mapped_column(Text)

    pr: Mapped["PullRequest"] = relationship(back_populates="files")


class PRCheckRun(Base):
    __tablename__ = "pr_check_runs"
    __table_args__ = (
        UniqueConstraint(
            "pr_id", "check_name", "run_attempt",
            name="uq_pr_check_run_pr_name_attempt",
        ),
        Index("ix_pr_check_run_pr_id", "pr_id"),
        Index("ix_pr_check_run_check_name", "check_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False)
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(30))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    run_attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    pr: Mapped["PullRequest"] = relationship(back_populates="check_runs")


class RepoTreeFile(Base):
    __tablename__ = "repo_tree_files"
    __table_args__ = (
        UniqueConstraint("repo_id", "path", name="uq_repo_tree_file_repo_path"),
        Index("ix_repo_tree_file_repo_id", "repo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repo: Mapped["Repository"] = relationship(back_populates="tree_files")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_issue_repo_number"),
        Index("ix_issue_state", "state"),
        Index("ix_issue_assignee_id", "assignee_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    assignee_github_username: Mapped[str | None] = mapped_column(String(255))
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(20))
    labels: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_to_close_s: Mapped[int | None] = mapped_column(Integer)
    html_url: Mapped[str | None] = mapped_column(Text)
    comment_count: Mapped[int] = mapped_column(Integer, server_default="0")
    body_length: Mapped[int] = mapped_column(Integer, server_default="0")
    has_checklist: Mapped[bool] = mapped_column(Boolean, server_default="false")
    state_reason: Mapped[str | None] = mapped_column(String(30))
    creator_github_username: Mapped[str | None] = mapped_column(String(255))
    milestone_title: Mapped[str | None] = mapped_column(String(255))
    milestone_due_on: Mapped[datetime | None] = mapped_column(Date)
    reopen_count: Mapped[int] = mapped_column(Integer, server_default="0")
    work_category: Mapped[str | None] = mapped_column(String(20))

    repo: Mapped["Repository"] = relationship(back_populates="issues")
    assignee: Mapped["Developer | None"] = relationship(back_populates="assigned_issues")
    comments: Mapped[list["IssueComment"]] = relationship(back_populates="issue")


class IssueComment(Base):
    __tablename__ = "issue_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False)
    author_github_username: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    mentions: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issue: Mapped["Issue"] = relationship(back_populates="comments")


class SyncEvent(Base):
    __tablename__ = "sync_events"
    __table_args__ = (
        Index("ix_sync_event_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_type: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str | None] = mapped_column(String(30))
    repos_synced: Mapped[int | None] = mapped_column(Integer)
    prs_upserted: Mapped[int | None] = mapped_column(Integer)
    issues_upserted: Mapped[int | None] = mapped_column(Integer)
    errors: Mapped[list | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int | None] = mapped_column(Integer)

    # Resumability and progress tracking
    repo_ids: Mapped[list | None] = mapped_column(JSONB)
    since_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_repos: Mapped[int | None] = mapped_column(Integer)
    current_repo_name: Mapped[str | None] = mapped_column(String(512))
    current_step: Mapped[str | None] = mapped_column(String(50))
    current_repo_prs_total: Mapped[int | None] = mapped_column(Integer)
    current_repo_prs_done: Mapped[int | None] = mapped_column(Integer)
    current_repo_issues_total: Mapped[int | None] = mapped_column(Integer)
    current_repo_issues_done: Mapped[int | None] = mapped_column(Integer)
    repos_completed: Mapped[list | None] = mapped_column(
        JSONB, server_default="[]"
    )
    repos_failed: Mapped[list | None] = mapped_column(
        JSONB, server_default="[]"
    )
    is_resumable: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False
    )
    resumed_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("sync_events.id")
    )
    resumed_from: Mapped["SyncEvent | None"] = relationship(
        remote_side="SyncEvent.id", foreign_keys=[resumed_from_id]
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False
    )
    log_summary: Mapped[list | None] = mapped_column(
        JSONB, server_default="[]"
    )
    rate_limit_wait_s: Mapped[int] = mapped_column(
        Integer, server_default="0", default=0
    )


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_type: Mapped[str | None] = mapped_column(String(50))
    scope_type: Mapped[str | None] = mapped_column(String(30))
    scope_id: Mapped[str | None] = mapped_column(String(255))
    date_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_summary: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    raw_response: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(100))
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    reused_from_id: Mapped[int | None] = mapped_column(Integer)
    triggered_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )


class DeveloperGoal(Base):
    __tablename__ = "developer_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    target_direction: Mapped[str] = mapped_column(
        String(10), nullable=False, default="above", server_default="above"
    )
    baseline_value: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    target_date: Mapped[datetime | None] = mapped_column(Date)
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(
        String(10), server_default="admin"
    )

    developer: Mapped["Developer"] = relationship(back_populates="goals")


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint(
            "repo_id", "workflow_run_id",
            name="uq_deployment_repo_run",
        ),
        Index("ix_deployment_repo_id", "repo_id"),
        Index("ix_deployment_deployed_at", "deployed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(100))
    sha: Mapped[str | None] = mapped_column(String(40))
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workflow_name: Mapped[str | None] = mapped_column(String(255))
    workflow_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str | None] = mapped_column(String(30))
    lead_time_s: Mapped[int | None] = mapped_column(Integer)
    is_failure: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    failure_detected_via: Mapped[str | None] = mapped_column(String(30))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_deployment_id: Mapped[int | None] = mapped_column(
        ForeignKey("deployments.id"), nullable=True
    )
    recovery_time_s: Mapped[int | None] = mapped_column(Integer)

    repo: Mapped["Repository"] = relationship(back_populates="deployments")
    recovery_deployment: Mapped["Deployment | None"] = relationship(
        remote_side="Deployment.id", foreign_keys=[recovery_deployment_id]
    )


class AISettings(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    feature_general_analysis: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    feature_one_on_one_prep: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    feature_team_health: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    feature_work_categorization: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    monthly_token_budget: Mapped[int | None] = mapped_column(Integer)
    budget_warning_threshold: Mapped[float] = mapped_column(
        Float, server_default="0.8"
    )
    input_token_price_per_million: Mapped[float] = mapped_column(
        Float, server_default="3.0"
    )
    output_token_price_per_million: Mapped[float] = mapped_column(
        Float, server_default="15.0"
    )
    pricing_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    cooldown_minutes: Mapped[int] = mapped_column(Integer, server_default="30")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255))


class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    items_classified: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )


class DeveloperRelationship(Base):
    __tablename__ = "developer_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "target_id", "relationship_type",
            name="uq_dev_rel_source_target_type",
        ),
        CheckConstraint("source_id != target_id", name="ck_dev_rel_no_self"),
        Index("ix_dev_rel_source", "source_id"),
        Index("ix_dev_rel_target", "target_id"),
        Index("ix_dev_rel_type", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    source: Mapped["Developer"] = relationship(
        back_populates="relationships_as_source", foreign_keys=[source_id]
    )
    target: Mapped["Developer"] = relationship(
        back_populates="relationships_as_target", foreign_keys=[target_id]
    )


class DeveloperCollaborationScore(Base):
    __tablename__ = "developer_collaboration_scores"
    __table_args__ = (
        UniqueConstraint(
            "developer_a_id", "developer_b_id", "period_start", "period_end",
            name="uq_collab_score_pair_period",
        ),
        CheckConstraint(
            "developer_a_id < developer_b_id", name="ck_collab_score_canonical"
        ),
        Index("ix_collab_score_a", "developer_a_id"),
        Index("ix_collab_score_b", "developer_b_id"),
        Index("ix_collab_score_total", "total_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    developer_a_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id"), nullable=False
    )
    developer_b_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id"), nullable=False
    )
    developer_a: Mapped["Developer"] = relationship(
        foreign_keys=[developer_a_id]
    )
    developer_b: Mapped["Developer"] = relationship(
        foreign_keys=[developer_b_id]
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    review_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    coauthor_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    issue_comment_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    mention_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    co_assigned_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    total_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )


class SlackConfig(Base):
    """Singleton (id=1) global Slack integration configuration."""
    __tablename__ = "slack_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    bot_token: Mapped[str | None] = mapped_column(Text)
    default_channel: Mapped[str | None] = mapped_column(String(255))
    notify_stale_prs: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_high_risk_prs: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_workload_alerts: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_sync_failures: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_sync_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notify_weekly_digest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    stale_pr_days_threshold: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    risk_score_threshold: Mapped[float] = mapped_column(Float, default=0.7, server_default="0.7")
    digest_day_of_week: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    digest_hour_utc: Mapped[int] = mapped_column(Integer, default=9, server_default="9")
    stale_check_hour_utc: Mapped[int] = mapped_column(Integer, default=9, server_default="9")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255))


class SlackUserSettings(Base):
    """Per-developer Slack notification preferences and Slack user ID."""
    __tablename__ = "slack_user_settings"
    __table_args__ = (
        UniqueConstraint("developer_id", name="uq_slack_user_dev"),
        Index("ix_slack_user_dev", "developer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id"), nullable=False
    )
    slack_user_id: Mapped[str | None] = mapped_column(String(50))
    notify_stale_prs: Mapped[bool] = mapped_column(Boolean, server_default="true")
    notify_high_risk_prs: Mapped[bool] = mapped_column(Boolean, server_default="true")
    notify_workload_alerts: Mapped[bool] = mapped_column(Boolean, server_default="true")
    notify_weekly_digest: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotificationLog(Base):
    """Audit trail for sent Slack notifications."""
    __tablename__ = "notification_log"
    __table_args__ = (
        Index("ix_notification_log_type", "notification_type"),
        Index("ix_notification_log_created", "created_at"),
        Index("ix_notification_log_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(255))
    recipient_developer_id: Mapped[int | None] = mapped_column(
        ForeignKey("developers.id")
    )
    status: Mapped[str] = mapped_column(String(20), server_default="sent")
    error_message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
