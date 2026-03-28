import { useSyncStatus, useSyncEvents } from '@/hooks/useSync'
import ErrorCard from '@/components/ErrorCard'
import TableSkeleton from '@/components/TableSkeleton'
import SyncOverviewPanel from './SyncOverviewPanel'
import SyncProgressView from './SyncProgressView'
import SyncWizard from './SyncWizard'
import ResumeBanner from './ResumeBanner'
import SyncHistoryTable from './SyncHistoryTable'

export default function SyncPage() {
  const { data: status, isLoading: statusLoading, isError: statusError, refetch: refetchStatus } = useSyncStatus()
  const { data: events, isLoading: eventsLoading, isError: eventsError, refetch: refetchEvents } = useSyncEvents()

  if (statusError) {
    return <ErrorCard message="Could not load sync status." onRetry={() => refetchStatus()} />
  }

  // Find the most recent resumable event (not the active one)
  const resumableEvent = !status?.active_sync
    ? (events ?? []).find((e) => e.is_resumable && e.status !== 'started')
    : undefined

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sync</h1>

      {/* Overview stats */}
      {statusLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : status ? (
        <SyncOverviewPanel status={status} />
      ) : null}

      {/* Resume banner */}
      {resumableEvent && (
        <ResumeBanner
          event={resumableEvent}
          onStartFresh={() => {/* wizard handles fresh start */}}
        />
      )}

      {/* Active sync progress OR wizard */}
      {status?.active_sync ? (
        <SyncProgressView sync={status.active_sync} />
      ) : (
        <SyncWizard />
      )}

      {/* Sync history */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Sync History</h2>
        {eventsError ? (
          <ErrorCard message="Could not load sync events." onRetry={() => refetchEvents()} />
        ) : eventsLoading ? (
          <TableSkeleton
            columns={8}
            rows={5}
            headers={['Type', 'Status', 'Progress', 'PRs', 'Issues', 'Errors', 'Duration', 'Started']}
          />
        ) : (
          <SyncHistoryTable events={events ?? []} />
        )}
      </div>
    </div>
  )
}
