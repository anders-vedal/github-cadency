import { Badge } from '@/components/ui/badge'
import type { SyncError } from '@/utils/types'

interface SyncErrorDetailProps {
  errors: SyncError[]
}

export default function SyncErrorDetail({ errors }: SyncErrorDetailProps) {
  if (errors.length === 0) return null

  // Group errors by repo
  const grouped = new Map<string, SyncError[]>()
  for (const err of errors) {
    const key = err.repo ?? 'General'
    const list = grouped.get(key) || []
    list.push(err)
    grouped.set(key, list)
  }

  return (
    <div className="space-y-3">
      {Array.from(grouped.entries()).map(([repo, repoErrors]) => (
        <div key={repo} className="space-y-1.5">
          <div className="text-sm font-medium">{repo}</div>
          {repoErrors.map((err, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs"
            >
              <Badge
                variant={err.retryable ? 'outline' : 'destructive'}
                className={err.retryable ? 'border-amber-500/50 text-amber-600' : ''}
              >
                {err.retryable ? 'Retryable' : 'Permanent'}
              </Badge>
              <span className="font-medium">{err.step}</span>
              {err.status_code && (
                <span className="text-muted-foreground">HTTP {err.status_code}</span>
              )}
              <span className="text-muted-foreground">{err.error_type}</span>
              <span className="flex-1 truncate text-muted-foreground">{err.message}</span>
              {err.attempt > 1 && (
                <span className="text-muted-foreground">attempt {err.attempt}</span>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
