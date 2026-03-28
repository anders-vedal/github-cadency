import { useState } from 'react'
import { useRepos, useToggleTracking } from '@/hooks/useSync'
import { useRepoStats } from '@/hooks/useStats'
import { useDateRange } from '@/hooks/useDateRange'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

function RepoStatsPanel({ repoId }: { repoId: number }) {
  const { dateFrom, dateTo } = useDateRange()
  const { data: stats, isLoading } = useRepoStats(repoId, dateFrom, dateTo)

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading stats...</div>
  if (!stats) return null

  return (
    <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
      <div>
        <div className="text-xs text-muted-foreground">PRs</div>
        <div className="font-medium">{stats.total_prs} ({stats.total_merged} merged)</div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">Issues</div>
        <div className="font-medium">{stats.total_issues} ({stats.total_issues_closed} closed)</div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">Reviews</div>
        <div className="font-medium">{stats.total_reviews}</div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">Avg Merge Time</div>
        <div className="font-medium">
          {stats.avg_time_to_merge_hours != null
            ? `${stats.avg_time_to_merge_hours.toFixed(1)}h`
            : 'N/A'}
        </div>
      </div>
      {stats.top_contributors.length > 0 && (
        <div className="col-span-full">
          <div className="text-xs text-muted-foreground mb-1">Top Contributors</div>
          <div className="flex flex-wrap gap-2">
            {stats.top_contributors.map((c) => (
              <Badge key={c.developer_id} variant="outline">
                {c.display_name} ({c.pr_count} PRs)
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Repos() {
  const { data: repos, isLoading } = useRepos()
  const toggle = useToggleTracking()
  const [expandedId, setExpandedId] = useState<number | null>(null)

  if (isLoading) return <div className="text-muted-foreground">Loading repos...</div>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Repositories</h1>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Repository</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Tracked</TableHead>
              <TableHead>Last Synced</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(repos ?? []).map((repo) => (
              <>
                <TableRow
                  key={repo.id}
                  className="cursor-pointer"
                  onClick={() => setExpandedId(expandedId === repo.id ? null : repo.id)}
                >
                  <TableCell>
                    <div>
                      <div className="font-medium">{repo.full_name ?? repo.name}</div>
                      {repo.description && (
                        <div className="text-xs text-muted-foreground line-clamp-1">
                          {repo.description}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {repo.language && <Badge variant="outline">{repo.language}</Badge>}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={repo.is_tracked}
                      onCheckedChange={(checked) => {
                        toggle.mutate({ id: repo.id, isTracked: checked })
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {repo.last_synced_at
                      ? new Date(repo.last_synced_at).toLocaleString()
                      : 'Never'}
                  </TableCell>
                </TableRow>
                {expandedId === repo.id && (
                  <TableRow key={`${repo.id}-stats`}>
                    <TableCell colSpan={4} className="bg-muted/30 p-0">
                      <RepoStatsPanel repoId={repo.id} />
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
            {(repos ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No repositories found. Run a sync to discover repos.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
