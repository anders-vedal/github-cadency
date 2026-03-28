from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

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


class AppRole(str, Enum):
    developer = "developer"
    admin = "admin"


class AnalysisType(str, Enum):
    communication = "communication"
    conflict = "conflict"
    sentiment = "sentiment"


class ScopeType(str, Enum):
    developer = "developer"
    team = "team"
    repo = "repo"


# --- Auth schemas ---


class AuthUser(BaseModel):
    developer_id: int
    github_username: str
    app_role: AppRole


class AuthMeResponse(BaseModel):
    developer_id: int
    github_username: str
    display_name: str
    app_role: AppRole
    avatar_url: str | None


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


class DeveloperUpdateAdmin(DeveloperUpdate):
    app_role: AppRole | None = None


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
    app_role: str
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
    prs_draft: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_changed_files: int = 0
    reviews_given: ReviewBreakdown = ReviewBreakdown()
    reviews_received: int = 0
    review_quality_breakdown: ReviewQualityBreakdown = ReviewQualityBreakdown()
    review_quality_score: float | None = None
    avg_time_to_first_review_hours: float | None = None
    avg_time_to_merge_hours: float | None = None
    avg_time_to_approve_hours: float | None = None
    avg_time_after_approve_hours: float | None = None
    prs_merged_without_approval: int = 0
    issues_assigned: int = 0
    issues_closed: int = 0
    avg_time_to_close_issue_hours: float | None = None
    avg_review_rounds: float | None = None
    prs_merged_first_pass: int = 0
    first_pass_rate: float | None = None
    prs_self_merged: int = 0
    self_merge_rate: float | None = None
    prs_reverted: int = 0
    reverts_authored: int = 0
    comment_type_distribution: dict[str, int] = {}
    nit_ratio: float | None = None
    blocker_catch_rate: float | None = None


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
    avg_review_rounds: float | None = None
    first_pass_rate: float | None = None
    revert_rate: float | None = None


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
    drafts_open: int = 0
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


# --- Stale PR schemas (P2-01) ---


class StalePR(BaseModel):
    pr_id: int
    number: int
    title: str
    html_url: str
    repo_name: str
    author_name: str | None = None
    author_id: int | None = None
    age_hours: float
    is_draft: bool = False
    review_count: int = 0
    has_approved: bool = False
    has_changes_requested: bool = False
    last_activity_at: datetime
    stale_reason: str  # "no_review", "changes_requested_no_response", "approved_not_merged"


class StalePRsResponse(BaseModel):
    stale_prs: list[StalePR]
    total_count: int


# --- Issue-PR Linkage schemas (P2-04) ---


class IssueLinkageStats(BaseModel):
    issues_with_linked_prs: int
    issues_without_linked_prs: int
    avg_prs_per_issue: float | None
    issues_with_multiple_prs: int
    prs_without_linked_issues: int


# --- Issue Quality schemas (P3-03) ---


class IssueQualityStats(BaseModel):
    total_issues_created: int
    avg_body_length: float
    pct_with_checklist: float
    avg_comment_count: float
    pct_closed_not_planned: float
    avg_reopen_count: float
    issues_without_body: int
    label_distribution: dict[str, int]


# --- Issue Creator Analytics schemas (P3-04) ---


class IssueCreatorStats(BaseModel):
    github_username: str
    display_name: str | None
    team: str | None
    role: str | None
    issues_created: int
    avg_time_to_close_hours: float | None
    avg_comment_count_before_pr: float | None
    pct_with_checklist: float
    pct_reopened: float
    pct_closed_not_planned: float
    avg_prs_per_issue: float | None
    issues_with_body_under_100_chars: int
    avg_time_to_first_pr_hours: float | None


class IssueCreatorStatsResponse(BaseModel):
    creators: list[IssueCreatorStats]
    team_averages: IssueCreatorStats


# --- Code Churn schemas (P3-06) ---


class FileChurnEntry(BaseModel):
    path: str
    change_frequency: int
    total_additions: int
    total_deletions: int
    total_churn: int
    contributor_count: int
    last_modified_at: datetime | None


class StaleDirectory(BaseModel):
    path: str
    file_count: int
    last_pr_activity: datetime | None


class CodeChurnResponse(BaseModel):
    repo_id: int
    repo_name: str
    hotspot_files: list[FileChurnEntry]
    stale_directories: list[StaleDirectory]
    total_files_in_repo: int
    total_files_changed: int
    tree_truncated: bool = False


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


class CollaborationTrendPeriod(BaseModel):
    period_start: datetime
    period_end: datetime
    period_label: str
    bus_factor_count: int
    silo_count: int
    isolated_developer_count: int


class CollaborationTrendsResponse(BaseModel):
    periods: list[CollaborationTrendPeriod]


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


class GoalSelfCreate(BaseModel):
    title: str
    description: str | None = None
    metric_key: MetricKey
    target_value: float
    target_direction: Literal["above", "below"] = "above"
    target_date: date | None = None


class GoalUpdate(BaseModel):
    status: Literal["active", "achieved", "abandoned"] | None = None
    notes: str | None = None


class GoalSelfUpdate(BaseModel):
    target_value: float | None = None
    target_date: date | None = None
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
    created_by: str | None


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
    pr_count: int = 0
    issue_count: int = 0


class RepoTrackUpdate(BaseModel):
    is_tracked: bool


class SyncTriggerRequest(BaseModel):
    sync_type: Literal["full", "incremental"] = "incremental"
    repo_ids: list[int] | None = None
    since: datetime | None = None


class SyncEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sync_type: str | None
    status: str | None
    repos_synced: int | None
    prs_upserted: int | None
    issues_upserted: int | None
    errors: list[Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_s: int | None
    repo_ids: list[int] | None = None
    since_override: datetime | None = None
    total_repos: int | None = None
    current_repo_name: str | None = None
    repos_completed: list[dict] | None = None
    repos_failed: list[dict] | None = None
    is_resumable: bool = False
    resumed_from_id: int | None = None
    log_summary: list[dict] | None = None
    rate_limit_wait_s: int = 0


class SyncStatusResponse(BaseModel):
    active_sync: SyncEventResponse | None = None
    last_completed: SyncEventResponse | None = None
    tracked_repos_count: int = 0
    total_repos_count: int = 0
    last_successful_sync: datetime | None = None
    last_sync_duration_s: int | None = None


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
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    reused: bool = False
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


# --- PR Risk Scoring schemas (P3-05) ---


class RiskFactor(BaseModel):
    factor: str  # e.g. "large_pr"
    weight: float
    description: str


class RiskAssessment(BaseModel):
    pr_id: int
    number: int
    title: str
    html_url: str
    repo_name: str
    author_name: str | None = None
    author_id: int | None = None
    risk_score: float  # 0.0-1.0
    risk_level: str  # low, medium, high, critical
    risk_factors: list[RiskFactor]
    is_open: bool = False


class RiskSummaryResponse(BaseModel):
    high_risk_prs: list[RiskAssessment]
    total_scored: int
    avg_risk_score: float
    prs_by_level: dict[str, int]


# --- CI/CD Check-Run schemas (P3-07) ---


class FlakyCheck(BaseModel):
    name: str
    failure_rate: float
    total_runs: int


class SlowestCheck(BaseModel):
    name: str
    avg_duration_s: float


class CIStatsResponse(BaseModel):
    prs_merged_with_failing_checks: int = 0
    avg_checks_to_green: float | None = None
    flaky_checks: list[FlakyCheck] = []
    avg_build_duration_s: float | None = None
    slowest_checks: list[SlowestCheck] = []


# --- DORA Metrics schemas (P4-01) ---


class DeploymentDetail(BaseModel):
    id: int
    repo_name: str | None = None
    environment: str | None = None
    sha: str | None = None
    deployed_at: datetime | None = None
    workflow_name: str | None = None
    status: str | None = None
    lead_time_hours: float | None = None


class DORAMetricsResponse(BaseModel):
    deploy_frequency: float = 0.0
    deploy_frequency_band: str = "low"
    avg_lead_time_hours: float | None = None
    lead_time_band: str = "low"
    total_deployments: int = 0
    period_days: int = 0
    deployments: list[DeploymentDetail] = []


# --- Work Categorization schemas (P4-02) ---


class CategoryAllocation(BaseModel):
    category: str
    count: int = 0
    additions: int = 0
    deletions: int = 0
    pct_of_total: float = 0.0


class IssueCategoryAllocation(BaseModel):
    category: str
    count: int = 0
    pct_of_total: float = 0.0


class DeveloperWorkAllocation(BaseModel):
    developer_id: int
    github_username: str
    display_name: str
    team: str | None = None
    pr_categories: dict[str, int] = {}
    issue_categories: dict[str, int] = {}
    total_prs: int = 0
    total_issues: int = 0


class WorkAllocationPeriod(BaseModel):
    period_start: datetime
    period_end: datetime
    period_label: str
    pr_categories: dict[str, int] = {}
    issue_categories: dict[str, int] = {}


class WorkAllocationResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    period_type: str
    pr_allocation: list[CategoryAllocation]
    issue_allocation: list[IssueCategoryAllocation]
    developer_breakdown: list[DeveloperWorkAllocation]
    trend: list[WorkAllocationPeriod]
    unknown_pct: float = 0.0
    ai_classified_count: int = 0
    total_prs: int = 0
    total_issues: int = 0


# --- AI Settings schemas (P5) ---


class AISettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ai_enabled: bool
    feature_general_analysis: bool
    feature_one_on_one_prep: bool
    feature_team_health: bool
    feature_work_categorization: bool
    monthly_token_budget: int | None
    budget_warning_threshold: float
    input_token_price_per_million: float
    output_token_price_per_million: float
    pricing_updated_at: datetime | None
    cooldown_minutes: int
    updated_at: datetime
    updated_by: str | None
    # Computed fields populated by service
    api_key_configured: bool = False
    current_month_tokens: int = 0
    current_month_cost_usd: float = 0.0
    budget_pct_used: float | None = None


class AISettingsUpdate(BaseModel):
    ai_enabled: bool | None = None
    feature_general_analysis: bool | None = None
    feature_one_on_one_prep: bool | None = None
    feature_team_health: bool | None = None
    feature_work_categorization: bool | None = None
    monthly_token_budget: int | None = None
    clear_budget: bool = False  # set True to clear budget (set to None)
    budget_warning_threshold: float | None = None
    input_token_price_per_million: float | None = None
    output_token_price_per_million: float | None = None
    cooldown_minutes: int | None = None


class AIFeatureStatus(BaseModel):
    feature: str
    enabled: bool
    label: str
    description: str
    disabled_impact: str
    tokens_this_month: int = 0
    cost_this_month_usd: float = 0.0
    call_count_this_month: int = 0
    last_used_at: datetime | None = None


class DailyUsage(BaseModel):
    date: str
    tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_feature: dict[str, dict] = {}


class AIUsageSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    budget_limit: int | None = None
    budget_pct_used: float | None = None
    features: list[AIFeatureStatus] = []
    daily_usage: list[DailyUsage] = []


class AICostEstimate(BaseModel):
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    data_items: int = 0
    note: str = ""
