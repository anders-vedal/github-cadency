from datetime import date, datetime

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
    team: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("teams.name", onupdate="CASCADE", ondelete="SET NULL")
    )
    app_role: Mapped[str] = mapped_column(String(20), nullable=False, default="developer", server_default="developer")
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
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
    assigned_issues: Mapped[list["Issue"]] = relationship(
        back_populates="assignee", foreign_keys="Issue.assignee_id"
    )
    created_issues: Mapped[list["Issue"]] = relationship(
        back_populates="creator", foreign_keys="Issue.creator_id"
    )
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
    work_category: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("work_categories.category_key", ondelete="SET NULL")
    )
    work_category_source: Mapped[str | None] = mapped_column(String(50))
    author_github_username: Mapped[str | None] = mapped_column(String(255))

    # Phase 09 — GitHub PR timeline enrichment aggregates
    force_push_count_after_first_review: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    review_requested_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    ready_for_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_flip_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    renamed_title_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    dismissed_review_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    merge_queue_waited_s: Mapped[int | None] = mapped_column(Integer)
    auto_merge_waited_s: Mapped[int | None] = mapped_column(Integer)
    codeowners_bypass: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    repo: Mapped["Repository"] = relationship(back_populates="pull_requests")
    author: Mapped["Developer | None"] = relationship(back_populates="pull_requests")
    reviews: Mapped[list["PRReview"]] = relationship(back_populates="pr")
    review_comments: Mapped[list["PRReviewComment"]] = relationship(back_populates="pr")
    files: Mapped[list["PRFile"]] = relationship(back_populates="pr")
    check_runs: Mapped[list["PRCheckRun"]] = relationship(back_populates="pr")
    timeline_events: Mapped[list["PRTimelineEvent"]] = relationship(back_populates="pr")


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
    __table_args__ = (
        Index("ix_pr_review_comment_pr_id", "pr_id"),
    )

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
    html_url: Mapped[str | None] = mapped_column(Text)

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
        Index("ix_issue_creator_id", "creator_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    assignee_github_username: Mapped[str | None] = mapped_column(String(255))
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
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
    issue_type: Mapped[str | None] = mapped_column(String(100))
    work_category: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("work_categories.category_key", ondelete="SET NULL")
    )
    work_category_source: Mapped[str | None] = mapped_column(String(50))

    repo: Mapped["Repository"] = relationship(back_populates="issues")
    assignee: Mapped["Developer | None"] = relationship(
        back_populates="assigned_issues", foreign_keys=[assignee_id]
    )
    creator: Mapped["Developer | None"] = relationship(
        back_populates="created_issues", foreign_keys=[creator_id]
    )
    comments: Mapped[list["IssueComment"]] = relationship(back_populates="issue")


class IssueComment(Base):
    __tablename__ = "issue_comments"
    __table_args__ = (
        Index("ix_issue_comment_issue_id", "issue_id"),
    )

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
    triggered_by: Mapped[str | None] = mapped_column(String(50))
    sync_scope: Mapped[str | None] = mapped_column(String(255))


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
    target_date: Mapped[date | None] = mapped_column(Date)
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


class AIAnalysisSchedule(Base):
    __tablename__ = "ai_analysis_schedules"
    __table_args__ = (
        Index("ix_ai_analysis_schedules_is_enabled", "is_enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Analysis config
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # For general analysis: 'communication', 'conflict', 'sentiment'
    # For others: stored in analysis_type directly ('one_on_one_prep', 'team_health')
    general_type: Mapped[str | None] = mapped_column(String(50))
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_ids: Mapped[list | None] = mapped_column(JSONB)
    time_range_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # Schedule config
    frequency: Mapped[str] = mapped_column(String(30), nullable=False)
    # 'daily', 'weekly', 'biweekly', 'monthly'
    day_of_week: Mapped[int | None] = mapped_column(Integer)
    # 0=Monday..6=Sunday, used for weekly/biweekly
    hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # State
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_analysis_id: Mapped[int | None] = mapped_column(Integer)
    last_run_status: Mapped[str | None] = mapped_column(String(30))
    # 'success', 'failed', 'budget_exceeded', 'feature_disabled'
    # Audit
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
        server_default=func.now()
    )


class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"
    __table_args__ = (
        Index("ix_ai_usage_log_created_at", "created_at"),
    )

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


class SyncScheduleConfig(Base):
    """Singleton (id=1) sync schedule configuration."""
    __tablename__ = "sync_schedule_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    auto_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    incremental_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=15, server_default="15"
    )
    full_sync_cron_hour: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2"
    )
    # Linear sync schedule
    linear_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    linear_sync_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=120, server_default="120"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=datetime.utcnow, server_default=func.now()
    )


class BenchmarkGroupConfig(Base):
    """Admin-configurable benchmark peer group definitions."""
    __tablename__ = "benchmark_group_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    roles: Mapped[list] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[list] = mapped_column(JSONB, nullable=False)
    min_team_size: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
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
        DateTime(timezone=True), server_default=func.now(), onupdate=datetime.utcnow
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


class Team(Base):
    """Canonical team list. Developer.team stores team name (validated against this table)."""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )


class WorkCategory(Base):
    """Admin-configurable work category definitions (feature, bugfix, epic, etc.)."""
    __tablename__ = "work_categories"

    category_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    exclude_from_stats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    rules: Mapped[list["WorkCategoryRule"]] = relationship(back_populates="category", cascade="all, delete-orphan")


class WorkCategoryRule(Base):
    """Admin-configurable rules for classifying PRs/issues into work categories."""
    __tablename__ = "work_category_rules"
    __table_args__ = (
        Index("ix_work_category_rules_priority", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_type: Mapped[str] = mapped_column(String(30), nullable=False)  # label, title_regex, prefix, issue_type
    match_value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    category_key: Mapped[str] = mapped_column(String(50), ForeignKey("work_categories.category_key"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    category: Mapped["WorkCategory"] = relationship(back_populates="rules")


class Notification(Base):
    """Materialized alert records with dedup and lifecycle management."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_alert_type", "alert_type"),
        Index("ix_notifications_severity", "severity"),
        Index("ix_notifications_resolved_at", "resolved_at"),
        Index("ix_notifications_developer_id", "developer_id"),
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_type_resolved", "alert_type", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    alert_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    link_path: Mapped[str | None] = mapped_column(String(500))
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )


class NotificationRead(Base):
    """Tracks which users have seen each notification."""
    __tablename__ = "notification_reads"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_notification_read"),
        Index("ix_notification_reads_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("developers.id"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )


class NotificationDismissal(Base):
    """Per-instance dismissal with optional expiry."""
    __tablename__ = "notification_dismissals"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_notification_dismissal"),
        Index("ix_notification_dismissals_user", "user_id"),
        Index("ix_notification_dismissals_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("developers.id"), nullable=False)
    dismiss_type: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )


class NotificationTypeDismissal(Base):
    """Dismiss an entire alert type (e.g. mute all underutilized alerts for 7 days)."""
    __tablename__ = "notification_type_dismissals"
    __table_args__ = (
        UniqueConstraint("alert_type", "user_id", name="uq_notification_type_dismissal"),
        Index("ix_notification_type_dismissals_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("developers.id"), nullable=False)
    dismiss_type: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )


class NotificationConfig(Base):
    """Singleton (id=1) admin-configurable alert thresholds and toggles."""
    __tablename__ = "notification_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Per-alert-type enable toggles
    alert_stale_pr_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_review_bottleneck_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_underutilized_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_uneven_assignment_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_merged_without_approval_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_revert_spike_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_high_risk_pr_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_bus_factor_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_declining_trends_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_issue_linkage_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_ai_budget_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_sync_failure_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_unassigned_roles_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_missing_config_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Planning alert toggles
    alert_velocity_declining_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_scope_creep_high_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_sprint_at_risk_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_triage_queue_growing_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_estimation_accuracy_low_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    alert_linear_sync_failure_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Configurable thresholds
    stale_pr_threshold_hours: Mapped[int] = mapped_column(Integer, server_default="48")
    review_bottleneck_multiplier: Mapped[float] = mapped_column(Float, server_default="2.0")
    revert_spike_threshold_pct: Mapped[float] = mapped_column(Float, server_default="5.0")
    high_risk_pr_min_level: Mapped[str] = mapped_column(String(20), server_default="high")
    issue_linkage_threshold_pct: Mapped[float] = mapped_column(Float, server_default="20.0")
    declining_trend_pr_drop_pct: Mapped[float] = mapped_column(Float, server_default="30.0")
    declining_trend_quality_drop_pct: Mapped[float] = mapped_column(Float, server_default="20.0")
    # Planning thresholds
    velocity_decline_pct: Mapped[float] = mapped_column(Float, server_default="20.0")
    scope_creep_threshold_pct: Mapped[float] = mapped_column(Float, server_default="25.0")
    sprint_risk_completion_pct: Mapped[float] = mapped_column(Float, server_default="50.0")
    triage_queue_max: Mapped[int] = mapped_column(Integer, server_default="10")
    triage_duration_hours_max: Mapped[int] = mapped_column(Integer, server_default="48")
    estimation_accuracy_min_pct: Mapped[float] = mapped_column(Float, server_default="60.0")
    # Contribution category exclusion
    exclude_contribution_categories: Mapped[list | None] = mapped_column(JSONB, server_default='["system", "non_contributor"]')
    # Evaluation schedule
    evaluation_interval_minutes: Mapped[int] = mapped_column(Integer, server_default="15")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255))


class IntegrationConfig(Base):
    """External integration configuration (Linear, future: Jira, etc.)."""
    __tablename__ = "integration_config"
    __table_args__ = (
        Index("ix_integration_config_type", "type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    api_key: Mapped[str | None] = mapped_column(Text)
    workspace_id: Mapped[str | None] = mapped_column(String(255))
    workspace_name: Mapped[str | None] = mapped_column(String(255))
    config: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")
    error_message: Mapped[str | None] = mapped_column(Text)
    is_primary_issue_source: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    external_projects: Mapped[list["ExternalProject"]] = relationship(back_populates="integration", cascade="all, delete-orphan")
    external_sprints: Mapped[list["ExternalSprint"]] = relationship(back_populates="integration", cascade="all, delete-orphan")
    external_issues: Mapped[list["ExternalIssue"]] = relationship(back_populates="integration", cascade="all, delete-orphan")


class ExternalProject(Base):
    """External project tracker projects (Linear projects, etc.)."""
    __tablename__ = "external_projects"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_external_projects_ext_id"),
        Index("ix_external_projects_integration", "integration_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integration_config.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(String(30))
    health: Mapped[str | None] = mapped_column(String(30))
    start_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    progress_pct: Mapped[float | None] = mapped_column(Float)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    integration: Mapped["IntegrationConfig"] = relationship(back_populates="external_projects")
    lead: Mapped["Developer | None"] = relationship(foreign_keys=[lead_id])
    issues: Mapped[list["ExternalIssue"]] = relationship(back_populates="project")


class ExternalSprint(Base):
    """External sprint/cycle data (Linear cycles, etc.)."""
    __tablename__ = "external_sprints"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_external_sprints_ext_id"),
        Index("ix_external_sprints_integration", "integration_id"),
        Index("ix_external_sprints_state", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integration_config.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    number: Mapped[int | None] = mapped_column(Integer)
    team_key: Mapped[str | None] = mapped_column(String(100))
    team_name: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    planned_scope: Mapped[int | None] = mapped_column(Integer)
    completed_scope: Mapped[int | None] = mapped_column(Integer)
    cancelled_scope: Mapped[int | None] = mapped_column(Integer)
    added_scope: Mapped[int | None] = mapped_column(Integer)
    scope_unit: Mapped[str | None] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )

    integration: Mapped["IntegrationConfig"] = relationship(back_populates="external_sprints")
    issues: Mapped[list["ExternalIssue"]] = relationship(back_populates="sprint")


class ExternalIssue(Base):
    """External issue tracker issues (Linear issues, etc.)."""
    __tablename__ = "external_issues"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_external_issues_ext_id"),
        Index("ix_external_issues_integration", "integration_id"),
        Index("ix_external_issues_identifier", "identifier"),
        Index("ix_external_issues_sprint", "sprint_id"),
        Index("ix_external_issues_project", "project_id"),
        Index("ix_external_issues_assignee", "assignee_developer_id"),
        Index("ix_external_issues_creator", "creator_developer_id"),
        Index("ix_external_issues_status_category", "status_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integration_config.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    identifier: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description_length: Mapped[int | None] = mapped_column(Integer)
    issue_type: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str | None] = mapped_column(String(100))
    status_category: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    priority_label: Mapped[str | None] = mapped_column(String(30))
    estimate: Mapped[float | None] = mapped_column(Float)
    assignee_email: Mapped[str | None] = mapped_column(String(320))
    assignee_developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    creator_email: Mapped[str | None] = mapped_column(String(320))
    creator_developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    work_category: Mapped[str | None] = mapped_column(String(50))
    work_category_source: Mapped[str | None] = mapped_column(String(20))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("external_projects.id", ondelete="SET NULL"))
    sprint_id: Mapped[int | None] = mapped_column(ForeignKey("external_sprints.id", ondelete="SET NULL"))
    parent_issue_id: Mapped[int | None] = mapped_column(ForeignKey("external_issues.id", ondelete="SET NULL"))
    labels: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )
    triage_duration_s: Mapped[int | None] = mapped_column(Integer)
    cycle_time_s: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(Text)

    # SLA (Linear exposes these directly on Issue)
    sla_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_breaches_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_high_risk_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_medium_risk_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_type: Mapped[str | None] = mapped_column(String(30))
    sla_status: Mapped[str | None] = mapped_column(String(30))

    # Triage
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triage_responsibility_team_id: Mapped[str | None] = mapped_column(String(255))
    triage_auto_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Stakeholder signal
    subscribers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Reactions blob
    reaction_data: Mapped[list | None] = mapped_column(JSONB)

    integration: Mapped["IntegrationConfig"] = relationship(back_populates="external_issues")
    assignee: Mapped["Developer | None"] = relationship(foreign_keys=[assignee_developer_id])
    creator: Mapped["Developer | None"] = relationship(foreign_keys=[creator_developer_id])
    project: Mapped["ExternalProject | None"] = relationship(back_populates="issues")
    sprint: Mapped["ExternalSprint | None"] = relationship(back_populates="issues")
    parent_issue: Mapped["ExternalIssue | None"] = relationship(remote_side="ExternalIssue.id")
    pr_links: Mapped[list["PRExternalIssueLink"]] = relationship(back_populates="external_issue")


class DeveloperIdentityMap(Base):
    """Maps developers to their identities in external systems (Linear, etc.)."""
    __tablename__ = "developer_identity_map"
    __table_args__ = (
        UniqueConstraint("developer_id", "integration_type", name="uq_dev_identity_map"),
        Index("ix_dev_identity_map_ext_email", "external_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), nullable=False)
    integration_type: Mapped[str] = mapped_column(String(30), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_email: Mapped[str | None] = mapped_column(String(320))
    external_display_name: Mapped[str | None] = mapped_column(String(255))
    mapped_by: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )

    developer: Mapped["Developer"] = relationship(foreign_keys=[developer_id])


class PRExternalIssueLink(Base):
    """Links pull requests to external issue tracker issues."""
    __tablename__ = "pr_external_issue_links"
    __table_args__ = (
        UniqueConstraint("pull_request_id", "external_issue_id", name="uq_pr_ext_issue_link"),
        Index("ix_pr_ext_issue_links_pr", "pull_request_id"),
        Index("ix_pr_ext_issue_links_issue", "external_issue_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False)
    external_issue_id: Mapped[int] = mapped_column(ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False)
    link_source: Mapped[str] = mapped_column(String(30), nullable=False)
    link_confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="low", server_default="low")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )

    pull_request: Mapped["PullRequest"] = relationship(foreign_keys=[pull_request_id])
    external_issue: Mapped["ExternalIssue"] = relationship(back_populates="pr_links")


class ClassifierRule(Base):
    """Admin-editable rules for incident/hotfix + AI-cohort classification (Phase 10 C3).

    A single table with a ``kind`` discriminator powers three rule families:

    - ``incident``: augments ``services/incident_classification.default_rules()``
      (title/label/revert detection driving Change Failure Rate).
    - ``ai_reviewer``: pattern strings matched against
      ``PRReview.reviewer_github_username`` to classify AI-reviewed PRs.
    - ``ai_author``: label patterns matched against ``PullRequest.labels`` to
      classify AI-authored PRs.

    All rows are additive on top of the hard-coded defaults (Python constants
    in each service). This lets DevPulse ship with a sensible baseline while
    letting admins override per-workspace.
    """

    __tablename__ = "classifier_rules"
    __table_args__ = (
        Index("ix_classifier_rules_kind", "kind", "enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 'incident' | 'ai_reviewer' | 'ai_author'
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # For incident: 'pr_title_prefix' | 'revert_detection' | 'github_label' |
    # 'linear_label' | 'linear_issue_type'.
    # For ai_reviewer / ai_author: 'username' / 'label' (kept as a string for
    # forward compatibility even though today the meaning is implied by kind).
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_hotfix: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_incident: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="100"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PRTimelineEvent(Base):
    """GitHub PR timeline items captured via GraphQL `timelineItems`.

    One row per event (force push, ready-for-review, review request, label,
    merge-queue transition, auto-merge toggle, cross-reference, etc). Used to
    derive bounce counts, review-queue latencies, CODEOWNERS bypass, and
    precise cycle-time stage decomposition.
    """

    __tablename__ = "pr_timeline_events"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_pr_timeline_event_ext_id"),
        Index(
            "ix_pr_timeline_events_pr_type_created",
            "pr_id",
            "event_type",
            "created_at",
        ),
        Index(
            "ix_pr_timeline_events_type_created", "event_type", "created_at"
        ),
        Index(
            "ix_pr_timeline_events_actor_created",
            "actor_developer_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_developer_id: Mapped[int | None] = mapped_column(
        ForeignKey("developers.id", ondelete="SET NULL")
    )
    actor_github_username: Mapped[str | None] = mapped_column(String(255))
    subject_developer_id: Mapped[int | None] = mapped_column(
        ForeignKey("developers.id", ondelete="SET NULL")
    )
    subject_github_username: Mapped[str | None] = mapped_column(String(255))
    before_sha: Mapped[str | None] = mapped_column(String(40))
    after_sha: Mapped[str | None] = mapped_column(String(40))
    data: Mapped[dict | None] = mapped_column(JSONB)

    pr: Mapped["PullRequest"] = relationship(
        back_populates="timeline_events", foreign_keys=[pr_id]
    )
    actor: Mapped["Developer | None"] = relationship(
        foreign_keys=[actor_developer_id], viewonly=True
    )
    subject: Mapped["Developer | None"] = relationship(
        foreign_keys=[subject_developer_id], viewonly=True
    )


class ExternalIssueComment(Base):
    """Comments on Linear issues. Stores metadata + 280-char preview, not full body."""
    __tablename__ = "external_issue_comments"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_ext_issue_comment_ext_id"),
        Index("ix_ext_issue_comments_issue_created", "issue_id", "created_at"),
        Index("ix_ext_issue_comments_author", "author_developer_id", "created_at"),
        Index("ix_ext_issue_comments_parent", "parent_comment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_comment_id: Mapped[int | None] = mapped_column(ForeignKey("external_issue_comments.id", ondelete="SET NULL"))
    author_developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    author_email: Mapped[str | None] = mapped_column(String(320))
    external_user_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    body_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    body_preview: Mapped[str | None] = mapped_column(String(280))
    reaction_data: Mapped[list | None] = mapped_column(JSONB)
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    bot_actor_type: Mapped[str | None] = mapped_column(String(50))

    issue: Mapped["ExternalIssue"] = relationship(foreign_keys=[issue_id])
    author: Mapped["Developer | None"] = relationship(foreign_keys=[author_developer_id])


class ExternalIssueHistoryEvent(Base):
    """Linear IssueHistory events — structured transitions with all changed columns."""
    __tablename__ = "external_issue_history"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_ext_issue_history_ext_id"),
        Index("ix_ext_issue_history_issue_changed", "issue_id", "changed_at"),
        Index("ix_ext_issue_history_category", "to_state_category", "changed_at"),
        Index("ix_ext_issue_history_actor", "actor_developer_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(320))
    bot_actor_type: Mapped[str | None] = mapped_column(String(50))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # State transition (store both raw state name and mapped category)
    from_state: Mapped[str | None] = mapped_column(String(100))
    to_state: Mapped[str | None] = mapped_column(String(100))
    from_state_category: Mapped[str | None] = mapped_column(String(30))
    to_state_category: Mapped[str | None] = mapped_column(String(30))
    # Assignee transition
    from_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    to_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    # Estimate
    from_estimate: Mapped[float | None] = mapped_column(Float)
    to_estimate: Mapped[float | None] = mapped_column(Float)
    # Priority
    from_priority: Mapped[int | None] = mapped_column(Integer)
    to_priority: Mapped[int | None] = mapped_column(Integer)
    # Cycle
    from_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("external_sprints.id", ondelete="SET NULL"))
    to_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("external_sprints.id", ondelete="SET NULL"))
    # Project
    from_project_id: Mapped[int | None] = mapped_column(ForeignKey("external_projects.id", ondelete="SET NULL"))
    to_project_id: Mapped[int | None] = mapped_column(ForeignKey("external_projects.id", ondelete="SET NULL"))
    # Parent
    from_parent_id: Mapped[int | None] = mapped_column(ForeignKey("external_issues.id", ondelete="SET NULL"))
    to_parent_id: Mapped[int | None] = mapped_column(ForeignKey("external_issues.id", ondelete="SET NULL"))
    # Labels
    added_label_ids: Mapped[list | None] = mapped_column(JSONB)
    removed_label_ids: Mapped[list | None] = mapped_column(JSONB)
    # Archive flags
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    auto_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    auto_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    issue: Mapped["ExternalIssue"] = relationship(foreign_keys=[issue_id])
    actor: Mapped["Developer | None"] = relationship(foreign_keys=[actor_developer_id])


class ExternalIssueAttachment(Base):
    """Attachments on Linear issues — e.g. GitHub PR links, Slack, Figma."""
    __tablename__ = "external_issue_attachments"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_ext_issue_attachment_ext_id"),
        Index("ix_ext_issue_attachments_issue_type", "issue_id", "normalized_source_type"),
        Index("ix_ext_issue_attachments_url", "url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50))
    normalized_source_type: Mapped[str | None] = mapped_column(String(30))
    title: Mapped[str | None] = mapped_column(String(500))
    attachment_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    issue: Mapped["ExternalIssue"] = relationship(foreign_keys=[issue_id])


class ExternalIssueRelation(Base):
    """Linear IssueRelation — blocks/blocked_by/related/duplicate. Stored bidirectionally."""
    __tablename__ = "external_issue_relations"
    __table_args__ = (
        UniqueConstraint("external_id", "relation_type", "issue_id", name="uq_ext_issue_relation_ext_id_type"),
        Index("ix_ext_issue_relations_issue_type", "issue_id", "relation_type"),
        Index("ix_ext_issue_relations_related_type", "related_issue_id", "relation_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False)
    related_issue_id: Mapped[int] = mapped_column(ForeignKey("external_issues.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    issue: Mapped["ExternalIssue"] = relationship(foreign_keys=[issue_id])
    related_issue: Mapped["ExternalIssue"] = relationship(foreign_keys=[related_issue_id])


class ExternalProjectUpdate(Base):
    """Linear ProjectUpdate — the authoritative project-health narrative (onTrack/atRisk/offTrack)."""
    __tablename__ = "external_project_updates"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_ext_project_update_ext_id"),
        Index("ix_ext_project_updates_project_created", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("external_projects.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    author_email: Mapped[str | None] = mapped_column(String(320))
    body_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    body_preview: Mapped[str | None] = mapped_column(String(280))
    diff_length: Mapped[int | None] = mapped_column(Integer)
    health: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reaction_data: Mapped[list | None] = mapped_column(JSONB)

    project: Mapped["ExternalProject"] = relationship(foreign_keys=[project_id])
    author: Mapped["Developer | None"] = relationship(foreign_keys=[author_developer_id])


class RoleDefinition(Base):
    """Admin-configurable role definitions linked to fixed contribution categories."""
    __tablename__ = "role_definitions"

    role_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contribution_category: Mapped[str] = mapped_column(String(30), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now()
    )
