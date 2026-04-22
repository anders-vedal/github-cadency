import { useCallback, useMemo, useState } from 'react'
import { Info, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const STORAGE_KEY = 'devpulse_metrics_banner_dismissed_quarter'

function currentQuarterKey(): string {
  const now = new Date()
  const q = Math.floor(now.getUTCMonth() / 3) + 1
  return `${now.getUTCFullYear()}Q${q}`
}

function isDismissedForCurrentQuarter(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return localStorage.getItem(STORAGE_KEY) === currentQuarterKey()
  } catch {
    return false
  }
}

interface Props {
  /**
   * Override the default copy. Governance pages or AI-cohort pages may want a
   * tailored reminder.
   */
  message?: string
  /**
   * Narrow the banner to a subsection; full-bleed elsewhere.
   */
  className?: string
}

const DEFAULT_MESSAGE =
  'Metrics here are for team discussion, not performance review. Patterns matter more than absolute numbers. If a number looks concerning, look for context before action.'

/**
 * Global Phase 11 banner: renders once per quarter per user, dismissible.
 * Quarterly re-show matches the research-backed recommendation to periodically
 * re-ground teams on how metrics should be used.
 */
export default function MetricsUsageBanner({ message, className }: Props) {
  const [dismissed, setDismissed] = useState(() => isDismissedForCurrentQuarter())

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, currentQuarterKey())
    } catch {
      // no-op; if storage is unavailable the banner stays hidden for the session
    }
    setDismissed(true)
  }, [])

  const quarterLabel = useMemo(() => currentQuarterKey(), [])

  if (dismissed) return null

  return (
    <div
      role="note"
      className={cn(
        'flex items-start gap-3 rounded-md border bg-muted/40 p-3 text-xs',
        className,
      )}
    >
      <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
      <div className="flex-1 text-muted-foreground">{message ?? DEFAULT_MESSAGE}</div>
      <button
        type="button"
        aria-label={`Dismiss for ${quarterLabel}`}
        onClick={dismiss}
        className="text-muted-foreground/70 hover:text-foreground"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
