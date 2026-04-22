import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface TrendIndicator {
  direction: 'up' | 'down' | 'stable'
  delta: string
  positive: boolean
}

interface PairedOutcome {
  label: string
  value: string | number
  tooltip?: string
}

interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  trend?: TrendIndicator
  tooltip?: string
  // Activity metrics (throughput, PRs opened, issues created, review count)
  // must declare the outcome metric they're paired against per Phase 11
  // metrics governance. Renders as a secondary line under the main value with
  // a separator so readers naturally read them together.
  pairedOutcome?: PairedOutcome
}

export default function StatCard({
  title,
  value,
  subtitle,
  trend,
  tooltip,
  pairedOutcome,
}: StatCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
          {title}
          {tooltip && (
            <Tooltip>
              <TooltipTrigger className="inline-flex text-muted-foreground/60 hover:text-muted-foreground transition-colors">
                <HelpCircle className="h-3.5 w-3.5" />
              </TooltipTrigger>
              <TooltipContent>{tooltip}</TooltipContent>
            </Tooltip>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2">
          <div className="text-2xl font-bold">{value}</div>
          {trend && trend.direction !== 'stable' && (
            <span
              className={cn(
                'inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-medium',
                trend.positive
                  ? 'bg-emerald-500/10 text-emerald-600'
                  : 'bg-red-500/10 text-red-600'
              )}
            >
              {trend.direction === 'up' ? '\u2191' : '\u2193'}
              {trend.delta}
            </span>
          )}
          {trend && trend.direction === 'stable' && (
            <span className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              &mdash;
            </span>
          )}
        </div>
        {subtitle && (
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        )}
        {pairedOutcome && (
          <div className="mt-2 flex items-center gap-1.5 border-t pt-2 text-xs text-muted-foreground">
            <span className="truncate">
              {pairedOutcome.label}:{' '}
              <span className="font-medium text-foreground">
                {pairedOutcome.value}
              </span>
            </span>
            {pairedOutcome.tooltip && (
              <Tooltip>
                <TooltipTrigger className="inline-flex text-muted-foreground/60 hover:text-muted-foreground transition-colors">
                  <HelpCircle className="h-3 w-3" />
                </TooltipTrigger>
                <TooltipContent>{pairedOutcome.tooltip}</TooltipContent>
              </Tooltip>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
