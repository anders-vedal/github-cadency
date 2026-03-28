import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type { DeveloperStats, RepoStats, TeamStats } from '@/utils/types'

function dateParams(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return params.toString()
}

export function useDeveloperStats(id: number, dateFrom?: string, dateTo?: string) {
  return useQuery<DeveloperStats>({
    queryKey: ['developer-stats', id, dateFrom, dateTo],
    queryFn: () => apiFetch(`/stats/developer/${id}?${dateParams(dateFrom, dateTo)}`),
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
