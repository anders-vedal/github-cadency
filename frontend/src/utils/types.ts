// --- Auth ---

export interface AuthUser {
  developer_id: number
  github_username: string
  display_name: string
  app_role: 'admin' | 'developer'
  avatar_url: string | null
}

// --- Role Definitions ---

export type ContributionCategory = 'code_contributor' | 'issue_contributor' | 'non_contributor' | 'system'

export interface RoleDefinition {
  role_key: string
  display_name: string
  contribution_category: ContributionCategory
  display_order: number
  is_default: boolean
}

// --- Teams ---

export interface Team {
  id: number
  name: string
  display_order: number
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
  office: string | null
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
  office?: string | null
  notes?: string | null
}

export type DeveloperUpdate = Partial<Omit<DeveloperCreate, 'github_username'>> & {
  is_active?: boolean
}

export interface DeactivationImpact {
  open_prs: number
  open_issues: number
  open_branches: string[]
}

export interface ActivitySummary {
  prs_authored: number
  prs_merged: number
  prs_open: number
  reviews_given: number
  issues_created: number
  issues_assigned: number
  repos_touched: number
  first_activity: string | null
  last_activity: string | null
  work_categories: Record<string, number>
}

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
  prs_linked_to_issue: number
  issue_linkage_rate: number | null
}

export interface DeveloperLinkageRow {
  developer_id: number
  github_username: string
  display_name: string
  team: string | null
  prs_total: number
  prs_linked: number
  linkage_rate: number
}

export interface IssueLinkageByDeveloper {
  developers: DeveloperLinkageRow[]
  team_average_rate: number
  attention_threshold: number
  attention_developers: DeveloperLinkageRow[]
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

export interface RepoSummaryItem {
  repo_id: number
  total_prs: number
  total_merged: number
  total_issues: number
  total_reviews: number
  avg_time_to_merge_hours: number | null
  last_pr_date: string | null
  prev_total_prs: number
  prev_total_merged: number
  prev_avg_time_to_merge_hours: number | null
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

export interface RepoDataDeleteResponse {
  repo_id: number
  full_name: string | null
  deleted: {
    pull_requests: number
    pr_reviews: number
    pr_review_comments: number
    pr_files: number
    pr_check_runs: number
    pr_external_issue_links: number
    issues: number
    issue_comments: number
    deployments: number
    repo_tree_files: number
  }
}

// --- Sync ---

export interface SyncRepoResult {
  repo_id: number
  repo_name: string
  status: 'ok' | 'partial'
  prs: number
  issues: number
  prs_skipped?: number
  issues_skipped?: number
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
  hint?: string
}

export interface PreflightCheck {
  field: string
  status: 'ok' | 'error' | 'warn'
  message: string
}

export interface PreflightResponse {
  checks: PreflightCheck[]
  ready: boolean
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
  current_step: string | null
  current_repo_prs_total: number | null
  current_repo_prs_done: number | null
  current_repo_issues_total: number | null
  current_repo_issues_done: number | null
  repos_completed: SyncRepoResult[] | null
  repos_failed: SyncRepoFailure[] | null
  is_resumable: boolean
  resumed_from_id: number | null
  cancel_requested: boolean
  log_summary: SyncLogEntry[] | null
  rate_limit_wait_s: number | null
  triggered_by: string | null
  sync_scope: string | null
}

export interface SyncScheduleConfig {
  auto_sync_enabled: boolean
  incremental_interval_minutes: number
  full_sync_cron_hour: number
  updated_at: string | null
}

export interface SyncStatusResponse {
  active_sync: SyncEvent | null
  last_completed: SyncEvent | null
  tracked_repos_count: number
  total_repos_count: number
  last_successful_sync: string | null
  last_sync_duration_s: number | null
  schedule: SyncScheduleConfig | null
}

export interface SyncStartRequest {
  sync_type: 'full' | 'incremental'
  repo_ids?: number[]
  since?: string
  sync_scope?: string
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
  repo_ids?: number[]
}

export interface OneOnOnePrepRequest {
  developer_id: number
  date_from: string
  date_to: string
  repo_ids?: number[]
}

export interface TeamHealthRequest {
  team?: string
  date_from: string
  date_to: string
  repo_ids?: number[]
}

export type AnalysisWizardType = 'communication' | 'conflict' | 'sentiment' | 'one_on_one_prep' | 'team_health'

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

export interface BenchmarkGroupResponse {
  group_key: string
  display_name: string
  display_order: number
  roles: string[]
  metrics: string[]
  min_team_size: number
  is_default: boolean
}

export interface BenchmarkMetricInfo {
  key: string
  label: string
  lower_is_better: boolean
  unit: string
}

export interface MetricValue {
  value: number | null
  percentile_band: 'below_p25' | 'p25_to_p50' | 'p50_to_p75' | 'above_p75' | null
}

export interface DeveloperBenchmarkRow {
  developer_id: number
  display_name: string
  avatar_url: string | null
  team: string | null
  role: string | null
  metrics: Record<string, MetricValue>
}

export interface TeamMedianRow {
  team: string
  sample_size: number
  metrics: Record<string, number | null>
}

export interface BenchmarksV2Response {
  group: BenchmarkGroupResponse
  period_start: string
  period_end: string
  sample_size: number
  team: string | null
  metrics: Record<string, BenchmarkMetric>
  metric_info: BenchmarkMetricInfo[]
  developers: DeveloperBenchmarkRow[]
  team_comparison: TeamMedianRow[] | null
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

export interface PairRelationship {
  label: string
  confidence: number
  explanation: string
}

export interface PairReviewedPR {
  pr_id: number
  pr_number: number
  title: string
  html_url: string | null
  repo_full_name: string
  review_state: string | null
  quality_tier: string
  comment_count: number
  additions: number | null
  deletions: number | null
  submitted_at: string | null
}

export interface CommentTypeBreakdown {
  comment_type: string
  count: number
}

export interface QualityTierBreakdown {
  tier: string
  count: number
}

export interface CollaborationPairDetail {
  reviewer_id: number
  reviewer_name: string
  reviewer_avatar_url: string | null
  reviewer_team: string | null
  author_id: number
  author_name: string
  author_avatar_url: string | null
  author_team: string | null
  total_reviews: number
  approval_rate: number
  changes_requested_rate: number
  avg_quality_tier: string
  quality_tier_breakdown: QualityTierBreakdown[]
  comment_type_breakdown: CommentTypeBreakdown[]
  total_comments: number
  relationship: PairRelationship
  recent_prs: PairReviewedPR[]
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
  html_url?: string | null
}

export interface SlowestCheck {
  name: string
  avg_duration_s: number
  html_url?: string | null
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
  is_failure: boolean
  failure_detected_via: string | null
  recovery_time_hours: number | null
}

export interface DORAMetricsResponse {
  deploy_frequency: number
  deploy_frequency_band: string
  avg_lead_time_hours: number | null
  lead_time_band: string
  total_deployments: number
  period_days: number
  deployments: DeploymentDetail[]
  total_all_deployments: number
  change_failure_rate: number | null
  cfr_band: string
  avg_mttr_hours: number | null
  mttr_band: string
  failure_deployments: number
  overall_band: string
}

// --- Work Categorization (P4-02) ---

export type WorkCategory = string

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

export interface WorkAllocationItem {
  id: number
  type: 'pr' | 'issue'
  number: number
  title: string | null
  labels: string[] | null
  repo_name: string | null
  author_name: string | null
  author_id: number | null
  html_url: string | null
  category: string
  category_source: string | null
  merged_at: string | null
  created_at: string | null
  additions: number | null
  deletions: number | null
}

export interface WorkAllocationItemsResponse {
  items: WorkAllocationItem[]
  total: number
  page: number
  page_size: number
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
  character_count: number
  system_prompt_tokens: number
  remaining_budget_tokens: number
  would_exceed_budget: boolean
  note: string
}

export interface AISchedule {
  id: number
  name: string
  analysis_type: string
  general_type: string | null
  scope_type: string
  scope_id: string
  repo_ids: number[] | null
  time_range_days: number
  frequency: string
  day_of_week: number | null
  hour: number
  minute: number
  is_enabled: boolean
  last_run_at: string | null
  last_run_analysis_id: number | null
  last_run_status: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  next_run_description: string | null
}

export interface AIScheduleCreate {
  name: string
  analysis_type: string
  general_type?: string
  scope_type: string
  scope_id: string
  repo_ids?: number[]
  time_range_days?: number
  frequency: string
  day_of_week?: number
  hour?: number
  minute?: number
}

export interface AIScheduleUpdate {
  name?: string
  is_enabled?: boolean
  repo_ids?: number[]
  time_range_days?: number
  frequency?: string
  day_of_week?: number
  hour?: number
  minute?: number
}

// --- Developer Relationships ---

export type RelationshipType = 'reports_to' | 'tech_lead_of' | 'team_lead_of'

export interface DeveloperRelationshipResponse {
  id: number
  source_id: number
  target_id: number
  relationship_type: string
  source_name: string
  target_name: string
  source_avatar_url: string | null
  target_avatar_url: string | null
  created_at: string
}

export interface DeveloperRelationshipsResponse {
  reports_to: DeveloperRelationshipResponse | null
  tech_lead: DeveloperRelationshipResponse | null
  team_lead: DeveloperRelationshipResponse | null
  direct_reports: DeveloperRelationshipResponse[]
  tech_leads_for: DeveloperRelationshipResponse[]
  team_leads_for: DeveloperRelationshipResponse[]
}

export interface OrgTreeNode {
  developer_id: number
  display_name: string
  github_username: string
  avatar_url: string | null
  role: string | null
  team: string | null
  office: string | null
  children: OrgTreeNode[]
}

export interface OrgTreeResponse {
  roots: OrgTreeNode[]
  unassigned: OrgTreeNode[]
}

// --- Enhanced Collaboration ---

export interface WorksWithEntry {
  developer_id: number
  display_name: string
  github_username: string
  avatar_url: string | null
  team: string | null
  total_score: number
  interaction_count: number
  review_score: number
  coauthor_score: number
  issue_comment_score: number
  mention_score: number
  co_assigned_score: number
}

export interface WorksWithResponse {
  developer_id: number
  collaborators: WorksWithEntry[]
}

export interface OverTaggedDeveloper {
  developer_id: number
  display_name: string
  github_username: string
  team: string | null
  combined_tag_rate: number
  pr_tag_rate: number
  issue_tag_rate: number
  team_average: number
  severity: 'mild' | 'moderate' | 'severe'
}

export interface OverTaggedResponse {
  developers: OverTaggedDeveloper[]
}

export interface CommunicationScoreEntry {
  developer_id: number
  display_name: string
  github_username: string
  avatar_url: string | null
  team: string | null
  communication_score: number
  review_engagement: number
  comment_depth: number
  reach: number
  responsiveness: number
}

export interface CommunicationScoresResponse {
  developers: CommunicationScoreEntry[]
}

// --- Slack Integration ---

export interface SlackConfigResponse {
  slack_enabled: boolean
  bot_token_configured: boolean
  default_channel: string | null
  notify_stale_prs: boolean
  notify_high_risk_prs: boolean
  notify_workload_alerts: boolean
  notify_sync_failures: boolean
  notify_sync_complete: boolean
  notify_weekly_digest: boolean
  stale_pr_days_threshold: number
  risk_score_threshold: number
  digest_day_of_week: number
  digest_hour_utc: number
  stale_check_hour_utc: number
  updated_at: string
  updated_by: string | null
}

export interface SlackConfigUpdate {
  slack_enabled?: boolean
  bot_token?: string
  default_channel?: string | null
  notify_stale_prs?: boolean
  notify_high_risk_prs?: boolean
  notify_workload_alerts?: boolean
  notify_sync_failures?: boolean
  notify_sync_complete?: boolean
  notify_weekly_digest?: boolean
  stale_pr_days_threshold?: number
  risk_score_threshold?: number
  digest_day_of_week?: number
  digest_hour_utc?: number
  stale_check_hour_utc?: number
}

export interface SlackUserSettingsResponse {
  developer_id: number
  slack_user_id: string | null
  notify_stale_prs: boolean
  notify_high_risk_prs: boolean
  notify_workload_alerts: boolean
  notify_weekly_digest: boolean
}

export interface SlackUserSettingsUpdate {
  slack_user_id?: string | null
  notify_stale_prs?: boolean
  notify_high_risk_prs?: boolean
  notify_workload_alerts?: boolean
  notify_weekly_digest?: boolean
}

export interface NotificationLogEntry {
  id: number
  notification_type: string
  channel: string | null
  recipient_developer_id: number | null
  status: string
  error_message: string | null
  payload: Record<string, unknown> | null
  created_at: string
}

export interface NotificationHistoryResponse {
  notifications: NotificationLogEntry[]
  total: number
}

export interface SlackTestResponse {
  success: boolean
  message: string
}

// --- Integration Config (Linear, etc.) ---

export interface IntegrationConfig {
  id: number
  type: string
  display_name: string | null
  api_key_configured: boolean
  workspace_id: string | null
  workspace_name: string | null
  status: string
  error_message: string | null
  is_primary_issue_source: boolean
  last_synced_at: string | null
  created_at: string
  updated_at: string
}

export interface IntegrationConfigCreate {
  type: string
  display_name?: string
  api_key?: string
}

export interface IntegrationConfigUpdate {
  display_name?: string
  api_key?: string
  status?: string
}

export interface IntegrationTestResponse {
  success: boolean
  message: string
  workspace_name: string | null
}

export interface IntegrationSyncStatus {
  is_syncing: boolean
  last_sync_event_id: number | null
  last_synced_at: string | null
  last_sync_status: string | null
  issues_synced: number
  sprints_synced: number
  projects_synced: number
}

export interface IssueSourceResponse {
  source: string
  integration_id: number | null
}

export interface LinearUser {
  id: string
  name: string
  display_name: string | null
  email: string | null
  active: boolean
  mapped_developer_id: number | null
  mapped_developer_name: string | null
}

export interface LinearUserListResponse {
  users: LinearUser[]
  total: number
  mapped_count: number
  unmapped_count: number
}

export interface MapUserRequest {
  external_user_id: string
  developer_id: number
}

export interface DeveloperIdentityMap {
  id: number
  developer_id: number
  integration_type: string
  external_user_id: string
  external_email: string | null
  external_display_name: string | null
  mapped_by: string
  created_at: string
}

// --- Sprint & Planning Stats ---

export interface ExternalSprint {
  id: number
  external_id: string
  name: string | null
  number: number | null
  team_key: string | null
  team_name: string | null
  state: string
  start_date: string | null
  end_date: string | null
  planned_scope: number | null
  completed_scope: number | null
  cancelled_scope: number | null
  added_scope: number | null
  url: string | null
}

export interface ExternalIssue {
  id: number
  external_id: string
  identifier: string
  title: string
  issue_type: string | null
  status: string | null
  status_category: string | null
  priority: number
  priority_label: string | null
  estimate: number | null
  assignee_developer_id: number | null
  project_id: number | null
  sprint_id: number | null
  labels: string[] | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  triage_duration_s: number | null
  cycle_time_s: number | null
  url: string | null
}

export interface SprintDetail extends ExternalSprint {
  issues: ExternalIssue[]
  completion_rate: number | null
  scope_creep_pct: number | null
}

export interface SprintVelocityPoint {
  sprint_id: number
  sprint_name: string | null
  sprint_number: number | null
  team_key: string | null
  completed_scope: number
  planned_scope: number
  start_date: string | null
  end_date: string | null
}

export interface SprintVelocityResponse {
  data: SprintVelocityPoint[]
  avg_velocity: number
  trend_direction: string
}

export interface SprintCompletionPoint {
  sprint_id: number
  sprint_name: string | null
  sprint_number: number | null
  planned_scope: number
  completed_scope: number
  completion_rate: number
}

export interface SprintCompletionResponse {
  data: SprintCompletionPoint[]
  avg_completion_rate: number
}

export interface ScopeCreepPoint {
  sprint_id: number
  sprint_name: string | null
  sprint_number: number | null
  planned_scope: number
  added_scope: number
  scope_creep_pct: number
}

export interface ScopeCreepResponse {
  data: ScopeCreepPoint[]
  avg_scope_creep_pct: number
}

export interface ExternalProject {
  id: number
  external_id: string
  key: string | null
  name: string
  status: string | null
  health: string | null
  start_date: string | null
  target_date: string | null
  progress_pct: number | null
  lead_id: number | null
  url: string | null
  issue_count: number
  completed_issue_count: number
}

export interface ExternalProjectDetail extends ExternalProject {
  issues: ExternalIssue[]
}

export interface TriageMetrics {
  avg_triage_duration_s: number
  median_triage_duration_s: number
  p90_triage_duration_s: number
  issues_in_triage: number
  total_triaged: number
}

export interface EstimationAccuracyPoint {
  sprint_id: number
  sprint_name: string | null
  sprint_number: number | null
  estimated_points: number
  completed_points: number
  accuracy_pct: number
}

export interface EstimationAccuracyResponse {
  data: EstimationAccuracyPoint[]
  avg_accuracy_pct: number
}

export interface WorkAlignment {
  total_prs: number
  linked_prs: number
  unlinked_prs: number
  alignment_pct: number
}

export interface PlanningCorrelationPoint {
  sprint_id: number
  sprint_name: string | null
  completion_rate: number
  avg_pr_merge_time_hours: number | null
}

export interface PlanningCorrelationResponse {
  data: PlanningCorrelationPoint[]
  correlation_coefficient: number | null
}

// --- System Version ---

export interface VersionInfo {
  version: string
  build: string
  commit: string
  deployed_at: string
  full_version: string
}

// --- Linear Insights v2 ---

// Phase 02 — Linkage Quality

export interface LinkQualityUnlinkedPR {
  pr_id: number
  number: number
  title: string
  created_at: string | null
  html_url: string | null
  author_github_username: string | null
  repo: string
}

export interface LinkQualityDisagreementLink {
  external_issue_id: number
  identifier: string
  link_source: string
  link_confidence: string
}

export interface LinkQualityDisagreementPR {
  pr_id: number
  number: number
  title: string
  html_url: string | null
  repo: string
  links: LinkQualityDisagreementLink[]
}

export interface LinkQualitySummary {
  total_prs: number
  linked_prs: number
  linkage_rate: number
  by_confidence: Record<string, number>
  by_source: Record<string, number>
  unlinked_recent: LinkQualityUnlinkedPR[]
  disagreement_prs: LinkQualityDisagreementPR[]
}

export interface RelinkResponse {
  sync_event_id: number
  status: string
  new_links?: number | null
}

export interface LinkageRateTrendBucket {
  week_start: string
  total: number
  linked: number
  linkage_rate: number | null
}

export interface LinkageRateTrendResponse {
  buckets: LinkageRateTrendBucket[]
}

// Phase 10 — DORA v2

export interface DoraV2Throughput {
  deployment_frequency: number | null
  lead_time_hours: number | null
  mttr_hours: number | null
}

export interface DoraV2Stability {
  change_failure_rate: number | null
  rework_rate: number | null
}

export interface DoraV2Bands {
  deployment_frequency: string
  lead_time: string
  mttr: string
  change_failure_rate: string
  rework_rate: string
  overall: string
}

export interface DoraV2CohortRow {
  merges: number
  rework_rate: number
  share_pct: number
}

export interface DoraV2Response {
  throughput: DoraV2Throughput
  stability: DoraV2Stability
  bands: DoraV2Bands
  cohorts: Record<string, DoraV2CohortRow>
  date_from: string
  date_to: string
}

// Phase 03 — Linear Usage Health

export type LinearHealthStatus = 'healthy' | 'warning' | 'critical'

export interface LinearHealthAdoption {
  linked_pr_count: number
  total_pr_count: number
  linkage_rate: number
  target: number
  status: LinearHealthStatus
}

export interface LinearHealthSpecQuality {
  median_description_length: number
  median_comments_before_first_pr: number
  high_comment_issue_pct: number
  status: LinearHealthStatus
}

export interface LinearHealthAutonomy {
  self_picked_count: number
  pushed_count: number
  self_picked_pct: number
  median_time_to_assign_s: number | null
  status: LinearHealthStatus
}

export interface LinearHealthDialogue {
  median_comments_per_issue: number
  p90_comments_per_issue: number
  silent_issue_pct: number
  distribution_shape: string
  status: LinearHealthStatus
}

export interface LinearHealthCreatorRow {
  developer_id: number
  developer_name: string
  issues_created: number
  avg_comments_on_their_issues: number
  avg_downstream_pr_review_rounds: number
  sample_size: number
}

export interface LinearHealthCreatorOutcome {
  top_creators: LinearHealthCreatorRow[]
}

export interface LinearUsageHealthResponse {
  adoption: LinearHealthAdoption
  spec_quality: LinearHealthSpecQuality
  autonomy: LinearHealthAutonomy
  dialogue_health: LinearHealthDialogue
  creator_outcome: LinearHealthCreatorOutcome
}

// Phase 04 — Issue Conversations

export interface ChattyIssueRef {
  id: number
  name: string | null
}

export interface ChattyIssueLinkedPR {
  pr_id: number
  number: number
  repo: string | null
  review_round_count: number | null
  merged_at: string | null
}

export interface ChattyIssueRow {
  issue_id: number
  identifier: string
  title: string
  url: string | null
  creator: ChattyIssueRef | null
  assignee: ChattyIssueRef | null
  project: ChattyIssueRef | null
  priority_label: string | null
  estimate: number | null
  comment_count: number
  unique_participants: number
  first_response_s: number | null
  created_at: string | null
  status: string | null
  linked_prs: ChattyIssueLinkedPR[]
  avg_linked_pr_review_rounds: number | null
}

export interface ConversationsScatterPoint {
  comment_count: number
  review_rounds: number
  issue_identifier: string
  pr_number: number
}

export interface FirstResponseHistogramBucket {
  bucket: string
  count: number
}

export interface ParticipantDistributionBucket {
  participants: string
  count: number
}

// Phase 05 — Developer Linear profiles

export interface LabelCountRow {
  label: string
  count: number
}

export interface LinearCreatorProfile {
  issues_created: number
  issues_created_by_type: Record<string, number>
  top_labels: LabelCountRow[]
  avg_description_length: number
  avg_comments_generated: number
  avg_downstream_pr_review_rounds: number
  sample_size_downstream_prs: number
  self_assigned_pct: number
  median_time_to_close_for_their_issues_s: number | null
}

export interface LinearWorkerProfile {
  issues_worked: number
  self_picked_count: number
  pushed_count: number
  self_picked_pct: number
  median_triage_to_start_s: number | null
  median_cycle_time_s: number | null
  issues_worked_by_status: Record<string, number>
  reassigned_to_other_count: number
}

export interface ShepherdCollaborator {
  developer_id: number
  name: string
  count: number
}

export interface LinearShepherdProfile {
  comments_on_others_issues: number
  issues_commented_on: number
  unique_teams_commented_on: number
  is_shepherd: boolean
  top_collaborators: ShepherdCollaborator[]
}

// Phase 06 — Flow Analytics

export interface FlowReadinessResponse {
  ready: boolean
  days_of_history: number
  issues_with_history: number
  threshold_days: number
  threshold_issues: number
}

export interface StatusTimeDistribution {
  status_category: string
  p50_s: number
  p75_s: number
  p90_s: number
  p95_s: number
  sample_size: number
}

export interface StatusRegression {
  issue_id: number
  identifier: string
  title: string
  url: string | null
  from_status: string
  to_status: string
  changed_at: string | null
  actor_id: number | null
  actor_name: string | null
}

export interface TriageBounce {
  issue_id: number
  identifier: string
  title: string
  url: string | null
}

export interface RefinementChurnDistribution {
  p50: number
  p90: number
  mean: number
  total_issues_with_churn: number
}

export interface RefinementChurnRow {
  issue_id: number
  identifier: string
  title: string
  url: string | null
  churn_events: number
}

export interface RefinementChurnResponse {
  distribution: RefinementChurnDistribution
  top: RefinementChurnRow[]
}

// Phase 07 — Bottleneck intelligence

export interface CumulativeFlowPoint {
  date: string
  triage: number
  backlog: number
  todo: number
  in_progress: number
  in_review: number
  done: number
  cancelled: number
}

export interface WipIssueRef {
  id: number
  identifier: string
  title: string
}

export interface WipOverLimit {
  developer_id: number
  developer_name: string
  in_progress_count: number
  threshold: number
  issues: WipIssueRef[]
}

export interface ReviewLoadTopRow {
  reviewer_id: number
  reviewer_name: string
  review_count: number
}

export interface ReviewLoadGini {
  gini: number
  total_reviews: number
  total_reviewers: number
  top_k_share: number
  top_reviewers: ReviewLoadTopRow[]
}

export interface ReviewNetworkNode {
  id: number
  name: string
  team: string | null
}

export interface ReviewNetworkEdge {
  reviewer_id: number
  author_id: number
  weight: number
}

export interface ReviewNetworkResponse {
  nodes: ReviewNetworkNode[]
  edges: ReviewNetworkEdge[]
}

export interface CrossTeamHandoff {
  issue_id: number
  identifier: string | null
  title: string | null
  from_team: string | null
  to_team: string | null
  changed_at: string | null
}

export interface BlockedChainRow {
  issue_id: number
  identifier: string
  title: string
  status: string | null
  blocker_depth: number
}

export interface ReviewPingPongRow {
  pr_id: number
  number: number
  title: string
  review_round_count: number
  author_id: number | null
  state: string
  html_url: string | null
  repo: string | null
}

export interface BusFactorFileRow {
  filename: string
  distinct_authors: number
  owner_name: string | null
}

export interface BimodalPeak {
  bin: number
  count: number
}

export interface BimodalAnalysis {
  is_bimodal: boolean
  peaks: BimodalPeak[]
  trough_ratio: number | null
  bins: number[] | null
  bucket_size: number | null
  min: number | null
  max: number | null
}

export interface CycleTimeHistogramResponse {
  sample_size: number
  p50_s: number
  p90_s: number
  bimodal_analysis: BimodalAnalysis
}

export interface BottleneckDigestItem {
  title: string
  severity: string
  detail: string
  drill_path: string
}
