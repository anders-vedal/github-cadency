import { useSyncEvents, useTriggerSync } from '@/hooks/useSync'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

function statusColor(status: string | null) {
  switch (status) {
    case 'completed': return 'default'
    case 'started': return 'secondary'
    case 'failed': return 'destructive'
    default: return 'outline'
  }
}

export default function SyncStatus() {
  const { data: events, isLoading } = useSyncEvents()
  const triggerSync = useTriggerSync()

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Sync Status</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={triggerSync.isPending}
            onClick={() => triggerSync.mutate('incremental')}
          >
            Incremental Sync
          </Button>
          <Button
            disabled={triggerSync.isPending}
            onClick={() => triggerSync.mutate('full')}
          >
            Full Sync
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading events...</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Repos</TableHead>
                <TableHead>PRs</TableHead>
                <TableHead>Issues</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(events ?? []).map((event) => (
                <TableRow key={event.id}>
                  <TableCell>
                    <Badge variant="outline">{event.sync_type}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusColor(event.status)}>{event.status}</Badge>
                  </TableCell>
                  <TableCell>{event.repos_synced ?? '-'}</TableCell>
                  <TableCell>{event.prs_upserted ?? '-'}</TableCell>
                  <TableCell>{event.issues_upserted ?? '-'}</TableCell>
                  <TableCell>
                    {event.duration_s != null ? `${event.duration_s}s` : '-'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {event.started_at
                      ? new Date(event.started_at).toLocaleString()
                      : '-'}
                  </TableCell>
                </TableRow>
              ))}
              {(events ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No sync events yet. Trigger a sync to get started.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
