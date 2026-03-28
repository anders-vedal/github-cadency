import { useParams } from 'react-router-dom'
import { useDeveloper } from '@/hooks/useDevelopers'
import { useDeveloperStats, useDeveloperTrends } from '@/hooks/useStats'
import { useDateRange } from '@/hooks/useDateRange'
import { useRunAnalysis, useRunOneOnOnePrep, useAIHistory } from '@/hooks/useAI'
import { useAuth } from '@/hooks/useAuth'
import {
  useGoals,
  useGoalProgress,
  useUpdateSelfGoal,
} from '@/hooks/useGoals'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle } from 'lucide-react'
import ErrorCard from '@/components/ErrorCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
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
import TrendChart from '@/components/charts/TrendChart'
import PercentileBar from '@/components/charts/PercentileBar'
import ReviewQualityDonut from '@/components/charts/ReviewQualityDonut'
import GoalSparkline from '@/components/charts/GoalSparkline'
import GoalCreateDialog, { metricKeyLabels } from '@/components/GoalCreateDialog'
import AnalysisResultRenderer from '@/components/ai/AnalysisResultRenderer'
import { useState } from 'react'
import type { TrendPeriod, GoalResponse } from '@/utils/types'

const trendCharts: {
  title: string
  metricKey: keyof TrendPeriod
  trendKey: string
  format?: (v: number) => string
}[] = [
  { title: 'PRs Merged', metricKey: 'prs_merged', trendKey: 'prs_merged' },
  {
    title: 'Time to Merge',
    metricKey: 'avg_time_to_merge_h',
    trendKey: 'avg_time_to_merge_h',
    format: (v) => `${v.toFixed(1)}h`,
  },
  { title: 'Reviews Given', metricKey: 'reviews_given', trendKey: 'reviews_given' },
  { title: 'Issues Closed', metricKey: 'issues_closed', trendKey: 'issues_closed' },
  { title: 'Additions', metricKey: 'additions', trendKey: 'additions' },
]


function GoalProgressRow({ goal }: { goal: GoalResponse }) {
  const { data: progress } = useGoalProgress(goal.id)

  const baseline = goal.baseline_value ?? 0
  const current = progress?.current_value ?? baseline
  const target = goal.target_value
  const range = Math.max(Math.abs(target - baseline), 1)
  const pct = Math.min(100, Math.max(0, ((current - baseline) / (target - baseline)) * 100))

  return (
    <div className="flex items-center gap-4">
      <div className="min-w-[140px]">
        <p className="text-sm font-medium">{goal.title}</p>
        <p className="text-xs text-muted-foreground">
          {metricKeyLabels[goal.metric_key] ?? goal.metric_key}
        </p>
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <span>{baseline.toFixed(1)}</span>
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${Math.max(0, pct)}%` }}
            />
          </div>
          <span>{target}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Current: <span className="font-medium text-foreground">{current.toFixed(1)}</span>
          {goal.target_date && (
            <> &middot; Due {new Date(goal.target_date).toLocaleDateString()}</>
          )}
        </p>
      </div>
      {progress && progress.history.length > 0 && (
        <GoalSparkline history={progress.history} targetValue={target} />
      )}
      <Badge
        variant={goal.status === 'achieved' ? 'default' : goal.status === 'abandoned' ? 'destructive' : 'secondary'}
      >
        {goal.status}
      </Badge>
    </div>
  )
}

const percentileLabels: Record<string, { label: string; lowerIsBetter: boolean; format?: (v: number) => string }> = {
  prs_merged: { label: 'PRs Merged', lowerIsBetter: false },
  avg_time_to_merge_hours: { label: 'Time to Merge', lowerIsBetter: true, format: (v) => `${v.toFixed(1)}h` },
  avg_time_to_first_review_hours: { label: 'Time to First Review', lowerIsBetter: true, format: (v) => `${v.toFixed(1)}h` },
  reviews_given: { label: 'Reviews Given', lowerIsBetter: false },
  review_quality_score: { label: 'Review Quality', lowerIsBetter: false, format: (v) => v.toFixed(1) },
  total_additions: { label: 'Code Additions', lowerIsBetter: false },
  time_to_approve_h: { label: 'Time to Approve', lowerIsBetter: true, format: (v: number) => `${v.toFixed(1)}h` },
  time_after_approve_h: { label: 'Time After Approve', lowerIsBetter: true, format: (v: number) => `${v.toFixed(1)}h` },
}

export default function DeveloperDetail() {
  const { id } = useParams<{ id: string }>()
  const devId = Number(id)
  const { dateFrom, dateTo } = useDateRange()
  const { data: dev, isLoading, isError, refetch } = useDeveloper(devId)
  const { data: stats } = useDeveloperStats(devId, dateFrom, dateTo)
  const { data: trends } = useDeveloperTrends(devId)
  const { data: aiHistory } = useAIHistory()
  const runAnalysis = useRunAnalysis()
  const runOneOnOnePrep = useRunOneOnOnePrep()
  const { user, isAdmin } = useAuth()
  const { data: goals } = useGoals(devId)
  const updateSelfGoal = useUpdateSelfGoal()
  const [analysisType, setAnalysisType] = useState<'communication' | 'sentiment'>('communication')
  const [analyzeOpen, setAnalyzeOpen] = useState(false)
  const [prepOpen, setPrepOpen] = useState(false)

  const isOwnPage = user?.developer_id === devId
  const canCreateGoal = isAdmin || isOwnPage

  if (isError) return <ErrorCard message="Could not load developer." onRetry={() => refetch()} />
  if (isLoading) {
    return (
      <div className="space-y-6">
        <Card>
          <CardContent className="flex items-center gap-6 pt-6">
            <Skeleton className="h-16 w-16 rounded-full" />
            <div className="space-y-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-40" />
            </div>
          </CardContent>
        </Card>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
      </div>
    )
  }
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
            <img src={dev.avatar_url} alt={dev.display_name} className="h-16 w-16 rounded-full" />
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
          <StatCard
            title="PRs Opened"
            value={stats.prs_opened}
            subtitle={`${stats.prs_merged} merged`}
            tooltip="Number of pull requests you authored in this period"
          />
          <StatCard
            title="PRs Open"
            value={stats.prs_open}
            tooltip="Pull requests you authored that are currently open"
          />
          <StatCard
            title="Code Changes"
            value={`+${stats.total_additions} / -${stats.total_deletions}`}
            subtitle={`${stats.total_changed_files} files`}
            tooltip="Lines added and removed across all your PRs in this period"
          />
          <StatCard
            title="Avg Time to Merge"
            value={stats.avg_time_to_merge_hours != null ? `${stats.avg_time_to_merge_hours.toFixed(1)}h` : 'N/A'}
            tooltip="Average hours from PR creation to merge, including review time and iteration"
          />
          <StatCard
            title="Reviews Given"
            value={stats.reviews_given.approved + stats.reviews_given.changes_requested + stats.reviews_given.commented}
            subtitle={`${stats.reviews_given.approved} approved, ${stats.reviews_given.changes_requested} changes req.`}
            tooltip="Number of PR reviews you submitted (approved, changes requested, or comments)"
          />
          <StatCard
            title="Reviews Received"
            value={stats.reviews_received}
            tooltip="Number of reviews others submitted on your pull requests"
          />
          <StatCard
            title="Issues Closed"
            value={stats.issues_closed}
            subtitle={`${stats.issues_assigned} assigned`}
            tooltip="Issues assigned to you that were closed in this period"
          />
          <StatCard
            title="Avg Time to Close"
            value={stats.avg_time_to_close_issue_hours != null ? `${stats.avg_time_to_close_issue_hours.toFixed(1)}h` : 'N/A'}
            tooltip="Average hours from issue creation to close for issues assigned to you"
          />
          <StatCard
            title="Avg Time to Approve"
            value={stats.avg_time_to_approve_hours != null ? `${stats.avg_time_to_approve_hours.toFixed(1)}h` : 'N/A'}
            tooltip="Average time from PR creation to last approval review"
          />
          <StatCard
            title="Avg Time After Approve"
            value={stats.avg_time_after_approve_hours != null ? `${stats.avg_time_after_approve_hours.toFixed(1)}h` : 'N/A'}
            tooltip="Average time from last approval to merge (post-approval idle time)"
          />
          <StatCard
            title="PRs Merged Without Approval"
            value={stats.prs_merged_without_approval}
            tooltip="PRs merged without any APPROVED review"
          />
          <StatCard
            title="PRs Reverted"
            value={stats.prs_reverted}
            tooltip="PRs you authored that were subsequently reverted by another PR"
          />
          <StatCard
            title="Reverts Authored"
            value={stats.reverts_authored}
            tooltip="Revert PRs you created — a positive signal of quickly fixing problems"
          />
        </div>
      )}

      {/* Your Trends */}
      {trends && trends.periods.length >= 2 && (
        <div className="space-y-3">
          <h2 className="flex items-center gap-1.5 text-lg font-semibold">
            Your Trends
            <Tooltip>
              <TooltipTrigger className="inline-flex text-muted-foreground/60 hover:text-muted-foreground transition-colors">
                <HelpCircle className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>
                Trend direction is computed via linear regression over the selected periods. Less than 5% change is considered stable.
              </TooltipContent>
            </Tooltip>
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {trendCharts.map((tc) => (
              <TrendChart
                key={tc.metricKey}
                title={tc.title}
                data={trends.periods}
                metricKey={tc.metricKey}
                direction={trends.trends[tc.trendKey]}
                formatValue={tc.format}
              />
            ))}
          </div>
        </div>
      )}

      {/* Team Context — Percentile Placement */}
      {stats && 'percentiles' in stats && stats.percentiles && (
        <div className="space-y-3">
          <h2 className="flex items-center gap-1.5 text-lg font-semibold">
            Team Context
            <Tooltip>
              <TooltipTrigger className="inline-flex text-muted-foreground/60 hover:text-muted-foreground transition-colors">
                <HelpCircle className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>
                Shows where you sit relative to team percentiles (p25/p50/p75). For time-based metrics, lower is better.
              </TooltipContent>
            </Tooltip>
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(stats.percentiles).map(([key, placement]) => {
              const config = percentileLabels[key]
              if (!config) return null
              return (
                <PercentileBar
                  key={key}
                  label={config.label}
                  placement={placement}
                  lowerIsBetter={config.lowerIsBetter}
                  formatValue={config.format}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Review Quality */}
      {stats && 'review_quality_breakdown' in stats && stats.review_quality_breakdown && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Review Quality</h2>
          <div className="max-w-sm">
            <ReviewQualityDonut
              breakdown={stats.review_quality_breakdown}
              score={stats.review_quality_score}
            />
          </div>
        </div>
      )}

      {/* Goals */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{isOwnPage ? 'My Goals' : 'Goals'}</h2>
          {canCreateGoal && (
            <GoalCreateDialog
              developerId={devId}
              isAdmin={isAdmin}
              isOwnPage={isOwnPage}
            />
          )}
        </div>

        {!goals || goals.length === 0 ? (
          <p className="text-sm text-muted-foreground">No goals yet.</p>
        ) : (
          <Card>
            <CardContent className="divide-y pt-4">
              {goals.map((goal) => (
                <div key={goal.id} className="py-3 first:pt-0 last:pb-0">
                  <GoalProgressRow goal={goal} />
                  {isOwnPage && goal.created_by === 'self' && goal.status === 'active' && (
                    <div className="mt-2 flex gap-2 ml-[156px]">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs h-7"
                        onClick={() =>
                          updateSelfGoal.mutate({
                            goalId: goal.id,
                            data: { status: 'achieved' },
                          })
                        }
                      >
                        Mark Achieved
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs h-7 text-muted-foreground"
                        onClick={() =>
                          updateSelfGoal.mutate({
                            goalId: goal.id,
                            data: { status: 'abandoned' },
                          })
                        }
                      >
                        Abandon
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      {/* AI Analysis */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">AI Analysis</h2>
          <div className="flex gap-2">
            {/* Generate 1:1 Prep Brief */}
            <Dialog open={prepOpen} onOpenChange={setPrepOpen}>
              <DialogTrigger asChild>
                <Button>Generate 1:1 Prep Brief</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Generate 1:1 Prep Brief</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <p className="text-sm">
                    Generate an AI-powered 1:1 meeting brief for{' '}
                    <span className="font-medium">{dev.display_name}</span>.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Date range: {dateFrom} to {dateTo}
                  </p>
                  <div className="flex justify-end gap-2">
                    <DialogClose asChild>
                      <Button variant="outline">Cancel</Button>
                    </DialogClose>
                    <Button
                      disabled={runOneOnOnePrep.isPending}
                      onClick={() => {
                        runOneOnOnePrep.mutate(
                          {
                            data: {
                              developer_id: devId,
                              date_from: new Date(dateFrom).toISOString(),
                              date_to: new Date(dateTo).toISOString(),
                            },
                          },
                          { onSuccess: () => setPrepOpen(false) }
                        )
                      }}
                    >
                      {runOneOnOnePrep.isPending ? 'Generating...' : 'Generate'}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>

            {/* Run generic AI Analysis */}
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
                            data: {
                              analysis_type: analysisType,
                              scope_type: 'developer',
                              scope_id: String(devId),
                              date_from: dateFrom,
                              date_to: dateTo,
                            },
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
                  <AnalysisResultRenderer analysisType={a.analysis_type} result={a.result} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
