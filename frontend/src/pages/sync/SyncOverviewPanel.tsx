import { Card, CardContent } from '@/components/ui/card'
import { Database, Clock, RefreshCw, BarChart3 } from 'lucide-react'
import type { SyncStatusResponse } from '@/utils/types'

interface SyncOverviewPanelProps {
  status: SyncStatusResponse
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '-'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${minutes}m ${secs}s`
}

export default function SyncOverviewPanel({ status }: SyncOverviewPanelProps) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card size="sm">
        <CardContent className="flex items-center gap-3">
          <Database className="h-4 w-4 text-muted-foreground" />
          <div>
            <div className="text-lg font-bold">
              {status.tracked_repos_count}/{status.total_repos_count}
            </div>
            <div className="text-xs text-muted-foreground">Tracked Repos</div>
          </div>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardContent className="flex items-center gap-3">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <div>
            <div className="text-lg font-bold">
              {timeAgo(status.last_successful_sync)}
            </div>
            <div className="text-xs text-muted-foreground">Last Sync</div>
          </div>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardContent className="flex items-center gap-3">
          <RefreshCw className="h-4 w-4 text-muted-foreground" />
          <div>
            <div className="text-lg font-bold">
              {formatDuration(status.last_sync_duration_s)}
            </div>
            <div className="text-xs text-muted-foreground">Last Duration</div>
          </div>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardContent className="flex items-center gap-3">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          <div>
            <div className="text-lg font-bold">
              {status.last_completed?.status === 'completed'
                ? 'Healthy'
                : status.last_completed?.status === 'completed_with_errors'
                  ? 'Partial'
                  : status.last_completed?.status === 'failed'
                    ? 'Failed'
                    : '-'}
            </div>
            <div className="text-xs text-muted-foreground">Last Status</div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
