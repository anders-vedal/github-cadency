from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


# --- Enums ---


class DeveloperRole(str, Enum):
    developer = "developer"
    senior_developer = "senior_developer"
    lead = "lead"
    architect = "architect"
    devops = "devops"
    qa = "qa"
    intern = "intern"


class AnalysisType(str, Enum):
    communication = "communication"
    conflict = "conflict"
    sentiment = "sentiment"


class ScopeType(str, Enum):
    developer = "developer"
    team = "team"
    repo = "repo"


# --- Developer schemas ---


class DeveloperCreate(BaseModel):
    github_username: str
    display_name: str
    email: str | None = None
    role: DeveloperRole | None = None
    skills: list[str] | None = None
    specialty: str | None = None
    location: str | None = None
    timezone: str | None = None
    team: str | None = None
    notes: str | None = None


class DeveloperUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: DeveloperRole | None = None
    skills: list[str] | None = None
    specialty: str | None = None
    location: str | None = None
    timezone: str | None = None
    team: str | None = None
    notes: str | None = None


class DeveloperResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    github_username: str
    display_name: str
    email: str | None
    role: str | None
    skills: list[str] | None
    specialty: str | None
    location: str | None
    timezone: str | None
    team: str | None
    is_active: bool
    avatar_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# --- Stats schemas ---


class DateRangeParams(BaseModel):
    date_from: datetime | None = None
    date_to: datetime | None = None


class ReviewBreakdown(BaseModel):
    approved: int = 0
    changes_requested: int = 0
    commented: int = 0


class ReviewQualityBreakdown(BaseModel):
    rubber_stamp: int = 0
    minimal: int = 0
    standard: int = 0
    thorough: int = 0


class DeveloperStatsResponse(BaseModel):
    prs_opened: int = 0
    prs_merged: int = 0
    prs_closed_without_merge: int = 0
    prs_open: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_changed_files: int = 0
    reviews_given: ReviewBreakdown = ReviewBreakdown()
    reviews_received: int = 0
    review_quality_breakdown: ReviewQualityBreakdown = ReviewQualityBreakdown()
    review_quality_score: float | None = None
    avg_time_to_first_review_hours: float | None = None
    avg_time_to_merge_hours: float | None = None
    issues_assigned: int = 0
    issues_closed: int = 0
    avg_time_to_close_issue_hours: float | None = None


class TopContributor(BaseModel):
    developer_id: int
    github_username: str
    display_name: str
    pr_count: int


class TeamStatsResponse(BaseModel):
    developer_count: int = 0
    total_prs: int = 0
    total_merged: int = 0
    merge_rate: float | None = None
    avg_time_to_first_review_hours: float | None = None
    avg_time_to_merge_hours: float | None = None
    total_reviews: int = 0
    total_issues_closed: int = 0


class RepoStatsResponse(BaseModel):
    total_prs: int = 0
    total_merged: int = 0
    total_issues: int = 0
    total_issues_closed: int = 0
    total_reviews: int = 0
    avg_time_to_merge_hours: float | None = None
    top_contributors: list[TopContributor] = []


# --- Benchmark schemas (M2) ---


class BenchmarkMetric(BaseModel):
    p25: float
    p50: float
    p75: float


class BenchmarksResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    sample_size: int
    team: str | None = None
    metrics: dict[str, BenchmarkMetric]


class PercentilePlacement(BaseModel):
    value: float
    percentile_band: str  # below_p25, p25_to_p50, p50_to_p75, above_p75
    team_median: float


class DeveloperStatsWithPercentilesResponse(DeveloperStatsResponse):
    percentiles: dict[str, PercentilePlacement] | None = None


# --- Trend schemas (M3) ---


class TrendPeriod(BaseModel):
    start: datetime
    end: datetime
    prs_merged: int = 0
    avg_time_to_merge_h: float | None = None
    reviews_given: int = 0
    additions: int = 0
    deletions: int = 0
    issues_closed: int = 0


class TrendDirection(BaseModel):
    direction: str  # improving, stable, worsening
    change_pct: float


class DeveloperTrendsResponse(BaseModel):
    developer_id: int
    period_type: str
    periods: list[TrendPeriod]
    trends: dict[str, TrendDirection]


# --- Workload schemas (M4) ---


class DeveloperWorkload(BaseModel):
    developer_id: int
    github_username: str
    display_name: str
    open_prs_authored: int = 0
    open_prs_reviewing: int = 0
    open_issues_assigned: int = 0
    reviews_given_this_period: int = 0
    reviews_received_this_period: int = 0
    prs_waiting_for_review: int = 0
    avg_review_wait_h: float | None = None
    workload_score: str = "balanced"  # low, balanced, high, overloaded


class WorkloadAlert(BaseModel):
    type: str  # review_bottleneck, stale_prs, uneven_assignment, underutilized
    developer_id: int | None = None
    message: str


class WorkloadResponse(BaseModel):
    developers: list[DeveloperWorkload]
    alerts: list[WorkloadAlert]


# --- Collaboration schemas (M5) ---


class CollaborationPair(BaseModel):
    reviewer_id: int
    reviewer_name: str
    reviewer_team: str | None
    author_id: int
    author_name: str
    author_team: str | None
    reviews_count: int = 0
    approvals: int = 0
    changes_requested: int = 0


class BusFactorEntry(BaseModel):
    repo_name: str
    sole_reviewer_id: int
    sole_reviewer_name: str
    review_share_pct: float


class CollaborationInsights(BaseModel):
    silos: list[dict]  # [{team_a, team_b, note}]
    bus_factors: list[BusFactorEntry]
    isolated_developers: list[dict]  # [{developer_id, display_name}]
    strongest_pairs: list[CollaborationPair]


class CollaborationResponse(BaseModel):
    matrix: list[CollaborationPair]
    insights: CollaborationInsights


# --- Goals schemas (M6) ---


class MetricKey(str, Enum):
    avg_pr_additions = "avg_pr_additions"
    time_to_merge_h = "time_to_merge_h"
    reviews_given = "reviews_given"
    review_quality_score = "review_quality_score"
    prs_merged = "prs_merged"
    time_to_first_review_h = "time_to_first_review_h"
    issues_closed = "issues_closed"
    prs_opened = "prs_opened"


class GoalCreate(BaseModel):
    developer_id: int
    title: str
    description: str | None = None
    metric_key: MetricKey
    target_value: float
    target_direction: Literal["above", "below"] = "above"
    target_date: date | None = None


class GoalUpdate(BaseModel):
    status: Literal["active", "achieved", "abandoned"] | None = None
    notes: str | None = None


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    developer_id: int
    title: str
    description: str | None
    metric_key: str
    target_value: float
    target_direction: str
    baseline_value: float | None
    status: str
    created_at: datetime
    target_date: date | None
    achieved_at: datetime | None
    notes: str | None


class GoalProgressPoint(BaseModel):
    period_end: datetime
    value: float


class GoalProgressResponse(BaseModel):
    goal_id: int
    title: str
    target_value: float
    target_direction: str
    baseline_value: float | None
    current_value: float | None
    status: str
    history: list[GoalProgressPoint]


# --- Sync schemas ---


class RepoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    github_id: int
    name: str | None
    full_name: str | None
    description: str | None
    language: str | None
    is_tracked: bool
    last_synced_at: datetime | None
    created_at: datetime


class RepoTrackUpdate(BaseModel):
    is_tracked: bool


class SyncEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sync_type: str | None
    status: str | None
    repos_synced: int | None
    prs_upserted: int | None
    issues_upserted: int | None
    errors: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_s: int | None


# --- AI Analysis schemas ---


class AIAnalyzeRequest(BaseModel):
    analysis_type: AnalysisType
    scope_type: ScopeType
    scope_id: str
    date_from: datetime
    date_to: datetime


class AIAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_type: str | None
    scope_type: str | None
    scope_id: str | None
    date_from: datetime | None
    date_to: datetime | None
    input_summary: str | None
    result: dict | None
    model_used: str | None
    tokens_used: int | None
    triggered_by: str | None
    created_at: datetime


# --- 1:1 Prep Brief schemas (M7) ---


class OneOnOnePrepRequest(BaseModel):
    developer_id: int
    date_from: datetime
    date_to: datetime


# --- Team Health Check schemas (M8) ---


class TeamHealthRequest(BaseModel):
    team: str | None = None
    date_from: datetime
    date_to: datetime
