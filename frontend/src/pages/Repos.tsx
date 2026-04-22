import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { useDeleteRepoData, useRepos, useToggleTracking } from '@/hooks/useSync'
import { useRepoStats, useReposSummary } from '@/hooks/useStats'
import { useDateRange } from '@/hooks/useDateRange'
import ErrorCard from '@/components/ErrorCard'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import SortableHead from '@/components/SortableHead'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { Repo, RepoSummaryItem } from '@/utils/types'

// --- Health scoring ---

type HealthLevel = 'healthy' | 'attention' | 'critical' | 'inactive' | 'not_synced' | 'unknown'

function getRepoHealth(repo: Repo, summary?: RepoSummaryItem): HealthLevel {
  if (!repo.is_tracked) return 'unknown'
  if (!repo.last_synced_at) return 'not_synced'
  if (!summary) return 'not_synced'

  const { avg_time_to_merge_hours: avgMerge, total_prs, last_pr_date } = summary

  // No activity in the selected period — dormant/stable repo, not a problem
  if (total_prs === 0 && avgMerge == null) return 'inactive'

  if (avgMerge != null && avgMerge > 48) return 'critical'

  if (avgMerge != null && avgMerge > 24) return 'attention'
  if (last_pr_date) {
    const daysSince = (Date.now() - new Date(last_pr_date).getTime()) / 86_400_000
    if (daysSince > 14) return 'attention'
  }

  return 'healthy'
}

const healthSortOrder: Record<HealthLevel, number> = {
  critical: 0,
  attention: 1,
  healthy: 2,
  inactive: 3,
  not_synced: 4,
  unknown: 5,
}

const healthConfig: Record<HealthLevel, { color: string; dot: string; label: string }> = {
  healthy: { color: 'text-emerald-600', dot: 'bg-emerald-500', label: 'Healthy' },
  attention: { color: 'text-amber-600', dot: 'bg-amber-500', label: 'Needs Attention' },
  critical: { color: 'text-red-600', dot: 'bg-red-500', label: 'Critical' },
  inactive: { color: 'text-muted-foreground', dot: 'bg-muted-foreground/40', label: 'Inactive' },
  not_synced: { color: 'text-blue-600', dot: 'bg-blue-400', label: 'Not Synced' },
  unknown: { color: 'text-muted-foreground', dot: 'bg-muted-foreground/40', label: 'Not Tracked' },
}

// --- Trend helpers ---

interface TrendIndicator {
  direction: 'up' | 'down' | 'stable'
  delta: string
  positive: boolean
}

function getTrend(
  current: number | null | undefined,
  previous: number | null | undefined,
  lowerIsBetter = false,
): TrendIndicator | undefined {
  if (current == null || previous == null || previous === 0) return undefined
  const pct = ((current - previous) / previous) * 100
  if (Math.abs(pct) < 5) return { direction: 'stable', delta: '\u2014', positive: true }
  const direction = pct > 0 ? 'up' : 'down'
  const positive = lowerIsBetter ? pct < 0 : pct > 0
  return { direction, delta: `${Math.abs(pct).toFixed(0)}%`, positive }
}

function TrendBadge({ trend }: { trend?: TrendIndicator }) {
  if (!trend || trend.direction === 'stable') return null
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-medium',
        trend.positive
          ? 'bg-emerald-500/10 text-emerald-600'
          : 'bg-red-500/10 text-red-600',
      )}
    >
      {trend.direction === 'up' ? '\u2191' : '\u2193'}
      {trend.delta}
    </span>
  )
}

// --- Delete confirmation dialog ---

function DeleteRepoDataDialog({
  repo,
  open,
  onOpenChange,
}: {
  repo: Repo
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [confirmText, setConfirmText] = useState('')
  const deleteData = useDeleteRepoData()
  const expected = repo.full_name ?? repo.name ?? ''
  const matches = confirmText === expected

  const handleClose = (next: boolean) => {
    if (!next) setConfirmText('')
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete synced data for {expected}?</DialogTitle>
          <DialogDescription>
            This permanently removes all PRs, reviews, review comments, check runs,
            issues, issue comments, deployments, and tree files cached for this
            repository. The repo will also be untracked. Settings, roles, and other
            repos are untouched. The repo can be re-synced later from GitHub.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Type <span className="font-mono font-semibold text-foreground">{expected}</span> to confirm.
          </p>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={expected}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!matches || deleteData.isPending}
            onClick={() => {
              deleteData.mutate(repo.id, {
                onSuccess: () => handleClose(false),
              })
            }}
          >
            {deleteData.isPending ? 'Deleting…' : 'Delete synced data'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// --- Expanded stats panel ---

function RepoStatsPanel({ repo }: { repo: Repo }) {
  const repoId = repo.id
  const { dateFrom, dateTo } = useDateRange()
  const { data: stats, isLoading } = useRepoStats(repoId, dateFrom, dateTo)
  const [deleteOpen, setDeleteOpen] = useState(false)

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-1">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-5 w-24" />
          </div>
        ))}
      </div>
    )
  }
  if (!stats) return null

  return (
    <div className="space-y-3 p-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <div className="text-xs text-muted-foreground">PRs</div>
          <div className="font-medium">
            {stats.total_prs} ({stats.total_merged} merged)
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Issues</div>
          <div className="font-medium">
            {stats.total_issues} ({stats.total_issues_closed} closed)
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Reviews</div>
          <div className="font-medium">{stats.total_reviews}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Avg Merge Time</div>
          <div className="font-medium">
            {stats.avg_time_to_merge_hours != null
              ? `${stats.avg_time_to_merge_hours.toFixed(1)}h`
              : 'N/A'}
          </div>
        </div>
        {stats.top_contributors.length > 0 && (
          <div className="col-span-full">
            <div className="mb-1 text-xs text-muted-foreground">Top Contributors</div>
            <div className="flex flex-wrap gap-2">
              {stats.top_contributors.map((c) => (
                <Badge key={c.developer_id} variant="outline">
                  {c.display_name} ({c.pr_count} PRs)
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="flex gap-2 border-t pt-3">
        <Link to={`/insights/dora?repo_id=${repoId}`}>
          <Button variant="outline" size="sm">DORA Metrics</Button>
        </Link>
        <Link to={`/insights/ci?repo_id=${repoId}`}>
          <Button variant="outline" size="sm">CI Health</Button>
        </Link>
        <Link to={`/insights/code-churn?repo_id=${repoId}`}>
          <Button variant="outline" size="sm">Code Churn</Button>
        </Link>
        <Button
          variant="destructive"
          size="sm"
          className="ml-auto"
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete synced data
        </Button>
      </div>
      <DeleteRepoDataDialog
        repo={repo}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </div>
  )
}

// --- Sort types ---

type SortField = 'name' | 'language' | 'total_prs' | 'avg_merge_time' | 'health' | 'tracked'

// --- Main page ---

export default function Repos() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: repos, isLoading, isError, refetch } = useRepos()
  const { data: summaryList, isLoading: summaryLoading } = useReposSummary(dateFrom, dateTo)
  const toggle = useToggleTracking()

  // Filters
  const [search, setSearch] = useState('')
  const [langFilter, setLangFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [healthFilter, setHealthFilter] = useState('')

  // Sort
  const [sortField, setSortField] = useState<SortField>('health')
  const [sortAsc, setSortAsc] = useState(true)

  // View
  const [view, setView] = useState<'table' | 'cards'>('table')

  // Expand
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // Index summary by repo_id
  const summaryMap = useMemo(() => {
    const m = new Map<number, RepoSummaryItem>()
    summaryList?.forEach((s) => m.set(s.repo_id, s))
    return m
  }, [summaryList])

  // Derive language options
  const languages = useMemo(() => {
    if (!repos) return []
    const set = new Set(repos.map((r) => r.language).filter(Boolean) as string[])
    return Array.from(set).sort()
  }, [repos])

  // Toggle sort
  const toggleSort = (field: SortField) => {
    if (sortField === field) setSortAsc(!sortAsc)
    else {
      setSortField(field)
      setSortAsc(field === 'name' || field === 'language')
    }
  }

  // Filter + sort
  const displayRepos = useMemo(() => {
    let list = repos ?? []

    if (search) {
      const q = search.toLowerCase()
      list = list.filter(
        (r) =>
          (r.full_name ?? r.name ?? '').toLowerCase().includes(q) ||
          (r.description ?? '').toLowerCase().includes(q),
      )
    }

    if (langFilter) list = list.filter((r) => r.language === langFilter)

    if (statusFilter === 'tracked') list = list.filter((r) => r.is_tracked)
    else if (statusFilter === 'untracked') list = list.filter((r) => !r.is_tracked)
    else if (statusFilter === 'never_synced') list = list.filter((r) => !r.last_synced_at)

    if (healthFilter && !summaryLoading)
      list = list.filter((r) => getRepoHealth(r, summaryMap.get(r.id)) === healthFilter)

    return [...list].sort((a, b) => {
      const dir = sortAsc ? 1 : -1
      const sa = summaryMap.get(a.id)
      const sb = summaryMap.get(b.id)

      switch (sortField) {
        case 'name':
          return dir * (a.full_name ?? a.name ?? '').localeCompare(b.full_name ?? b.name ?? '')
        case 'language':
          return dir * (a.language ?? '').localeCompare(b.language ?? '')
        case 'total_prs':
          return dir * ((sa?.total_prs ?? -1) - (sb?.total_prs ?? -1))
        case 'avg_merge_time':
          return dir * ((sa?.avg_time_to_merge_hours ?? 999) - (sb?.avg_time_to_merge_hours ?? 999))
        case 'health': {
          const ha = healthSortOrder[getRepoHealth(a, sa)]
          const hb = healthSortOrder[getRepoHealth(b, sb)]
          return dir * (ha - hb)
        }
        case 'tracked':
          return dir * (Number(a.is_tracked) - Number(b.is_tracked))
        default:
          return 0
      }
    })
  }, [repos, summaryMap, summaryLoading, search, langFilter, statusFilter, healthFilter, sortField, sortAsc])

  // Summary counts
  const trackedCount = repos?.filter((r) => r.is_tracked).length ?? 0
  const untrackedCount = repos?.filter((r) => !r.is_tracked).length ?? 0
  const neverSyncedCount = repos?.filter((r) => r.is_tracked && !r.last_synced_at).length ?? 0

  // Org-wide avg merge time (weighted)
  const orgMergeTime = useMemo(() => {
    if (!summaryList) return { current: null, trend: undefined as TrendIndicator | undefined }
    let totalSeconds = 0
    let totalMerged = 0
    let prevTotalSeconds = 0
    let prevTotalMerged = 0
    for (const s of summaryList) {
      if (s.avg_time_to_merge_hours != null && s.total_merged > 0) {
        totalSeconds += s.avg_time_to_merge_hours * s.total_merged
        totalMerged += s.total_merged
      }
      if (s.prev_avg_time_to_merge_hours != null && s.prev_total_merged > 0) {
        prevTotalSeconds += s.prev_avg_time_to_merge_hours * s.prev_total_merged
        prevTotalMerged += s.prev_total_merged
      }
    }
    const current = totalMerged > 0 ? totalSeconds / totalMerged : null
    const prev = prevTotalMerged > 0 ? prevTotalSeconds / prevTotalMerged : null
    return { current, trend: getTrend(current, prev, true) }
  }, [summaryList])

  if (isError)
    return <ErrorCard message="Could not load repositories." onRetry={() => refetch()} />

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Repositories</h1>
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
        <TableSkeleton
          columns={6}
          rows={6}
          headers={['Repository', 'Language', 'PRs', 'Avg Merge Time', 'Health', 'Tracked']}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Repositories</h1>

      {/* Summary strip */}
      <div className="grid gap-4 sm:grid-cols-4">
        <StatCard title="Tracked" value={trackedCount} />
        <StatCard title="Untracked" value={untrackedCount} />
        <StatCard
          title="Never Synced"
          value={neverSyncedCount}
          tooltip="Tracked repos that haven't been synced yet"
        />
        <StatCard
          title="Avg Merge Time"
          value={
            summaryLoading
              ? '...'
              : orgMergeTime.current != null
                ? `${orgMergeTime.current.toFixed(1)}h`
                : 'N/A'
          }
          subtitle="Across tracked repos"
          trend={orgMergeTime.trend}
        />
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search repositories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
        <Select value={langFilter || '__all__'} onValueChange={(v) => v && setLangFilter(v === '__all__' ? '' : v)}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Language" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Languages</SelectItem>
            {languages.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter || '__all__'} onValueChange={(v) => v && setStatusFilter(v === '__all__' ? '' : v)}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Status</SelectItem>
            <SelectItem value="tracked">Tracked</SelectItem>
            <SelectItem value="untracked">Untracked</SelectItem>
            <SelectItem value="never_synced">Never Synced</SelectItem>
          </SelectContent>
        </Select>
        <Select value={healthFilter || '__all__'} onValueChange={(v) => v && setHealthFilter(v === '__all__' ? '' : v)}>
          <SelectTrigger className="w-[170px]">
            <SelectValue placeholder="Health" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Health</SelectItem>
            <SelectItem value="healthy">Healthy</SelectItem>
            <SelectItem value="attention">Needs Attention</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
            <SelectItem value="not_synced">Not Synced</SelectItem>
          </SelectContent>
        </Select>

        <div className="ml-auto flex gap-1">
          <Button
            variant={view === 'table' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setView('table')}
          >
            Table
          </Button>
          <Button
            variant={view === 'cards' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setView('cards')}
          >
            Cards
          </Button>
        </div>
      </div>

      {/* Table view */}
      {view === 'table' && (
        <div className="rounded-md border overflow-hidden">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <SortableHead field="name" current={sortField} asc={sortAsc} onToggle={toggleSort} className="w-[40%]">
                  Repository
                </SortableHead>
                <SortableHead field="language" current={sortField} asc={sortAsc} onToggle={toggleSort} className="w-[10%]">
                  Language
                </SortableHead>
                <SortableHead field="total_prs" current={sortField} asc={sortAsc} onToggle={toggleSort} className="w-[12%]">
                  PRs
                </SortableHead>
                <SortableHead field="avg_merge_time" current={sortField} asc={sortAsc} onToggle={toggleSort} className="w-[15%]">
                  Avg Merge Time
                </SortableHead>
                <SortableHead field="health" current={sortField} asc={sortAsc} onToggle={toggleSort} className="w-[13%]">
                  Health
                </SortableHead>
                <SortableHead field="tracked" current={sortField} asc={sortAsc} onToggle={toggleSort} className="w-[10%]">
                  Tracked
                </SortableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayRepos.flatMap((repo) => {
                const summary = summaryMap.get(repo.id)
                const health = getRepoHealth(repo, summary)
                const hc = healthConfig[health]
                const prTrend = getTrend(summary?.total_prs, summary?.prev_total_prs)
                const mergeTrend = getTrend(
                  summary?.avg_time_to_merge_hours,
                  summary?.prev_avg_time_to_merge_hours,
                  true,
                )

                const rows = [
                  <TableRow
                    key={repo.id}
                    className="group cursor-pointer"
                    onClick={() => setExpandedId(expandedId === repo.id ? null : repo.id)}
                  >
                    <TableCell>
                      <div className="min-w-0">
                        <div className="font-medium truncate">{repo.full_name ?? repo.name}</div>
                        {repo.description && (
                          <div className="text-xs text-muted-foreground truncate">
                            {repo.description}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {repo.language && <Badge variant="outline">{repo.language}</Badge>}
                    </TableCell>
                    <TableCell>
                      {repo.is_tracked && summary ? (
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium">{summary.total_prs}</span>
                          <TrendBadge trend={prTrend} />
                        </div>
                      ) : (
                        <span className="text-muted-foreground">&mdash;</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {repo.is_tracked && summary ? (
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium">
                            {summary.avg_time_to_merge_hours != null
                              ? `${summary.avg_time_to_merge_hours.toFixed(1)}h`
                              : 'N/A'}
                          </span>
                          <TrendBadge trend={mergeTrend} />
                        </div>
                      ) : (
                        <span className="text-muted-foreground">&mdash;</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className={cn('h-2.5 w-2.5 rounded-full', hc.dot)} />
                        <span className={cn('text-sm', hc.color)}>{hc.label}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={repo.is_tracked}
                        onCheckedChange={(checked) => {
                          toggle.mutate({ id: repo.id, isTracked: checked })
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </TableCell>
                  </TableRow>,
                ]

                if (expandedId === repo.id) {
                  rows.push(
                    <TableRow key={`${repo.id}-expand`}>
                      <TableCell colSpan={6} className="bg-muted/30 p-0">
                        <RepoStatsPanel repo={repo} />
                      </TableCell>
                    </TableRow>,
                  )
                }

                return rows
              })}
              {displayRepos.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    {repos && repos.length > 0
                      ? 'No repositories match the current filters.'
                      : 'No repositories found. Run a sync to discover repos.'}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Card view */}
      {view === 'cards' && (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {displayRepos.map((repo) => {
            const summary = summaryMap.get(repo.id)
            const health = getRepoHealth(repo, summary)
            const hc = healthConfig[health]
            const prTrend = getTrend(summary?.total_prs, summary?.prev_total_prs)
            const mergeTrend = getTrend(
              summary?.avg_time_to_merge_hours,
              summary?.prev_avg_time_to_merge_hours,
              true,
            )

            return (
              <Card key={repo.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium truncate">{repo.full_name ?? repo.name}</div>
                      {repo.description && (
                        <div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                          {repo.description}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className={cn('h-2.5 w-2.5 rounded-full', hc.dot)} />
                      <span className={cn('text-xs', hc.color)}>{hc.label}</span>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pb-2">
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    {repo.language && <Badge variant="outline">{repo.language}</Badge>}
                  </div>
                  {repo.is_tracked && summary ? (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-muted-foreground">PRs</div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-lg font-bold">{summary.total_prs}</span>
                          <TrendBadge trend={prTrend} />
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Avg Merge</div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-lg font-bold">
                            {summary.avg_time_to_merge_hours != null
                              ? `${summary.avg_time_to_merge_hours.toFixed(1)}h`
                              : 'N/A'}
                          </span>
                          <TrendBadge trend={mergeTrend} />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">Not tracked</div>
                  )}
                </CardContent>
                <CardFooter className="pt-2 border-t">
                  <div className="flex items-center justify-between w-full">
                    <span className="text-sm text-muted-foreground">
                      {repo.last_synced_at
                        ? `Synced ${new Date(repo.last_synced_at).toLocaleDateString()}`
                        : 'Never synced'}
                    </span>
                    <Switch
                      checked={repo.is_tracked}
                      onCheckedChange={(checked) => {
                        toggle.mutate({ id: repo.id, isTracked: checked })
                      }}
                    />
                  </div>
                </CardFooter>
              </Card>
            )
          })}
          {displayRepos.length === 0 && (
            <div className="col-span-full text-center text-muted-foreground py-8">
              {repos && repos.length > 0
                ? 'No repositories match the current filters.'
                : 'No repositories found. Run a sync to discover repos.'}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="text-sm text-muted-foreground">
        Showing {displayRepos.length} of {repos?.length ?? 0} repositories
      </div>
    </div>
  )
}
