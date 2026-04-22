import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AlertTriangle, ExternalLink, Info } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import ErrorCard from '@/components/ErrorCard'
import DistributionStatCard from '@/components/DistributionStatCard'
import { useDateRange } from '@/hooks/useDateRange'
import { useIntegrations } from '@/hooks/useIntegrations'
import {
  useFlowReadiness,
  useRefinementChurn,
  useStatusRegressions,
  useStatusTimeDistribution,
  useTriageBounces,
} from '@/hooks/useFlowAnalytics'
import type { StatusTimeDistribution, TriageBounce } from '@/utils/types'

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

function StatusTimeHeatmap({ rows }: { rows: StatusTimeDistribution[] }) {
  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No data</p>
  }
  const maxP50 = Math.max(...rows.map((r) => r.p50_s), 1)
  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const ratio = row.p50_s > 0 ? row.p90_s / row.p50_s : 1
        // color = red if p90/p50 ratio high (volatile), green if low (consistent)
        const volatility =
          ratio > 3
            ? 'bg-red-500/40'
            : ratio > 2
              ? 'bg-amber-500/40'
              : 'bg-emerald-500/40'
        const widthPct = Math.round((row.p50_s / maxP50) * 100)
        return (
          <div
            key={row.status_category}
            className="grid grid-cols-[140px_1fr_auto] items-center gap-3 text-sm"
          >
            <span className="font-medium capitalize">
              {row.status_category.replace('_', ' ')}
            </span>
            <div className="h-6 rounded bg-muted/30">
              <div
                className={`h-full rounded ${volatility}`}
                style={{ width: `${widthPct}%` }}
              />
            </div>
            <span className="whitespace-nowrap text-xs text-muted-foreground tabular-nums">
              p50 {formatDuration(row.p50_s)} &middot; p90 {formatDuration(row.p90_s)} &middot;{' '}
              n={row.sample_size}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function TriageBouncesByCreator({ bounces }: { bounces: TriageBounce[] }) {
  // Bucket by identifier prefix as a proxy for creator grouping
  const buckets = useMemo(() => {
    const counts = new Map<string, number>()
    for (const b of bounces) {
      const prefix = b.identifier.split('-')[0] || '?'
      counts.set(prefix, (counts.get(prefix) ?? 0) + 1)
    }
    return Array.from(counts.entries())
      .map(([prefix, count]) => ({ prefix, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10)
  }, [bounces])

  if (buckets.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No triage bounces — nice.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={buckets}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="prefix" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Bar dataKey="count" name="Bounced issues" fill="hsl(var(--chart-4))" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function FlowAnalytics() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: integrations } = useIntegrations()
  const hasLinear = integrations?.some(
    (i) => i.type === 'linear' && i.status === 'active',
  )

  const { data: readiness } = useFlowReadiness({ enabled: !!hasLinear })
  const { data: distribution, isLoading: distLoading, isError, refetch } =
    useStatusTimeDistribution(dateFrom, dateTo, 'all', { enabled: !!hasLinear })
  const { data: regressions } = useStatusRegressions(dateFrom, dateTo, {
    enabled: !!hasLinear,
  })
  const { data: triageBounces } = useTriageBounces(dateFrom, dateTo, {
    enabled: !!hasLinear,
  })
  const { data: churn } = useRefinementChurn(dateFrom, dateTo, {
    enabled: !!hasLinear,
  })

  if (!hasLinear) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Flow Analytics</h1>
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertTriangle className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No Linear integration configured</p>
              <p className="text-sm text-muted-foreground">
                Flow analytics requires Linear issue history.
              </p>
            </div>
            <Link
              to="/admin/integrations"
              className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
            >
              Go to Integration Settings &rarr;
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isError) {
    return <ErrorCard message="Could not load flow analytics." onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Flow Analytics</h1>
        <p className="text-sm text-muted-foreground">
          Time in status, regressions, triage bounces, and refinement churn.
        </p>
      </div>

      {/* Readiness banner — only show when not ready */}
      {readiness && !readiness.ready && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="flex items-start gap-3 py-4">
            <Info className="mt-0.5 h-5 w-5 text-amber-600" />
            <div className="space-y-1">
              <p className="font-medium">Not enough history yet</p>
              <p className="text-sm text-muted-foreground">
                Flow analytics unlocks after {readiness.threshold_days} days of history
                and {readiness.threshold_issues} issues with history events. You currently
                have {readiness.days_of_history} days and {readiness.issues_with_history}{' '}
                issues tracked. The page stays visible so you can watch it fill in.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Status time heatmap */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Status time distribution</CardTitle>
          <p className="text-xs text-muted-foreground">
            Median time in each status. Color = p90/p50 ratio (red = volatile, green =
            consistent).
          </p>
        </CardHeader>
        <CardContent>
          {distLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <StatusTimeHeatmap rows={distribution ?? []} />
          )}
        </CardContent>
      </Card>

      {/* Per-state distribution cards — surfaces p50 + p90 per status with the
          p90/p50 volatility cue. Repeats the heatmap's data but as scannable
          cards for the Phase 11 governance "distribution-first" principle. */}
      {distribution && distribution.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {distribution.map((row) => {
            const ratio = row.p50_s > 0 ? row.p90_s / row.p50_s : 1
            const shapeLabel =
              ratio > 3 ? 'volatile' : ratio > 2 ? 'spread' : 'consistent'
            return (
              <DistributionStatCard
                key={row.status_category}
                title={row.status_category.replace('_', ' ')}
                p50={formatDuration(row.p50_s)}
                p90={formatDuration(row.p90_s)}
                shapeLabel={shapeLabel}
                tooltip={`Time issues spend in ${row.status_category.replace('_', ' ')}. n=${row.sample_size}.`}
              />
            )
          })}
        </div>
      )}

      {/* Regressions table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Status regressions</CardTitle>
          <p className="text-xs text-muted-foreground">
            Issues that went backwards (in-progress → todo, in-review → in-progress,
            done → in-progress). Who's sending work back?
          </p>
        </CardHeader>
        <CardContent>
          {!regressions || regressions.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No regressions detected.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Issue</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>To</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {regressions.slice(0, 50).map((r) => (
                  <TableRow key={`${r.issue_id}-${r.changed_at}`}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">
                          {r.identifier}
                        </span>
                        {r.url ? (
                          <a
                            href={r.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 hover:underline"
                          >
                            <span className="truncate">{r.title}</span>
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </a>
                        ) : (
                          <span className="truncate">{r.title}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs capitalize">
                        {r.from_status.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="text-xs capitalize">
                        {r.to_status.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">{r.actor_name ?? '—'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.changed_at ? new Date(r.changed_at).toLocaleDateString() : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Triage bounces */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Triage quality</CardTitle>
          <p className="text-xs text-muted-foreground">
            Issues that left triage, then came back. By team prefix.
          </p>
        </CardHeader>
        <CardContent>
          <TriageBouncesByCreator bounces={triageBounces ?? []} />
          {triageBounces && triageBounces.length > 0 && (
            <>
              <div className="mt-4 text-xs text-muted-foreground">
                {triageBounces.length} bouncing issue
                {triageBounces.length === 1 ? '' : 's'}
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Issue</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {triageBounces.slice(0, 20).map((b) => (
                    <TableRow key={b.issue_id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-muted-foreground">
                            {b.identifier}
                          </span>
                          {b.url ? (
                            <a
                              href={b.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 hover:underline"
                            >
                              {b.title}
                              <ExternalLink className="h-3 w-3 text-muted-foreground" />
                            </a>
                          ) : (
                            <span>{b.title}</span>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Refinement churn */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Refinement churn</CardTitle>
          <p className="text-xs text-muted-foreground">
            Estimate, priority, or project changes between issue creation and work start
            — high churn = unsettled scope before work began.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {!churn ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-md border px-3 py-2">
                  <div className="text-xs text-muted-foreground">p50</div>
                  <div className="text-xl font-semibold">{churn.distribution.p50}</div>
                </div>
                <div className="rounded-md border px-3 py-2">
                  <div className="text-xs text-muted-foreground">p90</div>
                  <div className="text-xl font-semibold">{churn.distribution.p90}</div>
                </div>
                <div className="rounded-md border px-3 py-2">
                  <div className="text-xs text-muted-foreground">Issues with churn</div>
                  <div className="text-xl font-semibold">
                    {churn.distribution.total_issues_with_churn}
                  </div>
                </div>
              </div>

              {churn.top.length > 0 && (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={churn.top.slice(0, 20)}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis dataKey="identifier" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="churn_events" name="Churn events" radius={[4, 4, 0, 0]}>
                        {churn.top.slice(0, 20).map((_, i) => (
                          <Cell key={i} fill="hsl(var(--chart-4))" />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Issue</TableHead>
                        <TableHead className="text-right">Churn events</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {churn.top.slice(0, 20).map((row) => (
                        <TableRow key={row.issue_id}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs text-muted-foreground">
                                {row.identifier}
                              </span>
                              {row.url ? (
                                <a
                                  href={row.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 hover:underline"
                                >
                                  {row.title}
                                  <ExternalLink className="h-3 w-3 text-muted-foreground" />
                                </a>
                              ) : (
                                <span>{row.title}</span>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            <Badge variant="outline">{row.churn_events}</Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
