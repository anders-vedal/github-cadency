import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type { Repo, SyncEvent, SyncStartRequest, SyncStatusResponse } from '@/utils/types'

export function useRepos() {
  return useQuery<Repo[]>({
    queryKey: ['repos'],
    queryFn: () => apiFetch('/sync/repos'),
  })
}

export function useToggleTracking() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, isTracked }: { id: number; isTracked: boolean }) =>
      apiFetch<Repo>(`/sync/repos/${id}/track`, {
        method: 'PATCH',
        body: JSON.stringify({ is_tracked: isTracked }),
      }),
    onSuccess: (_data, { isTracked }) => {
      qc.invalidateQueries({ queryKey: ['repos'] })
      qc.invalidateQueries({ queryKey: ['sync-repos'] })
      toast.success(isTracked ? 'Repository tracking enabled' : 'Repository tracking disabled')
    },
    onError: () => toast.error('Failed to update tracking'),
  })
}

export function useSyncStatus() {
  return useQuery<SyncStatusResponse>({
    queryKey: ['sync-status'],
    queryFn: () => apiFetch('/sync/status'),
    refetchInterval: (query) => {
      return query.state.data?.active_sync ? 3_000 : 10_000
    },
  })
}

export function useSyncEvents() {
  return useQuery<SyncEvent[]>({
    queryKey: ['sync-events'],
    queryFn: () => apiFetch('/sync/events'),
    refetchInterval: 10_000,
  })
}

export function useStartSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (request: SyncStartRequest) =>
      apiFetch('/sync/start', {
        method: 'POST',
        body: JSON.stringify(request),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Sync started')
    },
    onError: (error: Error) => {
      if (error.message.includes('409')) {
        toast.error('A sync is already in progress')
      } else {
        toast.error('Failed to start sync')
      }
    },
  })
}

export function useResumeSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (eventId: number) =>
      apiFetch(`/sync/resume/${eventId}`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Sync resumed')
    },
    onError: () => toast.error('Failed to resume sync'),
  })
}
