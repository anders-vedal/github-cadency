import { useId, useMemo } from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle } from 'lucide-react'
import type { DeploymentDetail } from '@/utils/types'

interface DeploymentTimelineProps {
  deployments: DeploymentDetail[]
}

interface TimelinePoint {
  timestamp: number
  label: string
  repoName: string
  sha: string
  isFailure: boolean
  failureVia: string | null
  recoveryHours: number | null
  status: string
}

function formatFailureVia(via: string | null): string {
  if (!via) return ''
  const map: Record<string, string> = {
    failed_deploy: 'Failed workflow run',
    revert_pr: 'Revert PR merged',
    hotfix_pr: 'Hotfix PR merged',
  }
  return map[via] ?? via
}

function CustomTooltipContent({ active, payload }: { active?: boolean; payload?: Array<{ payload: TimelinePoint }> }) {
  if (!active || !payload?.[0]) return null
  const d = payload[0].payload
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{d.label}</p>
      <p className="text-muted-foreground">{d.repoName}</p>
      {d.sha && <p className="font-mono text-xs text-muted-foreground">{d.sha.substring(0, 7)}</p>}
      <p className={d.isFailure ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}>
        {d.isFailure ? 'Failure' : 'Success'}
      </p>
      {d.isFailure && d.failureVia && (
        <p className="text-xs text-muted-foreground">Cause: {formatFailureVia(d.failureVia)}</p>
      )}
      {d.isFailure && d.recoveryHours != null && (
        <p className="text-xs text-muted-foreground">
          Recovery: {d.recoveryHours < 1 ? `${Math.round(d.recoveryHours * 60)}m` : d.recoveryHours < 24 ? `${d.recoveryHours.toFixed(1)}h` : `${(d.recoveryHours / 24).toFixed(1)}d`}
        </p>
      )}
    </div>
  )
}

export default function DeploymentTimeline({ deployments }: DeploymentTimelineProps) {
  const uid = useId()

  const data = useMemo<TimelinePoint[]>(() => {
    return deployments
      .filter((d) => d.deployed_at)
      .map((d) => {
        const ts = new Date(d.deployed_at!).getTime()
        return {
          timestamp: ts,
          label: new Date(ts).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          }),
          repoName: d.repo_name ?? 'unknown',
          sha: d.sha ?? '',
          isFailure: d.is_failure,
          failureVia: d.failure_detected_via,
          recoveryHours: d.recovery_time_hours,
          status: d.status ?? 'unknown',
        }
      })
      .sort((a, b) => a.timestamp - b.timestamp)
  }, [deployments])

  const successData = useMemo(() => data.filter((d) => !d.isFailure), [data])
  const failureData = useMemo(() => data.filter((d) => d.isFailure), [data])

  if (data.length === 0) return null

  const minTime = data[0].timestamp
  const maxTime = data[data.length - 1].timestamp

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Deployment Timeline</CardTitle>
          <Tooltip>
            <TooltipTrigger>
              <HelpCircle className="h-4 w-4 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              Deployment events over time. Green dots are successful deployments, red dots are failures (detected via failed workflow runs, revert PRs, or hotfix PRs). Hover for details.
            </TooltipContent>
          </Tooltip>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" /> Success
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" /> Failure
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={200}>
          <ScatterChart margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              type="number"
              dataKey="timestamp"
              domain={[minTime, maxTime]}
              tickFormatter={(ts: number) =>
                new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
              }
              className="text-xs"
              tick={{ fill: 'hsl(var(--muted-foreground))' }}
            />
            <YAxis hide type="number" dataKey={() => 1} domain={[0, 2]} />
            <RechartsTooltip content={<CustomTooltipContent />} />
            <Scatter name="Success" data={successData} fill="hsl(var(--chart-2, 142 71% 45%))">
              {successData.map((_, i) => (
                <Cell key={`s-${uid}-${i}`} className="fill-emerald-500" />
              ))}
            </Scatter>
            <Scatter name="Failure" data={failureData} fill="hsl(var(--chart-5, 0 84% 60%))">
              {failureData.map((_, i) => (
                <Cell key={`f-${uid}-${i}`} className="fill-red-500" />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
