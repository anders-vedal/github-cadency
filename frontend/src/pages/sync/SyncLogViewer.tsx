import { cn } from '@/lib/utils'
import type { SyncLogEntry } from '@/utils/types'

interface SyncLogViewerProps {
  logs: SyncLogEntry[]
}

const levelColors: Record<string, string> = {
  info: 'text-muted-foreground',
  warn: 'text-amber-600',
  error: 'text-red-600',
}

export default function SyncLogViewer({ logs }: SyncLogViewerProps) {
  if (logs.length === 0) {
    return <p className="text-sm text-muted-foreground">No log entries.</p>
  }

  return (
    <div className="max-h-64 overflow-y-auto rounded-md border bg-muted/30 p-3">
      <div className="space-y-0.5 font-mono text-xs">
        {logs.map((entry, i) => (
          <div key={i} className={cn('flex gap-2', levelColors[entry.level] || 'text-muted-foreground')}>
            <span className="shrink-0 text-muted-foreground/60">{entry.ts}</span>
            <span className="shrink-0 uppercase w-12">{entry.level}</span>
            {entry.repo && (
              <span className="shrink-0 font-medium">[{entry.repo}]</span>
            )}
            <span className="break-all">{entry.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
