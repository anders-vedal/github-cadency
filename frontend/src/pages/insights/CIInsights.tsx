import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useCIStats, useCheckFailures } from '@/hooks/useStats'
import { useRepos } from '@/hooks/useSync'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  HelpCircle,
  Clock,
  TriangleAlert,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronRight,
  Check,
  X as XIcon,
} from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { timeAgo } from '@/utils/format'
import { cn } from '@/lib/utils'
import type { FlakyCheck } from '@/utils/types'

const STALE_THRESHOLD_MS = 7 * 24 * 60 * 60 * 1000

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

function isStale(lastRunAt: string | null, now: number): boolean {
  if (!lastRunAt) return true
  return now - new Date(lastRunAt).getTime() > STALE_THRESHOLD_MS
}

function TrendCell({ check }: { check: FlakyCheck }) {
  const { trend, failure_rate_first_half: first, failure_rate_second_half: second } = check

  if (trend === null) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-muted-foreground" aria-label="Not enough data">
            —
          </span>
        </TooltipTrigger>
        <TooltipContent>
          Not enough data in one half of the window to compute a trend.
        </TooltipContent>
      </Tooltip>
    )
  }

  const firstPct = first !== null ? `${(first * 100).toFixed(1)}%` : '—'
  const secondPct = second !== null ? `${(second * 100).toFixed(1)}%` : '—'
  const tooltipText = `${firstPct} → ${secondPct}`

  let icon
  let srLabel
  if (trend === 'rising') {
    icon = <TrendingUp className="h-4 w-4 text-red-600 dark:text-red-400" />
    srLabel = `Failure rate rising: ${tooltipText}`
  } else if (trend === 'falling') {
    icon = <TrendingDown className="h-4 w-4 text-green-600 dark:text-green-400" />
    srLabel = `Failure rate falling: ${tooltipText}`
  } else {
    icon = <Minus className="h-4 w-4 text-muted-foreground" />
    srLabel = `Failure rate stable: ${tooltipText}`
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center" aria-label={srLabel}>
          {icon}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tooltipText}</TooltipContent>
    </Tooltip>
  )
}

function CheckNameCell({ name, url }: { name: string; url?: string | null }) {
  if (!url) {
    return <span className="font-mono text-sm">{name}</span>
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-mono text-sm text-primary hover:underline"
    >
      {name}
      <ExternalLink className="h-3 w-3" />
    </a>
  )
}

function CheckHealthTable({
  rows,
  rateColorClass,
  now,
  onRowClick,
}: {
  rows: FlakyCheck[]
  rateColorClass: string
  now: number
  onRowClick: (checkName: string) => void
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Check Name</TableHead>
          <TableHead className="text-right">Failure Rate</TableHead>
          <TableHead className="text-center">Trend</TableHead>
          <TableHead className="text-right">Total Runs</TableHead>
          <TableHead className="text-right">Last Seen</TableHead>
          <TableHead className="w-8" aria-label="Open details" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((c) => {
          const stale = isStale(c.last_run_at, now)
          return (
            <TableRow
              key={c.name}
              tabIndex={0}
              role="button"
              aria-label={`Show failing PRs for ${c.name}`}
              onClick={() => onRowClick(c.name)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onRowClick(c.name)
                }
              }}
              className={cn(
                'cursor-pointer hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none',
                stale && 'text-muted-foreground opacity-70',
              )}
            >
              <TableCell>
                <CheckNameCell name={c.name} url={c.html_url} />
              </TableCell>
              <TableCell
                className={cn('text-right font-medium', !stale && rateColorClass)}
              >
                {(c.failure_rate * 100).toFixed(1)}%
              </TableCell>
              <TableCell className="text-center">
                <TrendCell check={c} />
              </TableCell>
              <TableCell className="text-right">{c.total_runs}</TableCell>
              <TableCell className="text-right text-sm">
                {timeAgo(c.last_run_at)}
              </TableCell>
              <TableCell className="text-right">
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

function CheckFailuresDialog({
  checkName,
  onClose,
  dateFrom,
  dateTo,
  repoId,
}: {
  checkName: string | null
  onClose: () => void
  dateFrom?: string
  dateTo?: string
  repoId?: number | null
}) {
  const { data, isLoading, isError, refetch } = useCheckFailures(
    checkName,
    dateFrom,
    dateTo,
    repoId,
  )

  return (
    <Dialog open={checkName !== null} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="font-mono text-base">
            {checkName}
            {data && (
              <span className="ml-2 font-sans text-sm font-normal text-muted-foreground">
                ({data.entries.length} {data.entries.length === 1 ? 'failure' : 'failures'}{' '}
                in date window)
              </span>
            )}
          </DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <TableSkeleton columns={4} rows={5} />
        ) : isError ? (
          <ErrorCard message="Could not load failing PRs." onRetry={refetch} />
        ) : !data || data.entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No failing PRs recorded for this check in the date window.
          </p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>PR</TableHead>
                  <TableHead>Author</TableHead>
                  <TableHead>Failed</TableHead>
                  <TableHead className="text-center">Status</TableHead>
                  <TableHead className="text-right">Run</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.entries.map((e) => (
                  <TableRow key={`${e.repo_full_name}#${e.pr_number}-${e.run_attempt}`}>
                    <TableCell>
                      {e.pr_html_url ? (
                        <a
                          href={e.pr_html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                        >
                          <span className="font-mono">
                            {e.repo_full_name}#{e.pr_number}
                          </span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span className="font-mono text-sm">
                          {e.repo_full_name}#{e.pr_number}
                        </span>
                      )}
                      <div className="text-xs text-muted-foreground">{e.pr_title}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 text-sm">
                        {e.author_avatar_url && (
                          <img
                            src={e.author_avatar_url}
                            alt=""
                            className="h-5 w-5 rounded-full"
                          />
                        )}
                        <span>{e.author_login ?? '—'}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{timeAgo(e.failed_at)}</TableCell>
                    <TableCell className="text-center">
                      {e.was_eventually_green ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="inline-flex" aria-label="Later attempt succeeded">
                              <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>Later attempt succeeded</TooltipContent>
                        </Tooltip>
                      ) : (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="inline-flex" aria-label="Still failing">
                              <XIcon className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>No later success recorded</TooltipContent>
                        </Tooltip>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {e.run_html_url ? (
                        <a
                          href={e.run_html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                          aria-label={`Open run #${e.run_attempt} on GitHub`}
                        >
                          #{e.run_attempt}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          #{e.run_attempt}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default function CIInsights() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: repos } = useRepos()
  const [searchParams] = useSearchParams()
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(
    Number(searchParams.get('repo_id')) || null,
  )
  const [showStale, setShowStale] = useState(false)
  const [drillDownCheck, setDrillDownCheck] = useState<string | null>(null)
  const now = useMemo(() => Date.now(), [])

  const trackedRepos = useMemo(
    () => (repos ?? []).filter((r) => r.is_tracked),
    [repos],
  )

  const { data, isLoading, isError, refetch } = useCIStats(
    dateFrom,
    dateTo,
    selectedRepoId,
  )

  if (isError) {
    return <ErrorCard message="Could not load CI/CD stats." onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">CI/CD Pipeline</h1>
        <select
          className="rounded-md border bg-background px-3 py-1.5 text-sm"
          value={selectedRepoId ?? ''}
          onChange={(e) => setSelectedRepoId(Number(e.target.value) || null)}
        >
          <option value="">All Repos</option>
          {trackedRepos.map((r) => (
            <option key={r.id} value={r.id}>
              {r.full_name || r.name}
            </option>
          ))}
        </select>
      </div>

      {/* Summary cards */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
      ) : data ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            title="Merged with Failing Checks"
            value={data.prs_merged_with_failing_checks}
            tooltip="PRs that were merged despite having at least one check run with a 'failure' conclusion."
          />
          <StatCard
            title="Avg Attempts to Green"
            value={data.avg_checks_to_green?.toFixed(1) ?? '—'}
            tooltip="Average number of check-run attempts before all checks pass. Higher values suggest flaky tests or iterative fix cycles."
          />
          <StatCard
            title="Avg Build Duration"
            value={data.avg_build_duration_s ? formatDuration(data.avg_build_duration_s) : '—'}
            tooltip="Average duration across all check runs in the period."
          />
        </div>
      ) : null}

      {/* CI check health (broken + flaky) */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle>CI Check Health</CardTitle>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>Show stale (&gt;7 days)</span>
              <Switch checked={showStale} onCheckedChange={setShowStale} />
            </label>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {isLoading ? (
            <TableSkeleton columns={5} rows={3} />
          ) : !data || data.flaky_checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No flaky checks detected in this period.</p>
          ) : (
            (() => {
              const visible = showStale
                ? data.flaky_checks
                : data.flaky_checks.filter((c) => !isStale(c.last_run_at, now))
              const brokenRows = visible.filter((c) => c.category === 'broken')
              const flakyRows = visible.filter((c) => c.category === 'flaky')
              const hiddenByStale = data.flaky_checks.length - visible.length

              if (visible.length === 0) {
                return (
                  <p className="text-sm text-muted-foreground">
                    No flaky checks active in the last 7 days. Toggle &quot;Show stale&quot; to
                    include older runs.
                  </p>
                )
              }

              return (
                <>
                  {brokenRows.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <TriangleAlert className="h-5 w-5 text-red-600 dark:text-red-500" />
                        <h3 className="text-base font-semibold">Broken Checks</h3>
                        <Tooltip>
                          <TooltipTrigger>
                            <HelpCircle className="h-4 w-4 text-muted-foreground" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            Failure rate ≥90% — these jobs are likely broken, abandoned, or have a workflow file that needs attention. Delete the job or fix it.
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <CheckHealthTable
                        rows={brokenRows}
                        rateColorClass="text-red-600 dark:text-red-400"
                        now={now}
                        onRowClick={setDrillDownCheck}
                      />
                    </div>
                  )}

                  {flakyRows.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <TriangleAlert className="h-5 w-5 text-orange-500" />
                        <h3 className="text-base font-semibold">Flaky Checks</h3>
                        <Tooltip>
                          <TooltipTrigger>
                            <HelpCircle className="h-4 w-4 text-muted-foreground" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            Failure rate 10–90% — likely intermittent test failures. Click through to see which PRs.
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <CheckHealthTable
                        rows={flakyRows}
                        rateColorClass="text-orange-600 dark:text-orange-400"
                        now={now}
                        onRowClick={setDrillDownCheck}
                      />
                    </div>
                  )}

                  {!showStale && hiddenByStale > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {hiddenByStale} stale {hiddenByStale === 1 ? 'check' : 'checks'} hidden
                      (last run &gt;7 days ago). Toggle &quot;Show stale&quot; to include.
                    </p>
                  )}
                </>
              )
            })()
          )}
        </CardContent>
      </Card>

      {/* Slowest checks */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-blue-500" />
            <CardTitle>Slowest Checks</CardTitle>
            <Tooltip>
              <TooltipTrigger>
                <HelpCircle className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Top 5 check names ranked by average duration. Long-running checks slow down the feedback loop for developers.
              </TooltipContent>
            </Tooltip>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <TableSkeleton columns={2} rows={5} />
          ) : !data || data.slowest_checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No check-run duration data available.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check Name</TableHead>
                  <TableHead className="text-right">Avg Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.slowest_checks.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell>
                      <CheckNameCell name={c.name} url={c.html_url} />
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatDuration(c.avg_duration_s)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <CheckFailuresDialog
        checkName={drillDownCheck}
        onClose={() => setDrillDownCheck(null)}
        dateFrom={dateFrom}
        dateTo={dateTo}
        repoId={selectedRepoId}
      />
    </div>
  )
}
