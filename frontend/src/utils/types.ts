// --- Auth ---

export interface AuthUser {
  developer_id: number
  github_username: string
  display_name: string
  app_role: 'admin' | 'developer'
  avatar_url: string | null
}

// --- Developer ---

export interface Developer {
  id: number
  github_username: string
  display_name: string
  email: string | null
  role: string | null
  skills: string[] | null
  specialty: string | null
  location: string | null
  timezone: string | null
  team: string | null
  app_role: string
  is_active: boolean
  avatar_url: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface DeveloperCreate {
  github_username: string
  display_name: string
  email?: string | null
  role?: string | null
  skills?: string[] | null
  specialty?: string | null
  location?: string | null
  timezone?: string | null
  team?: string | null
  notes?: string | null
}

export type DeveloperUpdate = Partial<Omit<DeveloperCreate, 'github_username'>>

// --- Stats ---

export interface ReviewBreakdown {
  approved: number
  changes_requested: number
  commented: number
}

export interface DeveloperStats {
  prs_opened: number
  prs_merged: number
  prs_closed_without_merge: number
  prs_open: number
  prs_draft: number
  total_additions: number
  total_deletions: number
  total_changed_files: number
  reviews_given: ReviewBreakdown
  reviews_received: number
  avg_time_to_first_review_hours: number | null
  avg_time_to_merge_hours: number | null
  issues_assigned: number
  issues_closed: number
  avg_time_to_close_issue_hours: number | null
  avg_time_to_approve_hours: number | null
  avg_time_after_approve_hours: number | null
  prs_merged_without_approval: number
  prs_reverted: number
  reverts_authored: number
}

export interface TeamStats {
  developer_count: number
  total_prs: number
  total_merged: number
  merge_rate: number | null
  avg_time_to_first_review_hours: number | null
  avg_time_to_merge_hours: number | null
  total_reviews: number
  total_issues_closed: number
  revert_rate: number | null
}

export interface TopContributor {
  developer_id: number
  github_username: string
  display_name: string
  pr_count: number
}

export interface RepoStats {
  total_prs: number
  total_merged: number
  total_issues: number
  total_issues_closed: number
  total_reviews: number
  avg_time_to_merge_hours: number | null
  top_contributors: TopContributor[]
}

// --- Repo ---

export interface Repo {
  id: number
  github_id: number
  name: string | null
  full_name: string | null
  description: string | null
  language: string | null
  is_tracked: boolean
  last_synced_at: string | null
  created_at: string
  pr_count: number
  issue_count: number
}

// --- Sync ---

export interface SyncRepoResult {
  repo_id: number
  repo_name: string
  status: 'ok' | 'partial'
  prs: number
  issues: number
  warnings: string[]
}

export interface SyncRepoFailure {
  repo_id: number
  repo_name: string
  error: string
}

export interface SyncError {
  repo: string | null
  repo_id: number | null
  step: string
  error_type: string
  status_code: number | null
  message: string
  retryable: boolean
  timestamp: string
  attempt: number
}

export interface SyncLogEntry {
  ts: string
  level: 'info' | 'warn' | 'error'
  repo?: string
  msg: string
}

export interface SyncEvent {
  id: number
  sync_type: string | null
  status: string | null
  repos_synced: number | null
  prs_upserted: number | null
  issues_upserted: number | null
  errors: SyncError[] | null
  started_at: string | null
  completed_at: string | null
  duration_s: number | null
  repo_ids: number[] | null
  since_override: string | null
  total_repos: number | null
  current_repo_name: string | null
  repos_completed: SyncRepoResult[] | null
  repos_failed: SyncRepoFailure[] | null
  is_resumable: boolean
  resumed_from_id: number | null
  log_summary: SyncLogEntry[] | null
  rate_limit_wait_s: number | null
}

export interface SyncStatusResponse {
  active_sync: SyncEvent | null
  last_completed: SyncEvent | null
  tracked_repos_count: number
  total_repos_count: number
  last_successful_sync: string | null
  last_sync_duration_s: number | null
}

export interface SyncStartRequest {
  sync_type: 'full' | 'incremental'
  repo_ids?: number[]
  since?: string
}

export type TimeRangeOption =
  | 'since_last'
  | 'last_7d'
  | 'last_14d'
  | 'last_30d'
  | 'last_60d'
  | 'last_90d'
  | 'custom'
  | 'all'

// --- AI Analysis ---

export interface AIAnalysis {
  id: number
  analysis_type: string | null
  scope_type: string | null
  scope_id: string | null
  date_from: string | null
  date_to: string | null
  input_summary: string | null
  result: Record<string, unknown> | null
  model_used: string | null
  tokens_used: number | null
  input_tokens: number | null
  output_tokens: number | null
  estimated_cost_usd: number | null
  reused: boolean
  triggered_by: string | null
  created_at: string
}

export interface AIAnalyzeRequest {
  analysis_type: 'communication' | 'conflict' | 'sentiment'
  scope_type: 'developer' | 'team' | 'repo'
  scope_id: string
  date_from: string
  date_to: string
}

export interface OneOnOnePrepRequest {
  developer_id: number
  date_from: string
  date_to: string
}

export interface TeamHealthRequest {
  team?: string
  date_from: string
  date_to: string
}

// --- Review Quality (M1) ---

export interface ReviewQualityBreakdown {
  thorough: number
  standard: number
  minimal: number
  rubber_stamp: number
}

// --- Benchmarks / Percentiles (M2) ---

export interface BenchmarkMetric {
  p25: number
  p50: number
  p75: number
}

export interface PercentilePlacement {
  value: number
  percentile_band: 'below_p25' | 'p25_to_p50' | 'p50_to_p75' | 'above_p75'
  team_median: number
}

export interface DeveloperStatsWithPercentiles extends DeveloperStats {
  review_quality_breakdown?: ReviewQualityBreakdown
  review_quality_score?: number | null
  percentiles?: Record<string, PercentilePlacement> | null
}

// --- Trends (M3) ---

export interface TrendPeriod {
  start: string
  end: string
  prs_merged: number
  avg_time_to_merge_h: number | null
  reviews_given: number
  additions: number
  deletions: number
  issues_closed: number
}

export interface TrendDirection {
  direction: 'improving' | 'stable' | 'worsening'
  change_pct: number
}

export interface DeveloperTrendsResponse {
  developer_id: number
  period_type: string
  periods: TrendPeriod[]
  trends: Record<string, TrendDirection>
}

// --- Workload (M4) ---

export interface DeveloperWorkload {
  developer_id: number
  github_username: string
  display_name: string
  open_prs_authored: number
  drafts_open: number
  open_prs_reviewing: number
  open_issues_assigned: number
  reviews_given_this_period: number
  reviews_received_this_period: number
  prs_waiting_for_review: number
  avg_review_wait_h: number | null
  workload_score: 'low' | 'balanced' | 'high' | 'overloaded'
}

export interface WorkloadAlert {
  type: 'review_bottleneck' | 'stale_prs' | 'uneven_assignment' | 'underutilized' | 'merged_without_approval' | 'revert_spike'
  developer_id: number | null
  message: string
}

export interface WorkloadResponse {
  developers: DeveloperWorkload[]
  alerts: WorkloadAlert[]
}

// --- Stale PRs (P2-01) ---

export interface StalePR {
  pr_id: number
  number: number
  title: string
  html_url: string
  repo_name: string
  author_name: string | null
  author_id: number | null
  age_hours: number
  is_draft: boolean
  review_count: number
  has_approved: boolean
  has_changes_requested: boolean
  last_activity_at: string
  stale_reason: 'no_review' | 'changes_requested_no_response' | 'approved_not_merged'
}

export interface StalePRsResponse {
  stale_prs: StalePR[]
  total_count: number
}

// --- Benchmarks Response (M2) ---

export interface BenchmarksResponse {
  period_start: string
  period_end: string
  sample_size: number
  team: string | null
  metrics: Record<string, BenchmarkMetric>
}

// --- Collaboration (M5) ---

export interface CollaborationPair {
  reviewer_id: number
  reviewer_name: string
  reviewer_team: string | null
  author_id: number
  author_name: string
  author_team: string | null
  reviews_count: number
  approvals: number
  changes_requested: number
}

export interface BusFactorEntry {
  repo_name: string
  sole_reviewer_id: number
  sole_reviewer_name: string
  review_share_pct: number
}

export interface CollaborationInsights {
  silos: Array<{ team_a: string; team_b: string; note: string }>
  bus_factors: BusFactorEntry[]
  isolated_developers: Array<{ developer_id: number; display_name: string }>
  strongest_pairs: CollaborationPair[]
}

export interface CollaborationResponse {
  matrix: CollaborationPair[]
  insights: CollaborationInsights
}

// --- Goals (M6 + P1-03) ---

export type GoalMetricKey =
  | 'avg_pr_additions'
  | 'time_to_merge_h'
  | 'reviews_given'
  | 'review_quality_score'
  | 'prs_merged'
  | 'time_to_first_review_h'
  | 'issues_closed'
  | 'prs_opened'

export interface GoalResponse {
  id: number
  developer_id: number
  title: string
  description: string | null
  metric_key: string
  target_value: number
  target_direction: string
  baseline_value: number | null
  status: string
  created_at: string
  target_date: string | null
  achieved_at: string | null
  notes: string | null
  created_by: string | null
}

export interface GoalSelfCreate {
  title: string
  description?: string | null
  metric_key: GoalMetricKey
  target_value: number
  target_direction?: 'above' | 'below'
  target_date?: string | null
}

export interface GoalAdminCreate extends GoalSelfCreate {
  developer_id: number
}

export interface GoalSelfUpdate {
  target_value?: number | null
  target_date?: string | null
  status?: 'active' | 'achieved' | 'abandoned' | null
  notes?: string | null
}

export interface GoalAdminUpdate {
  status?: 'active' | 'achieved' | 'abandoned' | null
  notes?: string | null
}

// --- Issue Creator Analytics (P3-04) ---

export interface IssueCreatorStats {
  github_username: string
  display_name: string | null
  team: string | null
  role: string | null
  issues_created: number
  avg_time_to_close_hours: number | null
  avg_comment_count_before_pr: number | null
  pct_with_checklist: number
  pct_reopened: number
  pct_closed_not_planned: number
  avg_prs_per_issue: number | null
  issues_with_body_under_100_chars: number
  avg_time_to_first_pr_hours: number | null
}

export interface IssueCreatorStatsResponse {
  creators: IssueCreatorStats[]
  team_averages: IssueCreatorStats
}

// --- PR Risk Scoring (P3-05) ---

export interface RiskFactor {
  factor: string
  weight: number
  description: string
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface RiskAssessment {
  pr_id: number
  number: number
  title: string
  html_url: string
  repo_name: string
  author_name: string | null
  author_id: number | null
  risk_score: number
  risk_level: RiskLevel
  risk_factors: RiskFactor[]
  is_open: boolean
}

export interface RiskSummaryResponse {
  high_risk_prs: RiskAssessment[]
  total_scored: number
  avg_risk_score: number
  prs_by_level: Record<string, number>
}

export const riskLevelLabels: Record<RiskLevel, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

export const riskLevelStyles: Record<RiskLevel, string> = {
  low: 'bg-emerald-500/10 text-emerald-600',
  medium: 'bg-amber-500/10 text-amber-600',
  high: 'bg-orange-500/10 text-orange-600',
  critical: 'bg-red-500/10 text-red-600',
}

// --- Collaboration Trends (P4-04) ---

export interface CollaborationTrendPeriod {
  period_start: string
  period_end: string
  period_label: string
  bus_factor_count: number
  silo_count: number
  isolated_developer_count: number
}

export interface CollaborationTrendsResponse {
  periods: CollaborationTrendPeriod[]
}

// --- Goals ---

export interface GoalProgressPoint {
  period_end: string
  value: number
}

export interface GoalProgressResponse {
  goal_id: number
  title: string
  target_value: number
  target_direction: string
  baseline_value: number | null
  current_value: number | null
  status: string
  history: GoalProgressPoint[]
}

// --- Code Churn (P3-06) ---

export interface FileChurnEntry {
  path: string
  change_frequency: number
  total_additions: number
  total_deletions: number
  total_churn: number
  contributor_count: number
  last_modified_at: string | null
}

export interface StaleDirectory {
  path: string
  file_count: number
  last_pr_activity: string | null
}

export interface CodeChurnResponse {
  repo_id: number
  repo_name: string
  hotspot_files: FileChurnEntry[]
  stale_directories: StaleDirectory[]
  total_files_in_repo: number
  total_files_changed: number
  tree_truncated: boolean
}

// --- CI/CD Check-Run Stats (P3-07) ---

export interface FlakyCheck {
  name: string
  failure_rate: number
  total_runs: number
}

export interface SlowestCheck {
  name: string
  avg_duration_s: number
}

export interface CIStatsResponse {
  prs_merged_with_failing_checks: number
  avg_checks_to_green: number | null
  flaky_checks: FlakyCheck[]
  avg_build_duration_s: number | null
  slowest_checks: SlowestCheck[]
}

// --- DORA Metrics (P4-01) ---

export interface DeploymentDetail {
  id: number
  repo_name: string | null
  environment: string | null
  sha: string | null
  deployed_at: string | null
  workflow_name: string | null
  status: string | null
  lead_time_hours: number | null
}

export interface DORAMetricsResponse {
  deploy_frequency: number
  deploy_frequency_band: string
  avg_lead_time_hours: number | null
  lead_time_band: string
  total_deployments: number
  period_days: number
  deployments: DeploymentDetail[]
}

// --- Work Categorization (P4-02) ---

export type WorkCategory = 'feature' | 'bugfix' | 'tech_debt' | 'ops' | 'unknown'

export interface CategoryAllocation {
  category: WorkCategory
  count: number
  additions: number
  deletions: number
  pct_of_total: number
}

export interface IssueCategoryAllocation {
  category: WorkCategory
  count: number
  pct_of_total: number
}

export interface DeveloperWorkAllocation {
  developer_id: number
  github_username: string
  display_name: string
  team: string | null
  pr_categories: Record<string, number>
  issue_categories: Record<string, number>
  total_prs: number
  total_issues: number
}

export interface WorkAllocationPeriod {
  period_start: string
  period_end: string
  period_label: string
  pr_categories: Record<string, number>
  issue_categories: Record<string, number>
}

export interface WorkAllocationResponse {
  period_start: string
  period_end: string
  period_type: string
  pr_allocation: CategoryAllocation[]
  issue_allocation: IssueCategoryAllocation[]
  developer_breakdown: DeveloperWorkAllocation[]
  trend: WorkAllocationPeriod[]
  unknown_pct: number
  ai_classified_count: number
  total_prs: number
  total_issues: number
}

// --- AI Settings (P5) ---

export interface AIFeatureStatus {
  feature: string
  enabled: boolean
  label: string
  description: string
  disabled_impact: string
  tokens_this_month: number
  cost_this_month_usd: number
  call_count_this_month: number
  last_used_at: string | null
}

export interface AISettingsResponse {
  ai_enabled: boolean
  feature_general_analysis: boolean
  feature_one_on_one_prep: boolean
  feature_team_health: boolean
  feature_work_categorization: boolean
  monthly_token_budget: number | null
  budget_warning_threshold: number
  input_token_price_per_million: number
  output_token_price_per_million: number
  pricing_updated_at: string | null
  cooldown_minutes: number
  updated_at: string
  updated_by: string | null
  api_key_configured: boolean
  current_month_tokens: number
  current_month_cost_usd: number
  budget_pct_used: number | null
}

export interface AISettingsUpdate {
  ai_enabled?: boolean
  feature_general_analysis?: boolean
  feature_one_on_one_prep?: boolean
  feature_team_health?: boolean
  feature_work_categorization?: boolean
  monthly_token_budget?: number | null
  clear_budget?: boolean
  budget_warning_threshold?: number
  input_token_price_per_million?: number
  output_token_price_per_million?: number
  cooldown_minutes?: number
}

export interface DailyUsageEntry {
  date: string
  tokens: number
  cost_usd: number
  calls: number
  by_feature: Record<string, { tokens: number; calls: number }>
}

export interface AIUsageSummary {
  period_start: string
  period_end: string
  total_tokens: number
  total_cost_usd: number
  budget_limit: number | null
  budget_pct_used: number | null
  features: AIFeatureStatus[]
  daily_usage: DailyUsageEntry[]
}

export interface AICostEstimate {
  estimated_input_tokens: number
  estimated_output_tokens: number
  estimated_cost_usd: number
  data_items: number
  note: string
}
