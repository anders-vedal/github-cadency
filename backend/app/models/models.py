from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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
    skills: Mapped[dict | None] = mapped_column(JSONB)
    specialty: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str | None] = mapped_column(String(50))
    team: Mapped[str | None] = mapped_column(String(255))
    app_role: Mapped[str] = mapped_column(String(20), nullable=False, default="developer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="author")
    reviews: Mapped[list["PRReview"]] = relationship(back_populates="reviewer")
    assigned_issues: Mapped[list["Issue"]] = relationship(back_populates="assignee")
    goals: Mapped[list["DeveloperGoal"]] = relationship(back_populates="developer")


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(512), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    tree_truncated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
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

    repo: Mapped["Repository"] = relationship(back_populates="pull_requests")
    author: Mapped["Developer | None"] = relationship(back_populates="pull_requests")
    reviews: Mapped[list["PRReview"]] = relationship(back_populates="pr")
    review_comments: Mapped[list["PRReviewComment"]] = relationship(back_populates="pr")
    files: Mapped[list["PRFile"]] = relationship(back_populates="pr")
    check_runs: Mapped[list["PRCheckRun"]] = relationship(back_populates="pr")


class PRReview(Base):
    __tablename__ = "pr_reviews"

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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(20))
    labels: Mapped[dict | None] = mapped_column(JSONB)
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
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issue: Mapped["Issue"] = relationship(back_populates="comments")


class SyncEvent(Base):
    __tablename__ = "sync_events"

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
        DateTime(timezone=True), default=datetime.utcnow
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
        String(10), nullable=False, default="above"
    )
    baseline_value: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
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

    repo: Mapped["Repository"] = relationship(back_populates="deployments")


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
        DateTime(timezone=True), default=datetime.utcnow
    )
