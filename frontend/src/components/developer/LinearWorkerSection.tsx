import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import StatCard from '@/components/StatCard'
import ErrorCard from '@/components/ErrorCard'
import { useDeveloperLinearWorker } from '@/hooks/useDeveloperLinear'
import { useDateRange } from '@/hooks/useDateRange'

interface LinearWorkerSectionProps {
  developerId: number
  enabled: boolean
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return 'N/A'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

export default function LinearWorkerSection({
  developerId,
  enabled,
}: LinearWorkerSectionProps) {
  const { dateFrom, dateTo } = useDateRange()
  const { data, isLoading, isError, refetch } = useDeveloperLinearWorker(
    developerId,
    { dateFrom, dateTo },
    enabled,
  )

  if (!enabled) return null

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
    )
  }

  if (isError) {
    return <ErrorCard message="Could not load Linear worker profile." onRetry={refetch} />
  }

  if (!data || data.issues_worked === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-sm text-muted-foreground">
          No issues worked in this range.
        </CardContent>
      </Card>
    )
  }

  const statusData = Object.entries(data.issues_worked_by_status).map(([status, count]) => ({
    status: status.replace('_', ' '),
    count,
  }))

  return (
    <div className="space-y-3">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Issues Worked"
          value={data.issues_worked}
          subtitle={`${data.reassigned_to_other_count} handed off`}
          tooltip="Issues assigned to you during this range"
        />
        <StatCard
          title="Self-picked"
          value={`${Math.round(data.self_picked_pct * 100)}%`}
          subtitle={`${data.self_picked_count} self / ${data.pushed_count} pushed`}
          tooltip="Share of issues you both created and assigned yourself"
        />
        <StatCard
          title="Triage to Start"
          value={formatDuration(data.median_triage_to_start_s)}
          subtitle="median"
          tooltip="Median time from issue creation to you starting work"
        />
        <StatCard
          title="Cycle Time"
          value={formatDuration(data.median_cycle_time_s)}
          subtitle="median"
          tooltip="Median time from starting work to completion"
        />
      </div>

      {statusData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Status split</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={statusData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="status" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar
                  dataKey="count"
                  name="Issues"
                  fill="hsl(var(--chart-2))"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
