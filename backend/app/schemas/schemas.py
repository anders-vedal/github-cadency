from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Enums ---


class ContributionCategory(str, Enum):
    code_contributor = "code_contributor"
    issue_contributor = "issue_contributor"
    non_contributor = "non_contributor"
    system = "system"


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
    github_username: str = Field(max_length=39)
    display_name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=320)
    role: str | None = Field(default=None, max_length=200)
    skills: list[str] | None = None
    specialty: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=100)
    team: str | None = Field(default=None, max_length=200)
    office: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for skill in v:
                if len(skill) > 100:
                    raise ValueError("Each skill must be at most 100 characters")
        return v


class DeveloperUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    role: str | None = Field(default=None, max_length=200)
    skills: list[str] | None = None
    specialty: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=100)
    team: str | None = Field(default=None, max_length=200)
    office: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for skill in v:
                if len(skill) > 100:
                    raise ValueError("Each skill must be at most 100 characters")
        return v


class DeveloperUpdateAdmin(DeveloperUpdate):
    app_role: AppRole | None = None
    is_active: bool | None = None


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
    office: str | None
    app_role: str
    token_version: int = 1
    is_active: bool
    avatar_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DeactivationImpactResponse(BaseModel):
    open_prs: int
    open_issues: int
    open_branches: list[str]


class ActivitySummaryResponse(BaseModel):
    prs_authored: int = 0
    prs_merged: int = 0
    prs_open: int = 0
    reviews_given: int = 0
    issues_created: int = 0
    issues_assigned: int = 0
    repos_touched: int = 0
    first_activity: datetime | None = None
    last_activity: datetime | None = None
    work_categories: dict[str, int] = {}


# --- Team schemas ---


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_order: int


class TeamCreate(BaseModel):
    name: str


class TeamUpdate(BaseModel):
    name: str | None = None
    display_order: int | None = None


# --- Role definition schemas ---


class RoleDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_key: str
    display_name: str
    contribution_category: ContributionCategory
    display_order: int
    is_default: bool


class RoleCreate(BaseModel):
    role_key: str
    display_name: str
    contribution_category: ContributionCategory


class RoleUpdate(BaseModel):
    display_name: str | None = None
    contribution_category: ContributionCategory | None = None
    display_order: int | None = None


# --- Work category schemas ---

VALID_MATCH_TYPES = frozenset({"label", "title_regex", "prefix", "issue_type"})


class WorkCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_key: str
    display_name: str
    description: str | None = None
    color: str
    exclude_from_stats: bool
    display_order: int
    is_default: bool


class WorkCategoryCreate(BaseModel):
    category_key: str = Field(max_length=100)
    display_name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    color: str = Field(max_length=20)
    exclude_from_stats: bool = False


class WorkCategoryUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    color: str | None = None
    exclude_from_stats: bool | None = None
    display_order: int | None = None


class WorkCategoryRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_type: str
    match_value: str
    description: str | None = None
    case_sensitive: bool
    category_key: str
    priority: int


class WorkCategoryRuleCreate(BaseModel):
    match_type: str = Field(max_length=50)
    match_value: str = Field(max_length=1000)
    description: str | None = Field(default=None, max_length=2000)
    case_sensitive: bool = False
    category_key: str = Field(max_length=100)
    priority: int


class WorkCategoryRuleUpdate(BaseModel):
    match_type: str | None = None
    match_value: str | None = None
    description: str | None = None
    case_sensitive: bool | None = None
    category_key: str | None = None
    priority: int | None = None


class ReclassifyResponse(BaseModel):
    prs_updated: int
    issues_updated: int
    duration_s: float


class WorkCategorySuggestion(BaseModel):
    match_type: str
    match_value: str
    suggested_category: str
    usage_count: int


class BulkCreateRulesRequest(BaseModel):
    rules: list[WorkCategoryRuleCreate]


class BulkCreateRulesResponse(BaseModel):
    created: int


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
    prs_linked_to_issue: int = 0
    issue_linkage_rate: float | None = None


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


class RepoSummaryItem(BaseModel):
    repo_id: int
    total_prs: int = 0
    total_merged: int = 0
    total_issues: int = 0
    total_reviews: int = 0
    avg_time_to_merge_hours: float | None = None
    last_pr_date: datetime | None = None
    prev_total_prs: int = 0
    prev_total_merged: int = 0
    prev_avg_time_to_merge_hours: float | None = None


# --- Benchmark schemas (M2) ---


class BenchmarkMetric(BaseModel):
    p25: float
    p50: float
    p75: float


class PercentilePlacement(BaseModel):
    value: float
    percentile_band: str  # below_p25, p25_to_p50, p50_to_p75, above_p75
    team_median: float


class DeveloperStatsWithPercentilesResponse(DeveloperStatsResponse):
    percentiles: dict[str, PercentilePlacement] | None = None


# --- Benchmark Group Config schemas ---


class BenchmarkGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_key: str
    display_name: str
    display_order: int
    roles: list[str]
    metrics: list[str]
    min_team_size: int
    is_default: bool


class BenchmarkGroupUpdate(BaseModel):
    display_name: str | None = None
    display_order: int | None = None
    roles: list[str] | None = None
    metrics: list[str] | None = None
    min_team_size: int | None = None


class BenchmarkMetricInfo(BaseModel):
    key: str
    label: str
    lower_is_better: bool
    unit: str


class MetricValue(BaseModel):
    value: float | None
    percentile_band: str | None  # below_p25, p25_to_p50, p50_to_p75, above_p75


class DeveloperBenchmarkRow(BaseModel):
    developer_id: int
    display_name: str
    avatar_url: str | None
    team: str | None
    role: str | None
    metrics: dict[str, MetricValue]


class TeamMedianRow(BaseModel):
    team: str
    sample_size: int
    metrics: dict[str, float | None]


class BenchmarksV2Response(BaseModel):
    group: BenchmarkGroupResponse
    period_start: datetime
    period_end: datetime
    sample_size: int
    team: str | None = None
    metrics: dict[str, BenchmarkMetric]
    metric_info: list[BenchmarkMetricInfo]
    developers: list[DeveloperBenchmarkRow]
    team_comparison: list[TeamMedianRow] | None = None


class UnassignedRoleCountResponse(BaseModel):
    count: int


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


class SprintCommitment(BaseModel):
    sprint_name: str
    total_issues: int
    completed: int
    remaining: int
    days_left: int
    on_track: bool


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
    sprint_commitment: SprintCommitment | None = None


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


class DeveloperLinkageRow(BaseModel):
    developer_id: int
    github_username: str
    display_name: str
    team: str | None = None
    prs_total: int
    prs_linked: int
    linkage_rate: float  # 0.0–1.0


class IssueLinkageByDeveloper(BaseModel):
    developers: list[DeveloperLinkageRow]
    team_average_rate: float
    attention_threshold: float
    attention_developers: list[DeveloperLinkageRow]


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


class PairRelationship(BaseModel):
    label: str  # mentor, peer, one_way_dependency, rubber_stamp, gatekeeper, casual, none
    confidence: float  # 0-1
    explanation: str


class PairReviewedPR(BaseModel):
    pr_id: int
    pr_number: int
    title: str
    html_url: str | None
    repo_full_name: str
    review_state: str | None
    quality_tier: str
    comment_count: int
    additions: int | None
    deletions: int | None
    submitted_at: datetime | None


class CommentTypeBreakdown(BaseModel):
    comment_type: str
    count: int


class QualityTierBreakdown(BaseModel):
    tier: str
    count: int


class CollaborationPairDetail(BaseModel):
    reviewer_id: int
    reviewer_name: str
    reviewer_avatar_url: str | None
    reviewer_team: str | None
    author_id: int
    author_name: str
    author_avatar_url: str | None
    author_team: str | None
    total_reviews: int
    approval_rate: float
    changes_requested_rate: float
    avg_quality_tier: str
    quality_tier_breakdown: list[QualityTierBreakdown]
    comment_type_breakdown: list[CommentTypeBreakdown]
    total_comments: int
    relationship: PairRelationship
    recent_prs: list[PairReviewedPR]


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
    title: str = Field(max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    metric_key: MetricKey
    target_value: float
    target_direction: Literal["above", "below"] = "above"
    target_date: date | None = None


class GoalSelfCreate(BaseModel):
    title: str = Field(max_length=500)
    description: str | None = Field(default=None, max_length=5000)
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


class RepoDataDeletedCounts(BaseModel):
    pull_requests: int
    pr_reviews: int
    pr_review_comments: int
    pr_files: int
    pr_check_runs: int
    pr_external_issue_links: int
    issues: int
    issue_comments: int
    deployments: int
    repo_tree_files: int


class RepoDataDeleteResponse(BaseModel):
    repo_id: int
    full_name: str | None
    deleted: RepoDataDeletedCounts


class SyncTriggerRequest(BaseModel):
    sync_type: Literal["full", "incremental"] = "incremental"
    repo_ids: list[int] | None = None
    since: datetime | None = None
    sync_scope: str | None = Field(default=None, max_length=500)


class PreflightCheck(BaseModel):
    field: str
    status: Literal["ok", "error", "warn"]
    message: str


class PreflightResponse(BaseModel):
    checks: list[PreflightCheck]
    ready: bool


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
    current_step: str | None = None
    current_repo_prs_total: int | None = None
    current_repo_prs_done: int | None = None
    current_repo_issues_total: int | None = None
    current_repo_issues_done: int | None = None
    repos_completed: list[dict] | None = None
    repos_failed: list[dict] | None = None
    is_resumable: bool = False
    resumed_from_id: int | None = None
    cancel_requested: bool = False
    log_summary: list[dict] | None = None
    rate_limit_wait_s: int = 0
    triggered_by: str | None = None
    sync_scope: str | None = None


class SyncScheduleConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    auto_sync_enabled: bool = True
    incremental_interval_minutes: int = 15
    full_sync_cron_hour: int = 2
    updated_at: datetime | None = None


class SyncScheduleConfigUpdate(BaseModel):
    auto_sync_enabled: bool | None = None
    incremental_interval_minutes: int | None = None
    full_sync_cron_hour: int | None = None
    linear_sync_enabled: bool | None = None
    linear_sync_interval_minutes: int | None = None


class SyncStatusResponse(BaseModel):
    active_sync: SyncEventResponse | None = None
    last_completed: SyncEventResponse | None = None
    tracked_repos_count: int = 0
    total_repos_count: int = 0
    last_successful_sync: datetime | None = None
    last_sync_duration_s: int | None = None
    schedule: SyncScheduleConfigResponse | None = None


# --- AI Analysis schemas ---


class AIAnalyzeRequest(BaseModel):
    analysis_type: AnalysisType
    scope_type: ScopeType
    scope_id: str
    date_from: datetime
    date_to: datetime
    repo_ids: list[int] | None = None


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
    repo_ids: list[int] | None = None


# --- Team Health Check schemas (M8) ---


class TeamHealthRequest(BaseModel):
    team: str | None = None
    date_from: datetime
    date_to: datetime
    repo_ids: list[int] | None = None


# --- AI Analysis Schedule schemas (AW-02) ---


class AIScheduleCreate(BaseModel):
    name: str = Field(max_length=255)
    analysis_type: str
    general_type: str | None = None
    scope_type: str
    scope_id: str = Field(max_length=255)
    repo_ids: list[int] | None = None
    time_range_days: int = Field(default=30, ge=1, le=365)
    frequency: str  # daily, weekly, biweekly, monthly
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    hour: int = Field(default=8, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class AIScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    is_enabled: bool | None = None
    repo_ids: list[int] | None = None
    time_range_days: int | None = Field(default=None, ge=1, le=365)
    frequency: str | None = None
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    # analysis_type/scope not updatable — delete and recreate


class AIScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    analysis_type: str
    general_type: str | None
    scope_type: str
    scope_id: str
    repo_ids: list[int] | None
    time_range_days: int
    frequency: str
    day_of_week: int | None
    hour: int
    minute: int
    is_enabled: bool
    last_run_at: datetime | None
    last_run_analysis_id: int | None
    last_run_status: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    next_run_description: str | None = None


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
    is_failure: bool = False
    failure_detected_via: str | None = None
    recovery_time_hours: float | None = None


class DORAMetricsResponse(BaseModel):
    deploy_frequency: float = 0.0
    deploy_frequency_band: str = "low"
    avg_lead_time_hours: float | None = None
    lead_time_band: str = "low"
    total_deployments: int = 0
    period_days: int = 0
    deployments: list[DeploymentDetail] = []
    total_all_deployments: int = 0
    change_failure_rate: float | None = None
    cfr_band: str = "low"
    avg_mttr_hours: float | None = None
    mttr_band: str = "low"
    failure_deployments: int = 0
    overall_band: str = "low"


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


class WorkAllocationItem(BaseModel):
    id: int
    type: str
    number: int
    title: str | None = None
    labels: list[str] | None = None
    repo_name: str | None = None
    author_name: str | None = None
    author_id: int | None = None
    html_url: str | None = None
    category: str
    category_source: str | None = None
    merged_at: datetime | None = None
    created_at: datetime | None = None
    additions: int | None = None
    deletions: int | None = None


class WorkAllocationItemsResponse(BaseModel):
    items: list[WorkAllocationItem]
    total: int
    page: int
    page_size: int


class RecategorizeRequest(BaseModel):
    category: str


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
    character_count: int = 0
    system_prompt_tokens: int = 0
    remaining_budget_tokens: int = 0
    would_exceed_budget: bool = False
    note: str = ""


# --- Developer Relationships schemas ---


class RelationshipType(str, Enum):
    reports_to = "reports_to"
    tech_lead_of = "tech_lead_of"
    team_lead_of = "team_lead_of"


class DeveloperRelationshipCreate(BaseModel):
    target_id: int
    relationship_type: RelationshipType


class DeveloperRelationshipDelete(BaseModel):
    target_id: int
    relationship_type: RelationshipType


class DeveloperRelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    target_id: int
    relationship_type: str
    source_name: str
    target_name: str
    source_avatar_url: str | None = None
    target_avatar_url: str | None = None
    created_at: datetime


class DeveloperRelationshipsResponse(BaseModel):
    reports_to: DeveloperRelationshipResponse | None = None
    tech_lead: DeveloperRelationshipResponse | None = None
    team_lead: DeveloperRelationshipResponse | None = None
    direct_reports: list[DeveloperRelationshipResponse] = []
    tech_leads_for: list[DeveloperRelationshipResponse] = []
    team_leads_for: list[DeveloperRelationshipResponse] = []


class OrgTreeNode(BaseModel):
    developer_id: int
    display_name: str
    github_username: str
    avatar_url: str | None = None
    role: str | None = None
    team: str | None = None
    office: str | None = None
    children: list["OrgTreeNode"] = []


class OrgTreeResponse(BaseModel):
    roots: list[OrgTreeNode]
    unassigned: list[OrgTreeNode]


# --- Enhanced Collaboration schemas ---


class WorksWithEntry(BaseModel):
    developer_id: int
    display_name: str
    github_username: str
    avatar_url: str | None = None
    team: str | None = None
    total_score: float
    interaction_count: int
    review_score: float
    coauthor_score: float
    issue_comment_score: float
    mention_score: float
    co_assigned_score: float


class WorksWithResponse(BaseModel):
    developer_id: int
    collaborators: list[WorksWithEntry]


class OverTaggedDeveloper(BaseModel):
    developer_id: int
    display_name: str
    github_username: str
    team: str | None = None
    combined_tag_rate: float
    pr_tag_rate: float
    issue_tag_rate: float
    team_average: float
    severity: str  # mild, moderate, severe


class OverTaggedResponse(BaseModel):
    developers: list[OverTaggedDeveloper]


class CommunicationScoreEntry(BaseModel):
    developer_id: int
    display_name: str
    github_username: str
    avatar_url: str | None = None
    team: str | None = None
    communication_score: float
    review_engagement: float
    comment_depth: float
    reach: float
    responsiveness: float


class CommunicationScoresResponse(BaseModel):
    developers: list[CommunicationScoreEntry]


# --- Slack Integration schemas ---


class SlackNotificationType(str, Enum):
    stale_pr = "stale_pr"
    high_risk_pr = "high_risk_pr"
    workload = "workload"
    sync_complete = "sync_complete"
    sync_failure = "sync_failure"
    weekly_digest = "weekly_digest"


class SlackConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slack_enabled: bool
    bot_token_configured: bool = False
    default_channel: str | None
    notify_stale_prs: bool
    notify_high_risk_prs: bool
    notify_workload_alerts: bool
    notify_sync_failures: bool
    notify_sync_complete: bool
    notify_weekly_digest: bool
    stale_pr_days_threshold: int
    risk_score_threshold: float
    digest_day_of_week: int
    digest_hour_utc: int
    stale_check_hour_utc: int
    updated_at: datetime
    updated_by: str | None


class SlackConfigUpdate(BaseModel):
    slack_enabled: bool | None = None
    bot_token: str | None = None
    default_channel: str | None = None
    notify_stale_prs: bool | None = None
    notify_high_risk_prs: bool | None = None
    notify_workload_alerts: bool | None = None
    notify_sync_failures: bool | None = None
    notify_sync_complete: bool | None = None
    notify_weekly_digest: bool | None = None
    stale_pr_days_threshold: int | None = None
    risk_score_threshold: float | None = None
    digest_day_of_week: int | None = None
    digest_hour_utc: int | None = None
    stale_check_hour_utc: int | None = None


class SlackUserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    developer_id: int
    slack_user_id: str | None
    notify_stale_prs: bool
    notify_high_risk_prs: bool
    notify_workload_alerts: bool
    notify_weekly_digest: bool


class SlackUserSettingsUpdate(BaseModel):
    slack_user_id: str | None = None
    notify_stale_prs: bool | None = None
    notify_high_risk_prs: bool | None = None
    notify_workload_alerts: bool | None = None
    notify_weekly_digest: bool | None = None


class NotificationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notification_type: str
    channel: str | None
    recipient_developer_id: int | None
    status: str
    error_message: str | None
    payload: dict | None
    created_at: datetime


class NotificationHistoryResponse(BaseModel):
    notifications: list[NotificationLogResponse]
    total: int


class SlackTestResponse(BaseModel):
    success: bool
    message: str


# --- Notification Center ---


class AlertType(str, Enum):
    stale_pr = "stale_pr"
    review_bottleneck = "review_bottleneck"
    underutilized = "underutilized"
    uneven_assignment = "uneven_assignment"
    merged_without_approval = "merged_without_approval"
    revert_spike = "revert_spike"
    high_risk_pr = "high_risk_pr"
    bus_factor = "bus_factor"
    team_silo = "team_silo"
    isolated_developer = "isolated_developer"
    declining_trend = "declining_trend"
    issue_linkage = "issue_linkage"
    ai_budget = "ai_budget"
    sync_failure = "sync_failure"
    unassigned_roles = "unassigned_roles"
    missing_config = "missing_config"


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    severity: str
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    link_path: str | None = None
    developer_id: int | None = None
    metadata: dict | None = None
    is_read: bool = False
    is_dismissed: bool = False
    created_at: datetime
    updated_at: datetime


class NotificationsListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    counts_by_severity: dict[str, int]
    total: int


class DismissNotificationRequest(BaseModel):
    dismiss_type: Literal["permanent", "temporary"] = "permanent"
    duration_days: int | None = None


class DismissAlertTypeRequest(BaseModel):
    alert_type: str = Field(max_length=100)
    dismiss_type: Literal["permanent", "temporary"] = "permanent"
    duration_days: int | None = None


class NotificationConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_stale_pr_enabled: bool
    alert_review_bottleneck_enabled: bool
    alert_underutilized_enabled: bool
    alert_uneven_assignment_enabled: bool
    alert_merged_without_approval_enabled: bool
    alert_revert_spike_enabled: bool
    alert_high_risk_pr_enabled: bool
    alert_bus_factor_enabled: bool
    alert_declining_trends_enabled: bool
    alert_issue_linkage_enabled: bool
    alert_ai_budget_enabled: bool
    alert_sync_failure_enabled: bool
    alert_unassigned_roles_enabled: bool
    alert_missing_config_enabled: bool
    stale_pr_threshold_hours: int
    review_bottleneck_multiplier: float
    revert_spike_threshold_pct: float
    high_risk_pr_min_level: str
    issue_linkage_threshold_pct: float
    declining_trend_pr_drop_pct: float
    declining_trend_quality_drop_pct: float
    exclude_contribution_categories: list[str] | None
    evaluation_interval_minutes: int
    alert_types: list[dict] = []
    updated_at: datetime
    updated_by: str | None = None


class NotificationConfigUpdate(BaseModel):
    alert_stale_pr_enabled: bool | None = None
    alert_review_bottleneck_enabled: bool | None = None
    alert_underutilized_enabled: bool | None = None
    alert_uneven_assignment_enabled: bool | None = None
    alert_merged_without_approval_enabled: bool | None = None
    alert_revert_spike_enabled: bool | None = None
    alert_high_risk_pr_enabled: bool | None = None
    alert_bus_factor_enabled: bool | None = None
    alert_declining_trends_enabled: bool | None = None
    alert_issue_linkage_enabled: bool | None = None
    alert_ai_budget_enabled: bool | None = None
    alert_sync_failure_enabled: bool | None = None
    alert_unassigned_roles_enabled: bool | None = None
    alert_missing_config_enabled: bool | None = None
    alert_velocity_declining_enabled: bool | None = None
    alert_scope_creep_high_enabled: bool | None = None
    alert_sprint_at_risk_enabled: bool | None = None
    alert_triage_queue_growing_enabled: bool | None = None
    alert_estimation_accuracy_low_enabled: bool | None = None
    alert_linear_sync_failure_enabled: bool | None = None
    stale_pr_threshold_hours: int | None = None
    review_bottleneck_multiplier: float | None = None
    revert_spike_threshold_pct: float | None = None
    high_risk_pr_min_level: str | None = None
    issue_linkage_threshold_pct: float | None = None
    declining_trend_pr_drop_pct: float | None = None
    declining_trend_quality_drop_pct: float | None = None
    velocity_decline_pct: float | None = None
    scope_creep_threshold_pct: float | None = None
    sprint_risk_completion_pct: float | None = None
    triage_queue_max: int | None = None
    triage_duration_hours_max: int | None = None
    estimation_accuracy_min_pct: float | None = None
    exclude_contribution_categories: list[str] | None = None
    evaluation_interval_minutes: int | None = None


class EvaluationResultResponse(BaseModel):
    created: int
    updated: int
    resolved: int


# --- Frontend Log Ingestion ---


# --- Integration Config (Linear, etc.) ---


class IntegrationConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    display_name: str | None
    api_key_configured: bool = False
    workspace_id: str | None
    workspace_name: str | None
    status: str
    error_message: str | None
    is_primary_issue_source: bool
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IntegrationConfigCreate(BaseModel):
    type: str = Field(max_length=30)
    display_name: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=500)


class IntegrationConfigUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=30)


class IntegrationTestResponse(BaseModel):
    success: bool
    message: str
    workspace_name: str | None = None


class IntegrationSyncStatusResponse(BaseModel):
    is_syncing: bool
    last_sync_event_id: int | None = None
    last_synced_at: datetime | None = None
    last_sync_status: str | None = None
    issues_synced: int = 0
    sprints_synced: int = 0
    projects_synced: int = 0


class IssueSourceResponse(BaseModel):
    source: str
    integration_id: int | None = None


class LinearUserResponse(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    email: str | None = None
    active: bool = True
    mapped_developer_id: int | None = None
    mapped_developer_name: str | None = None


class LinearUserListResponse(BaseModel):
    users: list[LinearUserResponse]
    total: int
    mapped_count: int
    unmapped_count: int


class MapUserRequest(BaseModel):
    external_user_id: str = Field(max_length=255)
    developer_id: int


class DeveloperIdentityMapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    developer_id: int
    integration_type: str
    external_user_id: str
    external_email: str | None
    external_display_name: str | None
    mapped_by: str
    created_at: datetime


# --- Sprint & Planning Stats ---


class SprintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str | None
    number: int | None
    team_key: str | None
    team_name: str | None
    state: str
    start_date: date | None
    end_date: date | None
    planned_scope: int | None
    completed_scope: int | None
    cancelled_scope: int | None
    added_scope: int | None
    scope_unit: str | None = None
    url: str | None


class SprintDetailResponse(SprintResponse):
    issues: list["ExternalIssueResponse"] = []
    completion_rate: float | None = None
    scope_creep_pct: float | None = None


class SprintVelocityPoint(BaseModel):
    sprint_id: int
    sprint_name: str | None
    sprint_number: int | None
    team_key: str | None
    completed_scope: int
    planned_scope: int
    start_date: date | None
    end_date: date | None


class SprintVelocityResponse(BaseModel):
    data: list[SprintVelocityPoint]
    avg_velocity: float = 0.0
    trend_direction: str = "stable"


class SprintCompletionPoint(BaseModel):
    sprint_id: int
    sprint_name: str | None
    sprint_number: int | None
    planned_scope: int
    completed_scope: int
    completion_rate: float


class SprintCompletionResponse(BaseModel):
    data: list[SprintCompletionPoint]
    avg_completion_rate: float = 0.0


class ScopeCreepPoint(BaseModel):
    sprint_id: int
    sprint_name: str | None
    sprint_number: int | None
    planned_scope: int
    added_scope: int
    scope_creep_pct: float


class ScopeCreepResponse(BaseModel):
    data: list[ScopeCreepPoint]
    avg_scope_creep_pct: float = 0.0


class ExternalIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    identifier: str
    title: str
    issue_type: str | None
    status: str | None
    status_category: str | None
    priority: int
    priority_label: str | None
    estimate: float | None
    assignee_developer_id: int | None
    creator_developer_id: int | None = None
    creator_email: str | None = None
    work_category: str | None = None
    work_category_source: str | None = None
    project_id: int | None
    sprint_id: int | None
    labels: list | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    triage_duration_s: int | None
    cycle_time_s: int | None
    url: str | None


class ExternalProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    key: str | None
    name: str
    status: str | None
    health: str | None
    start_date: date | None
    target_date: date | None
    progress_pct: float | None
    lead_id: int | None
    url: str | None
    issue_count: int = 0
    completed_issue_count: int = 0


class ExternalProjectDetailResponse(ExternalProjectResponse):
    issues: list[ExternalIssueResponse] = []


class TriageMetricsResponse(BaseModel):
    avg_triage_duration_s: float = 0.0
    median_triage_duration_s: float = 0.0
    p90_triage_duration_s: float = 0.0
    issues_in_triage: int = 0
    total_triaged: int = 0


class EstimationAccuracyPoint(BaseModel):
    sprint_id: int
    sprint_name: str | None
    sprint_number: int | None
    estimated_points: float
    completed_points: float
    accuracy_pct: float


class EstimationAccuracyResponse(BaseModel):
    data: list[EstimationAccuracyPoint]
    avg_accuracy_pct: float = 0.0


class WorkAlignmentResponse(BaseModel):
    total_prs: int = 0
    linked_prs: int = 0
    unlinked_prs: int = 0
    alignment_pct: float = 0.0


class PlanningCorrelationPoint(BaseModel):
    sprint_id: int
    sprint_name: str | None
    completion_rate: float
    avg_pr_merge_time_hours: float | None


class PlanningCorrelationResponse(BaseModel):
    data: list[PlanningCorrelationPoint]
    correlation_coefficient: float | None = None


# --- System Version ---


class VersionResponse(BaseModel):
    version: str
    build: str
    commit: str
    deployed_at: str
    full_version: str


class FrontendLogEntry(BaseModel):
    level: Literal["warn", "error"] = "error"
    message: str = Field(max_length=4000)
    event_type: str = Field(default="frontend.error", max_length=100)
    context: dict[str, Any] | None = None
    timestamp: str | None = Field(default=None, max_length=50)
    url: str | None = Field(default=None, max_length=2000)
    user_agent: str | None = Field(default=None, max_length=500)

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("context must have at most 20 keys")
        for key, val in v.items():
            if len(key) > 50:
                raise ValueError(f"context key too long: {key[:50]}...")
            serialized = str(val)
            if len(serialized) > 1000:
                raise ValueError(f"context value too large for key: {key}")
        return v


class FrontendLogBatch(BaseModel):
    entries: list[FrontendLogEntry]
