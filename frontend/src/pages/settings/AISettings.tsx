import { useState, useCallback, useRef, useEffect, useId, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAISettings, useUpdateAISettings, useAIUsage } from '@/hooks/useAISettings'
import ErrorCard from '@/components/ErrorCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  Legend,
} from 'recharts'
import {
  AlertTriangle,
  CheckCircle2,
  HeartPulse,
  HelpCircle,
  MessageSquareText,
  Tags,
  Users,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AISettingsUpdate, AIFeatureStatus } from '@/utils/types'

const FEATURE_ICONS: Record<string, React.ElementType> = {
  general_analysis: MessageSquareText,
  one_on_one_prep: Users,
  team_health: HeartPulse,
  work_categorization: Tags,
}

const FEATURE_COLORS: Record<string, string> = {
  general_analysis: '#3b82f6',
  one_on_one_prep: '#8b5cf6',
  team_health: '#ef4444',
  work_categorization: '#f59e0b',
}

const tooltipStyle = {
  backgroundColor: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '6px',
  fontSize: '12px',
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function fmtCost(n: number): string {
  return `$${n.toFixed(2)}`
}

function timeAgo(iso: string | null): string {
  if (!iso) return 'Never'
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function AISettings() {
  const { data: settings, isLoading, isError, refetch } = useAISettings()
  const updateSettings = useUpdateAISettings()
  const [usageDays, setUsageDays] = useState(30)
  const { data: usage } = useAIUsage(usageDays)

  // Debounced save
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const save = useCallback(
    (updates: AISettingsUpdate) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        updateSettings.mutate(updates)
      }, 500)
    },
    [updateSettings],
  )

  // Immediate save (for toggles)
  const saveNow = useCallback(
    (updates: AISettingsUpdate) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      updateSettings.mutate(updates)
    },
    [updateSettings],
  )

  if (isError) {
    return <ErrorCard message="Failed to load AI settings." onRetry={refetch} />
  }

  if (isLoading || !settings) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">AI Settings</h1>
        <Skeleton className="h-12 w-full" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
        <Skeleton className="h-60 w-full" />
      </div>
    )
  }

  const masterOff = !settings.ai_enabled

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">AI Settings</h1>

      {/* Section 1: API Status */}
      <APIStatusBanner configured={settings.api_key_configured} />

      {/* Section 2: Master Switch */}
      <Card>
        <CardContent className="flex items-center justify-between py-4">
          <div>
            <p className="font-medium">AI Features</p>
            <p className="text-sm text-muted-foreground">
              Enable or disable all AI-powered features globally. When off, no API calls are made. Historical results remain accessible.
            </p>
          </div>
          <Switch
            checked={settings.ai_enabled}
            onCheckedChange={(checked) => saveNow({ ai_enabled: checked })}
          />
        </CardContent>
      </Card>

      {/* Dimmed wrapper when master switch is off */}
      <div className={cn(masterOff && 'opacity-50 pointer-events-none')}>
        {/* Section 3: Feature Toggle Cards */}
        <FeatureCards
          features={usage?.features ?? []}
          settings={settings}
          onToggle={(feature, enabled) => {
            const key = `feature_${feature}` as keyof AISettingsUpdate
            saveNow({ [key]: enabled } as AISettingsUpdate)
          }}
        />

        {/* Section 4: Budget Configuration */}
        <div className="mt-8">
          <BudgetSection settings={settings} onSave={save} />
        </div>

        {/* Section 5: Pricing Configuration */}
        <div className="mt-8">
          <PricingSection settings={settings} onSave={save} />
        </div>

        {/* Section 6: Usage Dashboard */}
        <div className="mt-8">
          <UsageDashboard
            usage={usage ?? null}
            days={usageDays}
            onDaysChange={setUsageDays}
          />
        </div>

        {/* Section 7: Cooldown Setting */}
        <div className="mt-8">
          <CooldownSection cooldown={settings.cooldown_minutes} onSave={save} />
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Section Components                                                  */
/* ------------------------------------------------------------------ */

function APIStatusBanner({ configured }: { configured: boolean }) {
  if (!configured) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
        <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
        <p className="text-sm text-amber-700 dark:text-amber-400">
          No Anthropic API key configured. AI features are unavailable. Set{' '}
          <code className="rounded bg-amber-500/20 px-1">ANTHROPIC_API_KEY</code> in your environment.
        </p>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
      <CheckCircle2 className="h-4 w-4" />
      <span>API key configured</span>
    </div>
  )
}

function FeatureCards({
  features,
  settings,
  onToggle,
}: {
  features: AIFeatureStatus[]
  settings: { ai_enabled: boolean } & Record<string, unknown>
  onToggle: (feature: string, enabled: boolean) => void
}) {
  // Fall back to settings fields if usage data hasn't loaded yet
  const featureKeys = ['general_analysis', 'one_on_one_prep', 'team_health', 'work_categorization']

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {featureKeys.map((key) => {
        const feat = features.find((f) => f.feature === key)
        const Icon = FEATURE_ICONS[key] ?? HelpCircle
        const enabled = (settings as Record<string, unknown>)[`feature_${key}`] as boolean
        const label = feat?.label ?? key.replace(/_/g, ' ')

        return (
          <Card key={key} className={cn(!enabled && 'bg-muted/50')}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <CardTitle className="text-sm font-medium">{label}</CardTitle>
                </div>
                <Switch
                  checked={enabled}
                  onCheckedChange={(checked) => onToggle(key, checked)}
                />
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-xs text-muted-foreground">
                {feat?.description ?? ''}
              </p>
              {!enabled && feat?.disabled_impact && (
                <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                  {feat.disabled_impact}
                </div>
              )}
              {feat && (
                <p className="text-xs text-muted-foreground">
                  {fmtTokens(feat.tokens_this_month)} tokens ({fmtCost(feat.cost_this_month_usd)})
                  {' '}&middot; {feat.call_count_this_month} calls
                  {' '}&middot; Last used {timeAgo(feat.last_used_at)}
                </p>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

function BudgetSection({
  settings,
  onSave,
}: {
  settings: {
    monthly_token_budget: number | null
    budget_warning_threshold: number
    current_month_tokens: number
    current_month_cost_usd: number
    budget_pct_used: number | null
  }
  onSave: (u: AISettingsUpdate) => void
}) {
  const [budget, setBudget] = useState(
    settings.monthly_token_budget != null ? String(settings.monthly_token_budget) : '',
  )
  const [threshold, setThreshold] = useState(settings.budget_warning_threshold)

  const hasBudget = settings.monthly_token_budget != null && settings.monthly_token_budget > 0
  const pct = settings.budget_pct_used ?? 0
  const pctColor = pct > 0.8 ? 'bg-red-500' : pct > 0.5 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Monthly Budget</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <Label className="text-xs">Monthly token budget</Label>
            <div className="flex items-center gap-2 mt-1">
              <Input
                type="number"
                placeholder="Unlimited"
                value={budget}
                onChange={(e) => {
                  setBudget(e.target.value)
                  const val = e.target.value.trim()
                  if (val === '' || val === '0') {
                    onSave({ clear_budget: true })
                  } else {
                    const n = parseInt(val, 10)
                    if (n > 0) onSave({ monthly_token_budget: n })
                  }
                }}
                className="max-w-[200px]"
              />
              <span className="text-sm text-muted-foreground">tokens</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Set to 0 or clear to remove the limit.
            </p>
          </div>
        </div>

        {hasBudget ? (
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span>
                {fmtTokens(settings.current_month_tokens)} / {fmtTokens(settings.monthly_token_budget!)} tokens
              </span>
              <span>
                {fmtCost(settings.current_month_cost_usd)} / {fmtCost(
                  (settings.monthly_token_budget! / 1_000_000) *
                    ((settings as Record<string, unknown>).input_token_price_per_million as number ?? 3) * 0.7 +
                    (settings.monthly_token_budget! / 1_000_000) *
                    ((settings as Record<string, unknown>).output_token_price_per_million as number ?? 15) * 0.3
                )} est.
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-muted">
              <div
                className={cn('h-2 rounded-full transition-all', pctColor)}
                style={{ width: `${Math.min(pct * 100, 100)}%` }}
              />
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <HelpCircle className="h-3.5 w-3.5" />
            <span>No budget limit &mdash; usage is unlimited</span>
          </div>
        )}

        <div>
          <Label className="text-xs">Warning threshold: {Math.round(threshold * 100)}%</Label>
          <input
            type="range"
            min="0.5"
            max="1.0"
            step="0.05"
            value={threshold}
            onChange={(e) => {
              const val = parseFloat(e.target.value)
              setThreshold(val)
              onSave({ budget_warning_threshold: val })
            }}
            className="mt-1 w-full accent-primary"
          />
          <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function PricingSection({
  settings,
  onSave,
}: {
  settings: {
    input_token_price_per_million: number
    output_token_price_per_million: number
    pricing_updated_at: string | null
  }
  onSave: (u: AISettingsUpdate) => void
}) {
  const [inputPrice, setInputPrice] = useState(String(settings.input_token_price_per_million))
  const [outputPrice, setOutputPrice] = useState(String(settings.output_token_price_per_million))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Pricing Configuration</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label className="text-xs">Input token price (per million)</Label>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-sm text-muted-foreground">$</span>
              <Input
                type="number"
                step="0.1"
                value={inputPrice}
                onChange={(e) => {
                  setInputPrice(e.target.value)
                  const val = parseFloat(e.target.value)
                  if (!isNaN(val) && val >= 0) {
                    onSave({ input_token_price_per_million: val })
                  }
                }}
              />
            </div>
          </div>
          <div>
            <Label className="text-xs">Output token price (per million)</Label>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-sm text-muted-foreground">$</span>
              <Input
                type="number"
                step="0.1"
                value={outputPrice}
                onChange={(e) => {
                  setOutputPrice(e.target.value)
                  const val = parseFloat(e.target.value)
                  if (!isNaN(val) && val >= 0) {
                    onSave({ output_token_price_per_million: val })
                  }
                }}
              />
            </div>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Last updated:{' '}
          {settings.pricing_updated_at
            ? new Date(settings.pricing_updated_at).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })
            : 'Never \u2014 using defaults'}
        </p>
        <p className="text-xs text-muted-foreground">
          Set these to match your Anthropic plan pricing for accurate cost estimates.
        </p>
      </CardContent>
    </Card>
  )
}

function UsageDashboard({
  usage,
  days,
  onDaysChange,
}: {
  usage: {
    total_tokens: number
    total_cost_usd: number
    features: AIFeatureStatus[]
    daily_usage: Array<{
      date: string
      tokens: number
      cost_usd: number
      calls: number
      by_feature: Record<string, { tokens: number; calls: number }>
    }>
  } | null
  days: number
  onDaysChange: (d: number) => void
}) {
  const chartId = useId()

  const chartData = useMemo(() => {
    if (!usage) return []
    return usage.daily_usage.map((d) => ({
      date: d.date,
      general_analysis: d.by_feature?.general_analysis?.tokens ?? 0,
      one_on_one_prep: d.by_feature?.one_on_one_prep?.tokens ?? 0,
      team_health: d.by_feature?.team_health?.tokens ?? 0,
      work_categorization: d.by_feature?.work_categorization?.tokens ?? 0,
    }))
  }, [usage])

  const totalCalls = useMemo(() => {
    if (!usage) return 0
    return usage.daily_usage.reduce((sum, d) => sum + d.calls, 0)
  }, [usage])

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Usage Dashboard</CardTitle>
          <div className="flex gap-1">
            {[7, 30, 90].map((d) => (
              <Button
                key={d}
                variant={days === d ? 'default' : 'outline'}
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => onDaysChange(d)}
              >
                {d}d
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary stat cards */}
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border px-4 py-3">
            <p className="text-xs text-muted-foreground">Total tokens</p>
            <p className="text-lg font-semibold">{usage ? fmtTokens(usage.total_tokens) : '-'}</p>
          </div>
          <div className="rounded-lg border px-4 py-3">
            <p className="text-xs text-muted-foreground">Estimated cost</p>
            <p className="text-lg font-semibold">{usage ? fmtCost(usage.total_cost_usd) : '-'}</p>
          </div>
          <div className="rounded-lg border px-4 py-3">
            <p className="text-xs text-muted-foreground">API calls</p>
            <p className="text-lg font-semibold">{totalCalls}</p>
          </div>
        </div>

        {/* Stacked area chart */}
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" fontSize={10} stroke="hsl(var(--muted-foreground))" />
              <YAxis fontSize={10} stroke="hsl(var(--muted-foreground))" tickFormatter={fmtTokens} />
              <RechartsTooltip
                contentStyle={tooltipStyle}
                formatter={(value: number, name: string) => [fmtTokens(value), name.replace(/_/g, ' ')]}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <Legend formatter={(value) => value.replace(/_/g, ' ')} />
              <Area
                type="monotone"
                dataKey="general_analysis"
                stackId="1"
                fill={FEATURE_COLORS.general_analysis}
                stroke={FEATURE_COLORS.general_analysis}
                fillOpacity={0.6}
              />
              <Area
                type="monotone"
                dataKey="one_on_one_prep"
                stackId="1"
                fill={FEATURE_COLORS.one_on_one_prep}
                stroke={FEATURE_COLORS.one_on_one_prep}
                fillOpacity={0.6}
              />
              <Area
                type="monotone"
                dataKey="team_health"
                stackId="1"
                fill={FEATURE_COLORS.team_health}
                stroke={FEATURE_COLORS.team_health}
                fillOpacity={0.6}
              />
              <Area
                type="monotone"
                dataKey="work_categorization"
                stackId="1"
                fill={FEATURE_COLORS.work_categorization}
                stroke={FEATURE_COLORS.work_categorization}
                fillOpacity={0.6}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
            No AI usage recorded yet
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function CooldownSection({
  cooldown,
  onSave,
}: {
  cooldown: number
  onSave: (u: AISettingsUpdate) => void
}) {
  const [value, setValue] = useState(String(cooldown))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Cooldown Period</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min="0"
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              const n = parseInt(e.target.value, 10)
              if (!isNaN(n) && n >= 0) onSave({ cooldown_minutes: n })
            }}
            className="max-w-[120px]"
          />
          <span className="text-sm text-muted-foreground">minutes</span>
        </div>
        <p className="text-xs text-muted-foreground">
          When the same analysis type and scope is requested within this window, the previous result is returned instead of calling AI again. Users can click "Regenerate" to bypass this.
        </p>
      </CardContent>
    </Card>
  )
}
