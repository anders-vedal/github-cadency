import { useMemo, useId } from 'react'
import { useDateRange } from '@/hooks/useDateRange'
import {
  useTeamStats,
  useWorkAllocation,
  useCollaboration,
  useCollaborationTrends,
  useWorkload,
  useRiskSummary,
  useStalePRs,
  useCIStats,
  useAllDeveloperStats,
} from '@/hooks/useStats'
import { useDevelopers } from '@/hooks/useDevelopers'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import ErrorCard from '@/components/ErrorCard'
import MetricsUsageBanner from '@/components/MetricsUsageBanner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  LineChart,
  Line,
} from 'recharts'
import { HelpCircle, AlertTriangle, ShieldAlert, Users, TrendingDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { riskLevelLabels, riskLevelStyles } from '@/utils/types'
import type { RiskLevel, DeveloperStatsWithPercentiles } from '@/utils/types'

import { FALLBACK_CATEGORY_CONFIG, FALLBACK_CATEGORY_ORDER } from '@/utils/categoryConfig'
import { useCategoryConfig } from '@/hooks/useWorkCategories'

const tooltipStyle = {
  backgroundColor: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '6px',
  fontSize: '12px',
}

const workloadScoreColors: Record<string, string> = {
  low: 'bg-blue-500/10 text-blue-600',
  balanced: 'bg-emerald-500/10 text-emerald-600',
  high: 'bg-amber-500/10 text-amber-600',
  overloaded: 'bg-red-500/10 text-red-600',
}

// --- Helpers ---

function computePreviousPeriod(dateFrom: string, dateTo: string) {
  const from = new Date(dateFrom)
  const to = new Date(dateTo)
  const durationMs = to.getTime() - from.getTime()
  const prevTo = new Date(from.getTime() - 86_400_000)
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

function fmtHours(h: number | null | undefined): string {
  if (h == null) return '-'
  if (h < 1) return `${Math.round(h * 60)}m`
  if (h < 24) return `${h.toFixed(1)}h`
  return `${(h / 24).toFixed(1)}d`
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '-'
  return `${(v * 100).toFixed(1)}%`
}

// --- Main component ---

export default function ExecutiveDashboard() {
  const { dateFrom, dateTo } = useDateRange()
  const { prevFrom, prevTo } = useMemo(
    () => computePreviousPeriod(dateFrom, dateTo),
    [dateFrom, dateTo],
  )
  const pieId = useId()
  const catConfig = useCategoryConfig()
  const CATEGORY_CONFIG = catConfig?.config ?? FALLBACK_CATEGORY_CONFIG
  const CATEGORY_ORDER = catConfig?.order ?? FALLBACK_CATEGORY_ORDER

  // Data fetching — all in parallel, each section handles its own loading
  const { data: stats, isLoading: statsLoading, isError: statsError, refetch: refetchStats } = useTeamStats(undefined, dateFrom, dateTo)
  const { data: prevStats } = useTeamStats(undefined, prevFrom, prevTo)
  const { data: allocation, isLoading: allocLoading } = useWorkAllocation(undefined, dateFrom, dateTo)
  const { data: collab, isLoading: collabLoading } = useCollaboration(undefined, dateFrom, dateTo)
  const { data: collabTrends, isLoading: collabTrendsLoading } = useCollaborationTrends(undefined, dateFrom, dateTo)
  const { data: workload, isLoading: workloadLoading } = useWorkload(undefined, dateFrom, dateTo)
  const { data: risk, isLoading: riskLoading } = useRiskSummary(undefined, dateFrom, dateTo, 'high', 'all')
  const { data: stalePRs } = useStalePRs()
  const { data: ciStats } = useCIStats(dateFrom, dateTo)
  const { data: developers } = useDevelopers()

  // Previous period developer stats for decline detection
  const developerIds = useMemo(() => developers?.map((d) => d.id) ?? [], [developers])
  const currentDevStats = useAllDeveloperStats(developerIds, dateFrom, dateTo)
  const prevDevStats = useAllDeveloperStats(developerIds, prevFrom, prevTo)

  // --- Computed: Declining developers ---
  const decliningDevs = useMemo(() => {
    if (!developers || developerIds.length === 0) return []
    const result: Array<{ name: string; id: number; reasons: string[] }> = []
    for (let i = 0; i < developerIds.length; i++) {
      const curr = currentDevStats[i]?.data as DeveloperStatsWithPercentiles | undefined
      const prev = prevDevStats[i]?.data as DeveloperStatsWithPercentiles | undefined
      if (!curr || !prev) continue
      const reasons: string[] = []
      // PRs merged drop > 30%
      if (prev.prs_merged > 0 && curr.prs_merged < prev.prs_merged * 0.7) {
        const drop = Math.round((1 - curr.prs_merged / prev.prs_merged) * 100)
        reasons.push(`PRs merged down ${drop}%`)
      }
      // Review quality score drop > 20%
      if (
        prev.review_quality_score != null &&
        curr.review_quality_score != null &&
        prev.review_quality_score > 0 &&
        curr.review_quality_score < prev.review_quality_score * 0.8
      ) {
        const drop = Math.round((1 - curr.review_quality_score / prev.review_quality_score) * 100)
        reasons.push(`Review quality down ${drop}%`)
      }
      if (reasons.length > 0) {
        result.push({ name: developers[i].display_name, id: developers[i].id, reasons })
      }
    }
    return result
  }, [developers, developerIds, currentDevStats, prevDevStats])

  // --- Computed: Investment donut data ---
  const prDonutData = useMemo(() => {
    if (!allocation) return []
    return allocation.pr_allocation
      .filter((a) => a.count > 0)
      .map((a) => ({
        name: CATEGORY_CONFIG[a.category]?.label ?? a.category,
        value: a.count,
        color: CATEGORY_CONFIG[a.category]?.color ?? '#94a3b8',
      }))
  }, [allocation])

  const trendData = useMemo(() => {
    if (!allocation) return []
    return allocation.trend.map((p) => ({
      label: p.period_label,
      ...Object.fromEntries(
        CATEGORY_ORDER.map((cat) => [cat, p.pr_categories[cat] ?? 0]),
      ),
    }))
  }, [allocation])

  // --- Computed: Workload distribution ---
  const workloadDistribution = useMemo(() => {
    if (!workload) return null
    const counts = { low: 0, balanced: 0, high: 0, overloaded: 0 }
    for (const dev of workload.developers) {
      counts[dev.workload_score] = (counts[dev.workload_score] ?? 0) + 1
    }
    return counts
  }, [workload])

  // --- Computed: Collaboration trend chart data ---
  const collabTrendData = useMemo(() => {
    if (!collabTrends) return []
    return collabTrends.periods.map((p) => ({
      label: p.period_label,
      'Bus Factors': p.bus_factor_count,
      Silos: p.silo_count,
      Isolated: p.isolated_developer_count,
    }))
  }, [collabTrends])

  if (statsError) {
    return <ErrorCard message="Failed to load executive dashboard data." onRetry={refetchStats} />
  }

  return (
    <div className="space-y-8">
      <MetricsUsageBanner />
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Executive Dashboard</h1>
        <Tooltip>
          <TooltipTrigger>
            <HelpCircle className="h-4 w-4 text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            <p>Strategic team health view for directors and VPs. Shows velocity, investment allocation, quality indicators, team health signals, and risk. All deltas compare selected period vs same-duration previous period.</p>
          </TooltipContent>
        </Tooltip>
      </div>

      {/* ===== Section 1: Team Velocity ===== */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Team Velocity</h2>
        {statsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </div>
        ) : stats ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                title="PRs Merged"
                value={stats.total_merged}
                tooltip="Total pull requests merged in the selected period."
                trend={computeTrend(stats.total_merged, prevStats?.total_merged)}
              />
              <StatCard
                title="Merge Rate"
                value={fmtPct(stats.merge_rate)}
                tooltip="Percentage of opened PRs that were merged."
                trend={computeTrend(stats.merge_rate, prevStats?.merge_rate)}
              />
              <StatCard
                title="Avg Time to Merge"
                value={fmtHours(stats.avg_time_to_merge_hours)}
                tooltip="Average hours from PR open to merge."
                trend={computeTrend(stats.avg_time_to_merge_hours, prevStats?.avg_time_to_merge_hours, true)}
              />
              <StatCard
                title="Avg Time to First Review"
                value={fmtHours(stats.avg_time_to_first_review_hours)}
                tooltip="Average hours from PR open to first review."
                trend={computeTrend(stats.avg_time_to_first_review_hours, prevStats?.avg_time_to_first_review_hours, true)}
              />
            </div>

            {/* Weekly velocity from allocation trend */}
            {allocation && allocation.trend.length > 1 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    PRs Merged Over Time ({allocation.period_type === 'weekly' ? 'Weekly' : 'Monthly'})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="label" fontSize={12} stroke="hsl(var(--muted-foreground))" />
                      <YAxis fontSize={12} stroke="hsl(var(--muted-foreground))" />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      {CATEGORY_ORDER.filter((c) => c !== 'unknown').map((cat) => (
                        <Bar key={cat} dataKey={cat} stackId="a" name={CATEGORY_CONFIG[cat].label} fill={CATEGORY_CONFIG[cat].color} />
                      ))}
                      <Bar dataKey="unknown" stackId="a" name="Unknown" fill="#94a3b8" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
          </>
        ) : null}
      </section>

      {/* ===== Section 2: Investment Allocation ===== */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Investment Allocation</h2>
        {allocLoading ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Card><CardContent className="h-[260px]" /></Card>
            <Card><CardContent className="h-[260px]" /></Card>
          </div>
        ) : allocation && allocation.total_prs > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  PR Allocation by Category
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative">
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={prDonutData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {prDonutData.map((entry) => (
                          <Cell key={`${pieId}-${entry.name}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <RechartsTooltip
                        contentStyle={tooltipStyle}
                        formatter={((value: number, name: string) => {
                          const total = prDonutData.reduce((s, d) => s + d.value, 0)
                          return [`${value} (${((value / total) * 100).toFixed(0)}%)`, name]
                        }) as never}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <div className="text-2xl font-bold">{allocation.total_prs}</div>
                      <div className="text-[10px] text-muted-foreground">PRs</div>
                    </div>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap justify-center gap-3">
                  {prDonutData.map((d) => (
                    <div key={d.name} className="flex items-center gap-1.5 text-xs">
                      <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                      <span className="text-muted-foreground">{d.name} ({d.value})</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {trendData.length > 1 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Allocation Trend ({allocation.period_type === 'weekly' ? 'Weekly' : 'Monthly'})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="label" fontSize={12} stroke="hsl(var(--muted-foreground))" />
                      <YAxis fontSize={12} stroke="hsl(var(--muted-foreground))" />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      <Legend />
                      {CATEGORY_ORDER.filter((c) => c !== 'unknown').map((cat) => (
                        <Bar key={cat} dataKey={cat} stackId="a" name={CATEGORY_CONFIG[cat].label} fill={CATEGORY_CONFIG[cat].color} />
                      ))}
                      <Bar dataKey="unknown" stackId="a" name="Unknown" fill="#94a3b8" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              No merged PRs in this period.
            </CardContent>
          </Card>
        )}
      </section>

      {/* ===== Section 3: Quality Indicators ===== */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Quality Indicators</h2>
        {statsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </div>
        ) : stats ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Revert Rate"
              value={fmtPct(stats.revert_rate)}
              tooltip="Percentage of merged PRs that are reverts. Lower is better."
              trend={computeTrend(stats.revert_rate, prevStats?.revert_rate, true)}
            />
            <StatCard
              title="Reviews Given"
              value={stats.total_reviews}
              tooltip="Total review events submitted by the team."
              trend={computeTrend(stats.total_reviews, prevStats?.total_reviews)}
            />
            <StatCard
              title="Issues Closed"
              value={stats.total_issues_closed}
              tooltip="Total issues closed in the selected period."
              trend={computeTrend(stats.total_issues_closed, prevStats?.total_issues_closed)}
            />
            {ciStats ? (
              <StatCard
                title="CI Failure Rate"
                value={
                  ciStats.prs_merged_with_failing_checks > 0 && stats.total_merged > 0
                    ? fmtPct(ciStats.prs_merged_with_failing_checks / stats.total_merged)
                    : '0%'
                }
                tooltip="Percentage of merged PRs that had failing CI checks."
                subtitle={`${ciStats.prs_merged_with_failing_checks} PRs with failures`}
              />
            ) : (
              <StatCard
                title="CI Failure Rate"
                value="-"
                tooltip="CI check-run data not available."
              />
            )}
          </div>
        ) : null}
      </section>

      {/* ===== Section 4: Team Health ===== */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Users className="h-5 w-5" />
          Team Health
        </h2>

        {collabLoading || workloadLoading ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Card><CardContent className="h-[120px]" /></Card>
            <Card><CardContent className="h-[120px]" /></Card>
            <Card><CardContent className="h-[120px]" /></Card>
          </div>
        ) : (
          <>
            {/* Health alert cards */}
            <div className="grid gap-4 md:grid-cols-3">
              {/* Bus Factors */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Bus Factor Alerts
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {collab && collab.insights.bus_factors.length > 0 ? (
                    <div className="space-y-1.5">
                      {collab.insights.bus_factors.map((bf, i) => (
                        <div key={i} className="text-sm">
                          <span className="font-medium">{bf.repo_name}</span>
                          <span className="text-muted-foreground">
                            {' '}&mdash; {bf.sole_reviewer_name} ({bf.review_share_pct.toFixed(0)}%)
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-emerald-600">No bus factor risks detected.</p>
                  )}
                </CardContent>
              </Card>

              {/* Silos */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    Team Silos
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {collab && collab.insights.silos.length > 0 ? (
                    <div className="space-y-1.5">
                      {collab.insights.silos.map((s, i) => (
                        <div key={i} className="text-sm text-amber-600">
                          {s.team_a} &harr; {s.team_b}: {s.note}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-emerald-600">No cross-team silos detected.</p>
                  )}
                </CardContent>
              </Card>

              {/* Workload Distribution */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Workload Distribution
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {workloadDistribution ? (
                    <div className="space-y-2">
                      {(['overloaded', 'high', 'balanced', 'low'] as const).map((level) => {
                        const count = workloadDistribution[level]
                        const total = workload?.developers.length ?? 1
                        const pct = total > 0 ? (count / total) * 100 : 0
                        return (
                          <div key={level} className="flex items-center gap-2">
                            <Badge variant="secondary" className={cn('text-xs w-24 justify-center', workloadScoreColors[level])}>
                              {level}
                            </Badge>
                            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                              <div
                                className={cn('h-full rounded-full', {
                                  'bg-blue-500': level === 'low',
                                  'bg-emerald-500': level === 'balanced',
                                  'bg-amber-500': level === 'high',
                                  'bg-red-500': level === 'overloaded',
                                })}
                                style={{ width: `${Math.max(pct, 2)}%` }}
                              />
                            </div>
                            <span className="text-sm text-muted-foreground w-6 text-right">{count}</span>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No workload data.</p>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Collaboration health trend chart */}
            {!collabTrendsLoading && collabTrendData.length > 1 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Collaboration Health Over Time (Monthly)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={collabTrendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="label" fontSize={12} stroke="hsl(var(--muted-foreground))" />
                      <YAxis fontSize={12} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      <Legend />
                      <Line type="monotone" dataKey="Bus Factors" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="Silos" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="Isolated" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </section>

      {/* ===== Section 5: Risks ===== */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <ShieldAlert className="h-5 w-5" />
          Risks
        </h2>

        {/* Summary stat cards */}
        <div className="grid gap-4 sm:grid-cols-3">
          {riskLoading ? (
            <>
              <StatCardSkeleton />
              <StatCardSkeleton />
              <StatCardSkeleton />
            </>
          ) : (
            <>
              <StatCard
                title="High-Risk PRs"
                value={risk ? risk.high_risk_prs.length : 0}
                tooltip="Open or merged PRs scored as high or critical risk in this period."
              />
              <StatCard
                title="Stale PR Backlog"
                value={stalePRs?.total_count ?? 0}
                tooltip="Open PRs currently needing attention (no review, changes requested, or approved but not merged)."
              />
              <StatCard
                title="Declining Developers"
                value={decliningDevs.length}
                tooltip="Developers whose PRs merged dropped >30% or review quality score dropped >20% vs the previous period."
              />
            </>
          )}
        </div>

        {/* High-risk PRs table */}
        {risk && risk.high_risk_prs.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                High-Risk Pull Requests
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>PR</TableHead>
                    <TableHead>Repo</TableHead>
                    <TableHead>Author</TableHead>
                    <TableHead>Risk</TableHead>
                    <TableHead>Top Factor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {risk.high_risk_prs.slice(0, 10).map((pr) => (
                    <TableRow key={pr.pr_id}>
                      <TableCell>
                        <a
                          href={pr.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline"
                        >
                          #{pr.number}
                        </a>
                        <span className="ml-2 text-sm">{pr.title.length > 50 ? pr.title.slice(0, 50) + '...' : pr.title}</span>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">{pr.repo_name}</TableCell>
                      <TableCell className="text-sm">{pr.author_name ?? 'External'}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={cn('text-xs', riskLevelStyles[pr.risk_level as RiskLevel])}>
                          {riskLevelLabels[pr.risk_level as RiskLevel]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {pr.risk_factors[0]?.description ?? '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Declining developers */}
        {decliningDevs.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                <TrendingDown className="h-3.5 w-3.5" />
                Developers with Declining Trends
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {decliningDevs.map((dev) => (
                  <div key={dev.id} className="flex items-center gap-3 text-sm">
                    <span className="font-medium">{dev.name}</span>
                    <div className="flex gap-1.5">
                      {dev.reasons.map((r, i) => (
                        <Badge key={i} variant="secondary" className="text-xs bg-red-500/10 text-red-600">
                          {r}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  )
}
