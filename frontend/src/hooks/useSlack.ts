import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'
import type {
  SlackConfigResponse,
  SlackConfigUpdate,
  SlackUserSettingsResponse,
  SlackUserSettingsUpdate,
  NotificationHistoryResponse,
  SlackTestResponse,
} from '@/utils/types'

// --- Admin: Global config ---

export function useSlackConfig() {
  return useQuery<SlackConfigResponse>({
    queryKey: ['slack-config'],
    queryFn: () => apiFetch('/slack/config'),
    staleTime: 30_000,
  })
}

export function useUpdateSlackConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (updates: SlackConfigUpdate) =>
      apiFetch<SlackConfigResponse>('/slack/config', {
        method: 'PATCH',
        body: JSON.stringify(updates),
      }),
    onSuccess: (data) => {
      qc.setQueryData(['slack-config'], data)
      toast.success('Slack settings updated')
    },
    onError: () => toast.error('Failed to update Slack settings'),
  })
}

export function useSlackTest() {
  return useMutation({
    mutationFn: () =>
      apiFetch<SlackTestResponse>('/slack/test', { method: 'POST' }),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(data.message)
      } else {
        toast.error(data.message)
      }
    },
    onError: () => toast.error('Failed to send test message'),
  })
}

export function useNotificationHistory(limit = 50, offset = 0) {
  return useQuery<NotificationHistoryResponse>({
    queryKey: ['notification-history', limit, offset],
    queryFn: () => apiFetch(`/slack/notifications?limit=${limit}&offset=${offset}`),
    staleTime: 30_000,
  })
}

// --- Per-user: Slack notification preferences ---

export function useSlackUserSettings() {
  return useQuery<SlackUserSettingsResponse>({
    queryKey: ['slack-user-settings'],
    queryFn: () => apiFetch('/slack/user-settings'),
    staleTime: 30_000,
  })
}

export function useUpdateSlackUserSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (updates: SlackUserSettingsUpdate) =>
      apiFetch<SlackUserSettingsResponse>('/slack/user-settings', {
        method: 'PATCH',
        body: JSON.stringify(updates),
      }),
    onSuccess: (data) => {
      qc.setQueryData(['slack-user-settings'], data)
      toast.success('Notification preferences updated')
    },
    onError: () => toast.error('Failed to update preferences'),
  })
}
