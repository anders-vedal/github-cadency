import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import SyncErrorDetail from './SyncErrorDetail'
import SyncLogViewer from './SyncLogViewer'
import type { SyncEvent, SyncError } from '@/utils/types'

interface SyncHistoryTableProps {
  events: SyncEvent[]
}

function statusVariant(status: string | null) {
  switch (status) {
    case 'completed': return 'default' as const
    case 'started': return 'secondary' as const
    case 'failed': return 'destructive' as const
    case 'completed_with_errors': return 'outline' as const
    default: return 'outline' as const
  }
}

function statusLabel(status: string | null): string {
  if (status === 'completed_with_errors') return 'partial'
  return status ?? '-'
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '-'
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

export default function SyncHistoryTable({ events }: SyncHistoryTableProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null)

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead>PRs</TableHead>
            <TableHead>Issues</TableHead>
            <TableHead>Errors</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => {
            const isActive = event.status === 'started'
            const isExpanded = expandedId === event.id
            const errorCount = (event.errors ?? []).length
            const failedCount = (event.repos_failed ?? []).length
            const completedCount = event.repos_completed?.length ?? event.repos_synced ?? 0
            const totalRepos = event.total_repos

            return (
              <TableRow
                key={event.id}
                className={cn(
                  'cursor-pointer',
                  isActive && 'border-l-4 border-l-primary',
                )}
                onClick={() => setExpandedId(isExpanded ? null : event.id)}
              >
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <Badge variant="outline">{event.sync_type}</Badge>
                    {event.resumed_from_id && (
                      <span className="text-xs text-muted-foreground" title={`Resumed from #${event.resumed_from_id}`}>
                        &#x21bb;
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    {isActive && (
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
                      </span>
                    )}
                    <Badge variant={statusVariant(event.status)}>
                      {statusLabel(event.status)}
                    </Badge>
                  </div>
                </TableCell>
                <TableCell>
                  {totalRepos != null
                    ? `${completedCount}/${totalRepos}`
                    : event.repos_synced ?? '-'}
                </TableCell>
                <TableCell>{event.prs_upserted ?? '-'}</TableCell>
                <TableCell>{event.issues_upserted ?? '-'}</TableCell>
                <TableCell>
                  {errorCount > 0 || failedCount > 0 ? (
                    <Badge variant="destructive">
                      {errorCount + failedCount}
                    </Badge>
                  ) : (
                    '-'
                  )}
                </TableCell>
                <TableCell>{formatDuration(event.duration_s)}</TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {timeAgo(event.started_at)}
                </TableCell>
              </TableRow>
            )
          })}
          {events.length === 0 && (
            <TableRow>
              <TableCell colSpan={8} className="text-center text-muted-foreground">
                No sync events yet. Trigger a sync to get started.
              </TableCell>
            </TableRow>
          )}

          {/* Expanded detail row */}
          {expandedId != null && (() => {
            const event = events.find((e) => e.id === expandedId)
            if (!event) return null
            const errors = (event.errors ?? []).filter(
              (e): e is SyncError => e != null && typeof e === 'object' && 'step' in e
            )
            const logs = event.log_summary ?? []
            return (
              <TableRow key={`${expandedId}-detail`}>
                <TableCell colSpan={8} className="bg-muted/30">
                  <div className="space-y-3 py-2">
                    {errors.length > 0 && (
                      <div>
                        <div className="mb-1 text-xs font-medium text-muted-foreground">Errors</div>
                        <SyncErrorDetail errors={errors} />
                      </div>
                    )}
                    {(event.repos_failed ?? []).length > 0 && (
                      <div>
                        <div className="mb-1 text-xs font-medium text-muted-foreground">Failed Repos</div>
                        <div className="space-y-1">
                          {(event.repos_failed ?? []).map((f, i) => (
                            <div key={i} className="flex items-center gap-2 text-xs">
                              <Badge variant="destructive" className="text-xs">failed</Badge>
                              <span className="font-medium">{f.repo_name}</span>
                              <span className="text-muted-foreground truncate">{f.error}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {logs.length > 0 && (
                      <div>
                        <div className="mb-1 text-xs font-medium text-muted-foreground">Sync Log</div>
                        <SyncLogViewer logs={logs} />
                      </div>
                    )}
                    {errors.length === 0 && logs.length === 0 && (event.repos_failed ?? []).length === 0 && (
                      <p className="text-xs text-muted-foreground">No detailed info for this sync event.</p>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            )
          })()}
        </TableBody>
      </Table>
    </div>
  )
}
