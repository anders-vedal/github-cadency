from datetime import datetime

from sqlalchemy import (
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
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(512), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repo")
    issues: Mapped[list["Issue"]] = relationship(back_populates="repo")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),
        Index("ix_pr_author_created", "author_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, nullable=False)
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
    html_url: Mapped[str | None] = mapped_column(Text)

    repo: Mapped["Repository"] = relationship(back_populates="pull_requests")
    author: Mapped["Developer | None"] = relationship(back_populates="pull_requests")
    reviews: Mapped[list["PRReview"]] = relationship(back_populates="pr")
    review_comments: Mapped[list["PRReviewComment"]] = relationship(back_populates="pr")


class PRReview(Base):
    __tablename__ = "pr_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
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
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id"), nullable=False
    )
    review_id: Mapped[int | None] = mapped_column(ForeignKey("pr_reviews.id"))
    author_github_username: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pr: Mapped["PullRequest"] = relationship(back_populates="review_comments")
    review: Mapped["PRReview | None"] = relationship(back_populates="comments")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_issue_repo_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, nullable=False)
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

    repo: Mapped["Repository"] = relationship(back_populates="issues")
    assignee: Mapped["Developer | None"] = relationship(back_populates="assigned_issues")
    comments: Mapped[list["IssueComment"]] = relationship(back_populates="issue")


class IssueComment(Base):
    __tablename__ = "issue_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False)
    author_github_username: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issue: Mapped["Issue"] = relationship(back_populates="comments")


class SyncEvent(Base):
    __tablename__ = "sync_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_type: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str | None] = mapped_column(String(20))
    repos_synced: Mapped[int | None] = mapped_column(Integer)
    prs_upserted: Mapped[int | None] = mapped_column(Integer)
    issues_upserted: Mapped[int | None] = mapped_column(Integer)
    errors: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int | None] = mapped_column(Integer)


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

    developer: Mapped["Developer"] = relationship(back_populates="goals")
