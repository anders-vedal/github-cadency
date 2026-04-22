import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type {
  BlockedChainRow,
  BottleneckDigestItem,
  BusFactorFileRow,
  CrossTeamHandoff,
  CumulativeFlowPoint,
  CycleTimeHistogramResponse,
  ReviewLoadGini,
  ReviewNetworkResponse,
  ReviewPingPongRow,
  WipOverLimit,
} from '@/utils/types'

function buildParams(dateFrom?: string, dateTo?: string, extra: Record<string, string> = {}) {
  const p = new URLSearchParams()
  if (dateFrom) p.set('date_from', dateFrom)
  if (dateTo) p.set('date_to', dateTo)
  for (const [k, v] of Object.entries(extra)) p.set(k, v)
  return p
}

export function useBottleneckSummary() {
  return useQuery<BottleneckDigestItem[]>({
    queryKey: ['bottleneck-summary'],
    queryFn: () => apiFetch('/bottlenecks/summary'),
    staleTime: 5 * 60_000,
  })
}

export function useCumulativeFlow(
  cycleId?: number,
  projectId?: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const p = buildParams(dateFrom, dateTo)
  if (cycleId != null) p.set('cycle_id', String(cycleId))
  if (projectId != null) p.set('project_id', String(projectId))
  return useQuery<CumulativeFlowPoint[]>({
    queryKey: ['cumulative-flow', cycleId, projectId, dateFrom, dateTo],
    queryFn: () => apiFetch(`/bottlenecks/cumulative-flow?${p}`),
    staleTime: 60_000,
  })
}

export function useWip(threshold: number = 4) {
  return useQuery<WipOverLimit[]>({
    queryKey: ['wip', threshold],
    queryFn: () => apiFetch(`/bottlenecks/wip?threshold=${threshold}`),
    staleTime: 60_000,
  })
}

export function useReviewLoad(dateFrom?: string, dateTo?: string) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<ReviewLoadGini>({
    queryKey: ['review-load', dateFrom, dateTo],
    queryFn: () => apiFetch(`/bottlenecks/review-load?${params}`),
    staleTime: 60_000,
  })
}

export function useReviewNetwork(dateFrom?: string, dateTo?: string) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<ReviewNetworkResponse>({
    queryKey: ['review-network', dateFrom, dateTo],
    queryFn: () => apiFetch(`/bottlenecks/review-network?${params}`),
    staleTime: 60_000,
  })
}

export function useCrossTeamHandoffs(dateFrom?: string, dateTo?: string) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<CrossTeamHandoff[]>({
    queryKey: ['cross-team-handoffs', dateFrom, dateTo],
    queryFn: () => apiFetch(`/bottlenecks/cross-team-handoffs?${params}`),
    staleTime: 60_000,
  })
}

export function useBlockedChains() {
  return useQuery<BlockedChainRow[]>({
    queryKey: ['blocked-chains'],
    queryFn: () => apiFetch('/bottlenecks/blocked-chains'),
    staleTime: 60_000,
  })
}

export function useReviewPingPong(dateFrom?: string, dateTo?: string) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<ReviewPingPongRow[]>({
    queryKey: ['review-ping-pong', dateFrom, dateTo],
    queryFn: () => apiFetch(`/bottlenecks/ping-pong?${params}`),
    staleTime: 60_000,
  })
}

export function useBusFactorFiles(sinceDays: number = 90, minAuthors: number = 2) {
  return useQuery<BusFactorFileRow[]>({
    queryKey: ['bus-factor-files', sinceDays, minAuthors],
    queryFn: () =>
      apiFetch(
        `/bottlenecks/bus-factor-files?since_days=${sinceDays}&min_authors=${minAuthors}`,
      ),
    staleTime: 60_000,
  })
}

export function useCycleHistogram(dateFrom?: string, dateTo?: string) {
  const params = buildParams(dateFrom, dateTo)
  return useQuery<CycleTimeHistogramResponse>({
    queryKey: ['cycle-histogram', dateFrom, dateTo],
    queryFn: () => apiFetch(`/bottlenecks/cycle-histogram?${params}`),
    staleTime: 60_000,
  })
}
