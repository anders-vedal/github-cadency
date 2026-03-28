import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type { AIAnalysis, AIAnalyzeRequest } from '@/utils/types'

export function useAIHistory() {
  return useQuery<AIAnalysis[]>({
    queryKey: ['ai-history'],
    queryFn: () => apiFetch('/ai/history'),
  })
}

export function useAIAnalysis(id: number) {
  return useQuery<AIAnalysis>({
    queryKey: ['ai-analysis', id],
    queryFn: () => apiFetch(`/ai/history/${id}`),
    enabled: !!id,
  })
}

export function useRunAnalysis() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AIAnalyzeRequest) =>
      apiFetch<AIAnalysis>('/ai/analyze', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-history'] }),
  })
}
