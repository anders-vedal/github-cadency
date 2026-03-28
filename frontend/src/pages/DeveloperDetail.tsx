import { useParams } from 'react-router-dom'
import { useDeveloper } from '@/hooks/useDevelopers'
import { useDeveloperStats } from '@/hooks/useStats'
import { useDateRange } from '@/hooks/useDateRange'
import { useRunAnalysis, useAIHistory } from '@/hooks/useAI'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from '@/components/ui/dialog'
import StatCard from '@/components/StatCard'
import { useState } from 'react'

export default function DeveloperDetail() {
  const { id } = useParams<{ id: string }>()
  const devId = Number(id)
  const { dateFrom, dateTo } = useDateRange()
  const { data: dev, isLoading } = useDeveloper(devId)
  const { data: stats } = useDeveloperStats(devId, dateFrom, dateTo)
  const { data: aiHistory } = useAIHistory()
  const runAnalysis = useRunAnalysis()
  const [analysisType, setAnalysisType] = useState<'communication' | 'sentiment'>('communication')
  const [analyzeOpen, setAnalyzeOpen] = useState(false)

  if (isLoading) return <div className="text-muted-foreground">Loading...</div>
  if (!dev) return <div className="text-muted-foreground">Developer not found.</div>

  const devAnalyses = (aiHistory ?? []).filter(
    (a) => a.scope_type === 'developer' && a.scope_id === String(devId)
  )

  return (
    <div className="space-y-6">
      {/* Profile card */}
      <Card>
        <CardContent className="flex items-center gap-6 pt-6">
          {dev.avatar_url ? (
            <img src={dev.avatar_url} alt="" className="h-16 w-16 rounded-full" />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted text-xl font-bold">
              {dev.display_name[0]}
            </div>
          )}
          <div className="space-y-1">
            <h1 className="text-2xl font-bold">{dev.display_name}</h1>
            <p className="text-muted-foreground">@{dev.github_username}</p>
            <div className="flex flex-wrap gap-2">
              {dev.role && <Badge variant="secondary">{dev.role.replace('_', ' ')}</Badge>}
              {dev.team && <Badge variant="outline">{dev.team}</Badge>}
              {dev.location && (
                <span className="text-sm text-muted-foreground">{dev.location}</span>
              )}
              {dev.timezone && (
                <span className="text-sm text-muted-foreground">({dev.timezone})</span>
              )}
            </div>
            {dev.skills && dev.skills.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {dev.skills.map((s) => (
                  <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard title="PRs Opened" value={stats.prs_opened} subtitle={`${stats.prs_merged} merged`} />
          <StatCard title="PRs Open" value={stats.prs_open} />
          <StatCard
            title="Code Changes"
            value={`+${stats.total_additions} / -${stats.total_deletions}`}
            subtitle={`${stats.total_changed_files} files`}
          />
          <StatCard
            title="Avg Time to Merge"
            value={stats.avg_time_to_merge_hours != null ? `${stats.avg_time_to_merge_hours.toFixed(1)}h` : 'N/A'}
          />
          <StatCard
            title="Reviews Given"
            value={stats.reviews_given.approved + stats.reviews_given.changes_requested + stats.reviews_given.commented}
            subtitle={`${stats.reviews_given.approved} approved, ${stats.reviews_given.changes_requested} changes req.`}
          />
          <StatCard title="Reviews Received" value={stats.reviews_received} />
          <StatCard title="Issues Closed" value={stats.issues_closed} subtitle={`${stats.issues_assigned} assigned`} />
          <StatCard
            title="Avg Time to Close"
            value={stats.avg_time_to_close_issue_hours != null ? `${stats.avg_time_to_close_issue_hours.toFixed(1)}h` : 'N/A'}
          />
        </div>
      )}

      {/* AI Analysis */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">AI Analysis</h2>
          <Dialog open={analyzeOpen} onOpenChange={setAnalyzeOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">Run AI Analysis</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Run Analysis</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Analysis Type</label>
                  <select
                    className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                    value={analysisType}
                    onChange={(e) => setAnalysisType(e.target.value as 'communication' | 'sentiment')}
                  >
                    <option value="communication">Communication</option>
                    <option value="sentiment">Sentiment</option>
                  </select>
                </div>
                <p className="text-sm text-muted-foreground">
                  Date range: {dateFrom} to {dateTo}
                </p>
                <div className="flex justify-end gap-2">
                  <DialogClose asChild>
                    <Button variant="outline">Cancel</Button>
                  </DialogClose>
                  <Button
                    disabled={runAnalysis.isPending}
                    onClick={() => {
                      runAnalysis.mutate(
                        {
                          analysis_type: analysisType,
                          scope_type: 'developer',
                          scope_id: String(devId),
                          date_from: new Date(dateFrom).toISOString(),
                          date_to: new Date(dateTo).toISOString(),
                        },
                        { onSuccess: () => setAnalyzeOpen(false) }
                      )
                    }}
                  >
                    {runAnalysis.isPending ? 'Running...' : 'Run'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {devAnalyses.length === 0 ? (
          <p className="text-sm text-muted-foreground">No analyses yet.</p>
        ) : (
          <div className="space-y-3">
            {devAnalyses.map((a) => (
              <Card key={a.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Badge variant="secondary">{a.analysis_type}</Badge>
                    <span className="text-muted-foreground">
                      {new Date(a.created_at).toLocaleDateString()}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="max-h-60 overflow-auto rounded bg-muted p-3 text-xs">
                    {JSON.stringify(a.result, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
