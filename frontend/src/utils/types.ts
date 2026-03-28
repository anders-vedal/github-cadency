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
}

// --- Sync ---

export interface SyncEvent {
  id: number
  sync_type: string | null
  status: string | null
  repos_synced: number | null
  prs_upserted: number | null
  issues_upserted: number | null
  errors: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  duration_s: number | null
}

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
