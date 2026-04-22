import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type { DoraV2Response } from '@/utils/types'

export function useDoraV2(
  dateFrom?: string,
  dateTo?: string,
  cohort: string = 'all',
) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (cohort) params.set('cohort', cohort)
  return useQuery<DoraV2Response>({
    queryKey: ['dora-v2', dateFrom, dateTo, cohort],
    queryFn: () => apiFetch(`/dora/v2?${params}`),
    staleTime: 60_000,
  })
}
