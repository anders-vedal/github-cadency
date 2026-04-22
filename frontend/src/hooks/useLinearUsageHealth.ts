import { useQuery } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/utils/api'
import type { LinearUsageHealthResponse } from '@/utils/types'

export function useLinearUsageHealth(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<LinearUsageHealthResponse, ApiError>({
    queryKey: ['linear-usage-health', dateFrom, dateTo],
    queryFn: () => apiFetch(`/linear/usage-health?${params}`),
    staleTime: 5 * 60_000,
    retry: (failureCount, error) => {
      // Don't retry on 409 (Linear not primary) — that's an expected config state
      if (error instanceof ApiError && error.status === 409) return false
      return failureCount < 1
    },
  })
}
