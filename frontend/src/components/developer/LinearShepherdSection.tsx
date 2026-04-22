import { Link } from 'react-router-dom'
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
import { useDeveloperLinearShepherd } from '@/hooks/useDeveloperLinear'
import { useDateRange } from '@/hooks/useDateRange'

interface LinearShepherdSectionProps {
  developerId: number
  enabled: boolean
}

export default function LinearShepherdSection({
  developerId,
  enabled,
}: LinearShepherdSectionProps) {
  const { dateFrom, dateTo } = useDateRange()
  const { data, isLoading, isError, refetch } = useDeveloperLinearShepherd(
    developerId,
    { dateFrom, dateTo },
    enabled,
  )

  if (!enabled) return null

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
    )
  }

  if (isError) {
    return <ErrorCard message="Could not load Linear shepherd profile." onRetry={refetch} />
  }

  if (!data || data.comments_on_others_issues === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-sm text-muted-foreground">
          No comments on other people's issues in this range.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          title="Comments on Others"
          value={data.comments_on_others_issues}
          subtitle={`across ${data.issues_commented_on} issues`}
          tooltip="Non-system comments you left on issues others created"
        />
        <StatCard
          title="Unique Teams"
          value={data.unique_teams_commented_on}
          subtitle="touched"
          tooltip="Distinct teams whose issues you engaged with"
        />
        <StatCard
          title="Shepherd?"
          value={data.is_shepherd ? 'Yes' : 'No'}
          tooltip="True when you comment on others' issues at > 3× the team median"
        />
      </div>

      {data.top_collaborators.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top collaborators</CardTitle>
            <p className="text-xs text-muted-foreground">
              People whose issues you engage with most.
            </p>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Developer</TableHead>
                  <TableHead className="text-right">Comments</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.top_collaborators.map((c) => (
                  <TableRow key={c.developer_id}>
                    <TableCell>
                      <Link
                        to={`/team/${c.developer_id}`}
                        className="font-medium hover:underline"
                      >
                        {c.name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Badge variant="outline">{c.count}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
