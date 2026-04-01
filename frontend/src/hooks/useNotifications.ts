import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'

export interface Notification {
  id: number
  alert_type: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  body: string | null
  entity_type: string | null
  entity_id: number | null
  link_path: string | null
  developer_id: number | null
  metadata: Record<string, unknown> | null
  is_read: boolean
  is_dismissed: boolean
  created_at: string
  updated_at: string
}

export interface NotificationsListResponse {
  notifications: Notification[]
  unread_count: number
  counts_by_severity: Record<string, number>
  total: number
}

export interface AlertTypeMeta {
  key: string
  label: string
  description: string
  enabled: boolean
  thresholds: ThresholdConfig[]
}

export interface ThresholdConfig {
  field: string
  label: string
  value: number
  unit: string
  min?: number
  max?: number
}

export interface NotificationConfigResponse {
  alert_stale_pr_enabled: boolean
  alert_review_bottleneck_enabled: boolean
  alert_underutilized_enabled: boolean
  alert_uneven_assignment_enabled: boolean
  alert_merged_without_approval_enabled: boolean
  alert_revert_spike_enabled: boolean
  alert_high_risk_pr_enabled: boolean
  alert_bus_factor_enabled: boolean
  alert_declining_trends_enabled: boolean
  alert_issue_linkage_enabled: boolean
  alert_ai_budget_enabled: boolean
  alert_sync_failure_enabled: boolean
  alert_unassigned_roles_enabled: boolean
  alert_missing_config_enabled: boolean
  stale_pr_threshold_hours: number
  review_bottleneck_multiplier: number
  revert_spike_threshold_pct: number
  high_risk_pr_min_level: string
  issue_linkage_threshold_pct: number
  declining_trend_pr_drop_pct: number
  declining_trend_quality_drop_pct: number
  exclude_contribution_categories: string[] | null
  evaluation_interval_minutes: number
  alert_types: AlertTypeMeta[]
  updated_at: string
  updated_by: string | null
}

// ── Queries ──

export function useNotifications(options?: {
  severity?: string
  alertType?: string
  includeDismissed?: boolean
  enabled?: boolean
}) {
  const params = new URLSearchParams()
  if (options?.severity) params.set('severity', options.severity)
  if (options?.alertType) params.set('alert_type', options.alertType)
  if (options?.includeDismissed) params.set('include_dismissed', 'true')
  const qs = params.toString()
  return useQuery<NotificationsListResponse>({
    queryKey: ['notifications', options?.severity, options?.alertType, options?.includeDismissed],
    queryFn: () => apiFetch(`/notifications${qs ? `?${qs}` : ''}`),
    staleTime: 30_000,
    enabled: options?.enabled !== false,
  })
}

export function useNotificationConfig() {
  return useQuery<NotificationConfigResponse>({
    queryKey: ['notification-config'],
    queryFn: () => apiFetch('/notifications/config'),
    staleTime: 60_000,
  })
}

// ── Mutations ──

export function useMarkRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

export function useMarkAllRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiFetch('/notifications/read-all', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

export function useDismissNotification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dismissType, durationDays }: {
      id: number
      dismissType: 'permanent' | 'temporary'
      durationDays?: number
    }) =>
      apiFetch(`/notifications/${id}/dismiss`, {
        method: 'POST',
        body: JSON.stringify({
          dismiss_type: dismissType,
          duration_days: durationDays,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

export function useDismissAlertType() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ alertType, dismissType, durationDays }: {
      alertType: string
      dismissType: 'permanent' | 'temporary'
      durationDays?: number
    }) =>
      apiFetch('/notifications/dismiss-type', {
        method: 'POST',
        body: JSON.stringify({
          alert_type: alertType,
          dismiss_type: dismissType,
          duration_days: durationDays,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

export function useUpdateNotificationConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (updates: Record<string, unknown>) =>
      apiFetch('/notifications/config', {
        method: 'PATCH',
        body: JSON.stringify(updates),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notification-config'] }),
  })
}

export function useEvaluateNotifications() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiFetch('/notifications/evaluate', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}
