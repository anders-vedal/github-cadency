import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import StatCard from '@/components/StatCard'
import ErrorCard from '@/components/ErrorCard'
import { useDeveloperLinearCreator } from '@/hooks/useDeveloperLinear'
import { useDateRange } from '@/hooks/useDateRange'

interface LinearCreatorSectionProps {
  developerId: number
  enabled: boolean
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return 'N/A'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

export default function LinearCreatorSection({
  developerId,
  enabled,
}: LinearCreatorSectionProps) {
  const { dateFrom, dateTo } = useDateRange()
  const { data, isLoading, isError, refetch } = useDeveloperLinearCreator(
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
    return <ErrorCard message="Could not load Linear creator profile." onRetry={refetch} />
  }

  if (!data || data.issues_created === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-sm text-muted-foreground">
          No issues created in this range.
        </CardContent>
      </Card>
    )
  }

  const lowSample = data.sample_size_downstream_prs < 5

  return (
    <div className="space-y-3">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Issues Written"
          value={data.issues_created}
          subtitle={`${Math.round(data.self_assigned_pct * 100)}% self-assigned`}
          tooltip="Issues you created in this range"
        />
        <StatCard
          title="Avg Description"
          value={`${data.avg_description_length} chars`}
          tooltip="Average length of the issue body you wrote"
        />
        <StatCard
          title="Avg Dialogue"
          value={data.avg_comments_generated.toFixed(1)}
          subtitle="comments/issue"
          tooltip="How much conversation your tickets generate (excluding system comments)"
        />
        <StatCard
          title="Ticket Clarity"
          value={
            lowSample
              ? `${data.avg_downstream_pr_review_rounds.toFixed(1)}`
              : data.avg_downstream_pr_review_rounds.toFixed(1)
          }
          subtitle={
            lowSample
              ? `n=${data.sample_size_downstream_prs} — low confidence`
              : `avg review rounds on linked PRs (n=${data.sample_size_downstream_prs})`
          }
          tooltip="Average review rounds on the PRs that closed your tickets. Lower is better — signals clear, actionable tickets."
        />
      </div>

      {/* By type + top labels */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              By Issue Type
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.issues_created_by_type).length === 0 ? (
                <span className="text-xs text-muted-foreground">No type data</span>
              ) : (
                Object.entries(data.issues_created_by_type)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => (
                    <Badge key={type} variant="outline" className="text-xs">
                      {type}: {count}
                    </Badge>
                  ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Top Labels
            </div>
            <div className="flex flex-wrap gap-2">
              {data.top_labels.length === 0 ? (
                <span className="text-xs text-muted-foreground">No labels</span>
              ) : (
                data.top_labels.slice(0, 10).map((l) => (
                  <Badge key={l.label} variant="secondary" className="text-xs">
                    {l.label} &middot; {l.count}
                  </Badge>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {data.median_time_to_close_for_their_issues_s != null && (
        <p className="text-xs text-muted-foreground">
          Median time from creation to close on your issues:{' '}
          <span className="font-medium text-foreground">
            {formatDuration(data.median_time_to_close_for_their_issues_s)}
          </span>
        </p>
      )}
    </div>
  )
}
