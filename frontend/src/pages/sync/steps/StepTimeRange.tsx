import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { TimeRangeOption } from '@/utils/types'

interface StepTimeRangeProps {
  timeRange: TimeRangeOption
  customDate: string
  repoCount: number
  onTimeRangeChange: (range: TimeRangeOption) => void
  onCustomDateChange: (date: string) => void
}

const options: { value: TimeRangeOption; label: string; description: string }[] = [
  { value: 'since_last', label: 'Since last sync', description: "Uses each repo's last sync time (default)" },
  { value: 'last_7d', label: 'Last 7 days', description: 'Fetch changes from the past week' },
  { value: 'last_14d', label: 'Last 14 days', description: 'Fetch changes from the past two weeks' },
  { value: 'last_30d', label: 'Last 30 days', description: 'Fetch changes from the past month' },
  { value: 'last_60d', label: 'Last 60 days', description: 'Fetch changes from the past two months' },
  { value: 'last_90d', label: 'Last 90 days', description: 'Fetch changes from the past quarter' },
  { value: 'custom', label: 'Custom date', description: 'Choose a specific start date' },
  { value: 'all', label: 'All history', description: 'Fetch everything — may take a very long time for large repos' },
]

export default function StepTimeRange({
  timeRange,
  customDate,
  repoCount,
  onTimeRangeChange,
  onCustomDateChange,
}: StepTimeRangeProps) {
  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((opt) => (
          <Card
            key={opt.value}
            size="sm"
            className={cn(
              'cursor-pointer transition-all',
              timeRange === opt.value
                ? 'ring-2 ring-primary'
                : 'hover:ring-1 hover:ring-primary/30',
            )}
            onClick={() => onTimeRangeChange(opt.value)}
          >
            <CardContent className="flex items-center gap-3">
              <div
                className={cn(
                  'h-3 w-3 shrink-0 rounded-full border-2',
                  timeRange === opt.value
                    ? 'border-primary bg-primary'
                    : 'border-muted-foreground/30',
                )}
              />
              <div>
                <div className="text-sm font-medium">{opt.label}</div>
                <div className="text-xs text-muted-foreground">{opt.description}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {timeRange === 'custom' && (
        <div className="flex items-center gap-3">
          <Label htmlFor="custom-date">Start date:</Label>
          <Input
            id="custom-date"
            type="date"
            value={customDate}
            onChange={(e) => onCustomDateChange(e.target.value)}
            className="w-44"
          />
        </div>
      )}

      {timeRange === 'all' && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700">
          Warning: Fetching all history may take a very long time for repos with many PRs.
          You can safely close this page — if the sync is interrupted, you can resume from where it left off.
        </div>
      )}

      <div className="text-sm text-muted-foreground">
        Scope: {repoCount} repos selected.
        Syncs are resumable if interrupted.
      </div>
    </div>
  )
}
