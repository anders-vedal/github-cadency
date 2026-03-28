import { useDateRange } from '@/hooks/useDateRange'
import { useTeamStats } from '@/hooks/useStats'
import StatCard from '@/components/StatCard'

export default function Dashboard() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: stats, isLoading } = useTeamStats(undefined, dateFrom, dateTo)

  if (isLoading) {
    return <div className="text-muted-foreground">Loading dashboard...</div>
  }

  if (!stats) {
    return <div className="text-muted-foreground">No data available. Run a sync first.</div>
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Active Developers"
          value={stats.developer_count}
        />
        <StatCard
          title="Total PRs"
          value={stats.total_prs}
          subtitle={`${stats.total_merged} merged`}
        />
        <StatCard
          title="Merge Rate"
          value={stats.merge_rate != null ? `${stats.merge_rate.toFixed(1)}%` : 'N/A'}
        />
        <StatCard
          title="Avg Time to Review"
          value={
            stats.avg_time_to_first_review_hours != null
              ? `${stats.avg_time_to_first_review_hours.toFixed(1)}h`
              : 'N/A'
          }
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
        />
        <StatCard title="Total Reviews" value={stats.total_reviews} />
        <StatCard title="Issues Closed" value={stats.total_issues_closed} />
      </div>
    </div>
  )
}
