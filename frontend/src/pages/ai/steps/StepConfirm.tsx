import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertTriangle, Calendar, ChevronDown, ChevronRight } from 'lucide-react'
import { useAICostEstimate } from '@/hooks/useAISettings'
import { useRepos } from '@/hooks/useSync'
import type { AnalysisWizardType, TimeRangeOption } from '@/utils/types'

interface StepConfirmProps {
  analysisType: AnalysisWizardType
  scopeType: string
  scopeId: string
  scopeName: string
  timeRange: TimeRangeOption
  customDate: string
  repoIds: number[]
  dateFrom: string
  dateTo: string
  onRun: () => void
  onSchedule: (schedule: {
    name: string
    frequency: string
    day_of_week?: number
    hour: number
    minute: number
  }) => void
  onBack: () => void
  isRunning: boolean
  isScheduling: boolean
}

const timeRangeLabels: Partial<Record<TimeRangeOption, string>> = {
  last_7d: 'Last 7 days',
  last_14d: 'Last 14 days',
  last_30d: 'Last 30 days',
  last_60d: 'Last 60 days',
  last_90d: 'Last 90 days',
  custom: 'Custom date',
}

const analysisTypeLabels: Record<AnalysisWizardType, string> = {
  communication: 'Communication Analysis',
  conflict: 'Conflict Detection',
  sentiment: 'Sentiment Analysis',
  one_on_one_prep: '1:1 Prep Brief',
  team_health: 'Team Health Check',
}

const timeRangeToDays: Partial<Record<TimeRangeOption, number>> = {
  last_7d: 7,
  last_14d: 14,
  last_30d: 30,
  last_60d: 60,
  last_90d: 90,
}

const hours = Array.from({ length: 24 }, (_, i) => i)
const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function formatHour(h: number): string {
  const period = h >= 12 ? 'PM' : 'AM'
  const hour12 = h === 0 ? 12 : h > 12 ? h - 12 : h
  return `${hour12}:00 ${period}`
}

export default function StepConfirm({
  analysisType,
  scopeType,
  scopeId,
  scopeName,
  timeRange,
  customDate,
  repoIds,
  dateFrom,
  dateTo,
  onRun,
  onSchedule,
  onBack,
  isRunning,
  isScheduling,
}: StepConfirmProps) {
  const estimate = useAICostEstimate()
  const { data: repos = [] } = useRepos()
  const [budgetOverride, setBudgetOverride] = useState(false)
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [scheduleName, setScheduleName] = useState(
    `${analysisTypeLabels[analysisType]} — ${scopeName}`,
  )
  const [frequency, setFrequency] = useState('weekly')
  const [dayOfWeek, setDayOfWeek] = useState(0)
  const [hour, setHour] = useState(8)

  const selectedRepos = repos.filter((r) => repoIds.includes(r.id))

  // Determine the feature name for the estimate endpoint
  const feature =
    analysisType === 'one_on_one_prep'
      ? 'one_on_one_prep'
      : analysisType === 'team_health'
        ? 'team_health'
        : 'general_analysis'

  const estimateScopeId =
    analysisType === 'one_on_one_prep'
      ? scopeId
      : analysisType === 'team_health'
        ? scopeId === '__all__' ? 'all' : scopeId
        : scopeId

  useEffect(() => {
    estimate.mutate({
      feature,
      scope_type: scopeType,
      scope_id: estimateScopeId,
      date_from: dateFrom,
      date_to: dateTo,
      repo_ids: repoIds.length > 0 ? repoIds : undefined,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const wouldExceed = estimate.data?.would_exceed_budget ?? false
  const canRun = !wouldExceed || budgetOverride

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Confirm Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Summary */}
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Analysis Type</span>
              <Badge variant="secondary">{analysisTypeLabels[analysisType]}</Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Scope</span>
              <span className="font-medium capitalize">{scopeType}: {scopeName}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Time Range</span>
              <span className="font-medium">
                {timeRangeLabels[timeRange] ?? timeRange}
                {timeRange === 'custom' && customDate ? ` (${customDate})` : ''}
              </span>
            </div>
            {repoIds.length > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Repositories</span>
                <span className="font-medium">{repoIds.length} repos</span>
              </div>
            )}
          </div>

          {repoIds.length > 0 && (
            <div className="rounded-md border p-3">
              <div className="text-xs font-medium text-muted-foreground mb-1.5">Filtered Repos</div>
              <div className="flex flex-wrap gap-1.5">
                {selectedRepos.slice(0, 5).map((r) => (
                  <Badge key={r.id} variant="outline" className="text-xs">{r.full_name}</Badge>
                ))}
                {selectedRepos.length > 5 && (
                  <Badge variant="secondary" className="text-xs">+{selectedRepos.length - 5} more</Badge>
                )}
              </div>
            </div>
          )}

          {/* Cost Estimate */}
          <div className="rounded-md border p-3 space-y-2">
            <div className="text-xs font-medium text-muted-foreground">Cost Estimate</div>
            {estimate.isPending && (
              <div className="space-y-1">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-48" />
              </div>
            )}
            {estimate.data && (
              <>
                <div className="text-lg font-semibold">
                  ~${estimate.data.estimated_cost_usd.toFixed(4)}
                </div>
                <div className="text-xs text-muted-foreground">
                  ~{estimate.data.estimated_input_tokens.toLocaleString()} input + ~{estimate.data.estimated_output_tokens.toLocaleString()} output tokens
                </div>
                {estimate.data.character_count > 0 && (
                  <div className="text-xs text-muted-foreground">
                    Based on {estimate.data.data_items} data items ({estimate.data.character_count.toLocaleString()} characters)
                  </div>
                )}
                {estimate.data.remaining_budget_tokens > 0 && (() => {
                  const estTokens = estimate.data.estimated_input_tokens + estimate.data.estimated_output_tokens
                  const pct = Math.min(100, Math.round((estTokens / estimate.data.remaining_budget_tokens) * 100))
                  return (
                    <div className="mt-2">
                      <div className="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>This analysis uses ~{pct}% of remaining budget</span>
                        <span>{estimate.data.remaining_budget_tokens.toLocaleString()} tokens left</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${wouldExceed ? 'bg-red-500' : 'bg-primary'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })()}
                {wouldExceed && (
                  <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/5 p-2 text-xs text-red-700 dark:text-red-400">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">This analysis would exceed your monthly budget.</p>
                      <label className="mt-1 flex items-center gap-2 cursor-pointer">
                        <Checkbox
                          checked={budgetOverride}
                          onCheckedChange={(v) => setBudgetOverride(v === true)}
                        />
                        Run anyway
                      </label>
                    </div>
                  </div>
                )}
              </>
            )}
            {estimate.isError && (
              <div className="text-xs text-red-600">
                Could not estimate cost.{' '}
                <button
                  className="underline"
                  onClick={() =>
                    estimate.mutate({
                      feature,
                      scope_type: scopeType,
                      scope_id: estimateScopeId,
                      date_from: dateFrom,
                      date_to: dateTo,
                      repo_ids: repoIds.length > 0 ? repoIds : undefined,
                    })
                  }
                >
                  Retry
                </button>
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" onClick={onBack} disabled={isRunning || isScheduling}>
              Back
            </Button>
            <Button
              variant="outline"
              onClick={() => setScheduleOpen(!scheduleOpen)}
              disabled={isRunning || isScheduling}
            >
              <Calendar className="mr-2 h-4 w-4" />
              Save as Schedule
              {scheduleOpen ? <ChevronDown className="ml-1 h-3 w-3" /> : <ChevronRight className="ml-1 h-3 w-3" />}
            </Button>
            <Button onClick={onRun} disabled={!canRun || isRunning || isScheduling}>
              {isRunning ? 'Running...' : 'Run Analysis'}
            </Button>
          </div>

          {/* Schedule config — expandable */}
          {scheduleOpen && (
            <div className="rounded-md border p-4 space-y-3">
              <h3 className="text-sm font-medium">Schedule Configuration</h3>
              <div className="space-y-2">
                <Label htmlFor="schedule-name">Schedule Name</Label>
                <Input
                  id="schedule-name"
                  value={scheduleName}
                  onChange={(e) => setScheduleName(e.target.value)}
                  placeholder="e.g., Weekly 1:1 Prep — Alice"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label>Frequency</Label>
                  <Select value={frequency} onValueChange={setFrequency}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="biweekly">Every 2 weeks</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {(frequency === 'weekly' || frequency === 'biweekly') && (
                  <div className="space-y-2">
                    <Label>Day</Label>
                    <Select value={String(dayOfWeek)} onValueChange={(v) => setDayOfWeek(Number(v))}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {dayNames.map((name, i) => (
                          <SelectItem key={i} value={String(i)}>{name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="space-y-2">
                  <Label>Time</Label>
                  <Select value={String(hour)} onValueChange={(v) => setHour(Number(v))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {hours.map((h) => (
                        <SelectItem key={h} value={String(h)}>{formatHour(h)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Runs {frequency} {(frequency === 'weekly' || frequency === 'biweekly') ? `on ${dayNames[dayOfWeek]}` : ''} at {formatHour(hour)}, analyzing the last{' '}
                {timeRangeToDays[timeRange] ?? 30} days
              </p>
              <div className="flex justify-end">
                <Button
                  onClick={() =>
                    onSchedule({
                      name: scheduleName,
                      frequency,
                      day_of_week: (frequency === 'weekly' || frequency === 'biweekly') ? dayOfWeek : undefined,
                      hour,
                      minute: 0,
                    })
                  }
                  disabled={!scheduleName.trim() || isScheduling}
                >
                  {isScheduling ? 'Saving...' : 'Save Schedule'}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
