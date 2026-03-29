import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type { PreflightResponse, Repo, SyncEvent, SyncStartRequest, SyncStatusResponse } from '@/utils/types'

/**
 * Extract a human-readable detail from an apiFetch error.
 * apiFetch throws `new Error("STATUS: BODY")`, so we try to parse the JSON detail.
 */
function extractErrorDetail(error: Error): string {
  const msg = error.message
  // Try to extract JSON detail from "STATUS: {\"detail\": \"...\"}"
  const colonIdx = msg.indexOf(': ')
  if (colonIdx > 0) {
    const body = msg.slice(colonIdx + 2)
    try {
      const parsed = JSON.parse(body)
      if (parsed.detail) return parsed.detail
    } catch {
      // Not JSON, return the raw body
      if (body.length > 0 && body.length < 300) return body
    }
  }
  return msg
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
        toast.error(`Failed to start sync: ${extractErrorDetail(error)}`)
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
      if (error.message.includes('409')) {
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
