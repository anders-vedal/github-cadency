import { useParams, Link } from 'react-router-dom'
import { useDeveloper, useActivitySummary, useUpdateDeveloper } from '@/hooks/useDevelopers'
import { useDeveloperStats, useDeveloperTrends } from '@/hooks/useStats'
import { useDeveloperSprintSummary } from '@/hooks/useSprints'
import { useDateRange } from '@/hooks/useDateRange'
import { useAIHistory } from '@/hooks/useAI'
import { useAuth } from '@/hooks/useAuth'
import { useRoles } from '@/hooks/useRoles'
import TeamCombobox from '@/components/TeamCombobox'
import {
  useGoals,
  useGoalProgress,
  useUpdateSelfGoal,
} from '@/hooks/useGoals'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle, Settings } from 'lucide-react'
import RelationshipsCard from '@/components/RelationshipsCard'
import WorksWithSection from '@/components/WorksWithSection'
import SlackPreferencesSection from '@/components/SlackPreferencesSection'
import LinearCreatorSection from '@/components/developer/LinearCreatorSection'
import LinearWorkerSection from '@/components/developer/LinearWorkerSection'
import LinearShepherdSection from '@/components/developer/LinearShepherdSection'
import { useIntegrations, useIssueSource } from '@/hooks/useIntegrations'
import DeactivateDialog from '@/components/DeactivateDialog'
import ErrorCard from '@/components/ErrorCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import StatCard from '@/components/StatCard'
import TrendChart from '@/components/charts/TrendChart'
import PercentileBar from '@/components/charts/PercentileBar'
import ReviewQualityDonut from '@/components/charts/ReviewQualityDonut'
import GoalSparkline from '@/components/charts/GoalSparkline'
import GoalCreateDialog, { metricKeyLabels } from '@/components/GoalCreateDialog'
import AnalysisResultRenderer from '@/components/ai/AnalysisResultRenderer'
import { FALLBACK_CATEGORY_CONFIG, FALLBACK_CATEGORY_ORDER } from '@/utils/categoryConfig'
import { useCategoryConfig } from '@/hooks/useWorkCategories'
import { useState, useEffect } from 'react'
import type { TrendPeriod, GoalResponse, Developer, DeveloperUpdate, RoleDefinition } from '@/utils/types'

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

function ActivitySummaryCard({ developerId }: { developerId: number }) {
  const { data: summary, isLoading } = useActivitySummary(developerId)
  const catConfig = useCategoryConfig()
  const CATEGORY_CONFIG = catConfig?.config ?? FALLBACK_CATEGORY_CONFIG
  const CATEGORY_ORDER = catConfig?.order ?? FALLBACK_CATEGORY_ORDER

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Lifetime Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-x-8 gap-y-2 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-5 w-32" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!summary) return null

  const totalCat = Object.values(summary.work_categories).reduce((a, b) => a + b, 0)

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Lifetime Activity</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-3">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">PRs Authored</span>
            <span className="font-medium">{summary.prs_authored} <span className="text-muted-foreground font-normal">({summary.prs_merged} merged, {summary.prs_open} open)</span></span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Reviews Given</span>
            <span className="font-medium">{summary.reviews_given}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Repos Touched</span>
            <span className="font-medium">{summary.repos_touched}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Issues Created</span>
            <span className="font-medium">{summary.issues_created}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Issues Assigned</span>
            <span className="font-medium">{summary.issues_assigned}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Active Since</span>
            <span className="font-medium">
              {summary.first_activity
                ? new Date(summary.first_activity).toLocaleDateString()
                : 'No activity'}
            </span>
          </div>
          {summary.last_activity && (
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Last Active</span>
              <span className="font-medium">{new Date(summary.last_activity).toLocaleDateString()}</span>
            </div>
          )}
        </div>

        {/* Work category breakdown bar */}
        {totalCat > 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Work Breakdown (merged PRs)</p>
            <div className="flex h-3 w-full overflow-hidden rounded-full">
              {CATEGORY_ORDER.map((cat) => {
                const count = summary.work_categories[cat] ?? 0
                if (count === 0) return null
                const pct = (count / totalCat) * 100
                return (
                  <Tooltip key={cat}>
                    <TooltipTrigger>
                      <div
                        className="h-full transition-all"
                        style={{ width: `${pct}%`, backgroundColor: CATEGORY_CONFIG[cat].color }}
                      />
                    </TooltipTrigger>
                    <TooltipContent>
                      {CATEGORY_CONFIG[cat].label}: {count} ({pct.toFixed(0)}%)
                    </TooltipContent>
                  </Tooltip>
                )
              })}
            </div>
            <div className="flex flex-wrap gap-3 text-xs">
              {CATEGORY_ORDER.map((cat) => {
                const count = summary.work_categories[cat] ?? 0
                if (count === 0) return null
                return (
                  <div key={cat} className="flex items-center gap-1.5">
                    <div
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: CATEGORY_CONFIG[cat].color }}
                    />
                    <span>{CATEGORY_CONFIG[cat].label}</span>
                    <span className="text-muted-foreground">{count}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}


function EditProfileDialog({
  developer,
  open,
  onOpenChange,
  onDeactivate,
}: {
  developer: Developer
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeactivate: () => void
}) {
  const { data: roles } = useRoles()
  const updateDev = useUpdateDeveloper(developer.id)

  const [form, setForm] = useState({
    display_name: developer.display_name,
    email: developer.email ?? '',
    role: developer.role ?? '',
    team: developer.team ?? '',
    office: developer.office ?? '',
    skills: developer.skills?.join(', ') ?? '',
    location: developer.location ?? '',
    timezone: developer.timezone ?? '',
  })

  useEffect(() => {
    if (open) {
      setForm({
        display_name: developer.display_name,
        email: developer.email ?? '',
        role: developer.role ?? '',
        team: developer.team ?? '',
        office: developer.office ?? '',
        skills: developer.skills?.join(', ') ?? '',
        location: developer.location ?? '',
        timezone: developer.timezone ?? '',
      })
    }
  }, [open, developer])

  const rolesByCategory = (roles ?? []).reduce<Record<string, RoleDefinition[]>>((acc, r) => {
    const cat = r.contribution_category
    ;(acc[cat] ??= []).push(r)
    return acc
  }, {})

  const categoryLabels: Record<string, string> = {
    code_contributor: 'Code Contributors',
    issue_contributor: 'Issue Contributors',
    non_contributor: 'Non-Contributors',
    system: 'System',
  }

  function handleSave() {
    const data: DeveloperUpdate = {
      display_name: form.display_name,
      email: form.email || null,
      role: form.role || null,
      team: form.team || null,
      office: form.office || null,
      skills: form.skills ? form.skills.split(',').map((s) => s.trim()).filter(Boolean) : null,
      location: form.location || null,
      timezone: form.timezone || null,
    }
    updateDev.mutate(data, { onSuccess: () => onOpenChange(false) })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit {developer.display_name}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="edit-display-name">Display Name</Label>
            <Input
              id="edit-display-name"
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-email">Email</Label>
            <Input
              id="edit-email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-role">Role</Label>
            <select
              id="edit-role"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            >
              <option value="">No role</option>
              {Object.entries(rolesByCategory).map(([cat, catRoles]) => (
                <optgroup key={cat} label={categoryLabels[cat] ?? cat}>
                  {catRoles.map((r) => (
                    <option key={r.role_key} value={r.role_key}>{r.display_name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="edit-team">Team</Label>
              <TeamCombobox
                id="edit-team"
                value={form.team}
                onChange={(val) => setForm({ ...form, team: val })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="edit-office">Office</Label>
              <Input
                id="edit-office"
                value={form.office}
                onChange={(e) => setForm({ ...form, office: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="edit-location">Location</Label>
              <Input
                id="edit-location"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="edit-timezone">Timezone</Label>
              <Input
                id="edit-timezone"
                placeholder="e.g. Europe/Oslo"
                value={form.timezone}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-skills">Skills</Label>
            <Input
              id="edit-skills"
              placeholder="Comma-separated"
              value={form.skills}
              onChange={(e) => setForm({ ...form, skills: e.target.value })}
            />
          </div>
        </div>
        <div className="flex items-center justify-between pt-2">
          {developer.is_active ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                onOpenChange(false)
                onDeactivate()
              }}
            >
              Deactivate
            </Button>
          ) : (
            <div />
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!form.display_name.trim() || updateDev.isPending}
            >
              {updateDev.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}


export default function DeveloperDetail() {
  const { id } = useParams<{ id: string }>()
  const devId = Number(id)
  const { dateFrom, dateTo } = useDateRange()
  const { data: dev, isLoading, isError, refetch } = useDeveloper(devId)
  const { data: stats } = useDeveloperStats(devId, dateFrom, dateTo)
  const { data: trends } = useDeveloperTrends(devId)
  const { data: aiHistory } = useAIHistory()
  const { data: sprintSummary } = useDeveloperSprintSummary(devId)
  const { user, isAdmin } = useAuth()
  const { data: integrations } = useIntegrations()
  const { data: issueSource } = useIssueSource()
  const hasLinear = integrations?.some((i) => i.type === 'linear' && i.status === 'active')
  const isLinearPrimary = !!hasLinear && issueSource?.source === 'linear'
  const { data: goals } = useGoals(devId)
  const updateSelfGoal = useUpdateSelfGoal()
  const [editOpen, setEditOpen] = useState(false)
  const [deactivateOpen, setDeactivateOpen] = useState(false)

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
      {/* Profile card + Relationships */}
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <Card>
          <CardContent className="flex items-center gap-6 pt-6">
            {dev.avatar_url ? (
              <img src={dev.avatar_url} alt={dev.display_name} className="h-16 w-16 rounded-full" />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted text-xl font-bold">
                {dev.display_name[0]}
              </div>
            )}
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold">{dev.display_name}</h1>
                {!dev.is_active && (
                  <Badge variant="destructive" className="text-xs">Inactive</Badge>
                )}
                {isAdmin && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="ml-auto h-8 w-8"
                    onClick={() => setEditOpen(true)}
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                )}
              </div>
              <p className="text-muted-foreground">@{dev.github_username}</p>
              <div className="flex flex-wrap gap-2">
                {dev.role && <Badge variant="secondary">{dev.role.replace('_', ' ')}</Badge>}
                {dev.team && <Badge variant="outline">{dev.team}</Badge>}
                {dev.office && <Badge variant="outline">{dev.office}</Badge>}
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
        <RelationshipsCard developerId={devId} />
      </div>

      {/* Activity Summary — visible to admin or own page */}
      {(isOwnPage || isAdmin) && <ActivitySummaryCard developerId={devId} />}

      {/* Active Sprint Card — shown when developer is mapped to Linear */}
      {sprintSummary?.active_sprint && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Active Sprint: {sprintSummary.active_sprint.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className={sprintSummary.active_sprint.on_track ? 'bg-emerald-500' : 'bg-amber-500'}
                      style={{ width: `${Math.min(sprintSummary.active_sprint.completion_pct, 100)}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm font-medium">
                  {sprintSummary.active_sprint.completed_issues}/{sprintSummary.active_sprint.total_issues} issues ({sprintSummary.active_sprint.completion_pct}%)
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{sprintSummary.active_sprint.days_remaining}d remaining</span>
                <span>·</span>
                <Badge variant={sprintSummary.active_sprint.on_track ? 'default' : 'secondary'} className="text-xs">
                  {sprintSummary.active_sprint.on_track ? 'On track' : 'Behind'}
                </Badge>
              </div>
              {sprintSummary.recent_sprints.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Recent: {sprintSummary.recent_sprints.map(s => `${s.name} (${s.completion_pct}%)`).join(' · ')}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Linear Creator / Worker / Shepherd sections — only when Linear is primary */}
      {isLinearPrimary && (isAdmin || isOwnPage) && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Linear creator</h2>
          <p className="text-sm text-muted-foreground">
            How clear are the tickets you write? — Ticket clarity is measured by review
            rounds on downstream PRs. Self-reflection, not a ranking.
          </p>
          <LinearCreatorSection developerId={devId} enabled={isLinearPrimary} />
        </div>
      )}

      {isLinearPrimary && (isAdmin || isOwnPage) && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Linear worker</h2>
          <p className="text-sm text-muted-foreground">
            Issues you execute: self-picked vs pushed, triage-to-start, cycle time.
          </p>
          <LinearWorkerSection developerId={devId} enabled={isLinearPrimary} />
        </div>
      )}

      {isLinearPrimary && (isAdmin || isOwnPage) && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Linear shepherd</h2>
          <p className="text-sm text-muted-foreground">
            Which collaborators do you engage with most, and across which teams?
          </p>
          <LinearShepherdSection developerId={devId} enabled={isLinearPrimary} />
        </div>
      )}

      {/* Edit Profile Dialog (admin only) */}
      {isAdmin && dev && (
        <>
          <EditProfileDialog
            developer={dev}
            open={editOpen}
            onOpenChange={setEditOpen}
            onDeactivate={() => setDeactivateOpen(true)}
          />
          <DeactivateDialog
            developer={dev}
            open={deactivateOpen}
            onOpenChange={setDeactivateOpen}
          />
        </>
      )}

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
          <StatCard
            title="Issue Linkage"
            value={stats.issue_linkage_rate != null ? `${(stats.issue_linkage_rate * 100).toFixed(1)}%` : 'N/A'}
            subtitle={`${stats.prs_linked_to_issue} of ${stats.prs_opened} PRs`}
            tooltip="Percentage of your PRs that reference an issue via Closes/Fixes/Resolves keywords"
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

      {/* Works With */}
      <WorksWithSection developerId={devId} />

      {/* Slack Notification Preferences — visible to own profile or admin */}
      {(isOwnPage || isAdmin) && <SlackPreferencesSection isOwnPage={isOwnPage} />}

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
            <Button render={<Link to={`/admin/ai/new?type=one_on_one_prep&developer_id=${devId}`} />}>
                Generate 1:1 Prep Brief
            </Button>
            <Button variant="outline" render={<Link to={`/admin/ai/new?type=communication&developer_id=${devId}`} />}>
                Run AI Analysis
            </Button>
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
