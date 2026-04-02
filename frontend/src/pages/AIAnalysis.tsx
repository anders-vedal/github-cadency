import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAIHistory, useRunAnalysis, useRunOneOnOnePrep, useRunTeamHealth } from '@/hooks/useAI'
import { useAISettings } from '@/hooks/useAISettings'
import { useAISchedules, useUpdateAISchedule, useDeleteAISchedule, useRunAISchedule } from '@/hooks/useAISchedules'
import ErrorCard from '@/components/ErrorCard'
import TableSkeleton from '@/components/TableSkeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import AnalysisResultRenderer from '@/components/ai/AnalysisResultRenderer'
import { AlertTriangle, Info, RefreshCw, Plus, Play, Pencil, Trash2 } from 'lucide-react'
import type { AIAnalyzeRequest, AIAnalysis as AIAnalysisType, AISchedule } from '@/utils/types'
import { timeAgo } from '@/utils/format'

function ReusedBanner({ analysis, onRegenerate, isPending }: {
  analysis: AIAnalysisType
  onRegenerate: () => void
  isPending: boolean
}) {
  if (!analysis.reused) return null
  return (
    <div className="mb-3 flex items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm">
      <Info className="h-4 w-4 shrink-0 text-blue-600" />
      <span className="text-blue-700 dark:text-blue-400">
        Showing cached result from {timeAgo(analysis.created_at)}.
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto h-7 gap-1 text-xs"
        disabled={isPending}
        onClick={onRegenerate}
      >
        <RefreshCw className="h-3 w-3" />
        Regenerate
      </Button>
    </div>
  )
}

function HistoryList({
  items,
  emptyMessage,
  onRegenerate,
  isRegenerating,
}: {
  items: AIAnalysisType[]
  emptyMessage: string
  onRegenerate?: (item: AIAnalysisType) => void
  isRegenerating?: boolean
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null)

  if (items.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        <Button className="mt-3" render={<Link to="/admin/ai/new" />}>
            <Plus className="mr-2 h-4 w-4" />
            New Analysis
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((a) => (
        <Card key={a.id}>
          <CardHeader
            className="cursor-pointer pb-2"
            onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}
          >
            <CardTitle className="flex items-center gap-2 text-sm">
              <Badge variant="secondary">{a.analysis_type}</Badge>
              {a.reused && <Badge variant="outline" className="text-blue-600">cached</Badge>}
              {a.triggered_by === 'scheduled' && <Badge variant="outline">scheduled</Badge>}
              {a.scope_type && a.scope_id && (
                <span className="text-muted-foreground">
                  {a.scope_type}: {a.scope_id}
                </span>
              )}
              <span className="ml-auto text-xs text-muted-foreground">
                {new Date(a.created_at).toLocaleString()}
              </span>
            </CardTitle>
          </CardHeader>
          {expandedId === a.id && (
            <CardContent>
              {onRegenerate && a.reused && (
                <ReusedBanner
                  analysis={a}
                  onRegenerate={() => onRegenerate(a)}
                  isPending={isRegenerating ?? false}
                />
              )}
              {a.input_summary && (
                <p className="mb-3 text-sm text-muted-foreground">{a.input_summary}</p>
              )}
              <AnalysisResultRenderer analysisType={a.analysis_type} result={a.result} />
              {a.estimated_cost_usd != null && a.estimated_cost_usd > 0 && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Cost: ${a.estimated_cost_usd.toFixed(4)} ({a.input_tokens?.toLocaleString()} in / {a.output_tokens?.toLocaleString()} out)
                </p>
              )}
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  )
}

const statusColors: Record<string, string> = {
  success: 'text-green-600 border-green-500/30',
  failed: 'text-red-600 border-red-500/30',
  budget_exceeded: 'text-amber-600 border-amber-500/30',
  feature_disabled: 'text-muted-foreground border-border',
}

function ScheduleRow({ schedule }: { schedule: AISchedule }) {
  const updateSchedule = useUpdateAISchedule()
  const deleteSchedule = useDeleteAISchedule()
  const runSchedule = useRunAISchedule()

  return (
    <tr className="border-b">
      <td className="px-3 py-2">
        <Link to={`/admin/ai/new?schedule=${schedule.id}`} className="text-sm font-medium hover:underline">
          {schedule.name}
        </Link>
      </td>
      <td className="px-3 py-2">
        <Badge variant="secondary" className="text-xs">
          {schedule.general_type ?? schedule.analysis_type}
        </Badge>
      </td>
      <td className="px-3 py-2 text-sm text-muted-foreground">
        {schedule.scope_type}: {schedule.scope_id}
      </td>
      <td className="px-3 py-2 text-sm text-muted-foreground">
        {schedule.next_run_description ?? schedule.frequency}
      </td>
      <td className="px-3 py-2 text-sm">
        {schedule.last_run_at ? (
          <span className="flex items-center gap-1">
            <span className="text-muted-foreground">{timeAgo(schedule.last_run_at)}</span>
            {schedule.last_run_status && (
              <Badge variant="outline" className={`text-xs ${statusColors[schedule.last_run_status] ?? ''}`}>
                {schedule.last_run_status}
              </Badge>
            )}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Never run</span>
        )}
      </td>
      <td className="px-3 py-2">
        <Switch
          checked={schedule.is_enabled}
          onCheckedChange={(checked) =>
            updateSchedule.mutate({ id: schedule.id, data: { is_enabled: checked } })
          }
        />
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            title="Run now"
            disabled={runSchedule.isPending}
            onClick={() => runSchedule.mutate(schedule.id)}
          >
            <Play className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" title="Edit" render={<Link to={`/admin/ai/new?schedule=${schedule.id}`} />}>
              <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-red-600 hover:text-red-700"
            title="Delete"
            disabled={deleteSchedule.isPending}
            onClick={() => {
              if (confirm(`Delete schedule "${schedule.name}"?`)) {
                deleteSchedule.mutate(schedule.id)
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

export default function AIAnalysis() {
  const { data: history, isLoading, isError, refetch } = useAIHistory()
  const { data: aiSettings } = useAISettings()
  const { data: schedules = [] } = useAISchedules()
  const runAnalysis = useRunAnalysis()
  const runOneOnOnePrep = useRunOneOnOnePrep()
  const runTeamHealth = useRunTeamHealth()

  const [typeFilter, setTypeFilter] = useState<string>('all')

  const allHistory = history ?? []
  const filteredHistory = typeFilter === 'all'
    ? allHistory
    : allHistory.filter((a) => a.analysis_type === typeFilter)

  const showBudgetWarning =
    aiSettings &&
    aiSettings.budget_pct_used != null &&
    aiSettings.budget_pct_used >= aiSettings.budget_warning_threshold

  const handleRegenerate = (item: AIAnalysisType) => {
    if (!item.analysis_type || !item.date_from || !item.date_to) return

    if (item.analysis_type === 'one_on_one_prep' && item.scope_id) {
      runOneOnOnePrep.mutate({
        data: { developer_id: Number(item.scope_id), date_from: item.date_from, date_to: item.date_to },
        force: true,
      })
    } else if (item.analysis_type === 'team_health') {
      runTeamHealth.mutate({
        data: {
          ...(item.scope_id && item.scope_id !== 'all' ? { team: item.scope_id } : {}),
          date_from: item.date_from,
          date_to: item.date_to,
        },
        force: true,
      })
    } else if (item.scope_type && item.scope_id) {
      runAnalysis.mutate({
        data: {
          analysis_type: item.analysis_type as AIAnalyzeRequest['analysis_type'],
          scope_type: item.scope_type as AIAnalyzeRequest['scope_type'],
          scope_id: item.scope_id,
          date_from: item.date_from,
          date_to: item.date_to,
        },
        force: true,
      })
    }
  }

  if (isError) {
    return <ErrorCard message="Could not load AI analysis history." onRetry={() => refetch()} />
  }
  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">AI Analysis</h1>
        <TableSkeleton columns={6} rows={4} headers={['Type', 'Scope', 'Date Range', 'Model', 'Tokens', 'Created']} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">AI Analysis</h1>
        <Button render={<Link to="/admin/ai/new" />}>
            <Plus className="mr-2 h-4 w-4" />
            New Analysis
        </Button>
      </div>

      {showBudgetWarning && (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
          <span className="text-amber-700 dark:text-amber-400">
            AI budget is {Math.round((aiSettings!.budget_pct_used ?? 0) * 100)}% used this month
            ({aiSettings!.current_month_tokens.toLocaleString()} / {aiSettings!.monthly_token_budget?.toLocaleString()} tokens).
          </span>
          <Link to="/admin/ai/settings" className="ml-auto text-xs font-medium text-amber-700 underline hover:no-underline dark:text-amber-400">
            Manage in AI Settings
          </Link>
        </div>
      )}

      <Tabs defaultValue="history">
        <TabsList>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="schedules">
            Schedules
            {schedules.length > 0 && (
              <Badge variant="secondary" className="ml-1.5 text-xs">{schedules.length}</Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="history">
          <div className="space-y-4">
            <div className="flex justify-end">
              <Select value={typeFilter} onValueChange={(v) => { if (v) setTypeFilter(v) }}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  <SelectItem value="communication">Communication</SelectItem>
                  <SelectItem value="conflict">Conflict</SelectItem>
                  <SelectItem value="sentiment">Sentiment</SelectItem>
                  <SelectItem value="one_on_one_prep">1:1 Prep</SelectItem>
                  <SelectItem value="team_health">Team Health</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <HistoryList
              items={filteredHistory}
              emptyMessage="No analyses yet. Run your first analysis to see results here."
              onRegenerate={handleRegenerate}
              isRegenerating={runAnalysis.isPending || runOneOnOnePrep.isPending || runTeamHealth.isPending}
            />
          </div>
        </TabsContent>

        <TabsContent value="schedules">
          {schedules.length === 0 ? (
            <div className="py-8 text-center">
              <p className="text-sm text-muted-foreground">
                No scheduled analyses. Create one from the New Analysis wizard.
              </p>
              <Button className="mt-3" render={<Link to="/admin/ai/new" />}>
                  <Plus className="mr-2 h-4 w-4" />
                  New Analysis
              </Button>
            </div>
          ) : (
            <Card>
              <CardContent className="p-0">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Name</th>
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Type</th>
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Scope</th>
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Frequency</th>
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Last Run</th>
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Enabled</th>
                      <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedules.map((s) => (
                      <ScheduleRow key={s.id} schedule={s} />
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
