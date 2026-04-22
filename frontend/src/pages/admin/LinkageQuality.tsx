import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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
import { useIntegrations } from '@/hooks/useIntegrations'
import {
  useLinkageQuality,
  useLinkageRateTrend,
  useRelinkIntegration,
} from '@/hooks/useLinkageQuality'

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'hsl(var(--chart-1))',
  medium: 'hsl(var(--chart-4))',
  low: '#f59e0b',
  unlinked: '#cbd5e1',
}

const SOURCE_LABELS: Record<string, string> = {
  linear_attachment: 'Linear attachment',
  branch: 'Branch name',
  title: 'PR title',
  body: 'PR body',
}

function formatDate(v: string | null | undefined) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleDateString()
  } catch {
    return v
  }
}

export default function LinkageQuality() {
  const { data: integrations } = useIntegrations()
  const linearIntegration = integrations?.find(
    (i) => i.type === 'linear' && i.status === 'active',
  )
  const integrationId = linearIntegration?.id

  const { data, isLoading, isError, refetch } = useLinkageQuality(integrationId)
  const { data: trendData } = useLinkageRateTrend(integrationId, 12)
  const relink = useRelinkIntegration()

  const trendSeries = useMemo(() => {
    if (!trendData) return []
    return trendData.buckets.map((b) => ({
      // Shorter "Apr 1" label — the full ISO date is heavy for a 12-tick x-axis
      label: new Date(b.week_start).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
      }),
      rate: b.linkage_rate != null ? Math.round(b.linkage_rate * 1000) / 10 : null,
      total: b.total,
      linked: b.linked,
    }))
  }, [trendData])

  const confidenceDonut = useMemo(() => {
    if (!data) return []
    const unlinked = Math.max(0, data.total_prs - data.linked_prs)
    const parts = [
      { name: 'High', value: data.by_confidence.high ?? 0, color: CONFIDENCE_COLORS.high },
      { name: 'Medium', value: data.by_confidence.medium ?? 0, color: CONFIDENCE_COLORS.medium },
      { name: 'Low', value: data.by_confidence.low ?? 0, color: CONFIDENCE_COLORS.low },
      { name: 'Unlinked', value: unlinked, color: CONFIDENCE_COLORS.unlinked },
    ]
    return parts.filter((p) => p.value > 0)
  }, [data])

  const sourceBars = useMemo(() => {
    if (!data) return []
    return Object.entries(data.by_source).map(([key, value]) => ({
      source: SOURCE_LABELS[key] ?? key,
      count: value,
    }))
  }, [data])

  if (!linearIntegration) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Linkage Quality</h1>
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertTriangle className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No active Linear integration</p>
              <p className="text-sm text-muted-foreground">
                Connect Linear to see PR↔issue linkage quality.
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
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Linkage Quality</h1>
        <ErrorCard message="Could not load linkage quality data." onRetry={() => refetch()} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Linkage Quality</h1>
          <p className="text-sm text-muted-foreground">
            How well are pull requests connected to Linear issues?
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => integrationId && relink.mutate(integrationId)}
          disabled={!integrationId || relink.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${relink.isPending ? 'animate-spin' : ''}`} />
          {relink.isPending ? 'Rerunning...' : 'Rerun linker'}
        </Button>
      </div>

      {isLoading || !data ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
        </div>
      ) : (
        <>
          {/* Summary stats */}
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard title="Total PRs" value={data.total_prs} />
            <StatCard title="Linked PRs" value={data.linked_prs} />
            <StatCard
              title="Linkage Rate"
              value={`${(data.linkage_rate * 100).toFixed(1)}%`}
              tooltip="Share of PRs linked to at least one Linear issue"
            />
          </div>

          {/* Donut + source breakdown side by side */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By Confidence</CardTitle>
              </CardHeader>
              <CardContent>
                {confidenceDonut.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    No PR data yet.
                  </p>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={240}>
                      <PieChart>
                        <Pie
                          data={confidenceDonut}
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={90}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {confidenceDonut.map((entry) => (
                            <Cell key={entry.name} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'hsl(var(--card))',
                            border: '1px solid hsl(var(--border))',
                            borderRadius: '6px',
                            fontSize: '12px',
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="mt-2 flex flex-wrap justify-center gap-3 text-xs">
                      {confidenceDonut.map((d) => (
                        <div key={d.name} className="flex items-center gap-1.5">
                          <div
                            className="h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: d.color }}
                          />
                          <span className="text-muted-foreground">
                            {d.name} ({d.value})
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">By Source</CardTitle>
              </CardHeader>
              <CardContent>
                {sourceBars.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    No source data yet.
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={sourceBars} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis type="number" tick={{ fontSize: 11 }} />
                      <YAxis
                        type="category"
                        dataKey="source"
                        tick={{ fontSize: 11 }}
                        width={130}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'hsl(var(--card))',
                          border: '1px solid hsl(var(--border))',
                          borderRadius: '6px',
                          fontSize: '12px',
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: '11px' }} />
                      <Bar
                        dataKey="count"
                        name="PR links"
                        fill="hsl(var(--chart-1))"
                        radius={[0, 4, 4, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 12-week linkage-rate trend */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Linkage rate — last 12 weeks</CardTitle>
              <p className="text-xs text-muted-foreground">
                Weekly share of PRs created that got linked to a Linear issue.
                Low weeks with few PRs (see dot sizes) are less meaningful than
                low weeks with high volume.
              </p>
            </CardHeader>
            <CardContent>
              {trendSeries.length === 0 || trendSeries.every((p) => p.total === 0) ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Not enough PR history to chart.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={trendSeries}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      domain={[0, 100]}
                      unit="%"
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '6px',
                        fontSize: '12px',
                      }}
                      formatter={(value, _name, item) => {
                        const payload = (item?.payload ?? {}) as {
                          linked: number
                          total: number
                        }
                        if (value == null) return ['no PRs', 'Rate']
                        return [
                          `${value}% (${payload.linked}/${payload.total})`,
                          'Linkage rate',
                        ]
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="rate"
                      name="Linkage rate"
                      stroke="hsl(var(--chart-1))"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      connectNulls={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Unlinked PRs table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Unlinked PRs (last 30 days)</CardTitle>
              <p className="text-xs text-muted-foreground">
                Recent merged PRs without a Linear issue — process gaps to close.
              </p>
            </CardHeader>
            <CardContent>
              {data.unlinked_recent.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  All recent PRs linked — nice.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>PR</TableHead>
                      <TableHead>Author</TableHead>
                      <TableHead>Repo</TableHead>
                      <TableHead>Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.unlinked_recent.map((pr) => (
                      <TableRow key={pr.pr_id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {pr.html_url ? (
                              <a
                                href={pr.html_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                              >
                                #{pr.number} {pr.title}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            ) : (
                              <span>#{pr.number} {pr.title}</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{pr.author_github_username ?? '—'}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {pr.repo}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(pr.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Disagreement PRs */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Multi-link PRs</CardTitle>
              <p className="text-xs text-muted-foreground">
                PRs with multiple issue links at the same confidence — either legitimate
                multi-issue work or confused linking.
              </p>
            </CardHeader>
            <CardContent>
              {data.disagreement_prs.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No disagreements detected.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>PR</TableHead>
                      <TableHead>Repo</TableHead>
                      <TableHead>Linked issues</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.disagreement_prs.map((pr) => (
                      <TableRow key={pr.pr_id}>
                        <TableCell>
                          {pr.html_url ? (
                            <a
                              href={pr.html_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                            >
                              #{pr.number} {pr.title}
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          ) : (
                            <span>#{pr.number} {pr.title}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {pr.repo}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {pr.links.map((link) => (
                              <Badge
                                key={`${link.external_issue_id}-${link.link_source}`}
                                variant="outline"
                                className="font-mono text-[10px]"
                              >
                                {link.identifier} &middot; {link.link_source} &middot;{' '}
                                {link.link_confidence}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}

    </div>
  )
}
