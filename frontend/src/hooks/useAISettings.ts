import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type { AISettingsResponse, AISettingsUpdate, AIUsageSummary, AICostEstimate } from '@/utils/types'

export function useAISettings() {
  return useQuery<AISettingsResponse>({
    queryKey: ['ai-settings'],
    queryFn: () => apiFetch('/ai/settings'),
    staleTime: 30_000,
  })
}

export function useUpdateAISettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (updates: AISettingsUpdate) =>
      apiFetch<AISettingsResponse>('/ai/settings', {
        method: 'PATCH',
        body: JSON.stringify(updates),
      }),
    onSuccess: (data) => {
      qc.setQueryData(['ai-settings'], data)
      toast.success('AI settings updated')
    },
    onError: () => toast.error('Failed to update AI settings'),
  })
}

export function useAIUsage(days: number = 30) {
  return useQuery<AIUsageSummary>({
    queryKey: ['ai-usage', days],
    queryFn: () => apiFetch(`/ai/usage?days=${days}`),
    staleTime: 60_000,
  })
}

export function useAICostEstimate() {
  return useMutation({
    mutationFn: (params: {
      feature: string
      scope_type?: string
      scope_id?: string
      date_from?: string
      date_to?: string
    }) => {
      const qs = new URLSearchParams({ feature: params.feature })
      if (params.scope_type) qs.set('scope_type', params.scope_type)
      if (params.scope_id) qs.set('scope_id', params.scope_id)
      if (params.date_from) qs.set('date_from', params.date_from)
      if (params.date_to) qs.set('date_to', params.date_to)
      return apiFetch<AICostEstimate>(`/ai/estimate?${qs}`, { method: 'POST' })
    },
  })
}
