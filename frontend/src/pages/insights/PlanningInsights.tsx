import { Link } from 'react-router-dom'
import {
  BarChart, Bar, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import StatCard from '@/components/StatCard'
import ErrorCard from '@/components/ErrorCard'
import { useDateRange } from '@/hooks/useDateRange'
import { useIntegrations } from '@/hooks/useIntegrations'
import {
  useTriageMetrics, useWorkAlignment, useEstimationAccuracy,
  usePlanningCorrelation,
} from '@/hooks/useSprints'

function formatDuration(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

export default function PlanningInsights() {
  const { data: integrations } = useIntegrations()
  const hasLinear = integrations?.some((i) => i.type === 'linear' && i.status === 'active')
  const { dateFrom, dateTo } = useDateRange()

  const { data: triage, isLoading: triageLoading, isError, refetch } = useTriageMetrics(dateFrom, dateTo)
  const { data: alignment, isLoading: alignLoading } = useWorkAlignment(dateFrom, dateTo)
  const { data: accuracy, isLoading: accLoading } = useEstimationAccuracy()
  const { data: correlation, isLoading: corrLoading } = usePlanningCorrelation()

  if (!hasLinear) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Planning Health</h1>
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertTriangle className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No Linear integration configured</p>
              <p className="text-sm text-muted-foreground">
                Connect Linear to see triage metrics, work alignment, and estimation accuracy.
              </p>
            </div>
            <Link to="/admin/integrations" className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400">
              Go to Integration Settings &rarr;
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isError) return <ErrorCard message="Could not load planning data." onRetry={refetch} />

  const isLoading = triageLoading || alignLoading || accLoading || corrLoading
  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Planning Health</h1>
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-lg" />)}
        </div>
        <Skeleton className="h-64 rounded-lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Planning Health</h1>

      {/* Summary stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Work Alignment"
          value={`${alignment?.alignment_pct ?? 0}%`}
          tooltip="% of PRs linked to tracked work"
        />
        <StatCard
          title="Avg Triage Time"
          value={formatDuration(triage?.avg_triage_duration_s ?? 0)}
          tooltip="Average time from issue creation to acceptance"
        />
        <StatCard
          title="Issues in Triage"
          value={triage?.issues_in_triage ?? 0}
          tooltip="Issues currently awaiting triage"
        />
        <StatCard
          title="Avg Estimation Accuracy"
          value={`${accuracy?.avg_accuracy_pct ?? 0}%`}
          tooltip="Completed points vs estimated points"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Work alignment breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Work Alignment</CardTitle>
          </CardHeader>
          <CardContent>
            {alignment && alignment.total_prs > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="mb-1 flex justify-between text-xs">
                      <span>Linked ({alignment.linked_prs})</span>
                      <span>Unlinked ({alignment.unlinked_prs})</span>
                    </div>
                    <div className="flex h-3 overflow-hidden rounded-full bg-muted">
                      <div
                        className="bg-emerald-500 transition-all"
                        style={{ width: `${alignment.alignment_pct}%` }}
                      />
                    </div>
                  </div>
                  <span className="text-lg font-bold">{alignment.alignment_pct}%</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {alignment.linked_prs} of {alignment.total_prs} PRs are linked to Linear issues
                </p>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">No PR data in selected range</p>
            )}
          </CardContent>
        </Card>

        {/* Triage metrics */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Triage Latency</CardTitle>
          </CardHeader>
          <CardContent>
            {triage && triage.total_triaged > 0 ? (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-2xl font-bold">{formatDuration(triage.avg_triage_duration_s)}</p>
                    <p className="text-xs text-muted-foreground">Average</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold">{formatDuration(triage.median_triage_duration_s)}</p>
                    <p className="text-xs text-muted-foreground">Median</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold">{formatDuration(triage.p90_triage_duration_s)}</p>
                    <p className="text-xs text-muted-foreground">P90</p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground text-center">
                  Based on {triage.total_triaged} triaged issues
                </p>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">No triage data available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Estimation accuracy chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Estimation Accuracy</CardTitle>
        </CardHeader>
        <CardContent>
          {accuracy?.data.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={accuracy.data}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="sprint_name" tick={{ fontSize: 11 }} tickFormatter={(v) => v ?? ''} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: 'Points', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }} />
                <Tooltip />
                <Bar dataKey="estimated_points" name="Estimated" fill="hsl(var(--chart-2))" radius={[4, 4, 0, 0]} opacity={0.5} />
                <Bar dataKey="completed_points" name="Completed" fill="hsl(var(--chart-1))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">No estimation data available</p>
          )}
        </CardContent>
      </Card>

      {/* Planning-delivery correlation */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Planning vs Delivery Correlation</CardTitle>
            {correlation?.correlation_coefficient != null && (
              <span className="text-xs text-muted-foreground">
                r = {correlation.correlation_coefficient}
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {correlation?.data.filter((d) => d.avg_pr_merge_time_hours != null).length ? (
            <ResponsiveContainer width="100%" height={280}>
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="completion_rate"
                  name="Completion Rate"
                  unit="%"
                  tick={{ fontSize: 11 }}
                  label={{ value: 'Completion Rate %', position: 'insideBottom', offset: -5, style: { fontSize: 11 } }}
                />
                <YAxis
                  dataKey="avg_pr_merge_time_hours"
                  name="Avg Merge Time"
                  unit="h"
                  tick={{ fontSize: 11 }}
                  label={{ value: 'Avg Merge Time (h)', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }}
                />
                <Tooltip
                  formatter={(v, name) =>
                    name === 'Completion Rate' ? `${v}%` : `${v}h`
                  }
                  labelFormatter={(_, payload) => {
                    const p = payload?.[0]?.payload
                    return p?.sprint_name ?? ''
                  }}
                />
                <Scatter
                  data={correlation.data.filter((d) => d.avg_pr_merge_time_hours != null)}
                  fill="hsl(var(--chart-1))"
                />
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Not enough data for correlation analysis (need sprints with linked PRs)
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
