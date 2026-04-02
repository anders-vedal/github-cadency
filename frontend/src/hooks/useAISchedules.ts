import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type { AISchedule, AIScheduleCreate, AIScheduleUpdate, AIAnalysis } from '@/utils/types'

export function useAISchedules() {
  return useQuery<AISchedule[]>({
    queryKey: ['ai-schedules'],
    queryFn: () => apiFetch('/ai/schedules'),
    staleTime: 30_000,
  })
}

export function useCreateAISchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AIScheduleCreate) =>
      apiFetch<AISchedule>('/ai/schedules', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-schedules'] })
      toast.success('Schedule created')
    },
    onError: () => toast.error('Failed to create schedule'),
  })
}

export function useUpdateAISchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AIScheduleUpdate }) =>
      apiFetch<AISchedule>(`/ai/schedules/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-schedules'] })
      toast.success('Schedule updated')
    },
    onError: () => toast.error('Failed to update schedule'),
  })
}

export function useDeleteAISchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/ai/schedules/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-schedules'] })
      toast.success('Schedule deleted')
    },
    onError: () => toast.error('Failed to delete schedule'),
  })
}

export function useRunAISchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<AIAnalysis>(`/ai/schedules/${id}/run`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-schedules'] })
      qc.invalidateQueries({ queryKey: ['ai-history'] })
      toast.success('Scheduled analysis completed')
    },
    onError: () => toast.error('Failed to run scheduled analysis'),
  })
}
