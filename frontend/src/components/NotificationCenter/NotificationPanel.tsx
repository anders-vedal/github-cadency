import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  useNotifications,
  useMarkRead,
  useMarkAllRead,
  useDismissNotification,
  useDismissAlertType,
  type Notification,
} from '@/hooks/useNotifications'
import { timeAgo } from '@/utils/format'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

type SeverityFilter = 'all' | 'critical' | 'warning' | 'info'

const severityStyles: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-blue-500',
}

const severityTextStyles: Record<string, string> = {
  critical: 'text-red-600 dark:text-red-400',
  warning: 'text-amber-600 dark:text-amber-400',
  info: 'text-blue-600 dark:text-blue-400',
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  stale_pr: 'Stale PRs',
  review_bottleneck: 'Review Bottlenecks',
  underutilized: 'Underutilized',
  uneven_assignment: 'Uneven Assignment',
  merged_without_approval: 'Merged Without Approval',
  revert_spike: 'Revert Spike',
  high_risk_pr: 'High-Risk PRs',
  bus_factor: 'Bus Factor',
  team_silo: 'Team Silos',
  isolated_developer: 'Isolated Developers',
  declining_trend: 'Declining Trends',
  issue_linkage: 'Issue Linkage',
  ai_budget: 'AI Budget',
  sync_failure: 'Sync Failure',
  unassigned_roles: 'Unassigned Roles',
  missing_config: 'Missing Config',
}

export default function NotificationPanel({ onClose }: { onClose: () => void }) {
  const [filter, setFilter] = useState<SeverityFilter>('all')
  const { data, isLoading } = useNotifications()
  const markRead = useMarkRead()
  const markAllRead = useMarkAllRead()
  const dismissNotification = useDismissNotification()
  const dismissType = useDismissAlertType()
  const navigate = useNavigate()
  const [dismissMenuId, setDismissMenuId] = useState<number | null>(null)

  const notifications = data?.notifications ?? []
  const counts = data?.counts_by_severity ?? {}

  const filtered = filter === 'all'
    ? notifications
    : notifications.filter((n) => n.severity === filter)

  // Group by severity when showing all
  const grouped = filter === 'all'
    ? (['critical', 'warning', 'info'] as const).map((sev) => ({
        severity: sev,
        items: filtered.filter((n) => n.severity === sev),
      })).filter((g) => g.items.length > 0)
    : [{ severity: filter, items: filtered }]

  function handleClick(n: Notification) {
    if (!n.is_read) {
      markRead.mutate(n.id)
    }
    if (n.link_path) {
      if (n.link_path.startsWith('http')) {
        window.open(n.link_path, '_blank')
      } else {
        navigate(n.link_path)
      }
    }
    onClose()
  }

  function handleDismiss(n: Notification, type: 'permanent' | 'temporary', days?: number) {
    dismissNotification.mutate({ id: n.id, dismissType: type, durationDays: days })
    setDismissMenuId(null)
  }

  function handleDismissType(alertType: string, type: 'permanent' | 'temporary', days?: number) {
    dismissType.mutate({ alertType, dismissType: type, durationDays: days })
    setDismissMenuId(null)
  }

  return (
    <div
      className="absolute right-0 top-full mt-2 w-[380px] rounded-lg border bg-popover shadow-lg z-50"
      role="dialog"
      aria-label="Notifications"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold">
          Notifications
          {data?.total ? (
            <span className="ml-1.5 text-muted-foreground font-normal">({data.total})</span>
          ) : null}
        </h3>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-muted-foreground"
          onClick={() => markAllRead.mutate()}
          disabled={!data?.unread_count}
        >
          Mark all read
        </Button>
      </div>

      {/* Severity tabs */}
      <div className="flex gap-1 border-b px-4 py-2" role="tablist">
        {(['all', 'critical', 'warning', 'info'] as const).map((tab) => {
          const count = tab === 'all' ? data?.total ?? 0 : counts[tab] ?? 0
          return (
            <button
              key={tab}
              role="tab"
              aria-selected={filter === tab}
              onClick={() => setFilter(tab)}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                filter === tab
                  ? 'bg-muted text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab === 'all' ? 'All' : tab.charAt(0).toUpperCase() + tab.slice(1)}
              {count > 0 && (
                <span className={cn('ml-1', tab !== 'all' && severityTextStyles[tab])}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Notification list */}
      <div className="max-h-[400px] overflow-y-auto">
        {isLoading ? (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-600">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </div>
            <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">All clear</p>
            <p className="text-xs text-muted-foreground">No active alerts</p>
          </div>
        ) : (
          grouped.map((group) => (
            <div key={group.severity}>
              {filter === 'all' && (
                <div className="sticky top-0 bg-popover/95 backdrop-blur px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.severity} ({group.items.length})
                </div>
              )}
              {group.items.map((n) => (
                <div
                  key={n.id}
                  className={cn(
                    'relative flex gap-3 px-4 py-3 transition-colors hover:bg-muted/50 cursor-pointer border-b border-border/50',
                    !n.is_read && 'border-l-2 border-l-blue-500'
                  )}
                >
                  {/* Severity dot */}
                  <div className="mt-1.5 shrink-0">
                    <div className={cn('h-2 w-2 rounded-full', severityStyles[n.severity])} />
                  </div>

                  {/* Content — clickable */}
                  <div className="min-w-0 flex-1" onClick={() => handleClick(n)}>
                    <p className={cn(
                      'text-sm leading-tight line-clamp-2',
                      n.is_read ? 'text-muted-foreground' : 'font-medium text-foreground'
                    )}>
                      {n.title}
                    </p>
                    {n.body && (
                      <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">{n.body}</p>
                    )}
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</span>
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {ALERT_TYPE_LABELS[n.alert_type] ?? n.alert_type}
                      </Badge>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-start gap-1">
                    {n.link_path && (
                      <button
                        onClick={() => handleClick(n)}
                        className="rounded p-1 text-muted-foreground hover:text-foreground"
                        aria-label="Go to"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
                        </svg>
                      </button>
                    )}
                    <div className="relative">
                      <button
                        onClick={(e) => { e.stopPropagation(); setDismissMenuId(dismissMenuId === n.id ? null : n.id) }}
                        className="rounded p-1 text-muted-foreground hover:text-foreground"
                        aria-label="Dismiss"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M18 6 6 18" /><path d="m6 6 12 12" />
                        </svg>
                      </button>
                      {dismissMenuId === n.id && (
                        <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border bg-popover p-1 shadow-md">
                          <button onClick={() => handleDismiss(n, 'permanent')} className="block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted">
                            Dismiss this alert
                          </button>
                          <button onClick={() => handleDismiss(n, 'temporary', 7)} className="block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted">
                            Dismiss for 7 days
                          </button>
                          <button onClick={() => handleDismiss(n, 'temporary', 30)} className="block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted">
                            Dismiss for 30 days
                          </button>
                          <div className="my-1 border-t" />
                          <button onClick={() => handleDismissType(n.alert_type, 'permanent')} className="block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted">
                            Mute all {ALERT_TYPE_LABELS[n.alert_type] ?? n.alert_type}
                          </button>
                          <button onClick={() => handleDismissType(n.alert_type, 'temporary', 7)} className="block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted">
                            Mute {ALERT_TYPE_LABELS[n.alert_type] ?? n.alert_type} for 7 days
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-center border-t px-4 py-2">
        <Link
          to="/admin/notifications"
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Notification Settings
        </Link>
      </div>
    </div>
  )
}
