import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useWorkload, useStalePRs } from '@/hooks/useStats'
import { useDevelopers } from '@/hooks/useDevelopers'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import StalePRsSection from '@/components/StalePRsSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { DeveloperWorkload } from '@/utils/types'

import AlertSummaryBar from '@/components/NotificationCenter/AlertSummaryBar'
import { workloadStyles } from '@/components/AlertStrip'
import SortableHead from '@/components/SortableHead'

const workloadBarColors: Record<DeveloperWorkload['workload_score'], string> = {
  low: 'bg-blue-500',
  balanced: 'bg-emerald-500',
  high: 'bg-amber-500',
  overloaded: 'bg-red-500',
}

const workloadSortOrder: Record<string, number> = {
  overloaded: 4,
  high: 3,
  balanced: 2,
  low: 1,
}

type SortField = 'display_name' | 'workload_score' | 'open_prs_authored' | 'open_prs_reviewing' | 'open_issues_assigned' | 'reviews_given_this_period' | 'prs_waiting_for_review'

export default function WorkloadOverview() {
  const { dateFrom, dateTo } = useDateRange()
  const [teamFilter, setTeamFilter] = useState<string>('')
  const [sortField, setSortField] = useState<SortField>('workload_score')
  const [sortAsc, setSortAsc] = useState(false)

  const { data: workload, isLoading: workloadLoading, isError: workloadError, refetch: refetchWorkload } = useWorkload(teamFilter || undefined, dateFrom, dateTo)
  const { data: stalePRs, isLoading: stalePRsLoading, isError: stalePRsError, refetch: refetchStalePRs } = useStalePRs(teamFilter || undefined)
  const { data: developers } = useDevelopers()

  const teams = useMemo(() => {
    if (!developers) return []
    const set = new Set(developers.map((d) => d.team).filter(Boolean) as string[])
    return Array.from(set).sort()
  }, [developers])

  const sortedDevs = useMemo(() => {
    if (!workload) return []
    const devs = [...workload.developers]
    devs.sort((a, b) => {
      let cmp: number
      if (sortField === 'workload_score') {
        cmp = (workloadSortOrder[a.workload_score] ?? 0) - (workloadSortOrder[b.workload_score] ?? 0)
      } else if (sortField === 'display_name') {
        cmp = a.display_name.localeCompare(b.display_name)
      } else {
        cmp = (a[sortField] as number) - (b[sortField] as number)
      }
      return sortAsc ? cmp : -cmp
    })
    return devs
  }, [workload, sortField, sortAsc])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc)
    } else {
      setSortField(field)
      setSortAsc(field === 'display_name')
    }
  }

  // Summary stats
  const overloadedCount = workload?.developers.filter((d) => d.workload_score === 'overloaded').length ?? 0
  const totalWaiting = workload?.developers.reduce((s, d) => s + d.prs_waiting_for_review, 0) ?? 0
  const alertCount = workload?.alerts.length ?? 0

  if (workloadError || stalePRsError) {
    return (
      <ErrorCard
        message="Could not load workload data."
        onRetry={() => { refetchWorkload(); refetchStalePRs() }}
      />
    )
  }

  const isLoading = workloadLoading || stalePRsLoading

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Workload Overview</h1>
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
        <Skeleton className="h-12 w-full rounded-lg" />
        <TableSkeleton columns={7} rows={5} headers={['Developer', 'Workload', 'Open PRs', 'Reviewing', 'Issues', 'Reviews Given', 'Awaiting Review']} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Workload Overview</h1>
        {teams.length > 0 && (
          <Select value={teamFilter || '__all__'} onValueChange={(v) => setTeamFilter(v === '__all__' ? '' : v)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="All teams" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All teams</SelectItem>
              {teams.map((t) => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          title="Overloaded"
          value={overloadedCount}
          tooltip="Developers with workload score 'overloaded' based on open PRs authored + reviewing + issues"
        />
        <StatCard
          title="PRs Awaiting Review"
          value={totalWaiting}
          tooltip="Total PRs across the team that have no review yet"
        />
        <StatCard
          title="Active Alerts"
          value={alertCount}
          tooltip="Automated alerts: review bottlenecks, stale PRs, uneven assignment, reverts, unapproved merges"
        />
      </div>

      {/* Alerts */}
      <AlertSummaryBar />

      {/* Stale PRs */}
      {stalePRs && stalePRs.stale_prs.length > 0 && (
        <StalePRsSection prs={stalePRs.stale_prs} />
      )}

      {/* Team workload grid */}
      {sortedDevs.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Team Workload</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHead field="display_name" current={sortField} asc={sortAsc} onToggle={toggleSort}>Developer</SortableHead>
                <SortableHead field="workload_score" current={sortField} asc={sortAsc} onToggle={toggleSort}>Workload</SortableHead>
                <SortableHead field="open_prs_authored" current={sortField} asc={sortAsc} onToggle={toggleSort}>Open PRs</SortableHead>
                <SortableHead field="open_prs_reviewing" current={sortField} asc={sortAsc} onToggle={toggleSort}>Reviewing</SortableHead>
                <SortableHead field="open_issues_assigned" current={sortField} asc={sortAsc} onToggle={toggleSort}>Issues</SortableHead>
                <SortableHead field="reviews_given_this_period" current={sortField} asc={sortAsc} onToggle={toggleSort}>Reviews Given</SortableHead>
                <SortableHead field="prs_waiting_for_review" current={sortField} asc={sortAsc} onToggle={toggleSort}>Awaiting Review</SortableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedDevs.map((dev) => (
                <TableRow key={dev.developer_id}>
                  <TableCell>
                    <Link to={`/team/${dev.developer_id}`} className="font-medium text-primary hover:underline">
                      {dev.display_name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                        <div
                          className={cn('h-full rounded-full transition-all', workloadBarColors[dev.workload_score])}
                          style={{ width: `${(workloadSortOrder[dev.workload_score] / 4) * 100}%` }}
                        />
                      </div>
                      <Badge variant="secondary" className={workloadStyles[dev.workload_score]}>
                        {dev.workload_score}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>{dev.open_prs_authored}</TableCell>
                  <TableCell>{dev.open_prs_reviewing}</TableCell>
                  <TableCell>{dev.open_issues_assigned}</TableCell>
                  <TableCell>{dev.reviews_given_this_period}</TableCell>
                  <TableCell>
                    <span className={cn(dev.prs_waiting_for_review > 0 && 'font-medium text-amber-600')}>
                      {dev.prs_waiting_for_review}
                    </span>
                    {dev.avg_review_wait_h != null && dev.prs_waiting_for_review > 0 && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        ({dev.avg_review_wait_h.toFixed(0)}h avg)
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

