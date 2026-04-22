import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useRiskSummary, useStalePRs, useTeamStats, useWorkload } from '@/hooks/useStats'
import { useDevelopers } from '@/hooks/useDevelopers'
import { useIntegrations, useIssueSource } from '@/hooks/useIntegrations'
import { useSprintVelocity, useWorkAlignment } from '@/hooks/useSprints'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import StalePRsSection from '@/components/StalePRsSection'
import LinearUsageHealthCard from '@/components/linear-health/LinearUsageHealthCard'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { RiskAssessment, TeamStats } from '@/utils/types'
import { riskLevelLabels, riskLevelStyles } from '@/utils/types'

import AlertSummaryBar from '@/components/NotificationCenter/AlertSummaryBar'
import { workloadStyles } from '@/components/AlertStrip'
import SortableHead from '@/components/SortableHead'

// --- Trend helpers ---

type SortField = 'display_name' | 'workload_score' | 'open_prs_authored' | 'prs_waiting_for_review' | 'reviews_given_this_period'

const workloadSortOrder: Record<string, number> = {
  overloaded: 4,
  high: 3,
  balanced: 2,
  low: 1,
}

function computePreviousPeriod(dateFrom: string, dateTo: string) {
  const from = new Date(dateFrom)
  const to = new Date(dateTo)
  const durationMs = to.getTime() - from.getTime()
  const prevTo = new Date(from.getTime() - 86_400_000) // day before current start
  const prevFrom = new Date(prevTo.getTime() - durationMs)
  return {
    prevFrom: prevFrom.toISOString().slice(0, 10),
    prevTo: prevTo.toISOString().slice(0, 10),
  }
}

function computeTrend(
  current: number | null | undefined,
  previous: number | null | undefined,
  lowerIsBetter = false,
): { direction: 'up' | 'down' | 'stable'; delta: string; positive: boolean } | undefined {
  if (current == null || previous == null || previous === 0) return undefined
  const pct = ((current - previous) / Math.abs(previous)) * 100
  if (Math.abs(pct) < 1) return { direction: 'stable', delta: '', positive: true }
  const direction = pct > 0 ? 'up' : 'down'
  const positive = lowerIsBetter ? pct < 0 : pct > 0
  return { direction, delta: `${Math.abs(pct).toFixed(0)}%`, positive }
}

export default function Dashboard() {
  const { dateFrom, dateTo } = useDateRange()
  const { prevFrom, prevTo } = useMemo(
    () => computePreviousPeriod(dateFrom, dateTo),
    [dateFrom, dateTo]
  )

  // Parallel data fetching
  const { data: stats, isLoading: statsLoading, isError: statsError, refetch: refetchStats } = useTeamStats(undefined, dateFrom, dateTo)
  const { data: prevStats } = useTeamStats(undefined, prevFrom, prevTo)
  const { data: workload, isLoading: workloadLoading, isError: workloadError, refetch: refetchWorkload } = useWorkload(undefined, dateFrom, dateTo)
  const { data: stalePRs, isLoading: stalePRsLoading, isError: stalePRsError, refetch: refetchStalePRs } = useStalePRs()
  const { data: riskSummary } = useRiskSummary(undefined, dateFrom, dateTo, 'low', 'all')
  const { data: riskOpen } = useRiskSummary(undefined, dateFrom, dateTo, 'high', 'open')
  const { data: integrations } = useIntegrations()
  const hasLinear = integrations?.some((i) => i.type === 'linear' && i.status === 'active')
  const { data: issueSource } = useIssueSource()
  const isLinearPrimary = hasLinear && issueSource?.source === 'linear'
  const { data: velocity } = useSprintVelocity(undefined, 5)
  const { data: alignment } = useWorkAlignment(dateFrom, dateTo)
  const { data: developers } = useDevelopers()

  // Team grid state
  const [sortField, setSortField] = useState<SortField>('display_name')
  const [sortAsc, setSortAsc] = useState(true)
  const [teamFilter, setTeamFilter] = useState<string>('')

  // Extract unique teams
  const teams = useMemo(() => {
    if (!developers) return []
    const set = new Set(developers.map((d) => d.team).filter(Boolean) as string[])
    return Array.from(set).sort()
  }, [developers])

  // Build risk score lookup for stale PRs
  const riskScoresMap = useMemo(() => {
    if (!riskSummary) return undefined
    const map: Record<number, RiskAssessment> = {}
    for (const a of riskSummary.high_risk_prs) {
      map[a.pr_id] = a
    }
    return map
  }, [riskSummary])

  // Open high-risk PRs for the dashboard section (pre-filtered by API: scope=open, min_risk_level=high)
  const openHighRiskPRs = riskOpen?.high_risk_prs ?? []

  // Filter and sort workload developers
  const sortedDevs = useMemo(() => {
    if (!workload) return []
    let devs = [...workload.developers]
    if (teamFilter) {
      const devIds = new Set(
        developers?.filter((d) => d.team === teamFilter).map((d) => d.id)
      )
      devs = devs.filter((d) => devIds.has(d.developer_id))
    }
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
  }, [workload, teamFilter, developers, sortField, sortAsc])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc)
    } else {
      setSortField(field)
      setSortAsc(field === 'display_name')
    }
  }

  const isLoading = statsLoading || workloadLoading || stalePRsLoading

  if (statsError || workloadError || stalePRsError) {
    return (
      <ErrorCard
        message="Could not load dashboard data."
        onRetry={() => { refetchStats(); refetchWorkload(); refetchStalePRs() }}
      />
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Skeleton className="h-12 w-full rounded-lg" />
        <TableSkeleton columns={4} rows={3} headers={['Pull Request', 'Author', 'Age', 'Reason']} />
        <TableSkeleton columns={5} rows={4} headers={['Developer', 'Workload', 'Open PRs', 'Awaiting Review', 'Reviews Given']} />
        <h2 className="text-lg font-semibold">Period Velocity</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
      </div>
    )
  }

  if (!stats && !workload) {
    return <div className="text-muted-foreground">No data available. Run a sync first.</div>
  }

  // Build trend data from current vs previous period
  function trend(
    key: keyof TeamStats,
    lowerIsBetter = false,
  ) {
    return computeTrend(
      stats?.[key] as number | null,
      prevStats?.[key] as number | null,
      lowerIsBetter,
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Zone 1: Compact alert summary bar */}
      <AlertSummaryBar />

      {/* Zone 1b: Stale PRs — Needs Attention */}
      {stalePRs && stalePRs.stale_prs.length > 0 && (
        <StalePRsSection prs={stalePRs.stale_prs} riskScores={riskScoresMap} />
      )}

      {/* Zone 1c: High-Risk PRs */}
      {openHighRiskPRs.length > 0 && (
        <HighRiskPRsSection prs={openHighRiskPRs} />
      )}

      {/* Zone 2: Team Status Grid */}
      {workload && workload.developers.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Team Status</h2>
            {teams.length > 0 && (
              <Select value={teamFilter || '__all__'} onValueChange={(v) => v && setTeamFilter(v === '__all__' ? '' : v)}>
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
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHead field="display_name" current={sortField} asc={sortAsc} onToggle={toggleSort}>
                  Developer
                </SortableHead>
                <SortableHead field="workload_score" current={sortField} asc={sortAsc} onToggle={toggleSort}>
                  Workload
                </SortableHead>
                <SortableHead field="open_prs_authored" current={sortField} asc={sortAsc} onToggle={toggleSort}>
                  Open PRs
                </SortableHead>
                <SortableHead field="prs_waiting_for_review" current={sortField} asc={sortAsc} onToggle={toggleSort}>
                  Awaiting Review
                </SortableHead>
                <SortableHead field="reviews_given_this_period" current={sortField} asc={sortAsc} onToggle={toggleSort}>
                  Reviews Given
                </SortableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedDevs.map((dev) => (
                <TableRow key={dev.developer_id}>
                  <TableCell>
                    <Link
                      to={`/team/${dev.developer_id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {dev.display_name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={workloadStyles[dev.workload_score]}
                    >
                      {dev.workload_score}
                    </Badge>
                  </TableCell>
                  <TableCell>{dev.open_prs_authored}</TableCell>
                  <TableCell>{dev.prs_waiting_for_review}</TableCell>
                  <TableCell>{dev.reviews_given_this_period}</TableCell>
                </TableRow>
              ))}
              {sortedDevs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No developers found.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Zone 3: Period Velocity with Trend Deltas */}
      {stats && (
        <>
          <h2 className="text-lg font-semibold">Period Velocity</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Active Developers"
              value={stats.developer_count}
              trend={trend('developer_count')}
              tooltip="Developers who authored at least one PR or review in this period"
            />
            <StatCard
              title="Total PRs"
              value={stats.total_prs}
              subtitle={`${stats.total_merged} merged`}
              trend={trend('total_prs')}
              tooltip="Total pull requests opened across the team in this period"
            />
            <StatCard
              title="Merge Rate"
              value={stats.merge_rate != null ? `${(stats.merge_rate * 100).toFixed(1)}%` : 'N/A'}
              trend={trend('merge_rate')}
              tooltip="Percentage of closed PRs that were merged (merged / (merged + closed without merge))"
            />
            <StatCard
              title="Avg Time to Review"
              value={
                stats.avg_time_to_first_review_hours != null
                  ? `${stats.avg_time_to_first_review_hours.toFixed(1)}h`
                  : 'N/A'
              }
              trend={trend('avg_time_to_first_review_hours', true)}
              tooltip="Average hours from PR creation to first review across the team. Lower is better."
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              title="Avg Time to Merge"
              value={
                stats.avg_time_to_merge_hours != null
                  ? `${stats.avg_time_to_merge_hours.toFixed(1)}h`
                  : 'N/A'
              }
              trend={trend('avg_time_to_merge_hours', true)}
              tooltip="Average hours from PR creation to merge, including review time and iteration. Lower is better."
            />
            <StatCard
              title="Total Reviews"
              value={stats.total_reviews}
              trend={trend('total_reviews')}
              tooltip="Total PR reviews submitted across the team (approved, changes requested, or comments)"
            />
            <StatCard
              title="Issues Closed"
              value={stats.total_issues_closed}
              trend={trend('total_issues_closed')}
              tooltip="Total issues closed across the team in this period"
            />
            <StatCard
              title="Revert Rate"
              value={stats.revert_rate != null ? `${(stats.revert_rate * 100).toFixed(1)}%` : 'N/A'}
              tooltip="Percentage of merged PRs that are reverts — high rates signal quality issues"
            />
          </div>
        </>
      )}

      {/* Linear Usage Health — only when Linear is primary issue source */}
      {isLinearPrimary && <LinearUsageHealthCard />}

      {/* Sprint Planning Cards — only when Linear is active */}
      {hasLinear && (velocity || alignment) && (
        <>
          <h2 className="text-lg font-semibold">Sprint Planning</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {velocity && velocity.data && velocity.data.length > 0 && (
              <StatCard
                title="Sprint Velocity"
                value={`${velocity.avg_velocity ?? 0}`}
                subtitle={`avg over ${velocity.data.length} sprints`}
                tooltip="Average completed scope per sprint"
              />
            )}
            {alignment && (
              <StatCard
                title="Work Alignment"
                value={`${alignment.alignment_pct ?? 0}%`}
                subtitle={`${alignment.linked_prs ?? 0} of ${(alignment.linked_prs ?? 0) + (alignment.unlinked_prs ?? 0)} PRs linked`}
                tooltip="Percentage of PRs linked to planned work items"
              />
            )}
          </div>
        </>
      )}

    </div>
  )
}

// --- Sub-components ---

function HighRiskPRsSection({ prs }: { prs: RiskAssessment[] }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">High-Risk PRs</h2>
        <span className="text-sm text-muted-foreground">
          {prs.length} open PR{prs.length !== 1 ? 's' : ''} at high or critical risk
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Pull Request</TableHead>
            <TableHead>Author</TableHead>
            <TableHead>Risk</TableHead>
            <TableHead>Score</TableHead>
            <TableHead>Factors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {prs.map((pr) => (
            <TableRow key={pr.pr_id}>
              <TableCell>
                <div className="flex flex-col gap-0.5">
                  <a
                    href={pr.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-primary hover:underline"
                  >
                    #{pr.number} {pr.title}
                  </a>
                  <span className="text-xs text-muted-foreground">{pr.repo_name}</span>
                </div>
              </TableCell>
              <TableCell>
                {pr.author_id ? (
                  <Link
                    to={`/team/${pr.author_id}`}
                    className="text-sm hover:underline"
                  >
                    {pr.author_name ?? 'Unknown'}
                  </Link>
                ) : (
                  <span className="text-sm text-muted-foreground">{pr.author_name ?? 'External'}</span>
                )}
              </TableCell>
              <TableCell>
                <Badge
                  variant="secondary"
                  className={riskLevelStyles[pr.risk_level]}
                >
                  {riskLevelLabels[pr.risk_level]}
                </Badge>
              </TableCell>
              <TableCell>
                <span className="text-sm font-medium">{(pr.risk_score * 100).toFixed(0)}%</span>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {pr.risk_factors.map((f) => (
                    <span
                      key={f.factor}
                      className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                      title={f.description}
                    >
                      {f.description}
                    </span>
                  ))}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
