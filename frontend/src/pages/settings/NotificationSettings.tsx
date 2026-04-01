import { useCallback, useRef } from 'react'
import { toast } from 'sonner'
import {
  useNotificationConfig,
  useUpdateNotificationConfig,
  useEvaluateNotifications,
  type AlertTypeMeta,
} from '@/hooks/useNotifications'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import ErrorCard from '@/components/ErrorCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'

const GROUPS = [
  { label: 'Code Review Alerts', types: ['stale_pr', 'review_bottleneck', 'merged_without_approval'] },
  { label: 'Workload Alerts', types: ['underutilized', 'uneven_assignment', 'revert_spike'] },
  { label: 'Risk Alerts', types: ['high_risk_pr'] },
  { label: 'Collaboration Alerts', types: ['bus_factor', 'team_silo', 'isolated_developer'] },
  { label: 'Trend Alerts', types: ['declining_trend', 'issue_linkage'] },
  { label: 'System Alerts', types: ['ai_budget', 'sync_failure', 'unassigned_roles', 'missing_config'] },
]

const CATEGORIES = [
  { value: 'system', label: 'System (bots)' },
  { value: 'non_contributor', label: 'Non-contributor (designers)' },
  { value: 'issue_contributor', label: 'Issue contributor (PMs)' },
  { value: 'code_contributor', label: 'Code contributor (developers)' },
]

export default function NotificationSettings() {
  const { data: config, isLoading, error } = useNotificationConfig()
  const update = useUpdateNotificationConfig()
  const evaluate = useEvaluateNotifications()
  const debounceTimers = useRef<Record<string, NodeJS.Timeout>>({})

  const debouncedUpdate = useCallback((field: string, value: unknown) => {
    if (debounceTimers.current[field]) clearTimeout(debounceTimers.current[field])
    debounceTimers.current[field] = setTimeout(() => {
      update.mutate({ [field]: value }, {
        onSuccess: () => toast.success('Setting saved'),
        onError: () => toast.error('Failed to save setting'),
      })
    }, 800)
  }, [update])

  const toggleUpdate = useCallback((field: string, value: boolean) => {
    update.mutate({ [field]: value }, {
      onSuccess: () => toast.success('Setting saved'),
      onError: () => toast.error('Failed to save setting'),
    })
  }, [update])

  if (isLoading) return <div className="space-y-4"><StatCardSkeleton /><StatCardSkeleton /></div>
  if (error || !config) return <ErrorCard title="Failed to load notification settings" error={error} />

  const alertTypeMap: Record<string, AlertTypeMeta> = {}
  for (const at of config.alert_types) {
    alertTypeMap[at.key] = at
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Notification Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Configure alert types, thresholds, and evaluation schedule</p>
      </div>

      {/* Alert type groups */}
      {GROUPS.map((group) => (
        <div key={group.label} className="space-y-3">
          <h2 className="text-lg font-semibold">{group.label}</h2>
          <div className="grid gap-3">
            {group.types.map((typeKey) => {
              const meta = alertTypeMap[typeKey]
              if (!meta) return null
              const toggleField = `alert_${typeKey}_enabled`
              return (
                <Card key={typeKey} className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{meta.label}</span>
                        <Badge variant="outline" className="text-[10px]">{typeKey}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{meta.description}</p>
                      {meta.thresholds.length > 0 && meta.enabled && (
                        <div className="mt-3 flex flex-wrap gap-4">
                          {meta.thresholds.map((t) => (
                            <div key={t.field} className="flex items-center gap-2">
                              <Label className="text-xs text-muted-foreground whitespace-nowrap">{t.label}</Label>
                              <Input
                                type="number"
                                defaultValue={t.value}
                                min={t.min}
                                max={t.max}
                                step={t.unit === '%' || t.unit === 'x median' ? 0.5 : 1}
                                className="h-8 w-20 text-sm"
                                onChange={(e) => debouncedUpdate(t.field, parseFloat(e.target.value))}
                              />
                              {t.unit && <span className="text-xs text-muted-foreground">{t.unit}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <Switch
                      checked={meta.enabled}
                      onCheckedChange={(checked) => toggleUpdate(toggleField, checked)}
                    />
                  </div>
                </Card>
              )
            })}
          </div>
        </div>
      ))}

      {/* Contribution category exclusion */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Excluded Categories</h2>
        <p className="text-xs text-muted-foreground">Developers with these role categories will not trigger activity-based alerts</p>
        <Card className="p-4">
          <div className="flex flex-wrap gap-3">
            {CATEGORIES.map((cat) => {
              const current = config.exclude_contribution_categories ?? []
              const checked = current.includes(cat.value)
              return (
                <label key={cat.value} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...current, cat.value]
                        : current.filter((c) => c !== cat.value)
                      toggleUpdate('exclude_contribution_categories', next as unknown as boolean)
                    }}
                    className="rounded border-input"
                  />
                  <span className="text-sm">{cat.label}</span>
                </label>
              )
            })}
          </div>
        </Card>
      </div>

      {/* Evaluation */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Evaluation</h2>
        <Card className="p-4 space-y-4">
          <div className="flex items-center gap-3">
            <Label className="text-sm">Evaluation interval</Label>
            <Input
              type="number"
              defaultValue={config.evaluation_interval_minutes}
              min={5}
              max={60}
              className="h-8 w-20 text-sm"
              onChange={(e) => debouncedUpdate('evaluation_interval_minutes', parseInt(e.target.value))}
            />
            <span className="text-xs text-muted-foreground">minutes</span>
          </div>
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              onClick={() => evaluate.mutate(undefined, {
                onSuccess: () => toast.success('Evaluation complete'),
                onError: () => toast.error('Evaluation failed'),
              })}
              disabled={evaluate.isPending}
            >
              {evaluate.isPending ? 'Evaluating...' : 'Evaluate now'}
            </Button>
            {config.updated_at && (
              <span className="text-xs text-muted-foreground">
                Last updated: {new Date(config.updated_at).toLocaleString()}
              </span>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
