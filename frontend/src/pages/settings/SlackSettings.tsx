import { useState, useCallback, useRef } from 'react'
import {
  useSlackConfig,
  useUpdateSlackConfig,
  useSlackTest,
  useNotificationHistory,
} from '@/hooks/useSlack'
import ErrorCard from '@/components/ErrorCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  AlertTriangle,
  Bell,
  BellOff,
  CheckCircle2,
  Clock,
  Hash,
  MessageSquare,
  Send,
  Timer,
  TrendingUp,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SlackConfigUpdate, SlackConfigResponse, NotificationHistoryResponse } from '@/utils/types'

const NOTIFICATION_TYPES = [
  {
    key: 'notify_stale_prs' as const,
    label: 'Stale PR Nudges',
    description: 'Daily DMs to PR authors when their PRs are open too long.',
    icon: Clock,
    schedule: 'Daily',
  },
  {
    key: 'notify_high_risk_prs' as const,
    label: 'High-Risk PR Alerts',
    description: 'DM PR authors when a new PR exceeds the risk score threshold.',
    icon: AlertTriangle,
    schedule: 'On sync',
  },
  {
    key: 'notify_workload_alerts' as const,
    label: 'Workload Alerts',
    description: 'DM developers when their workload becomes overloaded.',
    icon: TrendingUp,
    schedule: 'On sync',
  },
  {
    key: 'notify_sync_failures' as const,
    label: 'Sync Failure Alerts',
    description: 'Post to the default channel when a sync fails or has errors.',
    icon: Zap,
    schedule: 'On sync',
  },
  {
    key: 'notify_sync_complete' as const,
    label: 'Sync Complete',
    description: 'Post to the default channel on successful sync completion.',
    icon: CheckCircle2,
    schedule: 'On sync',
  },
  {
    key: 'notify_weekly_digest' as const,
    label: 'Weekly Digest',
    description: 'DM all subscribed developers a weekly metrics summary.',
    icon: MessageSquare,
    schedule: 'Weekly',
  },
]

const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function SlackSettings() {
  const { data: config, isLoading, isError, refetch } = useSlackConfig()
  const updateConfig = useUpdateSlackConfig()
  const testSlack = useSlackTest()
  const { data: history } = useNotificationHistory()

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const save = useCallback(
    (updates: SlackConfigUpdate) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => updateConfig.mutate(updates), 500)
    },
    [updateConfig],
  )

  const saveNow = useCallback(
    (updates: SlackConfigUpdate) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      updateConfig.mutate(updates)
    },
    [updateConfig],
  )

  if (isError) return <ErrorCard message="Failed to load Slack settings." onRetry={refetch} />

  if (isLoading || !config) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Slack Integration</h1>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-40 w-full" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    )
  }

  const masterOff = !config.slack_enabled

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Slack Integration</h1>

      {/* Connection status */}
      <ConnectionBanner config={config} />

      {/* Master switch */}
      <Card>
        <CardContent className="flex items-center justify-between py-4">
          <div>
            <p className="font-medium">Slack Notifications</p>
            <p className="text-sm text-muted-foreground">
              Enable or disable all Slack notifications globally. Individual notification types can be toggled below.
            </p>
          </div>
          <Switch
            checked={config.slack_enabled}
            onCheckedChange={(checked) => saveNow({ slack_enabled: checked })}
          />
        </CardContent>
      </Card>

      <div className={cn(masterOff && 'opacity-50 pointer-events-none')}>
        {/* Bot token + default channel */}
        <ConnectionConfig config={config} onSave={save} onTest={() => testSlack.mutate()} testing={testSlack.isPending} />

        {/* Notification type toggles */}
        <div className="mt-8">
          <h2 className="text-lg font-semibold mb-4">Notification Types</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {NOTIFICATION_TYPES.map((nt) => {
              const Icon = nt.icon
              const enabled = config[nt.key]
              return (
                <Card key={nt.key} className={cn(!enabled && 'bg-muted/50')}>
                  <CardContent className="py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                        <div>
                          <p className="text-sm font-medium">{nt.label}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{nt.description}</p>
                          <Badge variant="outline" className="mt-1.5 text-[10px]">{nt.schedule}</Badge>
                        </div>
                      </div>
                      <Switch
                        checked={enabled}
                        onCheckedChange={(checked) => saveNow({ [nt.key]: checked })}
                      />
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>

        {/* Thresholds */}
        <div className="mt-8">
          <ThresholdConfig config={config} onSave={save} />
        </div>

        {/* Schedule config */}
        <div className="mt-8">
          <ScheduleConfig config={config} onSave={save} />
        </div>

        {/* Notification history */}
        <div className="mt-8">
          <NotificationHistory history={history} />
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */

function ConnectionBanner({ config }: { config: SlackConfigResponse }) {
  if (!config.bot_token_configured) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
        <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
        <p className="text-sm text-amber-700 dark:text-amber-400">
          No Slack bot token configured. Create a Slack App, add the <code className="rounded bg-amber-500/20 px-1">chat:write</code> scope,
          and paste the Bot User OAuth Token below.
        </p>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
      <CheckCircle2 className="h-4 w-4" />
      <span>Slack bot token configured</span>
    </div>
  )
}

function ConnectionConfig({
  config,
  onSave,
  onTest,
  testing,
}: {
  config: SlackConfigResponse
  onSave: (u: SlackConfigUpdate) => void
  onTest: () => void
  testing: boolean
}) {
  const [token, setToken] = useState('')
  const [channel, setChannel] = useState(config.default_channel ?? '')

  return (
    <Card className="mt-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Connection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label className="text-xs">Bot Token</Label>
          <div className="flex items-center gap-2 mt-1">
            <Input
              type="password"
              placeholder={config.bot_token_configured ? 'Token configured (hidden)' : 'xoxb-...'}
              value={token}
              onChange={(e) => {
                setToken(e.target.value)
                if (e.target.value.trim()) {
                  onSave({ bot_token: e.target.value.trim() })
                }
              }}
              className="max-w-md"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={onTest}
              disabled={testing || !config.bot_token_configured}
            >
              <Send className="mr-1.5 h-3.5 w-3.5" />
              {testing ? 'Sending...' : 'Test'}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Find this in your Slack App settings under OAuth & Permissions.
          </p>
        </div>

        <div>
          <Label className="text-xs">Default Channel</Label>
          <div className="flex items-center gap-2 mt-1">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="engineering"
              value={channel}
              onChange={(e) => {
                setChannel(e.target.value)
                onSave({ default_channel: e.target.value.trim() || null })
              }}
              className="max-w-xs"
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Channel for sync notifications. DM notifications go directly to developers.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

function ThresholdConfig({
  config,
  onSave,
}: {
  config: SlackConfigResponse
  onSave: (u: SlackConfigUpdate) => void
}) {
  const [staleDays, setStaleDays] = useState(String(config.stale_pr_days_threshold))
  const [riskThreshold, setRiskThreshold] = useState(String(config.risk_score_threshold))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Thresholds</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label className="text-xs">Stale PR threshold (days)</Label>
            <Input
              type="number"
              min="1"
              max="30"
              value={staleDays}
              onChange={(e) => {
                setStaleDays(e.target.value)
                const n = parseInt(e.target.value, 10)
                if (!isNaN(n) && n > 0) onSave({ stale_pr_days_threshold: n })
              }}
              className="mt-1 max-w-[120px]"
            />
            <p className="text-xs text-muted-foreground mt-1">
              PRs open longer than this are considered stale.
            </p>
          </div>

          <div>
            <Label className="text-xs">Risk score threshold</Label>
            <Input
              type="number"
              min="0"
              max="1"
              step="0.1"
              value={riskThreshold}
              onChange={(e) => {
                setRiskThreshold(e.target.value)
                const n = parseFloat(e.target.value)
                if (!isNaN(n) && n >= 0 && n <= 1) onSave({ risk_score_threshold: n })
              }}
              className="mt-1 max-w-[120px]"
            />
            <p className="text-xs text-muted-foreground mt-1">
              PRs with risk score above this trigger alerts (0-1).
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ScheduleConfig({
  config,
  onSave,
}: {
  config: SlackConfigResponse
  onSave: (u: SlackConfigUpdate) => void
}) {
  const [staleHour, setStaleHour] = useState(String(config.stale_check_hour_utc))
  const [digestDay, setDigestDay] = useState(config.digest_day_of_week)
  const [digestHour, setDigestHour] = useState(String(config.digest_hour_utc))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Schedule</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <Label className="text-xs">Stale PR check hour (UTC)</Label>
            <Input
              type="number"
              min="0"
              max="23"
              value={staleHour}
              onChange={(e) => {
                setStaleHour(e.target.value)
                const n = parseInt(e.target.value, 10)
                if (!isNaN(n) && n >= 0 && n <= 23) onSave({ stale_check_hour_utc: n })
              }}
              className="mt-1 max-w-[100px]"
            />
          </div>

          <div>
            <Label className="text-xs">Digest day</Label>
            <select
              value={digestDay}
              onChange={(e) => {
                const val = parseInt(e.target.value, 10)
                setDigestDay(val)
                onSave({ digest_day_of_week: val })
              }}
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {DAYS_OF_WEEK.map((day, i) => (
                <option key={i} value={i}>{day}</option>
              ))}
            </select>
          </div>

          <div>
            <Label className="text-xs">Digest hour (UTC)</Label>
            <Input
              type="number"
              min="0"
              max="23"
              value={digestHour}
              onChange={(e) => {
                setDigestHour(e.target.value)
                const n = parseInt(e.target.value, 10)
                if (!isNaN(n) && n >= 0 && n <= 23) onSave({ digest_hour_utc: n })
              }}
              className="mt-1 max-w-[100px]"
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Times are in UTC. The stale PR check runs daily; the weekly digest runs once on the selected day.
        </p>
      </CardContent>
    </Card>
  )
}

function NotificationHistory({
  history,
}: {
  history: NotificationHistoryResponse | undefined
}) {
  if (!history || history.total === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Notification History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No notifications sent yet.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Notification History</CardTitle>
          <span className="text-xs text-muted-foreground">{history.total} total</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-2 pr-4">Type</th>
                <th className="pb-2 pr-4">Channel</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {history.notifications.slice(0, 20).map((n) => (
                <tr key={n.id} className="border-b last:border-0">
                  <td className="py-2 pr-4">
                    <Badge variant="outline" className="text-[10px]">
                      {n.notification_type.replace(/_/g, ' ')}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">{n.channel ?? '-'}</td>
                  <td className="py-2 pr-4">
                    {n.status === 'sent' ? (
                      <span className="text-xs text-emerald-600 dark:text-emerald-400">sent</span>
                    ) : (
                      <span className="text-xs text-red-600 dark:text-red-400" title={n.error_message ?? ''}>
                        failed
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">
                    {new Date(n.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
