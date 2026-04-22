import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useDoraMetrics } from '@/hooks/useStats'
import { useDoraV2 } from '@/hooks/useDoraV2'
import { useRepos } from '@/hooks/useSync'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import AiCohortBadge from '@/components/AiCohortBadge'
import DeploymentTimeline from '@/components/charts/DeploymentTimeline'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle, Rocket, Clock, AlertTriangle, TimerReset, Shield, Info } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const bandColors: Record<string, string> = {
  elite: 'text-emerald-600 dark:text-emerald-400',
  high: 'text-blue-600 dark:text-blue-400',
  medium: 'text-amber-600 dark:text-amber-400',
  low: 'text-red-600 dark:text-red-400',
}

const bandLabels: Record<string, string> = {
  elite: 'Elite',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

function formatLeadTime(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`
  if (hours < 24) return `${hours.toFixed(1)}h`
  return `${(hours / 24).toFixed(1)}d`
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatFailureVia(via: string | null): string {
  if (!via) return '—'
  const map: Record<string, string> = {
    failed_deploy: 'Failed deploy',
    revert_pr: 'Revert PR',
    hotfix_pr: 'Hotfix PR',
  }
  return map[via] ?? via
}

type CohortFilter = 'all' | 'human' | 'ai_reviewed' | 'ai_authored' | 'hybrid'

const COHORT_OPTIONS: { value: CohortFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'human', label: 'Human' },
  { value: 'ai_reviewed', label: 'AI-reviewed' },
  { value: 'ai_authored', label: 'AI-authored' },
  { value: 'hybrid', label: 'Hybrid' },
]

function formatReworkRate(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

function formatShare(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

export default function DoraMetrics() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: repos } = useRepos()
  const [searchParams] = useSearchParams()
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(
    Number(searchParams.get('repo_id')) || null,
  )
  const [cohort, setCohort] = useState<CohortFilter>('all')

  const trackedRepos = useMemo(
    () => (repos ?? []).filter((r) => r.is_tracked),
    [repos],
  )

  const { data, isLoading, isError, refetch } = useDoraMetrics(
    dateFrom,
    dateTo,
    selectedRepoId,
  )
  // v2 ships separately and adds rework rate + cohort split. Backend tolerates
  // cohort="all" as the default; the toggle only exists for visualization.
  const { data: v2Data } = useDoraV2(dateFrom, dateTo, cohort)

  // AI share of volume = sum of AI-touched cohorts. Used on the CFR/rework cards
  // to warn readers when the number blends human + AI-heavy PRs.
  const aiSharePct = useMemo(() => {
    const c = v2Data?.cohorts
    if (!c) return null
    const ai =
      (c.ai_reviewed?.share_pct ?? 0) +
      (c.ai_authored?.share_pct ?? 0) +
      (c.hybrid?.share_pct ?? 0)
    return Math.round(ai * 10) / 10
  }, [v2Data])

  if (isError) {
    return <ErrorCard message="Could not load DORA metrics." onRetry={refetch} />
  }

  const noDeployments = !isLoading && data && data.total_deployments === 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">DORA Metrics</h1>
          <Tooltip>
            <TooltipTrigger>
              <HelpCircle className="h-4 w-4 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              DORA (DevOps Research and Assessment) metrics measure software delivery performance across four key dimensions: Deployment Frequency, Lead Time for Changes, Change Failure Rate, and Mean Time to Recovery.
            </TooltipContent>
          </Tooltip>
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex rounded-md border p-0.5" role="tablist" aria-label="Cohort">
            {COHORT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={cohort === opt.value}
                onClick={() => setCohort(opt.value)}
                className={cn(
                  'rounded px-2.5 py-1 text-xs font-medium transition-colors',
                  cohort === opt.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <select
            className="rounded-md border bg-background px-3 py-1.5 text-sm"
            value={selectedRepoId ?? ''}
            onChange={(e) => setSelectedRepoId(Number(e.target.value) || null)}
          >
            <option value="">All Repos</option>
            {trackedRepos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.full_name || r.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      {aiSharePct != null && aiSharePct > 0 && cohort === 'all' && (
        <div className="flex items-center gap-2 rounded-md border bg-muted/40 p-2.5 text-xs">
          <AiCohortBadge aiSharePct={aiSharePct} variant="short" />
          <span className="text-muted-foreground">
            AI-reviewed and AI-authored PRs are blended into these numbers. Switch
            cohorts above or see the comparison below.
          </span>
        </div>
      )}

      {noDeployments ? (
        <Card>
          <CardContent className="py-8">
            <div className="flex flex-col items-center gap-3 text-center">
              <Info className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                No deployments found in this period. Configure the <code className="rounded bg-muted px-1 py-0.5 text-xs">DEPLOY_WORKFLOW_NAME</code> environment variable to match your deployment workflow name in GitHub Actions.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary cards — 6 metrics in 3x2 grid */}
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <StatCardSkeleton key={i} />
              ))}
            </div>
          ) : data ? (
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard
                title="Deploy Frequency"
                value={data.deploy_frequency > 0 ? `${data.deploy_frequency.toFixed(2)}/day` : '—'}
                subtitle={`${data.total_deployments} deploys in ${data.period_days}d`}
                tooltip="Average number of successful deployments per day. Calculated from GitHub Actions workflow runs."
              />
              <StatCard
                title="Avg Lead Time"
                value={data.avg_lead_time_hours != null ? formatLeadTime(data.avg_lead_time_hours) : '—'}
                tooltip="Average time from the oldest undeployed merged PR to the deployment completing."
              />
              <StatCard
                title="Change Failure Rate"
                value={data.change_failure_rate != null ? `${data.change_failure_rate.toFixed(1)}%` : '—'}
                subtitle={`${data.failure_deployments} failure${data.failure_deployments !== 1 ? 's' : ''} of ${data.total_all_deployments} total`}
                tooltip="Percentage of deployments that cause a production failure, detected via failed workflow runs, revert PRs, or hotfix PRs."
              />
              <StatCard
                title="Avg MTTR"
                value={data.avg_mttr_hours != null ? formatLeadTime(data.avg_mttr_hours) : '—'}
                tooltip="Mean Time to Recovery — average time between a failure deployment and the next successful deployment."
              />
              <StatCard
                title="Frequency Band"
                value={bandLabels[data.deploy_frequency_band] ?? data.deploy_frequency_band}
                subtitle={
                  data.deploy_frequency_band === 'elite' ? 'Multiple per day'
                    : data.deploy_frequency_band === 'high' ? 'Daily to weekly'
                    : data.deploy_frequency_band === 'medium' ? 'Weekly to monthly'
                    : 'Less than monthly'
                }
              />
              <StatCard
                title="Lead Time Band"
                value={bandLabels[data.lead_time_band] ?? data.lead_time_band}
                subtitle={
                  data.lead_time_band === 'elite' ? 'Less than 1 hour'
                    : data.lead_time_band === 'high' ? 'Less than 1 day'
                    : data.lead_time_band === 'medium' ? 'Less than 1 week'
                    : 'More than 1 week'
                }
              />
            </div>
          ) : null}

          {/* Band performance strip — 5 indicators */}
          {data && (
            <div className="grid gap-4 sm:grid-cols-5">
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <Shield className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Overall DORA</p>
                    <p className={`text-lg font-semibold ${bandColors[data.overall_band] ?? ''}`}>
                      {bandLabels[data.overall_band] ?? data.overall_band} Performer
                    </p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <Rocket className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Deploy Frequency</p>
                    <p className={`text-lg font-semibold ${bandColors[data.deploy_frequency_band] ?? ''}`}>
                      {bandLabels[data.deploy_frequency_band] ?? data.deploy_frequency_band}
                    </p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <Clock className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Lead Time</p>
                    <p className={`text-lg font-semibold ${bandColors[data.lead_time_band] ?? ''}`}>
                      {bandLabels[data.lead_time_band] ?? data.lead_time_band}
                    </p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <AlertTriangle className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Failure Rate</p>
                    <p className={`text-lg font-semibold ${bandColors[data.cfr_band] ?? ''}`}>
                      {bandLabels[data.cfr_band] ?? data.cfr_band}
                    </p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <TimerReset className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Recovery Time</p>
                    <p className={`text-lg font-semibold ${bandColors[data.mttr_band] ?? ''}`}>
                      {bandLabels[data.mttr_band] ?? data.mttr_band}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* v2 additions: rework rate stat + cohort comparison */}
          {v2Data && (
            <div className="grid gap-4 sm:grid-cols-2">
              <StatCard
                title="Rework Rate"
                value={formatReworkRate(v2Data.stability.rework_rate)}
                subtitle={`Band: ${bandLabels[v2Data.bands.rework_rate] ?? v2Data.bands.rework_rate}`}
                tooltip="Share of merged PRs followed by another PR touching the same file within 7 days. High rework rate = merged too fast."
              />
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <CardTitle>Cohort comparison</CardTitle>
                    <Tooltip>
                      <TooltipTrigger>
                        <HelpCircle className="h-4 w-4 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs">
                        AI-cohort split: each row shows how many PRs that cohort merged in range, its rework rate, and its share of total volume. Blending these masks bimodal cycle-time distributions.
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Cohort</TableHead>
                        <TableHead className="text-right">Merges</TableHead>
                        <TableHead className="text-right">Rework</TableHead>
                        <TableHead className="text-right">Share</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(['human', 'ai_reviewed', 'ai_authored', 'hybrid'] as const).map((key) => {
                        const row = v2Data.cohorts[key]
                        return (
                          <TableRow key={key}>
                            <TableCell className="capitalize">
                              {key.replace('_', '-')}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {row?.merges ?? 0}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {row ? formatReworkRate(row.rework_rate) : '—'}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {row ? formatShare(row.share_pct) : '—'}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Deployment Timeline */}
          {data && data.deployments.length > 0 && (
            <DeploymentTimeline deployments={data.deployments} />
          )}

          {/* Recent deployments table */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <CardTitle>Recent Deployments</CardTitle>
                <Tooltip>
                  <TooltipTrigger>
                    <HelpCircle className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    Last 20 deployments in the selected period, including both successes and failures.
                  </TooltipContent>
                </Tooltip>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton columns={7} rows={5} />
              ) : !data || data.deployments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No deployments in this period.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Deployed At</TableHead>
                      <TableHead>Repository</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Workflow</TableHead>
                      <TableHead>SHA</TableHead>
                      <TableHead className="text-right">Lead Time</TableHead>
                      <TableHead className="text-right">Recovery</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.deployments.map((d) => (
                      <TableRow key={d.id} className={d.is_failure ? 'bg-red-50/50 dark:bg-red-950/20' : ''}>
                        <TableCell className="text-sm">{formatDate(d.deployed_at)}</TableCell>
                        <TableCell className="font-mono text-sm">{d.repo_name ?? '—'}</TableCell>
                        <TableCell>
                          {d.is_failure ? (
                            <Badge variant="destructive" className="text-xs">
                              {formatFailureVia(d.failure_detected_via)}
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="text-xs">
                              {d.status ?? 'success'}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-sm">{d.workflow_name ?? '—'}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {d.sha?.substring(0, 7) ?? '—'}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {d.lead_time_hours != null ? formatLeadTime(d.lead_time_hours) : '—'}
                        </TableCell>
                        <TableCell className="text-right text-sm">
                          {d.recovery_time_hours != null ? formatLeadTime(d.recovery_time_hours) : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
