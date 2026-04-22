import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type {
  LinkQualitySummary,
  LinkageRateTrendResponse,
  RelinkResponse,
} from '@/utils/types'

export function useLinkageQuality(integrationId: number | undefined) {
  return useQuery<LinkQualitySummary>({
    queryKey: ['linkage-quality', integrationId],
    queryFn: () => apiFetch(`/integrations/${integrationId}/linkage-quality`),
    enabled: !!integrationId,
    staleTime: 60_000,
  })
}

export function useLinkageRateTrend(
  integrationId: number | undefined,
  weeks = 12,
) {
  return useQuery<LinkageRateTrendResponse>({
    queryKey: ['linkage-quality-trend', integrationId, weeks],
    queryFn: () =>
      apiFetch(
        `/integrations/${integrationId}/linkage-quality/trend?weeks=${weeks}`,
      ),
    enabled: !!integrationId,
    staleTime: 60_000,
  })
}

export function useRelinkIntegration() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (integrationId: number) =>
      apiFetch<RelinkResponse>(`/integrations/${integrationId}/relink`, { method: 'POST' }),
    onSuccess: (_data, integrationId) => {
      qc.invalidateQueries({ queryKey: ['linkage-quality', integrationId] })
      toast.success('Relink complete')
    },
    onError: () => toast.error('Failed to rerun linker'),
  })
}
