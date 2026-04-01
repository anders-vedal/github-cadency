import { useNotifications } from '@/hooks/useNotifications'

export default function AlertSummaryBar() {
  const { data } = useNotifications()
  const counts = data?.counts_by_severity ?? {}
  const critical = counts.critical ?? 0
  const warning = counts.warning ?? 0
  const info = counts.info ?? 0
  const total = critical + warning + info

  if (total === 0) {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm font-medium text-emerald-700 dark:text-emerald-400">
        All clear — no issues detected.
      </div>
    )
  }

  const parts: string[] = []
  if (critical > 0) parts.push(`${critical} critical`)
  if (warning > 0) parts.push(`${warning} warning${warning !== 1 ? 's' : ''}`)
  if (info > 0) parts.push(`${info} info`)

  return (
    <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/30 px-4 py-3 text-sm">
      <div className="flex items-center gap-1.5">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground">
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        <span>
          {critical > 0 && <span className="font-medium text-red-600 dark:text-red-400">{critical} critical</span>}
          {critical > 0 && (warning > 0 || info > 0) && <span className="text-muted-foreground">, </span>}
          {warning > 0 && <span className="font-medium text-amber-600 dark:text-amber-400">{warning} warning{warning !== 1 ? 's' : ''}</span>}
          {warning > 0 && info > 0 && <span className="text-muted-foreground">, </span>}
          {info > 0 && <span className="font-medium text-blue-600 dark:text-blue-400">{info} info</span>}
        </span>
      </div>
      <span className="text-xs text-muted-foreground">
        View in notification center
      </span>
    </div>
  )
}
