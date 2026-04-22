import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type {
  LinearCreatorProfile,
  LinearShepherdProfile,
  LinearWorkerProfile,
} from '@/utils/types'

interface DateRange {
  dateFrom?: string
  dateTo?: string
}

function buildParams({ dateFrom, dateTo }: DateRange) {
  const p = new URLSearchParams()
  if (dateFrom) p.set('date_from', dateFrom)
  if (dateTo) p.set('date_to', dateTo)
  return p
}

export function useDeveloperLinearCreator(
  developerId: number | undefined,
  range: DateRange = {},
  enabled: boolean = true,
) {
  const params = buildParams(range)
  return useQuery<LinearCreatorProfile>({
    queryKey: ['developer-linear-creator', developerId, range.dateFrom, range.dateTo],
    queryFn: () =>
      apiFetch(`/developers/${developerId}/linear-creator-profile?${params}`),
    enabled: !!developerId && enabled,
    staleTime: 60_000,
  })
}

export function useDeveloperLinearWorker(
  developerId: number | undefined,
  range: DateRange = {},
  enabled: boolean = true,
) {
  const params = buildParams(range)
  return useQuery<LinearWorkerProfile>({
    queryKey: ['developer-linear-worker', developerId, range.dateFrom, range.dateTo],
    queryFn: () =>
      apiFetch(`/developers/${developerId}/linear-worker-profile?${params}`),
    enabled: !!developerId && enabled,
    staleTime: 60_000,
  })
}

export function useDeveloperLinearShepherd(
  developerId: number | undefined,
  range: DateRange = {},
  enabled: boolean = true,
) {
  const params = buildParams(range)
  return useQuery<LinearShepherdProfile>({
    queryKey: ['developer-linear-shepherd', developerId, range.dateFrom, range.dateTo],
    queryFn: () =>
      apiFetch(`/developers/${developerId}/linear-shepherd-profile?${params}`),
    enabled: !!developerId && enabled,
    staleTime: 60_000,
  })
}
