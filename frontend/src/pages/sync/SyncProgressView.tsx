import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { AlertTriangle, Loader2 } from 'lucide-react'
import SyncErrorDetail from './SyncErrorDetail'
import SyncLogViewer from './SyncLogViewer'
import type { SyncEvent } from '@/utils/types'

interface SyncProgressViewProps {
  sync: SyncEvent
}

export default function SyncProgressView({ sync }: SyncProgressViewProps) {
  const [elapsed, setElapsed] = useState(0)
  const [showErrors, setShowErrors] = useState(false)
  const [showLog, setShowLog] = useState(false)

  useEffect(() => {
    if (!sync.started_at) return
    const start = new Date(sync.started_at).getTime()
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [sync.started_at])

  const completedCount = sync.repos_completed?.length ?? 0
  const failedCount = sync.repos_failed?.length ?? 0
  const totalRepos = sync.total_repos ?? 0
  const progressPct = totalRepos > 0 ? Math.round((completedCount / totalRepos) * 100) : 0

  const minutes = Math.floor(elapsed / 60)
  const seconds = elapsed % 60
  const elapsedStr = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`

  const errors = (sync.errors ?? []).filter(
    (e): e is NonNullable<typeof e> => e != null && typeof e === 'object'
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Sync In Progress
          <Badge variant="outline" className="ml-auto">{sync.sync_type}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Progress bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span>{completedCount} / {totalRepos} repos</span>
            <span className="text-muted-foreground">{progressPct}%</span>
          </div>
          <Progress value={progressPct} />
        </div>

        {/* Current repo */}
        {sync.current_repo_name && (
          <div className="flex items-center gap-2 text-sm">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
            </span>
            <span className="text-muted-foreground">Syncing:</span>
            <span className="font-medium">{sync.current_repo_name}</span>
          </div>
        )}

        {/* Counters */}
        <div className="flex gap-6 text-sm">
          <div>
            <span className="text-muted-foreground">PRs: </span>
            <span className="font-medium">{sync.prs_upserted ?? 0}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Issues: </span>
            <span className="font-medium">{sync.issues_upserted ?? 0}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Elapsed: </span>
            <span className="font-medium">{elapsedStr}</span>
          </div>
          {(sync.rate_limit_wait_s ?? 0) > 0 && (
            <div className="text-amber-600">
              <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
              Rate limited ({sync.rate_limit_wait_s}s wait)
            </div>
          )}
        </div>

        {/* Error count */}
        {failedCount > 0 && (
          <button
            onClick={() => setShowErrors(!showErrors)}
            className="flex items-center gap-2 text-sm text-red-600 hover:underline"
          >
            <Badge variant="destructive">{failedCount}</Badge>
            repos failed so far
          </button>
        )}
        {showErrors && (
          <>
            {errors.length > 0 && <SyncErrorDetail errors={errors} />}
            {(sync.repos_failed ?? []).length > 0 && (
              <div className="space-y-1">
                {(sync.repos_failed ?? []).map((f, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-md border px-3 py-2 text-xs">
                    <Badge variant="destructive">failed</Badge>
                    <span className="font-medium">{f.repo_name}</span>
                    <span className="text-muted-foreground truncate">{f.error}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Log toggle */}
        <button
          onClick={() => setShowLog(!showLog)}
          className="text-xs text-muted-foreground hover:underline"
        >
          {showLog ? 'Hide' : 'Show'} sync log ({(sync.log_summary ?? []).length} entries)
        </button>
        {showLog && <SyncLogViewer logs={sync.log_summary ?? []} />}
      </CardContent>
    </Card>
  )
}
