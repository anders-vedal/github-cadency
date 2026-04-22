import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiError, apiFetch } from '@/utils/api'
import type { PreflightResponse, Repo, RepoDataDeleteResponse, SyncEvent, SyncScheduleConfig, SyncStartRequest, SyncStatusResponse } from '@/utils/types'

/** Extract a human-readable detail from an apiFetch error. */
function extractErrorDetail(error: Error): string {
  if (error instanceof ApiError) {
    const d = error.detail
    return typeof d === 'string' ? d : d?.message ?? error.message
  }
  return error.message
}

export function usePreflight() {
  return useQuery<PreflightResponse>({
    queryKey: ['sync-preflight'],
    queryFn: () => apiFetch('/sync/preflight'),
    staleTime: 60_000,
  })
}

export function useRepos() {
  return useQuery<Repo[]>({
    queryKey: ['repos'],
    queryFn: () => apiFetch('/sync/repos'),
  })
}

export function useDiscoverRepos() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiFetch<Repo[]>('/sync/discover-repos', { method: 'POST' }),
    onSuccess: (repos) => {
      qc.setQueryData(['repos'], repos)
      toast.success(`Discovered ${repos.length} repositories`)
    },
    onError: (error: Error) => {
      toast.error(extractErrorDetail(error))
    },
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
      toast.success(isTracked ? 'Repository tracking enabled' : 'Repository tracking disabled')
    },
    onError: () => toast.error('Failed to update tracking'),
  })
}

export function useDeleteRepoData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<RepoDataDeleteResponse>(`/sync/repos/${id}/data`, { method: 'DELETE' }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['repos'] })
      qc.invalidateQueries({ queryKey: ['repos-summary'] })
      const total = Object.values(result.deleted).reduce((a, b) => a + b, 0)
      toast.success(
        total > 0
          ? `Deleted ${total.toLocaleString()} records for ${result.full_name ?? 'repo'}`
          : `No synced data to delete for ${result.full_name ?? 'repo'}`,
      )
    },
    onError: (error: Error) => toast.error(`Failed to delete data: ${extractErrorDetail(error)}`),
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
      apiFetch<SyncEvent>('/sync/start', {
        method: 'POST',
        body: JSON.stringify(request),
      }),
    onSuccess: (syncEvent: SyncEvent) => {
      // Set the returned sync event as active_sync immediately so the UI
      // switches to the progress view without waiting for the next poll.
      qc.setQueryData<SyncStatusResponse>(['sync-status'], (old) =>
        old ? { ...old, active_sync: syncEvent } : undefined,
      )
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Sync started')
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.error('A sync is already in progress')
      } else {
        toast.error(`Failed to start sync: ${extractErrorDetail(error)}`)
      }
    },
  })
}

export function useResumeSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (eventId: number) =>
      apiFetch<SyncEvent>(`/sync/resume/${eventId}`, { method: 'POST' }),
    onSuccess: (syncEvent: SyncEvent) => {
      qc.setQueryData<SyncStatusResponse>(['sync-status'], (old) =>
        old ? { ...old, active_sync: syncEvent } : undefined,
      )
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Sync resumed')
    },
    onError: (error: Error) => toast.error(`Failed to resume sync: ${extractErrorDetail(error)}`),
  })
}

export function useCancelSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiFetch('/sync/cancel', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Cancel requested — sync will stop after current step')
    },
    onError: (error: Error) => toast.error(`Failed to cancel sync: ${extractErrorDetail(error)}`),
  })
}

export function useForceStopSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiFetch('/sync/force-stop', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Sync force-stopped')
    },
    onError: (error: Error) => toast.error(`Failed to force-stop sync: ${extractErrorDetail(error)}`),
  })
}

export function useSyncContributors() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiFetch('/sync/contributors', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      qc.invalidateQueries({ queryKey: ['sync-events'] })
      toast.success('Contributor sync started')
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.error('A sync is already in progress')
      } else {
        toast.error(`Failed to sync contributors: ${extractErrorDetail(error)}`)
      }
    },
  })
}

export function useSyncEvent(eventId: number | undefined) {
  return useQuery<SyncEvent>({
    queryKey: ['sync-event', eventId],
    queryFn: () => apiFetch(`/sync/events/${eventId}`),
    enabled: !!eventId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'started' ? 3_000 : false
    },
  })
}

export function useSyncSchedule() {
  return useQuery<SyncScheduleConfig>({
    queryKey: ['sync-schedule'],
    queryFn: () => apiFetch('/sync/schedule'),
    staleTime: 60_000,
  })
}

export function useUpdateSyncSchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<SyncScheduleConfig>) =>
      apiFetch<SyncScheduleConfig>('/sync/schedule', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(['sync-schedule'], updated)
      qc.invalidateQueries({ queryKey: ['sync-status'] })
      toast.success('Sync schedule updated')
    },
    onError: (error: Error) => toast.error(`Failed to update schedule: ${extractErrorDetail(error)}`),
  })
}
