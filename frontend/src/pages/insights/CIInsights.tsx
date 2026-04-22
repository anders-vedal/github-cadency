import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useCIStats } from '@/hooks/useStats'
import { useRepos } from '@/hooks/useSync'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle, Clock, TriangleAlert, ExternalLink } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
  return `${(seconds / 3600).toFixed(1)}h`
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

export default function CIInsights() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: repos } = useRepos()
  const [searchParams] = useSearchParams()
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(
    Number(searchParams.get('repo_id')) || null,
  )

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

      {/* Flaky checks */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <TriangleAlert className="h-5 w-5 text-orange-500" />
            <CardTitle>Flaky Checks</CardTitle>
            <Tooltip>
              <TooltipTrigger>
                <HelpCircle className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Check names with a failure rate above 10% (minimum 5 runs). These likely indicate flaky tests that fail intermittently.
              </TooltipContent>
            </Tooltip>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <TableSkeleton columns={3} rows={3} />
          ) : !data || data.flaky_checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No flaky checks detected in this period.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check Name</TableHead>
                  <TableHead className="text-right">Failure Rate</TableHead>
                  <TableHead className="text-right">Total Runs</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.flaky_checks.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell>
                      <CheckNameCell name={c.name} url={c.html_url} />
                    </TableCell>
                    <TableCell className="text-right font-medium text-red-600 dark:text-red-400">
                      {(c.failure_rate * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell className="text-right">{c.total_runs}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
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
    </div>
  )
}
