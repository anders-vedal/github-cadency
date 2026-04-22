import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type {
  FlowReadinessResponse,
  RefinementChurnResponse,
  StatusRegression,
  StatusTimeDistribution,
  TriageBounce,
} from '@/utils/types'

function buildParams(dateFrom?: string, dateTo?: string, extra: Record<string, string> = {}) {
  const p = new URLSearchParams()
  if (dateFrom) p.set('date_from', dateFrom)
  if (dateTo) p.set('date_to', dateTo)
  for (const [k, v] of Object.entries(extra)) p.set(k, v)
  return p
}

export function useFlowReadiness({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery<FlowReadinessResponse>({
    queryKey: ['flow-readiness'],
    queryFn: () => apiFetch('/flow/readiness'),
    staleTime: 5 * 60_000,
    enabled,
  })
}

export function useStatusTimeDistribution(
  dateFrom?: string,
  dateTo?: string,
  groupBy: string = 'all',
  { enabled = true }: { enabled?: boolean } = {},
) {
  const params = buildParams(dateFrom, dateTo, { group_by: groupBy })
  return useQuery<StatusTimeDistribution[]>({
    queryKey: ['status-time-distribution', dateFrom, dateTo, groupBy],
    queryFn: () => apiFetch(`/flow/status-distribution?${params}`),
    staleTime: 60_000,
    enabled,
  })
}

export function useStatusRegressions(
  dateFrom?: string,
  dateTo?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<StatusRegression[]>({
    queryKey: ['status-regressions', dateFrom, dateTo],
    queryFn: () => apiFetch(`/flow/regressions?${params}`),
    staleTime: 60_000,
    enabled,
  })
}

export function useTriageBounces(
  dateFrom?: string,
  dateTo?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<TriageBounce[]>({
    queryKey: ['triage-bounces', dateFrom, dateTo],
    queryFn: () => apiFetch(`/flow/triage-bounces?${params}`),
    staleTime: 60_000,
    enabled,
  })
}

export function useRefinementChurn(
  dateFrom?: string,
  dateTo?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<RefinementChurnResponse>({
    queryKey: ['refinement-churn', dateFrom, dateTo],
    queryFn: () => apiFetch(`/flow/refinement-churn?${params}`),
    staleTime: 60_000,
    enabled,
  })
}
