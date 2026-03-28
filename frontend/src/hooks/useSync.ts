import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type { Repo, SyncEvent } from '@/utils/types'

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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['repos'] }),
  })
}

export function useSyncEvents() {
  return useQuery<SyncEvent[]>({
    queryKey: ['sync-events'],
    queryFn: () => apiFetch('/sync/events'),
    refetchInterval: 10_000,
  })
}

export function useTriggerSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (type: 'full' | 'incremental') =>
      apiFetch(`/sync/${type}`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync-events'] }),
  })
}
