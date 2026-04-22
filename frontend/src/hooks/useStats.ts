import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type {
  BenchmarkGroupResponse,
  BenchmarksV2Response,
  CICheckFailuresResponse,
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
  RepoSummaryItem,
  RiskSummaryResponse,
  StalePRsResponse,
  TeamStats,
  WorkAllocationItem,
  IssueLinkageByDeveloper,
  WorkAllocationItemsResponse,
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

export function useReposSummary(dateFrom?: string, dateTo?: string) {
  return useQuery<RepoSummaryItem[]>({
    queryKey: ['repos-summary', dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/repos/summary?${dateParams(dateFrom, dateTo)}`),
    staleTime: 60_000,
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

export function useBenchmarkGroups() {
  return useQuery<BenchmarkGroupResponse[]>({
    queryKey: ['benchmark-groups'],
    queryFn: () => apiFetch('/stats/benchmark-groups'),
  })
}

export function useBenchmarksV2(group?: string, team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (group) params.set('group', group)
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<BenchmarksV2Response>({
    queryKey: ['benchmarks-v2', group, team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/benchmarks?${params}`),
  })
}

export function useUnassignedRoleCount() {
  return useQuery<{ count: number }>({
    queryKey: ['unassigned-role-count'],
    queryFn: () => apiFetch('/developers/unassigned-role-count'),
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

export function useWorkAllocationItems(
  category: string,
  itemType: string = 'all',
  dateFrom?: string,
  dateTo?: string,
  page: number = 1,
  pageSize: number = 20,
  enabled: boolean = true,
) {
  const params = new URLSearchParams()
  params.set('category', category)
  params.set('type', itemType)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return useQuery<WorkAllocationItemsResponse>({
    queryKey: ['work-allocation-items', category, itemType, dateFrom, dateTo, page, pageSize],
    queryFn: () => apiFetch(`/stats/work-allocation/items?${params}`),
    enabled,
  })
}

export function useRecategorizeItem() {
  const queryClient = useQueryClient()
  return useMutation<
    WorkAllocationItem,
    Error,
    { itemType: string; itemId: number; category: string }
  >({
    mutationFn: ({ itemType, itemId, category }) =>
      apiFetch(`/stats/work-allocation/items/${itemType}/${itemId}/category`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['work-allocation'] })
      queryClient.invalidateQueries({ queryKey: ['work-allocation-items'] })
    },
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

export function useCheckFailures(
  checkName: string | null,
  dateFrom?: string,
  dateTo?: string,
  repoId?: number | null,
) {
  const params = new URLSearchParams()
  if (checkName) params.set('check_name', checkName)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (repoId) params.set('repo_id', String(repoId))
  return useQuery<CICheckFailuresResponse>({
    queryKey: ['ci-check-failures', checkName, dateFrom, dateTo, repoId],
    queryFn: () => apiFetch(`/stats/ci/check-failures?${params}`),
    enabled: !!checkName,
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

export function useIssueLinkageByDeveloper(team?: string, dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<IssueLinkageByDeveloper>({
    queryKey: ['issue-linkage-developers', team, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/issue-linkage/developers?${params}`),
  })
}
