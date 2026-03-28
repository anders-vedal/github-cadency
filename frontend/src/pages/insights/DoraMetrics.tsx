import { useMemo, useState } from 'react'
import { useDateRange } from '@/hooks/useDateRange'
import { useDoraMetrics } from '@/hooks/useStats'
import { useRepos } from '@/hooks/useSync'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle, Rocket, Clock, Info } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

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

export default function DoraMetrics() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: repos } = useRepos()
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null)

  const trackedRepos = useMemo(
    () => (repos ?? []).filter((r) => r.is_tracked),
    [repos],
  )

  const { data, isLoading, isError, refetch } = useDoraMetrics(
    dateFrom,
    dateTo,
    selectedRepoId,
  )

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
              DORA (DevOps Research and Assessment) metrics measure software delivery performance. Deploy Frequency and Change Lead Time are tracked from GitHub Actions workflow runs.
            </TooltipContent>
          </Tooltip>
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
          {/* Summary cards */}
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <StatCardSkeleton key={i} />
              ))}
            </div>
          ) : data ? (
            <div className="grid gap-4 sm:grid-cols-4">
              <StatCard
                title="Deploy Frequency"
                value={data.deploy_frequency > 0 ? `${data.deploy_frequency.toFixed(2)}/day` : '—'}
                subtitle={`${data.total_deployments} deploys in ${data.period_days}d`}
                tooltip="Average number of successful deployments per day in the selected period. Calculated from GitHub Actions workflow runs matching DEPLOY_WORKFLOW_NAME."
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
                tooltip="DORA benchmark classification: Elite (multiple/day), High (daily–weekly), Medium (weekly–monthly), Low (<monthly)."
              />
              <StatCard
                title="Avg Lead Time"
                value={data.avg_lead_time_hours != null ? formatLeadTime(data.avg_lead_time_hours) : '—'}
                tooltip="Average time from the oldest undeployed merged PR to the deployment completing. Measures how quickly code reaches production after merge."
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
                tooltip="DORA benchmark classification: Elite (<1h), High (<1 day), Medium (<1 week), Low (>1 week)."
              />
            </div>
          ) : null}

          {/* Band indicator strip */}
          {data && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <Rocket className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Deployment Frequency</p>
                    <p className={`text-lg font-semibold ${bandColors[data.deploy_frequency_band] ?? ''}`}>
                      {bandLabels[data.deploy_frequency_band] ?? data.deploy_frequency_band} Performer
                    </p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-3 py-4">
                  <Clock className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Change Lead Time</p>
                    <p className={`text-lg font-semibold ${bandColors[data.lead_time_band] ?? ''}`}>
                      {bandLabels[data.lead_time_band] ?? data.lead_time_band} Performer
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
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
                    Last 20 deployments in the selected period, with per-deployment lead time from oldest undeployed merged PR.
                  </TooltipContent>
                </Tooltip>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <TableSkeleton columns={5} rows={5} />
              ) : !data || data.deployments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No deployments in this period.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Deployed At</TableHead>
                      <TableHead>Repository</TableHead>
                      <TableHead>Workflow</TableHead>
                      <TableHead>SHA</TableHead>
                      <TableHead className="text-right">Lead Time</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.deployments.map((d) => (
                      <TableRow key={d.id}>
                        <TableCell className="text-sm">{formatDate(d.deployed_at)}</TableCell>
                        <TableCell className="font-mono text-sm">{d.repo_name ?? '—'}</TableCell>
                        <TableCell className="text-sm">{d.workflow_name ?? '—'}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {d.sha?.substring(0, 7) ?? '—'}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {d.lead_time_hours != null ? formatLeadTime(d.lead_time_hours) : '—'}
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
