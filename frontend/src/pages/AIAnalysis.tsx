import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAIHistory, useRunAnalysis, useRunOneOnOnePrep, useRunTeamHealth } from '@/hooks/useAI'
import { useAISettings, useAICostEstimate } from '@/hooks/useAISettings'
import { useDevelopers } from '@/hooks/useDevelopers'
import { useRepos } from '@/hooks/useSync'
import { useDateRange } from '@/hooks/useDateRange'
import ErrorCard from '@/components/ErrorCard'
import TableSkeleton from '@/components/TableSkeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import AnalysisResultRenderer from '@/components/ai/AnalysisResultRenderer'
import { AlertTriangle, Info, RefreshCw } from 'lucide-react'
import type { AIAnalyzeRequest, AIAnalysis as AIAnalysisType } from '@/utils/types'

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

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

function CostEstimateLine({ feature, scopeType, scopeId, dateFrom, dateTo }: {
  feature: string
  scopeType?: string
  scopeId?: string
  dateFrom?: string
  dateTo?: string
}) {
  const estimate = useAICostEstimate()

  // Fetch on mount
  useState(() => {
    estimate.mutate({ feature, scope_type: scopeType, scope_id: scopeId, date_from: dateFrom, date_to: dateTo })
  })

  if (estimate.isPending) {
    return <Skeleton className="h-4 w-48" />
  }
  if (estimate.data) {
    const { estimated_input_tokens, estimated_output_tokens, estimated_cost_usd } = estimate.data
    return (
      <p className="text-xs text-muted-foreground">
        Estimated: ~{(estimated_input_tokens + estimated_output_tokens).toLocaleString()} tokens (~${estimated_cost_usd.toFixed(4)})
      </p>
    )
  }
  return null
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
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>
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

export default function AIAnalysis() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: history, isLoading, isError, refetch } = useAIHistory()
  const runAnalysis = useRunAnalysis()
  const runOneOnOnePrep = useRunOneOnOnePrep()
  const runTeamHealth = useRunTeamHealth()
  const { data: developers } = useDevelopers()
  const { data: repos } = useRepos()
  const { data: aiSettings } = useAISettings()

  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<AIAnalyzeRequest>({
    analysis_type: 'communication',
    scope_type: 'developer',
    scope_id: '',
    date_from: '',
    date_to: '',
  })

  // 1:1 prep state
  const [prepDevId, setPrepDevId] = useState('')

  // Team health state
  const [healthTeam, setHealthTeam] = useState('')

  const teams = [...new Set((developers ?? []).map((d) => d.team).filter(Boolean))] as string[]

  const generalTypes = ['communication', 'conflict', 'sentiment']
  const generalHistory = (history ?? []).filter((a) => generalTypes.includes(a.analysis_type ?? ''))
  const prepHistory = (history ?? []).filter((a) => a.analysis_type === 'one_on_one_prep')
  const healthHistory = (history ?? []).filter((a) => a.analysis_type === 'team_health')

  // Budget warning
  const showBudgetWarning =
    aiSettings &&
    aiSettings.budget_pct_used != null &&
    aiSettings.budget_pct_used >= aiSettings.budget_warning_threshold

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
      <h1 className="text-2xl font-bold">AI Analysis</h1>

      {/* Budget warning */}
      {showBudgetWarning && (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
          <span className="text-amber-700 dark:text-amber-400">
            AI budget is {Math.round((aiSettings.budget_pct_used ?? 0) * 100)}% used this month
            ({aiSettings.current_month_tokens.toLocaleString()} / {aiSettings.monthly_token_budget?.toLocaleString()} tokens).
          </span>
          <Link to="/settings/ai" className="ml-auto text-xs font-medium text-amber-700 underline hover:no-underline dark:text-amber-400">
            Manage in AI Settings
          </Link>
        </div>
      )}

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General Analysis</TabsTrigger>
          <TabsTrigger value="prep">1:1 Prep</TabsTrigger>
          <TabsTrigger value="health">Team Health</TabsTrigger>
        </TabsList>

        {/* General Analysis Tab */}
        <TabsContent value="general">
          <div className="space-y-4">
            <div className="flex justify-end">
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                  <Button>New Analysis</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Run AI Analysis</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <label className="text-sm font-medium">Analysis Type</label>
                      <select
                        className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                        value={form.analysis_type}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            analysis_type: e.target.value as AIAnalyzeRequest['analysis_type'],
                          })
                        }
                      >
                        <option value="communication">Communication</option>
                        <option value="conflict">Conflict</option>
                        <option value="sentiment">Sentiment</option>
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-sm font-medium">Scope</label>
                      <select
                        className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                        value={form.scope_type}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            scope_type: e.target.value as AIAnalyzeRequest['scope_type'],
                            scope_id: '',
                          })
                        }
                      >
                        <option value="developer">Developer</option>
                        <option value="team">Team</option>
                        <option value="repo">Repository</option>
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-sm font-medium">
                        {form.scope_type === 'developer'
                          ? 'Developer'
                          : form.scope_type === 'team'
                            ? 'Team'
                            : 'Repository'}
                      </label>
                      <select
                        className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                        value={form.scope_id}
                        onChange={(e) => setForm({ ...form, scope_id: e.target.value })}
                      >
                        <option value="">Select...</option>
                        {form.scope_type === 'developer' &&
                          (developers ?? []).map((d) => (
                            <option key={d.id} value={String(d.id)}>
                              {d.display_name} (@{d.github_username})
                            </option>
                          ))}
                        {form.scope_type === 'team' &&
                          teams.map((t) => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        {form.scope_type === 'repo' &&
                          (repos ?? []).map((r) => (
                            <option key={r.id} value={String(r.id)}>
                              {r.full_name}
                            </option>
                          ))}
                      </select>
                    </div>

                    <p className="text-sm text-muted-foreground">
                      Date range: {dateFrom} to {dateTo}
                    </p>

                    {form.scope_id && (
                      <CostEstimateLine
                        feature="general_analysis"
                        scopeType={form.scope_type}
                        scopeId={form.scope_id}
                        dateFrom={new Date(dateFrom).toISOString()}
                        dateTo={new Date(dateTo).toISOString()}
                      />
                    )}

                    <div className="flex justify-end gap-2">
                      <DialogClose asChild>
                        <Button variant="outline">Cancel</Button>
                      </DialogClose>
                      <Button
                        disabled={!form.scope_id || runAnalysis.isPending}
                        onClick={() => {
                          runAnalysis.mutate(
                            {
                              data: {
                                ...form,
                                date_from: new Date(dateFrom).toISOString(),
                                date_to: new Date(dateTo).toISOString(),
                              },
                            },
                            { onSuccess: () => setOpen(false) }
                          )
                        }}
                      >
                        {runAnalysis.isPending ? 'Running...' : 'Run Analysis'}
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            </div>

            <HistoryList
              items={generalHistory}
              emptyMessage="No general analyses yet. Run one to get started."
              onRegenerate={(item) => {
                if (item.analysis_type && item.scope_type && item.scope_id && item.date_from && item.date_to) {
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
              }}
              isRegenerating={runAnalysis.isPending}
            />
          </div>
        </TabsContent>

        {/* 1:1 Prep Tab */}
        <TabsContent value="prep">
          <div className="space-y-4">
            <Card>
              <CardContent className="flex flex-wrap items-end gap-4 pt-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Developer</label>
                  <select
                    className="flex h-9 w-full min-w-[200px] rounded-md border bg-background px-3 py-1 text-sm"
                    value={prepDevId}
                    onChange={(e) => setPrepDevId(e.target.value)}
                  >
                    <option value="">Select developer...</option>
                    {(developers ?? []).map((d) => (
                      <option key={d.id} value={String(d.id)}>
                        {d.display_name} (@{d.github_username})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="text-sm text-muted-foreground">
                  {dateFrom} to {dateTo}
                </div>
                <Button
                  disabled={!prepDevId || runOneOnOnePrep.isPending}
                  onClick={() => {
                    runOneOnOnePrep.mutate({
                      data: {
                        developer_id: Number(prepDevId),
                        date_from: new Date(dateFrom).toISOString(),
                        date_to: new Date(dateTo).toISOString(),
                      },
                    })
                  }}
                >
                  {runOneOnOnePrep.isPending ? 'Generating...' : 'Generate Brief'}
                </Button>
              </CardContent>
            </Card>

            <HistoryList
              items={prepHistory}
              emptyMessage="No 1:1 prep briefs yet."
              onRegenerate={(item) => {
                if (item.scope_id && item.date_from && item.date_to) {
                  runOneOnOnePrep.mutate({
                    data: {
                      developer_id: Number(item.scope_id),
                      date_from: item.date_from,
                      date_to: item.date_to,
                    },
                    force: true,
                  })
                }
              }}
              isRegenerating={runOneOnOnePrep.isPending}
            />
          </div>
        </TabsContent>

        {/* Team Health Tab */}
        <TabsContent value="health">
          <div className="space-y-4">
            <Card>
              <CardContent className="flex flex-wrap items-end gap-4 pt-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Team</label>
                  <select
                    className="flex h-9 w-full min-w-[200px] rounded-md border bg-background px-3 py-1 text-sm"
                    value={healthTeam}
                    onChange={(e) => setHealthTeam(e.target.value)}
                  >
                    <option value="">All teams</option>
                    {teams.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div className="text-sm text-muted-foreground">
                  {dateFrom} to {dateTo}
                </div>
                <Button
                  disabled={runTeamHealth.isPending}
                  onClick={() => {
                    runTeamHealth.mutate({
                      data: {
                        ...(healthTeam ? { team: healthTeam } : {}),
                        date_from: new Date(dateFrom).toISOString(),
                        date_to: new Date(dateTo).toISOString(),
                      },
                    })
                  }}
                >
                  {runTeamHealth.isPending ? 'Generating...' : 'Generate Assessment'}
                </Button>
              </CardContent>
            </Card>

            <HistoryList
              items={healthHistory}
              emptyMessage="No team health assessments yet."
              onRegenerate={(item) => {
                if (item.date_from && item.date_to) {
                  runTeamHealth.mutate({
                    data: {
                      ...(item.scope_id && item.scope_id !== 'all' ? { team: item.scope_id } : {}),
                      date_from: item.date_from,
                      date_to: item.date_to,
                    },
                    force: true,
                  })
                }
              }}
              isRegenerating={runTeamHealth.isPending}
            />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
