import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type { AIAnalysis, AIAnalyzeRequest, OneOnOnePrepRequest, TeamHealthRequest } from '@/utils/types'

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
    mutationFn: ({ data, force }: { data: AIAnalyzeRequest; force?: boolean }) =>
      apiFetch<AIAnalysis>(`/ai/analyze${force ? '?force=true' : ''}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['ai-history'] })
      toast.success(result.reused ? 'Showing cached result' : 'Analysis complete')
    },
    onError: (err: Error) =>
      toast.error(err.message?.includes('429') ? 'Monthly AI budget exceeded' : 'Analysis failed'),
  })
}

export function useRunOneOnOnePrep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ data, force }: { data: OneOnOnePrepRequest; force?: boolean }) =>
      apiFetch<AIAnalysis>(`/ai/one-on-one-prep${force ? '?force=true' : ''}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['ai-history'] })
      toast.success(result.reused ? 'Showing cached result' : '1:1 prep brief generated')
    },
    onError: (err: Error) =>
      toast.error(err.message?.includes('429') ? 'Monthly AI budget exceeded' : 'Failed to generate 1:1 prep'),
  })
}

export function useRunTeamHealth() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ data, force }: { data: TeamHealthRequest; force?: boolean }) =>
      apiFetch<AIAnalysis>(`/ai/team-health${force ? '?force=true' : ''}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['ai-history'] })
      toast.success(result.reused ? 'Showing cached result' : 'Team health check generated')
    },
    onError: (err: Error) =>
      toast.error(err.message?.includes('429') ? 'Monthly AI budget exceeded' : 'Failed to generate team health check'),
  })
}
