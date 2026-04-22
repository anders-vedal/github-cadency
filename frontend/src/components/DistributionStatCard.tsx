import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { HelpCircle } from 'lucide-react'
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'

interface HistogramBucket {
  label: string
  count: number
}

interface Props {
  title: string
  /** Primary percentile (median). */
  p50: string | number | null | undefined
  /** Tail percentile. */
  p90: string | number | null | undefined
  /** Optional histogram shape — a sparkline of bucketed counts. */
  histogram?: HistogramBucket[]
  /** Optional shape tag surfaced as a chip: "bimodal", "normal", "skewed", etc. */
  shapeLabel?: string
  tooltip?: string
  /** Inline disclosure chip (e.g. AiCohortBadge). */
  adornment?: React.ReactNode
}

function formatValue(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  return typeof v === 'number' ? String(v) : v
}

/**
 * Phase 11 distribution-first card: cycle time, review rounds, and other
 * long-tailed metrics always ship as p50 + p90 + optional histogram shape.
 * Replaces single-number averages for distributions where averaging misleads.
 */
export default function DistributionStatCard({
  title,
  p50,
  p90,
  histogram,
  shapeLabel,
  tooltip,
  adornment,
}: Props) {
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
          {adornment && <div className="ml-auto">{adornment}</div>}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-4">
          <div>
            <div className="text-xs text-muted-foreground">p50</div>
            <div className="text-2xl font-bold">{formatValue(p50)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">p90</div>
            <div className="text-xl font-semibold text-muted-foreground">
              {formatValue(p90)}
            </div>
          </div>
          {shapeLabel && (
            <span className="ml-auto inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {shapeLabel}
            </span>
          )}
        </div>
        {histogram && histogram.length > 0 && (
          <div className="mt-3 h-16">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={histogram}>
                <XAxis dataKey="label" hide />
                <YAxis hide />
                <Bar
                  dataKey="count"
                  fill="hsl(var(--chart-1))"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
