import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { WorkloadAlert, DeveloperWorkload } from '@/utils/types'

// --- Alert severity mapping ---

export type Severity = 'critical' | 'warning' | 'info'

export const alertSeverityMap: Record<WorkloadAlert['type'], Severity> = {
  stale_prs: 'critical',
  review_bottleneck: 'warning',
  uneven_assignment: 'warning',
  underutilized: 'info',
  merged_without_approval: 'warning',
  revert_spike: 'critical',
}

export const severityStyles: Record<Severity, string> = {
  critical: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
}

export const severityLabels: Record<Severity, string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
}

export const workloadStyles: Record<DeveloperWorkload['workload_score'], string> = {
  low: 'bg-blue-500/10 text-blue-600',
  balanced: 'bg-emerald-500/10 text-emerald-600',
  high: 'bg-amber-500/10 text-amber-600',
  overloaded: 'bg-red-500/10 text-red-600',
}

export default function AlertStrip({ alerts, emptyMessage = 'All clear — no issues detected.' }: {
  alerts: WorkloadAlert[]
  emptyMessage?: string
}) {
  if (alerts.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm font-medium text-emerald-700 dark:text-emerald-400">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const severity = alertSeverityMap[alert.type]
        return (
          <div
            key={`${alert.type}-${alert.developer_id}-${i}`}
            className={cn(
              'flex items-center gap-3 rounded-lg border px-4 py-3 text-sm',
              severityStyles[severity]
            )}
          >
            <Badge
              variant="outline"
              className={cn('shrink-0 text-[10px] uppercase', severityStyles[severity])}
            >
              {severityLabels[severity]}
            </Badge>
            <span className="flex-1">{alert.message}</span>
            {alert.developer_id && (
              <Link
                to={`/team/${alert.developer_id}`}
                className="shrink-0 text-xs font-medium underline underline-offset-2"
              >
                View
              </Link>
            )}
          </div>
        )
      })}
    </div>
  )
}
