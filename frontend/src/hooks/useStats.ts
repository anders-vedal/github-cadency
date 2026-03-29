import { useQuery, useQueries } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type {
  BenchmarksResponse,
  CIStatsResponse,
  CodeChurnResponse,
  CollaborationPairDetail,
  CollaborationResponse,
  CollaborationTrendsResponse,
  DORAMetricsResponse,
  DeveloperStatsWithPercentiles,
  DeveloperTrendsResponse,
  IssueCreatorStatsResponse,
  RepoStats,
  RiskSummaryResponse,
  StalePRsResponse,
  TeamStats,
  WorkAllocationResponse,
  WorkloadResponse,
} from '@/utils/types'

function dateParams(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return params.toString()
}

export function useDeveloperStats(id: number, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  params.set('include_percentiles', 'true')
  return useQuery<DeveloperStatsWithPercentiles>({
    queryKey: ['developer-stats', id, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/developer/${id}?${params}`),
    enabled: !!id,
  })
}

export function useTeamStats(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<TeamStats>({
    queryKey: ['team-stats', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/team?${params}`),
  })
}

export function useRepoStats(id: number, dateFrom?: string, dateTo?: string) {
  return useQuery<RepoStats>({
    queryKey: ['repo-stats', id, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/repo/${id}?${dateParams(dateFrom, dateTo)}`),
    enabled: !!id,
  })
}

export function useDeveloperTrends(
  id: number,
  periodType: string = 'week',
  periods: number = 8,
) {
  const params = new URLSearchParams()
  params.set('period_type', periodType)
  params.set('periods', String(periods))
  return useQuery<DeveloperTrendsResponse>({
    queryKey: ['developer-trends', id, periodType, periods],
    queryFn: () => apiFetch(`/stats/developer/${id}/trends?${params}`),
    enabled: !!id,
  })
}

export function useStalePRs(team?: string, thresholdHours?: number) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (thresholdHours) params.set('threshold_hours', String(thresholdHours))
  return useQuery<StalePRsResponse>({
    queryKey: ['stale-prs', team, thresholdHours],
    queryFn: () => apiFetch(`/stats/stale-prs?${params}`),
  })
}

export function useWorkload(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<WorkloadResponse>({
    queryKey: ['workload', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/workload?${params}`),
  })
}

export function useBenchmarks(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<BenchmarksResponse>({
    queryKey: ['benchmarks', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/benchmarks?${params}`),
  })
}

export function useAllDeveloperStats(
  developerIds: number[],
  dateFrom?: string,
  dateTo?: string,
) {
  return useQueries({
    queries: developerIds.map((id) => {
      const params = new URLSearchParams()
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      params.set('include_percentiles', 'true')
      return {
        queryKey: ['developer-stats', id, dateFrom, dateTo],
        queryFn: () => apiFetch<DeveloperStatsWithPercentiles>(`/stats/developer/${id}?${params}`),
        enabled: !!id,
      }
    }),
  })
}

export function useIssueCreatorStats(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<IssueCreatorStatsResponse>({
    queryKey: ['issue-creator-stats', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/issues/creators?${params}`),
  })
}

export function useCollaboration(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<CollaborationResponse>({
    queryKey: ['collaboration', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/collaboration?${params}`),
  })
}

export function useCollaborationPairDetail(
  reviewerId: number | null,
  authorId: number | null,
  dateFrom?: string,
  dateTo?: string,
) {
  const params = new URLSearchParams()
  if (reviewerId != null) params.set('reviewer_id', String(reviewerId))
  if (authorId != null) params.set('author_id', String(authorId))
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<CollaborationPairDetail>({
    queryKey: ['collaboration-pair', reviewerId, authorId, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/collaboration/pair?${params}`),
    enabled: reviewerId != null && authorId != null,
  })
}

export function useCollaborationTrends(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<CollaborationTrendsResponse>({
    queryKey: ['collaboration-trends', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/collaboration/trends?${params}`),
  })
}

export function useRiskSummary(
  team?: string,
  dateFrom?: string,
  dateTo?: string,
  minRiskLevel: string = 'medium',
  scope: string = 'all',
) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  params.set('min_risk_level', minRiskLevel)
  params.set('scope', scope)
  return useQuery<RiskSummaryResponse>({
    queryKey: ['risk-summary', team, dateFrom, dateTo, minRiskLevel, scope],
    queryFn: () => apiFetch(`/stats/risk-summary?${params}`),
  })
}

export function useCodeChurn(
  repoId: number | null,
  dateFrom?: string,
  dateTo?: string,
  limit: number = 50,
) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  params.set('limit', String(limit))
  return useQuery<CodeChurnResponse>({
    queryKey: ['code-churn', repoId, dateFrom, dateTo, limit],
    queryFn: () => apiFetch(`/stats/repo/${repoId}/churn?${params}`),
    enabled: !!repoId,
  })
}

export function useWorkAllocation(
  team?: string,
  dateFrom?: string,
  dateTo?: string,
  useAi: boolean = false,
) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (useAi) params.set('use_ai', 'true')
  return useQuery<WorkAllocationResponse>({
    queryKey: ['work-allocation', team, dateFrom, dateTo, useAi],
    queryFn: () => apiFetch(`/stats/work-allocation?${params}`),
  })
}

export function useCIStats(
  dateFrom?: string,
  dateTo?: string,
  repoId?: number | null,
) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (repoId) params.set('repo_id', String(repoId))
  return useQuery<CIStatsResponse>({
    queryKey: ['ci-stats', dateFrom, dateTo, repoId],
    queryFn: () => apiFetch(`/stats/ci?${params}`),
  })
}

export function useDoraMetrics(
  dateFrom?: string,
  dateTo?: string,
  repoId?: number | null,
) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (repoId) params.set('repo_id', String(repoId))
  return useQuery<DORAMetricsResponse>({
    queryKey: ['dora-metrics', dateFrom, dateTo, repoId],
    queryFn: () => apiFetch(`/stats/dora?${params}`),
  })
}
