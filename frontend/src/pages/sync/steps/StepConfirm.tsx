import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { Repo, TimeRangeOption } from '@/utils/types'

interface StepConfirmProps {
  syncType: 'full' | 'incremental'
  selectedRepos: Repo[]
  timeRange: TimeRangeOption
  customDate: string
  onStart: () => void
  onBack: () => void
  isPending: boolean
}

const timeRangeLabels: Record<TimeRangeOption, string> = {
  since_last: 'Since last sync',
  last_7d: 'Last 7 days',
  last_14d: 'Last 14 days',
  last_30d: 'Last 30 days',
  last_60d: 'Last 60 days',
  last_90d: 'Last 90 days',
  custom: 'Custom date',
  all: 'All history',
}

export default function StepConfirm({
  syncType,
  selectedRepos,
  timeRange,
  customDate,
  onStart,
  onBack,
  isPending,
}: StepConfirmProps) {
  const displayRepos = selectedRepos.slice(0, 5)
  const remaining = selectedRepos.length - displayRepos.length

  return (
    <Card>
      <CardHeader>
        <CardTitle>Confirm Sync</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Sync Type</span>
            <Badge variant="outline">{syncType}</Badge>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Repositories</span>
            <span className="font-medium">{selectedRepos.length} repos</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Time Range</span>
            <span className="font-medium">
              {timeRangeLabels[timeRange]}
              {timeRange === 'custom' && customDate ? ` (${customDate})` : ''}
            </span>
          </div>
        </div>

        <div className="rounded-md border p-3">
          <div className="text-xs font-medium text-muted-foreground mb-1.5">Selected Repos</div>
          <div className="flex flex-wrap gap-1.5">
            {displayRepos.map((r) => (
              <Badge key={r.id} variant="outline" className="text-xs">
                {r.full_name}
              </Badge>
            ))}
            {remaining > 0 && (
              <Badge variant="secondary" className="text-xs">
                +{remaining} more
              </Badge>
            )}
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onBack} disabled={isPending}>
            Back
          </Button>
          <Button onClick={onStart} disabled={isPending}>
            {isPending ? 'Starting...' : 'Start Sync'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
