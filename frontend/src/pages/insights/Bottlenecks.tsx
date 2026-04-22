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
import {
  AlertCircle,
  AlertTriangle,
  ExternalLink,
  Users,
} from 'lucide-react'
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
import StatCard from '@/components/StatCard'
import ErrorCard from '@/components/ErrorCard'
import CumulativeFlowDiagram from '@/components/charts/CumulativeFlowDiagram'
import LorenzCurve from '@/components/charts/LorenzCurve'
import { useDateRange } from '@/hooks/useDateRange'
import { useIntegrations } from '@/hooks/useIntegrations'
import {
  useBlockedChains,
  useBottleneckSummary,
  useBusFactorFiles,
  useCrossTeamHandoffs,
  useCumulativeFlow,
  useCycleHistogram,
  useReviewLoad,
  useReviewNetwork,
  useReviewPingPong,
  useWip,
} from '@/hooks/useBottlenecks'
import { cn } from '@/lib/utils'

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'border-red-500/40 bg-red-500/5',
  warning: 'border-amber-500/40 bg-amber-500/5',
  info: 'border-blue-500/40 bg-blue-500/5',
}

const SEVERITY_ICON: Record<string, string> = {
  critical: 'text-red-600',
  warning: 'text-amber-600',
  info: 'text-blue-600',
}

export default function Bottlenecks() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: integrations } = useIntegrations()
  const hasLinear = integrations?.some(
    (i) => i.type === 'linear' && i.status === 'active',
  )

  const { data: summary, isLoading: summaryLoading, isError, refetch } =
    useBottleneckSummary()
  const { data: cfd } = useCumulativeFlow(undefined, undefined, dateFrom, dateTo)
  const { data: wip } = useWip(4)
  const { data: reviewLoad } = useReviewLoad(dateFrom, dateTo)
  const { data: reviewNetwork } = useReviewNetwork(dateFrom, dateTo)
  const { data: crossTeam } = useCrossTeamHandoffs(dateFrom, dateTo)
  const { data: blockedChains } = useBlockedChains()
  const { data: pingPong } = useReviewPingPong(dateFrom, dateTo)
  const { data: busFactor } = useBusFactorFiles(90, 2)
  const { data: cycleHist } = useCycleHistogram(dateFrom, dateTo)

  // WIP bar chart data
  const wipBars = useMemo(() => {
    return (wip ?? []).map((w) => ({
      name: w.developer_name,
      count: w.in_progress_count,
      threshold: w.threshold,
    }))
  }, [wip])

  // Review network silo classification — simple component count via BFS
  const siloClusters = useMemo(() => {
    if (!reviewNetwork || reviewNetwork.nodes.length === 0) return []
    const adj = new Map<number, Set<number>>()
    for (const n of reviewNetwork.nodes) adj.set(n.id, new Set())
    for (const e of reviewNetwork.edges) {
      adj.get(e.reviewer_id)?.add(e.author_id)
      adj.get(e.author_id)?.add(e.reviewer_id)
    }
    const visited = new Set<number>()
    const clusters: { size: number; node_ids: number[] }[] = []
    for (const n of reviewNetwork.nodes) {
      if (visited.has(n.id)) continue
      const stack = [n.id]
      const members: number[] = []
      while (stack.length > 0) {
        const cur = stack.pop()!
        if (visited.has(cur)) continue
        visited.add(cur)
        members.push(cur)
        const neighbors = adj.get(cur)
        if (neighbors) for (const nb of neighbors) if (!visited.has(nb)) stack.push(nb)
      }
      clusters.push({ size: members.length, node_ids: members })
    }
    return clusters.sort((a, b) => b.size - a.size)
  }, [reviewNetwork])

  if (!hasLinear) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Bottlenecks</h1>
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertTriangle className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No Linear integration configured</p>
              <p className="text-sm text-muted-foreground">
                Bottleneck intelligence needs Linear issue data to work.
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
    return <ErrorCard message="Could not load bottleneck data." onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Bottlenecks</h1>
        <p className="text-sm text-muted-foreground">
          Where work is stuck, who is overloaded, and where teams are silo'd.
        </p>
      </div>

      {/* Summary digest */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Current top bottlenecks</CardTitle>
        </CardHeader>
        <CardContent>
          {summaryLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : !summary || summary.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No active bottlenecks detected.
            </p>
          ) : (
            <div className="space-y-2">
              {summary.map((item, i) => (
                <Link
                  key={i}
                  to={item.drill_path}
                  className={cn(
                    'flex items-start gap-3 rounded-md border px-3 py-2 transition-colors hover:bg-muted/50',
                    SEVERITY_STYLES[item.severity] ?? '',
                  )}
                >
                  <AlertCircle
                    className={cn(
                      'mt-0.5 h-4 w-4 shrink-0',
                      SEVERITY_ICON[item.severity] ?? 'text-muted-foreground',
                    )}
                  />
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium">{item.title}</div>
                    <div className="text-xs text-muted-foreground">{item.detail}</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cycle histogram stats */}
      {cycleHist && cycleHist.sample_size > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard title="Sample size" value={cycleHist.sample_size} subtitle="PRs in range" />
          <StatCard
            title="Median cycle time"
            value={formatDuration(cycleHist.p50_s)}
          />
          <StatCard
            title="p90 cycle time"
            value={formatDuration(cycleHist.p90_s)}
            subtitle={cycleHist.bimodal_analysis.is_bimodal ? 'Bimodal — investigate' : undefined}
          />
        </div>
      )}

      {/* Cumulative Flow Diagram */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cumulative Flow</CardTitle>
          <p className="text-xs text-muted-foreground">
            Issues in each status over time. Widening bands = flow problem.
          </p>
        </CardHeader>
        <CardContent>
          <CumulativeFlowDiagram data={cfd ?? []} />
        </CardContent>
      </Card>

      {/* WIP per developer */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">WIP per developer (&gt; 4)</CardTitle>
          <p className="text-xs text-muted-foreground">
            Developers with more than 4 concurrent in-progress issues.
          </p>
        </CardHeader>
        <CardContent>
          {wipBars.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nobody's above the WIP threshold.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(200, wipBars.length * 30)}>
              <BarChart data={wipBars} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  width={120}
                />
                <Tooltip />
                <Bar dataKey="count" name="In-progress" fill="hsl(var(--chart-4))" radius={[0, 4, 4, 0]}>
                  {wipBars.map((_, i) => (
                    <Cell key={i} fill="hsl(var(--chart-4))" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Review load Gini + Lorenz curve + top reviewers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Review load distribution</CardTitle>
          <p className="text-xs text-muted-foreground">
            How evenly are code reviews distributed across reviewers?
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {!reviewLoad ? (
            <Skeleton className="h-60 w-full" />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <StatCard title="Gini" value={reviewLoad.gini.toFixed(3)} />
                <StatCard title="Total reviews" value={reviewLoad.total_reviews} />
                <StatCard
                  title="Top-K share"
                  value={`${Math.round(reviewLoad.top_k_share * 100)}%`}
                  subtitle="of reviews done by top reviewers"
                />
              </div>
              <LorenzCurve
                values={reviewLoad.top_reviewers.map((r) => r.review_count)}
                gini={reviewLoad.gini}
              />
              {reviewLoad.top_reviewers.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Reviewer</TableHead>
                      <TableHead className="text-right">Reviews</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reviewLoad.top_reviewers.map((r) => (
                      <TableRow key={r.reviewer_id}>
                        <TableCell>
                          <Link
                            to={`/team/${r.reviewer_id}`}
                            className="font-medium hover:underline"
                          >
                            {r.reviewer_name}
                          </Link>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {r.review_count}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Review network — table fallback */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Review network</CardTitle>
          <p className="text-xs text-muted-foreground">
            Reviewer clusters — groups that mostly review each other. Components of size 1-2
            signal silos.
          </p>
        </CardHeader>
        <CardContent>
          {!reviewNetwork || reviewNetwork.nodes.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No review network data.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="text-xs text-muted-foreground">
                {reviewNetwork.nodes.length} nodes, {reviewNetwork.edges.length} edges,{' '}
                {siloClusters.length} connected component
                {siloClusters.length === 1 ? '' : 's'}
              </div>
              <div className="space-y-1.5">
                {siloClusters.slice(0, 10).map((cluster, i) => {
                  const members = cluster.node_ids
                    .map((id) => reviewNetwork.nodes.find((n) => n.id === id))
                    .filter((n): n is NonNullable<typeof n> => !!n)
                  const isSilo = cluster.size <= 2
                  return (
                    <div
                      key={i}
                      className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
                    >
                      <Users className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">
                        Cluster {i + 1} &middot; {cluster.size} dev
                        {cluster.size === 1 ? '' : 's'}
                      </span>
                      {isSilo && (
                        <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
                          Silo
                        </Badge>
                      )}
                      <div className="flex flex-wrap gap-1">
                        {members.slice(0, 10).map((m) => (
                          <Link
                            key={m.id}
                            to={`/team/${m.id}`}
                            className="text-xs text-muted-foreground hover:underline"
                          >
                            {m.name}
                          </Link>
                        ))}
                        {members.length > 10 && (
                          <span className="text-xs text-muted-foreground">
                            +{members.length - 10}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cross-team handoffs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cross-team handoffs</CardTitle>
          <p className="text-xs text-muted-foreground">
            Issues that moved between teams. Time in transit = friction.
          </p>
        </CardHeader>
        <CardContent>
          {!crossTeam || crossTeam.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No cross-team handoffs in this range.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Issue</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>To</TableHead>
                  <TableHead>When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {crossTeam.slice(0, 30).map((row) => (
                  <TableRow key={`${row.issue_id}-${row.changed_at}`}>
                    <TableCell>
                      <span className="font-mono text-xs text-muted-foreground">
                        {row.identifier ?? '—'}
                      </span>
                      <span className="ml-2">{row.title ?? '—'}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.from_team ?? '—'}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{row.to_team ?? '—'}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {row.changed_at ? new Date(row.changed_at).toLocaleDateString() : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Blocked chains */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Blocked chains</CardTitle>
          <p className="text-xs text-muted-foreground">
            Open issues in dependency chains of depth 3+.
          </p>
        </CardHeader>
        <CardContent>
          {!blockedChains || blockedChains.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No deep dependency chains.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Issue</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Chain depth</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {blockedChains.map((r) => (
                  <TableRow key={r.issue_id}>
                    <TableCell>
                      <span className="font-mono text-xs text-muted-foreground">
                        {r.identifier}
                      </span>
                      <span className="ml-2">{r.title}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs capitalize">
                        {(r.status ?? 'unknown').replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Badge variant="secondary">{r.blocker_depth}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Ping-pong PRs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Review ping-pong</CardTitle>
          <p className="text-xs text-muted-foreground">
            Open PRs with more than 3 review rounds.
          </p>
        </CardHeader>
        <CardContent>
          {!pingPong || pingPong.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No ping-pong PRs.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>PR</TableHead>
                  <TableHead>Repo</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead className="text-right">Rounds</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pingPong.map((r) => (
                  <TableRow key={r.pr_id}>
                    <TableCell>
                      {r.html_url ? (
                        <a
                          href={r.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                        >
                          #{r.number} {r.title}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span>
                          #{r.number} {r.title}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.repo ?? '—'}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs capitalize">
                        {r.state}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Badge variant="secondary">{r.review_round_count}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Bus factor files */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Single-owner files</CardTitle>
          <p className="text-xs text-muted-foreground">
            Files touched by only one author in the last 90 days.
          </p>
        </CardHeader>
        <CardContent>
          {!busFactor || busFactor.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No single-owner files detected.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead className="text-right">Authors</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {busFactor.slice(0, 30).map((row) => (
                  <TableRow key={row.filename}>
                    <TableCell className="font-mono text-xs">{row.filename}</TableCell>
                    <TableCell className="text-xs">{row.owner_name ?? '—'}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.distinct_authors}
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
